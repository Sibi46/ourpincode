from datetime import timedelta
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from jobs.models import AdminActivity, Complaint
from . import models as m, activities as a, permissions as p, activity_forms as f
from . import services as svc, messaging
from .views import form_page, teacher_for


def page(request, title, **context):
    response = render(request, 'tuition/activities.html', {'title': title, **context})
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'same-origin'
    return response


def link(name, obj=None):
    return reverse('tuition:' + name, args=[obj.uid] if obj else [])


def card(title, url, description=''):
    return {'title': title, 'url': url, 'description': description}


def can_manage(user, teacher):
    try:
        p.own(user, teacher)
        return True
    except PermissionDenied:
        return False


def target_access(user, obj):
    teacher = a.teacher_of(obj)
    if teacher and can_manage(user, teacher):
        return True
    p.active(user)
    ids = set(p.learners(user).values_list('pk', flat=True))
    if not ids.intersection(x.pk for x in a.target_learners(obj)):
        raise PermissionDenied
    return False


@login_required
def teacher_hub(request, uid):
    teacher = teacher_for(request, uid)
    cards = [card(e.title, link('event', e), e.get_kind_display()) for e in teacher.events.all()]
    cards += [card(x.title, link('achievement', x), 'Achievement') for x in teacher.achievements.all()]
    cards += [card(x.title, link('assignment', x), 'Assignment') for x in m.Assignment.objects.filter(lesson__teacher=teacher)]
    cards += [card(x.title, link('announcement', x), 'Announcement') for x in teacher.announcements.all()]
    cards += [card(x.title or 'Media', link('asset', x), x.moderation) for x in media_for_teacher(teacher)]
    cards += [card('Messages: ' + x.enrolment.learner.name, link('thread', x)) for x in m.TuitionConversation.objects.filter(enrolment__lesson__teacher=teacher)]
    progress = [{'enrolment': e, 'points': a.points(e), 'level': current_level(e)} for e in m.Enrolment.objects.filter(lesson__teacher=teacher).select_related('learner', 'lesson')]
    return page(request, 'Activities · ' + teacher.name, cards=cards, progress=progress, actions=[
        ('Create event / competition / festival', link('event_create', teacher)),
        ('Issue achievement / certificate', link('achievement_create', teacher)),
        ('Points and levels', link('point_settings', teacher)),
        ('Announcement', link('announcement_create', teacher)),
        ('Upload gallery media', reverse('tuition:activity_upload', args=['teacher', teacher.uid])),
        ('Public showcase', reverse('tuition:showcase', args=[teacher.slug]))])


@login_required
def learner_hub(request):
    learners = p.learners(request.user)
    enrolments = m.Enrolment.objects.filter(learner__in=learners)
    teacher_ids = enrolments.values_list('lesson__teacher_id', flat=True)
    cards = [card(e.title, link('event', e), e.get_kind_display()) for e in m.LearningEvent.objects.filter(teacher_id__in=teacher_ids).exclude(status='draft')]
    achievements = m.Achievement.objects.filter(enrolment__in=enrolments)
    cards += [card(x.title, link('achievement', x), 'Achievement / consent') for x in achievements]
    for assignment in m.Assignment.objects.filter(lesson_id__in=enrolments.values_list('lesson_id', flat=True), active=True):
        if a.assignment_enrolments(assignment).filter(pk__in=enrolments).exists():
            cards.append(card(assignment.title, link('assignment', assignment), 'Assignment'))
    for announcement in m.Announcement.objects.filter(teacher_id__in=teacher_ids, publish_at__lte=timezone.now(), moderation='approved'):
        if a.announcement_audience(announcement).filter(pk__in=enrolments).exists():
            cards.append(card(announcement.title, link('announcement', announcement), 'Announcement'))
    for asset in m.MediaAsset.objects.filter(Q(subjects__learner__in=learners) | Q(achievement__in=achievements)).distinct():
        cards.append(card(asset.title or 'Media consent', link('asset', asset), 'Review media and consent'))
    return page(request, 'My activities and progress', cards=cards, progress=[{'enrolment': e, 'points': a.points(e), 'level': current_level(e)} for e in enrolments],
        consents=m.PublicationConsent.objects.filter(learner__in=learners).select_related('learner'),
        invitations=m.EventParticipation.objects.filter(learner__in=learners, status='invited').select_related('event'))


def current_level(enrolment):
    level = enrolment.lesson.teacher.levels.filter(threshold__lte=a.points(enrolment)).order_by('-threshold').first()
    return level.name if level else 'Beginner'


@login_required
def event_edit(request, teacher_id=None, uid=None):
    obj = get_object_or_404(m.LearningEvent, uid=uid) if uid else m.LearningEvent(teacher=teacher_for(request, teacher_id))
    p.own(request.user, obj.teacher)
    form = f.EventForm(request.POST or None, instance=obj)
    return form_page(request, 'Event / competition / festival', form, lambda form: link('event', a.save_event(request.user, form.save(commit=False))))


def event_detail(request, uid):
    event = get_object_or_404(m.LearningEvent, uid=uid)
    owner = can_manage(request.user, event.teacher)
    own_enrolments = m.Enrolment.objects.none()
    if request.user.is_authenticated and request.user.admin_role != 'scoped_admin':
        own_enrolments = a.event_audience(event).filter(learner__in=p.learners(request.user))
    if not owner and not own_enrolments.exists() and not a.event_public(event):
        raise PermissionDenied
    if not owner and event.status == 'draft':
        raise PermissionDenied
    programme = list(event.programme.all())
    results = list(m.EventResult.objects.filter(participation__event=event))
    if not owner:
        programme = [x for x in programme if a.public_allowed(x) or x.participants.filter(enrolment__in=own_enrolments).exists()]
        results = [x for x in results if a.public_allowed(x) or own_enrolments.filter(pk=x.participation.enrolment_id).exists()]
    actions = [('Register / withdraw', link('event_register', event))] if request.user.is_authenticated else []
    if owner:
        actions = [('Edit event', link('event_edit', event)), ('Invite students', link('event_invite', event)), ('Add programme', link('programme_create', event)), ('Upload event media', reverse('tuition:activity_upload', args=['event', event.uid]))]
    cards = [card(x.title, link('programme', x), str(x.start)) for x in programme]
    cards += [card(x.title, link('result', x), x.get_award_display()) for x in results]
    for asset in event.media.all():
        if owner or a.public_allowed(asset) or (request.user.is_authenticated and set(own_enrolments.values_list('learner_id', flat=True)).intersection(x.pk for x in a.target_learners(asset))):
            cards.append(card(asset.title, link('asset', asset), 'Event gallery'))
    return page(request, event.title, description=event.description, meta=f'{event.get_kind_display()} · {event.start} – {event.end} · {event.venue} · {event.status}', actions=actions, cards=cards,
        participants=event.participants.select_related('learner') if owner else None)


@login_required
def event_register(request, uid, invite=False):
    event = get_object_or_404(m.LearningEvent, uid=uid)
    if invite:
        p.own(request.user, event.teacher)
        qs = a.event_audience(event)
    else:
        qs = a.event_audience(event).filter(learner__in=p.learners(request.user))
    class RegisterForm(forms.Form):
        enrolment = forms.ModelChoiceField(queryset=qs)
        consent = forms.BooleanField(required=False, label='I authorize participation and accept the event/trip details. This is not publication consent.')
        withdraw = forms.BooleanField(required=False)
    form = RegisterForm(request.POST or None)
    def save(form):
        a.register_event(request.user, event, form.cleaned_data['enrolment'], form.cleaned_data['consent'], invite=invite, withdraw=form.cleaned_data['withdraw'])
        return link('event', event)
    return form_page(request, 'Invite students' if invite else 'Event registration', form, save)


@login_required
def programme_edit(request, event_id=None, uid=None):
    obj = get_object_or_404(m.ProgrammeItem, uid=uid) if uid else m.ProgrammeItem(event=get_object_or_404(m.LearningEvent, uid=event_id))
    p.own(request.user, obj.event.teacher)
    form = f.ProgrammeForm(request.POST or None, instance=obj)
    form.fields['participants'].queryset = obj.event.participants.filter(status__in=['registered', 'accepted'])
    def save(form):
        return link('event', a.save_programme(request.user, form.save(commit=False), form.cleaned_data['participants']).event)
    return form_page(request, 'Festival programme', form, save)


@login_required
def participant_review(request, uid):
    obj = get_object_or_404(m.EventParticipation, uid=uid)
    p.own(request.user, obj.event.teacher)
    class ReviewForm(forms.Form):
        status = forms.ChoiceField(choices=[('accepted', 'Accept registered student'), ('withdrawn', 'Withdraw')])
    form = ReviewForm(request.POST or None)
    return form_page(request, 'Manage registration', form, lambda form: link('event', a.manage_participant(request.user, obj, form.cleaned_data['status']).event))


def programme_detail(request, uid):
    obj = get_object_or_404(m.ProgrammeItem, uid=uid)
    owner = can_manage(request.user, obj.event.teacher)
    if not a.public_allowed(obj):
        target_access(request.user, obj)
    return page(request, obj.title, description=obj.description, meta=f'{obj.start} – {obj.end} · {obj.venue}',
        actions=[('Edit programme', link('programme_edit', obj))] if owner else [('Publication consent', reverse('tuition:consent', args=['programme', obj.uid]))] if request.user.is_authenticated else [])


@login_required
def result_edit(request, person_id=None, uid=None):
    obj = get_object_or_404(m.EventResult, uid=uid) if uid else m.EventResult(participation=get_object_or_404(m.EventParticipation, uid=person_id))
    p.own(request.user, obj.participation.event.teacher)
    form = f.ResultForm(request.POST or None, instance=obj)
    return form_page(request, 'Record award / result', form, lambda form: link('result', a.save_result(request.user, form.save(commit=False))))


def result_detail(request, uid):
    obj = get_object_or_404(m.EventResult, uid=uid)
    owner = can_manage(request.user, a.teacher_of(obj))
    if not a.public_allowed(obj):
        target_access(request.user, obj)
    consent = a.valid_consent(obj, obj.participation.learner)
    return page(request, obj.title, description=obj.notes, meta=obj.get_award_display(), public_name=consent.display_name if consent else '',
        actions=[('Edit result', link('result_edit', obj))] if owner else [('Publication consent', reverse('tuition:consent', args=['result', obj.uid]))] if request.user.is_authenticated else [])


@login_required
def achievement_edit(request, teacher_id=None, uid=None):
    obj = get_object_or_404(m.Achievement, uid=uid) if uid else m.Achievement(teacher=teacher_for(request, teacher_id))
    p.own(request.user, obj.teacher)
    form = f.AchievementForm(request.POST or None, instance=obj)
    form.fields['enrolment'].queryset = m.Enrolment.objects.filter(lesson__teacher=obj.teacher)
    form.fields['result'].queryset = m.EventResult.objects.filter(participation__event__teacher=obj.teacher)
    form.fields['level'].queryset = obj.teacher.levels.all()
    return form_page(request, 'Achievement / certificate', form, lambda form: link('achievement', a.save_achievement(request.user, form.save(commit=False))))


def achievement_detail(request, uid):
    obj = get_object_or_404(m.Achievement, uid=uid)
    owner = can_manage(request.user, obj.teacher)
    if not a.public_allowed(obj):
        target_access(request.user, obj)
    actions = []
    if owner:
        actions = [('Edit achievement', link('achievement_edit', obj)), ('Upload achievement media', reverse('tuition:activity_upload', args=['achievement', obj.uid]))]
    if request.user.is_authenticated:
        try:
            target_access(request.user, obj)
            actions.append(('Print certificate', link('certificate', obj)))
            if obj.enrolment_id:
                actions.append(('Publication consent', reverse('tuition:consent', args=['achievement', obj.uid])))
        except PermissionDenied:
            pass
    images = [x for x in obj.media.all() if owner or a.public_allowed(x)]
    if request.user.is_authenticated and not owner:
        try:
            target_access(request.user, obj)
            images = list(obj.media.all())
        except PermissionDenied:
            pass
    consent = a.valid_consent(obj, obj.enrolment.learner) if obj.enrolment_id else None
    return page(request, obj.title, description=obj.description, meta=str(obj.date), public_name=consent.display_name if consent else '', actions=actions,
        cards=[card(x.title, link('asset', x), 'Media') for x in images])


@login_required
def certificate(request, uid):
    obj = get_object_or_404(m.Achievement, uid=uid)
    target_access(request.user, obj)
    if obj.moderation == 'rejected':
        raise PermissionDenied
    response = render(request, 'tuition/certificate.html', {'achievement': obj})
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


TARGETS = {'achievement': m.Achievement, 'asset': m.MediaAsset, 'programme': m.ProgrammeItem, 'result': m.EventResult}


@login_required
def consent_view(request, kind, uid):
    if kind not in TARGETS:
        raise PermissionDenied
    obj = get_object_or_404(TARGETS[kind], uid=uid)
    target_access(request.user, obj)
    form = f.ConsentForm(request.POST or None, initial={'expires_at': timezone.now()+timedelta(days=90), 'revision': obj.revision})
    from django.utils.html import format_html
    form.fields['confirm'].help_text = format_html('<a href="{}" target="_blank" rel="noopener">Review the exact content in another tab</a>. Publication is public; revocation stops future website access, but cannot recall copies already downloaded.', link(kind, obj))
    eligible = [x.pk for x in a.target_learners(obj) if p.adult_authority(request.user, x)]
    form.fields['learner'].queryset = m.Learner.objects.filter(pk__in=eligible)
    def save(form):
        if form.cleaned_data['revision'] != obj.revision:
            raise ValidationError('Content changed. Review the current version before granting consent.')
        a.consent(request.user, obj, form.cleaned_data['learner'], form.cleaned_data['display_name'], form.cleaned_data['allow_media'], form.cleaned_data['expires_at'])
        return 'tuition:learner_hub'
    return form_page(request, 'Consent for: ' + getattr(obj, 'title', 'media') + f' (revision {obj.revision})', form, save)


@login_required
@require_POST
def revoke_consent(request, uid):
    obj = get_object_or_404(m.PublicationConsent, uid=uid)
    a.revoke(request.user, obj)
    return redirect('tuition:learner_hub')


def showcase(request, slug):
    teacher = get_object_or_404(m.TeacherProfile, slug=slug, status='approved', owner__is_active=True)
    cards = [card(x.title, link('achievement', x), str(x.date)) for x in teacher.achievements.all() if a.public_allowed(x)]
    cards += [card(x.title, link('asset', x), 'Gallery') for x in media_for_teacher(teacher) if a.public_allowed(x)]
    cards += [card(x.title, link('event', x), x.get_kind_display()) for x in teacher.events.all() if a.event_public(x)]
    return page(request, teacher.name + ' · Showcase', cards=cards)


@login_required
def point_settings(request, uid):
    teacher = teacher_for(request, uid)
    return page(request, 'Points and levels', cards=[card(x.source, reverse('tuition:point_edit', args=[x.uid]), str(x.value)) for x in teacher.point_rules.all()] + [card(x.name, link('level_edit', x), f'{x.threshold} points') for x in teacher.levels.all()],
        actions=[('Add point rule', link('point_create', teacher)), ('Add level', link('level_create', teacher))])


@login_required
def point_edit(request, teacher_id=None, uid=None, level=False):
    model, form_type = (m.LevelDefinition, f.LevelForm) if level else (m.PointRule, f.PointForm)
    obj = get_object_or_404(model, uid=uid) if uid else model(teacher=teacher_for(request, teacher_id))
    p.own(request.user, obj.teacher)
    form = form_type(request.POST or None, instance=obj)
    def save(form):
        svc.lock_teacher(request.user, obj.teacher)
        record = form.save(commit=False)
        if not level and record.pk:
            old = m.PointRule.objects.get(pk=record.pk)
            if old.source != record.source:
                raise ValidationError('Create a new rule for a different source; do not rewrite history.')
            record.version = old.version + 1
        record.full_clean(); record.save()
        svc.audit(request.user, record, 'points_configured')
        if level:
            for enrolment in m.Enrolment.objects.filter(lesson__teacher=obj.teacher):
                a.update_level(enrolment)
        return link('point_settings', obj.teacher)
    return form_page(request, 'Level' if level else 'Point rule (future awards)', form, save)


@login_required
def assignment_edit(request, lesson_id=None, uid=None):
    obj = get_object_or_404(m.Assignment, uid=uid) if uid else m.Assignment(lesson=get_object_or_404(m.Lesson, uid=lesson_id))
    p.own(request.user, obj.lesson.teacher)
    form = f.AssignmentForm(request.POST or None, instance=obj)
    form.fields['batch'].queryset = obj.lesson.batches.all()
    return form_page(request, 'Assignment', form, lambda form: link('assignment', a.save_assignment(request.user, form.save(commit=False))))


@login_required
def assignment_detail(request, uid):
    obj = get_object_or_404(m.Assignment, uid=uid)
    owner = can_manage(request.user, obj.lesson.teacher)
    qs = a.assignment_enrolments(obj).filter(learner__in=p.learners(request.user))
    if not owner and not qs.exists():
        raise PermissionDenied
    class SubmitForm(forms.Form):
        enrolment = forms.ModelChoiceField(queryset=qs)
        body = forms.CharField(widget=forms.Textarea, max_length=10000)
    form = SubmitForm(request.POST or None) if not owner else None
    if request.method == 'POST':
        if not form:
            raise PermissionDenied
        return form_page(request, 'Submit assignment', form, lambda form: link('submission', a.submit(request.user, obj, form.cleaned_data['enrolment'], form.cleaned_data['body'])))
    submissions = obj.submissions.all() if owner else obj.submissions.filter(enrolment__in=qs)
    return page(request, obj.title, description=obj.instructions, meta=str(obj.due_at), form=form,
        cards=[card(str(x.enrolment), link('submission', x), x.status) for x in submissions], actions=[('Edit assignment', link('assignment_edit', obj))] if owner else [])


@login_required
def submission_detail(request, uid):
    obj = get_object_or_404(m.Submission, uid=uid)
    p.enrolment_access(request.user, obj.enrolment)
    owner = can_manage(request.user, obj.assignment.lesson.teacher)
    class ReviewForm(forms.Form):
        status = forms.ChoiceField(choices=[('completed', 'Completed'), ('returned', 'Return for revision')])
        feedback = forms.CharField(widget=forms.Textarea, required=False)
    form = ReviewForm(request.POST or None) if owner else None
    if request.method == 'POST':
        if not form:
            raise PermissionDenied
        return form_page(request, 'Review assignment', form, lambda form: link('submission', a.review_submission(request.user, obj, form.cleaned_data['status'], form.cleaned_data['feedback'])))
    return page(request, obj.assignment.title, description=obj.body, meta=obj.status + ' · ' + obj.feedback, form=form,
        cards=[card(x.title, link('asset', x), 'Private attachment') for x in obj.media.all()],
        actions=[('Add private attachment', reverse('tuition:activity_upload', args=['submission', obj.uid]))] if not owner else [])


@login_required
def announcement_edit(request, teacher_id=None, uid=None):
    obj = get_object_or_404(m.Announcement, uid=uid) if uid else m.Announcement(teacher=teacher_for(request, teacher_id))
    p.own(request.user, obj.teacher)
    form = f.AnnouncementForm(request.POST or None, instance=obj)
    form.fields['lesson'].queryset = obj.teacher.lessons.all()
    form.fields['batch'].queryset = m.Batch.objects.filter(lesson__teacher=obj.teacher)
    form.fields['event'].queryset = obj.teacher.events.all()
    return form_page(request, 'Announcement', form, lambda form: link('announcement', a.save_announcement(request.user, form.save(commit=False))))


@login_required
def announcement_detail(request, uid):
    obj = get_object_or_404(m.Announcement, uid=uid)
    owner = can_manage(request.user, obj.teacher)
    if not owner and (obj.moderation != 'approved' or obj.publish_at > timezone.now() or not a.announcement_audience(obj).filter(learner__in=p.learners(request.user)).exists()):
        raise PermissionDenied
    return page(request, obj.title, description=obj.body, actions=[('Edit announcement', link('announcement_edit', obj))] if owner else [])


def media_for_teacher(teacher):
    return m.MediaAsset.objects.filter(Q(teacher=teacher) | Q(achievement__teacher=teacher) | Q(event__teacher=teacher) | Q(submission__assignment__lesson__teacher=teacher))


@login_required
def activity_upload(request, kind, uid):
    from .activity_storage import upload
    parents = {'teacher': m.TeacherProfile, 'achievement': m.Achievement, 'event': m.LearningEvent, 'submission': m.Submission}
    if kind not in parents:
        raise PermissionDenied
    parent = get_object_or_404(parents[kind], uid=uid)
    teacher = a.teacher_of(parent)
    if kind == 'submission':
        p.learner_access(request.user, parent.enrolment.learner)
    else:
        p.own(request.user, teacher)
    form = f.MediaForm(request.POST or None, request.FILES or None)
    form.fields['subjects'].queryset = m.Learner.objects.filter(enrolments__lesson__teacher=teacher).distinct() if kind != 'submission' else m.Learner.objects.filter(pk=parent.enrolment.learner_id)
    def save(form):
        asset = upload(request.user, form.cleaned_data['file'], parent, form.cleaned_data['title'], form.cleaned_data['public_requested'], form.cleaned_data['subjects'])
        return link('asset', asset)
    return form_page(request, 'Upload private or consent-reviewed media', form, save)


def asset_detail(request, uid):
    obj = get_object_or_404(m.MediaAsset, uid=uid)
    if not a.public_allowed(obj):
        asset_access(request.user, obj)
    actions = [('Open media', reverse('tuition:activity_file', args=[obj.uid]))]
    if request.user.is_authenticated and a.target_learners(obj):
        actions.append(('Publication consent', reverse('tuition:consent', args=['asset', obj.uid])))
    return page(request, obj.title or 'Learning media', meta=obj.moderation, actions=actions)


def asset_access(user, obj):
    teacher = a.teacher_of(obj)
    if teacher and can_manage(user, teacher):
        return
    if obj.submission_id:
        p.enrolment_access(user, obj.submission.enrolment)
        return
    target_access(user, obj)


def activity_file(request, uid):
    from .storage import storage
    obj = get_object_or_404(m.MediaAsset, uid=uid)
    if not a.public_allowed(obj):
        asset_access(request.user, obj)
    response = FileResponse(storage().open(obj.storage_key), content_type=obj.mime)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Referrer-Policy'] = 'no-referrer'
    response['Content-Disposition'] = 'inline; filename="learning-media' + ('.mp4' if obj.mime == 'video/mp4' else '.webm' if obj.mime == 'video/webm' else '.jpg') + '"'
    return response


@login_required
def thread_start(request, uid):
    enrolment = get_object_or_404(m.Enrolment, uid=uid)
    p.enrolment_access(request.user, enrolment)
    ids = [u.pk for u in get_user_model().objects.filter(pk__in=p.recipients(enrolment.learner)) if p.adult_authority(u, enrolment.learner)]
    if enrolment.lesson.teacher.owner_id != request.user.pk:
        ids = [request.user.pk] if request.user.pk in ids else []
    class StartForm(forms.Form):
        adult = forms.ModelChoiceField(queryset=get_user_model().objects.filter(pk__in=ids))
    form = StartForm(request.POST or None)
    return form_page(request, 'Message verified adult / teacher', form, lambda form: link('thread', messaging.start(request.user, enrolment, form.cleaned_data['adult'])))


@login_required
def thread_detail(request, uid):
    obj = get_object_or_404(m.TuitionConversation, uid=uid)
    messaging.authorize(request.user, obj)
    class MessageForm(forms.Form):
        message = forms.CharField(widget=forms.Textarea, max_length=5000)
    form = MessageForm(request.POST or None)
    if request.method == 'POST':
        return form_page(request, 'Learning message', form, lambda form: (messaging.send(request.user, obj, form.cleaned_data['message']), link('thread', obj))[1])
    history = Paginator(obj.conversation.messages.order_by('-sent_at', '-pk'), 50).get_page(request.GET.get('page'))
    actions = []
    if history.has_previous():
        actions.append(('Newer messages', '?page='+str(history.previous_page_number())))
    if history.has_next():
        actions.append(('Older messages', '?page='+str(history.next_page_number())))
    return page(request, 'Learning messages', form=form, chat_messages=reversed(list(history)), actions=actions, thread=obj)


@login_required
@require_POST
def thread_read(request, uid):
    obj = get_object_or_404(m.TuitionConversation, uid=uid)
    messaging.authorize(request.user, obj)
    obj.conversation.messages.filter(receiver=request.user, is_read=False).update(is_read=True)
    return redirect('tuition:thread', uid=obj.uid)
