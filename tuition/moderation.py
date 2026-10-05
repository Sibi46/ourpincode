from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.utils import timezone
from jobs.models import Complaint, AdminActivity
from . import models as m, permissions as p, activities as a, services as svc
from .activity_views import page, card, link, media_for_teacher
from .views import form_page
from .activity_forms import ComplaintForm


CONTENT = {'event': m.LearningEvent, 'programme': m.ProgrammeItem, 'result': m.EventResult,
           'achievement': m.Achievement, 'asset': m.MediaAsset, 'announcement': m.Announcement}


def content_queryset(kind, teachers):
    paths = {'event': 'teacher', 'programme': 'event__teacher', 'result': 'participation__event__teacher',
             'achievement': 'teacher', 'announcement': 'teacher'}
    if kind == 'asset':
        return m.MediaAsset.objects.filter(Q(teacher__in=teachers) | Q(event__teacher__in=teachers) | Q(achievement__teacher__in=teachers) | Q(submission__assignment__lesson__teacher__in=teachers))
    return CONTENT[kind].objects.filter(**{paths[kind]+'__in': teachers})


@login_required
def hub(request):
    teachers = p.admin_teachers(request.user)
    kind = request.GET.get('kind', 'event')
    if kind not in CONTENT:
        kind = 'event'
    content_page = Paginator(content_queryset(kind, teachers).order_by('-created_at', '-pk'), 30).get_page(request.GET.get('content_page'))
    content = [{'kind': kind, 'obj': obj} for obj in content_page]
    enrolments = m.Enrolment.objects.filter(lesson__teacher__in=teachers).select_related('learner', 'lesson')
    complaints = m.TuitionComplaint.objects.filter(teacher__in=teachers).select_related('complaint')
    # Report aggregates are scoped exactly like the editable records.
    reports = {'Teachers': teachers.count(), 'Active enrolments': enrolments.filter(status='active').count(),
        'Events': m.LearningEvent.objects.filter(teacher__in=teachers).count(),
        'Open complaints': complaints.filter(complaint__status__in=['open', 'in_review']).count(),
        'Pending content': sum(content_queryset(k, teachers).filter(moderation='pending').count() for k in CONTENT)}
    activity = AdminActivity.objects.filter(section='tuition')
    if not (request.user.is_superuser or request.user.admin_role == 'super_admin'):
        activity = activity.filter(details__teacher_uid__in=[str(x) for x in teachers.values_list('uid', flat=True)])
    pages = {
        'teachers_page': Paginator(teachers.order_by('-created_at', '-pk'), 30).get_page(request.GET.get('teachers_page')),
        'students_page': Paginator(enrolments.order_by('-created_at', '-pk'), 30).get_page(request.GET.get('students_page')),
        'complaints_page': Paginator(complaints.order_by('-created_at', '-pk'), 30).get_page(request.GET.get('complaints_page')),
        'activity_page': Paginator(activity.order_by('-created_at', '-pk'), 50).get_page(request.GET.get('activity_page')),
        'content_page': content_page,
    }
    navigation = []
    for key, current in pages.items():
        for label, number in [('Previous', current.number-1), ('Next', current.number+1)]:
            if 1 <= number <= current.paginator.num_pages:
                query = request.GET.copy(); query[key] = number
                navigation.append((f'{label} {key.removesuffix("_page")}', '?' + query.urlencode()))
    return page(request, 'Tuition administration', admin_teachers=pages['teachers_page'], moderation=content,
        admin_students=pages['students_page'], admin_complaints=pages['complaints_page'], reports=reports, activity=pages['activity_page'],
        actions=[(key.title(), '?kind='+key) for key in CONTENT] + navigation + ([('Guardian verification', link('review'))] if request.user.is_superuser or request.user.admin_role == 'super_admin' else []),
        categories=m.Subject.objects.all() if request.user.is_superuser or request.user.admin_role == 'super_admin' else None)


@login_required
def subject_edit(request, pk=None):
    p.main_admin(request.user)
    obj = get_object_or_404(m.Subject, pk=pk) if pk else m.Subject()
    class SubjectForm(forms.ModelForm):
        class Meta:
            model = m.Subject
            fields = ['name', 'slug', 'parent', 'active']
    form = SubjectForm(request.POST or None, instance=obj)
    def save(form):
        record = form.save(commit=False)
        cursor, seen = record.parent, {record.pk}
        while cursor:
            if cursor.pk in seen:
                raise ValidationError('Category hierarchy cannot contain a cycle.')
            seen.add(cursor.pk); cursor = cursor.parent
        record.save(); svc.audit(request.user, record, 'category_updated')
        return 'tuition:admin_hub'
    return form_page(request, 'Teaching category', form, save)


@login_required
def content_review(request, kind, uid):
    teachers = p.admin_teachers(request.user)
    if kind not in CONTENT:
        raise PermissionDenied
    obj = get_object_or_404(content_queryset(kind, teachers), uid=uid)
    class ReviewForm(forms.Form):
        version = forms.CharField(widget=forms.HiddenInput)
        decision = forms.ChoiceField(choices=[('approved', 'Approve'), ('rejected', 'Reject / unpublish')])
        subjects_complete = forms.BooleanField(required=False, label='For media: I checked all recognizable students against the declared subjects. Reject if anyone is missing.')
    version = str(getattr(obj, 'revision', obj.updated_at.isoformat()))
    form = ReviewForm(request.POST or None, initial={'version': version})
    if request.method == 'POST':
        def save(form):
            if form.cleaned_data['version'] != version:
                raise ValidationError('Content changed. Review the current version before moderating.')
            if isinstance(obj, m.MediaAsset):
                obj.subjects_complete = form.cleaned_data['subjects_complete']
                obj.save(update_fields=['subjects_complete'])
            a.moderate(request.user, obj, form.cleaned_data['decision'])
            return 'tuition:admin_hub'
        return form_page(request, 'Review content', form, save)
    svc.audit(request.user, obj, 'content_inspected')
    return page(request, 'Review: ' + getattr(obj, 'title', kind), description=getattr(obj, 'description', getattr(obj, 'body', getattr(obj, 'notes', ''))), form=form,
        review_asset=obj if kind == 'asset' else None, review_subjects=a.target_learners(obj) if kind in ('asset', 'programme', 'result', 'achievement') else [],
        review_meta=str(getattr(obj, 'start', getattr(obj, 'date', ''))))


@login_required
def media_preview(request, uid):
    from .storage import storage
    from django.http import FileResponse
    obj = get_object_or_404(content_queryset('asset', p.admin_teachers(request.user)), uid=uid)
    svc.audit(request.user, obj, 'private_media_read')
    response = FileResponse(storage().open(obj.storage_key), content_type=obj.mime)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Referrer-Policy'] = 'no-referrer'
    return response


@login_required
def teacher_review(request, uid):
    obj = get_object_or_404(p.admin_teachers(request.user), uid=uid)
    class TeacherReview(forms.Form):
        status = forms.ChoiceField(choices=m.TeacherProfile._meta.get_field('status').choices)
    form = TeacherReview(request.POST or None, initial={'status': obj.status})
    def save(form):
        p.moderate(request.user, obj)
        record = m.TeacherProfile.objects.select_for_update().get(pk=obj.pk)
        record.status = form.cleaned_data['status']; record.save()
        svc.audit(request.user, record, 'teacher_moderated')
        svc.notify(f'teacher-review:{record.pk}:{record.updated_at.isoformat()}', 'Teacher profile reviewed', [record.owner_id])
        return 'tuition:admin_hub'
    return form_page(request, obj.name + ' · ' + obj.pincode, form, save)


@login_required
def student_review(request, uid):
    enrolment = get_object_or_404(m.Enrolment.objects.filter(lesson__teacher__in=p.admin_teachers(request.user)), uid=uid)
    class StudentReview(forms.Form):
        status = forms.ChoiceField(choices=[('active', 'Active'), ('paused', 'Paused'), ('withdrawn', 'Withdrawn')])
        identity_verified = forms.BooleanField(required=False, label='Main admin only: adult learner identity and DOB verified')
    form = StudentReview(request.POST or None, initial={'status': enrolment.status, 'identity_verified': enrolment.learner.identity_verified})
    def save(form):
        p.moderate(request.user, enrolment.lesson.teacher)
        m.TeacherProfile.objects.select_for_update().get(pk=enrolment.lesson.teacher_id)
        obj = m.Enrolment.objects.select_for_update().get(pk=enrolment.pk)
        status = form.cleaned_data['status']
        if status == 'active' and obj.status != 'active':
            if obj.lesson.enrolments.filter(status='active').count() >= obj.lesson.capacity:
                raise ValidationError('Lesson is full.')
            member = m.BatchMembership.objects.filter(enrolment=obj).first()
            if member and member.batch_id and (member.batch.status != 'active' or member.batch.memberships.filter(enrolment__status='active').count() >= member.batch.capacity):
                raise ValidationError('Batch is full or inactive.')
        obj.status = status; obj.save(update_fields=['status'])
        roster = m.SessionParticipant.objects.filter(enrolment=obj, session__start__gte=timezone.now())
        roster.update(eligible=False)
        member = m.BatchMembership.objects.filter(enrolment=obj).first()
        if status == 'active' and member and member.batch_id:
            roster.filter(session__batch_id=member.batch_id, session__status='scheduled').update(eligible=True)
        if form.cleaned_data['identity_verified'] != obj.learner.identity_verified:
            p.main_admin(request.user)
            if form.cleaned_data['identity_verified'] and not obj.learner.adult:
                raise ValidationError('Adult identity verification requires an adult DOB.')
            obj.learner.identity_verified = form.cleaned_data['identity_verified']; obj.learner.save(update_fields=['identity_verified'])
        svc.audit(request.user, obj, 'student_review')
        return 'tuition:admin_hub'
    if request.method == 'POST':
        return form_page(request, 'Review student enrolment', form, save)
    svc.audit(request.user, enrolment, 'student_inspected')
    return page(request, enrolment.learner.name, description=f'{enrolment.lesson.name} · {enrolment.status}', form=form)


@login_required
def complaint_create(request, uid):
    teacher = get_object_or_404(m.TeacherProfile, uid=uid)
    p.active(request.user)
    form = ComplaintForm(request.POST or None)
    def save(form):
        obj = Complaint.objects.create(submitted_by=request.user, complaint_type='other', subject=form.cleaned_data['subject'], description=form.cleaned_data['description'])
        context = m.TuitionComplaint.objects.create(teacher=teacher, complaint=obj)
        svc.audit(request.user, context, 'complaint_created')
        return link('my_complaints')
    return form_page(request, 'Report tuition concern', form, save)


@login_required
def my_complaints(request):
    p.active(request.user)
    return page(request, 'My tuition reports', complaints=m.TuitionComplaint.objects.filter(complaint__submitted_by=request.user).select_related('complaint'))


@login_required
def complaint_review(request, uid):
    context = get_object_or_404(m.TuitionComplaint.objects.filter(teacher__in=p.admin_teachers(request.user)), uid=uid)
    class ComplaintReview(forms.Form):
        status = forms.ChoiceField(choices=Complaint.COMPLAINT_STATUS)
        resolution = forms.CharField(widget=forms.Textarea, required=False)
    form = ComplaintReview(request.POST or None)
    def save(form):
        p.moderate(request.user, context.teacher)
        obj = Complaint.objects.select_for_update().get(pk=context.complaint_id)
        if form.cleaned_data['status'] in ('resolved', 'closed') and not form.cleaned_data['resolution'].strip():
            raise ValidationError('Describe the resolution.')
        obj.status, obj.resolution, obj.assigned_to = form.cleaned_data['status'], form.cleaned_data['resolution'], request.user
        obj.resolved_at = timezone.now() if obj.status in ('resolved', 'closed') else None
        obj.save(); svc.audit(request.user, context, 'complaint_review')
        svc.notify(f'complaint:{obj.pk}:{timezone.now().isoformat()}', 'Your tuition report was updated', [obj.submitted_by_id], '/tuition/complaints/')
        return 'tuition:admin_hub'
    if request.method == 'POST':
        return form_page(request, 'Review complaint', form, save)
    svc.audit(request.user, context, 'complaint_inspected')
    return page(request, context.complaint.subject, description=context.complaint.description, form=form)
