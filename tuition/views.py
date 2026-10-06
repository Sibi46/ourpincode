import hashlib
import math
from datetime import datetime, timedelta
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count, F
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from . import models as m, forms as f, services as svc, permissions as perm
from .storage import upload_image, storage


def page(request, title, template='tuition/page.html', **context):
    response = render(request, template, {'title': title, **context})
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


def form_page(request, title, form, save, template='tuition/page.html'):
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                destination = save(form)
            messages.success(request, 'Saved successfully.')
            return redirect(destination)
        except ValidationError as exc:
            form.add_error(None, ValidationError(exc.messages))
    return page(request, title, template=template, form=form)


def teacher_for(request, uid):
    teacher = get_object_or_404(m.TeacherProfile, uid=uid)
    perm.own(request.user, teacher)
    return teacher


def teacher_url(teacher):
    return reverse('tuition:teacher', args=[teacher.uid])


def discover(request):
    form = f.SearchForm(request.GET)
    teachers = m.TeacherProfile.objects.filter(status='approved', owner__is_active=True).prefetch_related('subjects')
    if form.is_valid():
        d = form.cleaned_data
        lessons = m.Lesson.objects.filter(active=True).filter(Q(end_date__isnull=True) | Q(end_date__gte=timezone.localdate())).annotate(used=Count('enrolments', filter=Q(enrolments__status='active'))).filter(used__lt=F('capacity'))
        if d['q']:
            teachers = teachers.filter(Q(name__icontains=d['q']) | Q(lessons__name__icontains=d['q'], lessons__active=True))
        if d['pincode']:
            teachers = teachers.filter(Q(pincode__in=d['pincode']) | Q(service_areas__pincode__in=d['pincode']))
        if d['kind']:
            teachers = teachers.filter(kind=d['kind'])
        if d['subject']:
            lessons = lessons.filter(subjects=d['subject'])
        if d['mode']:
            lessons = lessons.filter(mode__in=[d['mode'], 'hybrid'])
        if d['age'] is not None:
            teachers = teachers.filter(min_age__lte=d['age'], max_age__gte=d['age'])
            lessons = lessons.filter(min_age__lte=d['age'], max_age__gte=d['age'])
        if any(d[k] is not None and d[k] != '' for k in ('weekday', 'start', 'end')):
            upcoming = m.ClassSession.objects.filter(status='scheduled', start__gte=timezone.now(), batch__status='active').select_related('batch', 'rule')
            matching_lessons = set()
            for session in upcoming:
                from zoneinfo import ZoneInfo
                zone = ZoneInfo(session.rule.timezone_name) if session.rule_id else timezone.get_current_timezone()
                local_start, local_end = timezone.localtime(session.start, zone), timezone.localtime(session.end, zone)
                if d['weekday'] is not None and local_start.weekday() != d['weekday']:
                    continue
                if d['start'] and local_end.time() <= d['start']:
                    continue
                if d['end'] and local_start.time() >= d['end']:
                    continue
                if session.batch.memberships.filter(enrolment__status='active').count() >= session.batch.capacity:
                    continue
                matching_lessons.add(session.batch.lesson_id)
            lessons = lessons.filter(pk__in=matching_lessons)
        if d['subject'] or d['mode'] or d['age'] is not None or d['weekday'] is not None or d['start'] or d['end']:
            teachers = teachers.filter(lessons__in=lessons)
        if d['radius'] is not None:
            lat, lon, radius = d['latitude'], d['longitude'], d['radius']
            latitude_delta = radius / 111.0
            teachers = teachers.filter(latitude__isnull=False, longitude__isnull=False, latitude__gte=max(-90, lat-latitude_delta), latitude__lte=min(90, lat+latitude_delta))
            found = []
            for t in teachers.distinct():
                a, b = math.radians(lat), math.radians(float(t.latitude))
                h = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(float(t.longitude)-lon)/2)**2
                distance = 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, h))))
                if distance <= radius + 0.000001:
                    t.distance = round(distance, 2)
                    found.append(t)
            teachers = sorted(found, key=lambda t: (t.distance, t.pk))
        else:
            teachers = teachers.distinct().order_by('name', 'pk')
    else:
        teachers = teachers.none()
    return page(request, 'Find a teacher', template='tuition/discover.html', search=form, teachers=Paginator(teachers, 20).get_page(request.GET.get('page')))


def public_profile(request, slug):
    teacher = get_object_or_404(m.TeacherProfile, slug=slug, status='approved', owner__is_active=True)
    from .activities import public_allowed
    return page(request, teacher.name, public_teacher=teacher, lessons=teacher.lessons.filter(active=True), availability=teacher.availability.all(), public_images=[asset for asset in m.MediaAsset.objects.filter(teacher=teacher, mime__startswith='image/') if public_allowed(asset)])


@login_required
def register_teacher(request, uid=None):
    perm.active(request.user)
    teacher = teacher_for(request, uid) if uid else m.TeacherProfile(owner=request.user)
    initial = {'service_pins': ', '.join(teacher.service_areas.values_list('pincode', flat=True))} if teacher.pk else {}
    form = f.TeacherForm(request.POST or None, instance=teacher, initial=initial)
    def save(form):
        obj = form.save(commit=False)
        obj.owner = request.user
        obj.status = 'pending'
        from jobs.models import PinCode
        obj.mapped_pin = PinCode.objects.filter(code=obj.pincode, is_active=True, district__is_active=True, district__state__is_active=True).first()
        obj.save()
        form.save_m2m()
        from .activities import defaults
        defaults(obj)
        wanted = form.cleaned_data['service_pins']
        obj.service_areas.exclude(pincode__in=wanted).delete()
        for pin in wanted:
            m.ServiceArea.objects.get_or_create(teacher=obj, pincode=pin)
        svc.audit(request.user, obj, 'profile_saved')
        return teacher_url(obj)
    return form_page(request, 'Teacher / academy profile', form, save, template='tuition/register.html')


@login_required
def dashboard(request):
    perm.active(request.user)
    return page(request, 'Your learning space', owned=m.TeacherProfile.objects.filter(owner=request.user), learners=perm.learners(request.user), claimable=m.Application.objects.filter(uid__in=request.session.get('tuition_receipts', []), applicant__isnull=True),
        guardian_requests=m.GuardianLink.objects.filter(user=request.user), applications=m.Application.objects.filter(applicant=request.user),
        notifications=request.user.notifications.filter(link__startswith='/tuition/').order_by('-created_at')[:30])


@login_required
def teacher_dashboard(request, uid):
    teacher = teacher_for(request, uid)
    enrolments = m.Enrolment.objects.filter(lesson__teacher=teacher).select_related('learner', 'lesson')
    invoices = m.Invoice.objects.filter(agreement__enrolment__lesson__teacher=teacher, state='open')
    return page(request, teacher.name, teacher=teacher, lessons=teacher.lessons.all(), enrolments=enrolments,
        student_total=enrolments.filter(status='active').values('learner_id').distinct().count(),
        active_batches=m.Batch.objects.filter(lesson__teacher=teacher, status='active').count(),
        upcoming_events=teacher.events.filter(start__gte=timezone.now()).exclude(status='cancelled').order_by('start')[:10],
        today_classes=m.ClassSession.objects.filter(batch__lesson__teacher=teacher, start__date=timezone.localdate(), status='scheduled').count(),
        pending_fees=sum(i.balance for i in invoices), applications=teacher.applications.select_related('lesson', 'learner'),
        sessions=m.ClassSession.objects.filter(batch__lesson__teacher=teacher, end__gte=timezone.now()).order_by('start')[:100])


@login_required
def lesson_edit(request, teacher_id=None, uid=None):
    if uid:
        obj = get_object_or_404(m.Lesson, uid=uid)
        teacher = obj.teacher
        perm.own(request.user, teacher)
    else:
        teacher = teacher_for(request, teacher_id)
        obj = m.Lesson(teacher=teacher)
    form = f.LessonForm(request.POST or None, instance=obj)
    def save(form):
        svc.lock_teacher(request.user, teacher)
        lesson = form.save(commit=False)
        if lesson.pk and lesson.enrolments.filter(status='active').count() > lesson.capacity:
            raise ValidationError('Capacity cannot be below current enrolment.')
        lesson.save()
        form.save_m2m()
        svc.audit(request.user, lesson, 'lesson_saved')
        return reverse('tuition:lesson', args=[lesson.uid])
    return form_page(request, 'Lesson details', form, save)


@login_required
def lesson_detail(request, uid):
    lesson = get_object_or_404(m.Lesson, uid=uid)
    perm.own(request.user, lesson.teacher)
    return page(request, lesson.name, lesson=lesson, batches=lesson.batches.all(), enrolments=lesson.enrolments.select_related('learner', 'lesson'))


@login_required
def batch_edit(request, lesson_id=None, uid=None):
    obj = get_object_or_404(m.Batch, uid=uid) if uid else m.Batch(lesson=get_object_or_404(m.Lesson, uid=lesson_id))
    perm.own(request.user, obj.lesson.teacher)
    form = f.BatchForm(request.POST or None, instance=obj)
    def save(form):
        svc.lock_teacher(request.user, obj.lesson.teacher)
        batch = form.save(commit=False)
        if batch.pk and batch.memberships.filter(enrolment__status='active').count() > batch.capacity:
            raise ValidationError('Capacity cannot be below the current roster.')
        batch.save()
        if batch.status != 'active':
            for session in batch.sessions.filter(start__gte=timezone.now(), status='scheduled'):
                session.status = 'cancelled'
                session.reason = 'Batch cancelled or archived'
                # Cancellation preserves existing attendance and meeting history.
                session.revision += 1
                session.save()
                ids = set()
                for person in session.participants.all():
                    ids.update(perm.recipients(person.enrolment.learner))
                svc.notify(f'class:{session.pk}:{session.revision}', 'Class cancelled', ids)
        svc.audit(request.user, batch, 'batch_saved')
        return reverse('tuition:batch', args=[batch.uid])
    return form_page(request, 'Batch details', form, save)


@login_required
def batch_detail(request, uid):
    batch = get_object_or_404(m.Batch, uid=uid)
    perm.own(request.user, batch.lesson.teacher)
    return page(request, batch.name, batch=batch, rules=batch.rules.all(), sessions=batch.sessions.order_by('start')[:100], enrolments=m.Enrolment.objects.filter(membership__batch=batch))


@login_required
def availability(request, uid):
    teacher = teacher_for(request, uid)
    form = f.AvailabilityForm(request.POST or None, instance=m.Availability(teacher=teacher))
    def save(form):
        obj = form.save()
        svc.audit(request.user, obj, 'availability')
        return teacher_url(teacher)
    return form_page(request, 'Add teaching hours', form, save)


@login_required
def learner_create(request, uid=None):
    perm.active(request.user)
    obj = get_object_or_404(perm.learners(request.user), uid=uid) if uid else m.Learner(created_by=request.user)
    form = f.LearnerForm(request.POST or None, instance=obj, initial={'self_registration': bool(obj.user_id == request.user.pk)})
    if obj.pk:
        for name in ('self_registration', 'relationship', 'attestation'):
            form.fields.pop(name)
    def save(form):
        existing = bool(form.instance.pk)
        obj = form.save(commit=False)
        if existing and {'name', 'dob'}.intersection(form.changed_data):
            obj.identity_verified = False
        if not existing and form.cleaned_data['self_registration']:
            if m.Learner.objects.filter(user=request.user).exists():
                raise ValidationError('Your learner profile already exists.')
            obj.user = request.user
        obj.save()
        form.save_m2m()
        if not existing and not obj.user_id:
            m.GuardianLink.objects.create(learner=obj, user=request.user, relationship=form.cleaned_data['relationship'], attestation=form.cleaned_data['attestation'])
        svc.audit(request.user, obj, 'learner_created')
        return 'tuition:dashboard'
    return form_page(request, 'Add yourself or a child', form, save)


@login_required
def learner_detail(request, uid):
    learner = get_object_or_404(perm.learners(request.user), uid=uid)
    return page(request, learner.name, learner=learner, enrolments=learner.enrolments.select_related('lesson__teacher'), assets=m.MediaAsset.objects.filter(learner=learner))


def apply(request, uid):
    lesson = get_object_or_404(m.Lesson, uid=uid, active=True, teacher__status='approved', teacher__owner__is_active=True)
    obj = m.Application(teacher=lesson.teacher, lesson=lesson)
    form = f.ApplicationForm(request.POST or None, instance=obj)
    if request.user.is_authenticated:
        perm.active(request.user)
        form.fields['learner'].queryset = perm.learners(request.user)
    def save(form):
        # An IP bucket is only abuse control, never an identity/authorization check.
        key = 'tuition-apply:' + hashlib.sha256(request.META.get('REMOTE_ADDR', '').encode()).hexdigest()
        hits = cache.get(key, 0)
        if hits >= 10:
            raise ValidationError('Too many enquiries. Please try again later.')
        cache.set(key, hits + 1, 3600)
        app = form.save(commit=False)
        app.applicant = request.user if request.user.is_authenticated else None
        app.save()
        if not app.applicant_id:
            request.session['tuition_receipts'] = (request.session.get('tuition_receipts', []) + [str(app.uid)])[-10:]
        svc.notify(f'application:{app.pk}:new', 'New learning enquiry', [lesson.teacher.owner_id], teacher_url(lesson.teacher))
        return 'tuition:received'
    return form_page(request, f'Apply to learn: {lesson.name}', form, save)


def received(request):
    return page(request, 'Application received', notice='Your enquiry has been submitted. Sign in on this browser and open My learning to claim it and select your authorized learner profile.')


@login_required
@require_POST
def claim_application(request, uid):
    perm.active(request.user)
    if str(uid) not in request.session.get('tuition_receipts', []):
        raise PermissionDenied
    with transaction.atomic():
        app = get_object_or_404(m.Application.objects.select_for_update(), uid=uid, applicant__isnull=True)
        app.applicant = request.user
        app.save()
        svc.audit(request.user, app, 'application_claimed')
    request.session['tuition_receipts'] = [item for item in request.session.get('tuition_receipts', []) if item != str(uid)]
    return redirect('tuition:application', uid=uid)


@login_required
@require_POST
def refresh_schedule(request, uid):
    teacher = teacher_for(request, uid)
    for rule in m.ScheduleRule.objects.filter(batch__lesson__teacher=teacher, active=True):
        try:
            svc.generate(rule)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
    return redirect('tuition:teacher', uid=uid)


@login_required
def application_detail(request, uid):
    app = get_object_or_404(m.Application, uid=uid)
    perm.active(request.user)
    is_teacher = app.teacher.owner_id == request.user.pk
    if is_teacher:
        perm.own(request.user, app.teacher)
    elif app.applicant_id != request.user.pk:
        raise PermissionDenied
    class ResponseForm(forms.Form):
        response = forms.CharField(widget=forms.Textarea)
        decision = forms.ChoiceField(choices=[('needs_info', 'Request information'), ('accepted', 'Accept'), ('rejected', 'Reject')]) if is_teacher else forms.ChoiceField(choices=[('pending', 'Send information'), ('withdrawn', 'Withdraw')])
        learner = forms.ModelChoiceField(queryset=perm.learners(request.user), required=False) if not is_teacher else forms.CharField(required=False, widget=forms.HiddenInput)
    form = ResponseForm(request.POST or None)
    def save(form):
        if is_teacher:
            svc.decide(request.user, app, form.cleaned_data['decision'], form.cleaned_data['response'])
        else:
            locked = m.Application.objects.select_for_update().get(pk=app.pk)
            if locked.status not in ('pending', 'needs_info'):
                raise ValidationError('Application is closed.')
            locked.message = form.cleaned_data['response']
            locked.status = form.cleaned_data['decision']
            if form.cleaned_data.get('learner'):
                locked.learner = form.cleaned_data['learner']
            locked.save()
            svc.audit(request.user, locked, 'application_reply')
            svc.notify(f'application:{app.pk}:{locked.updated_at.isoformat()}', 'Learning enquiry updated', [app.teacher.owner_id], teacher_url(app.teacher))
        return reverse('tuition:application', args=[app.uid])
    if request.method == 'POST':
        return form_page(request, 'Application response', form, save)
    return page(request, 'Learning application', application=app, form=form)


@login_required
def enrolment_detail(request, uid):
    enrolment = get_object_or_404(m.Enrolment, uid=uid)
    perm.enrolment_access(request.user, enrolment)
    return page(request, str(enrolment), enrolment=enrolment, manage=enrolment.lesson.teacher.owner_id == request.user.pk,
        fees=enrolment.fees.all(), invoices=m.Invoice.objects.filter(agreement__enrolment=enrolment),
        attendance=m.Attendance.objects.filter(participant__enrolment=enrolment).select_related('participant__session'), progress=enrolment.progress.all(),
        sessions=m.ClassSession.objects.filter(participants__enrolment=enrolment, participants__eligible=True).order_by('start')[:100])


@login_required
def transfer(request, uid):
    enrolment = get_object_or_404(m.Enrolment, uid=uid)
    perm.own(request.user, enrolment.lesson.teacher)
    class TransferForm(forms.Form):
        batch = forms.ModelChoiceField(queryset=enrolment.lesson.batches.filter(status='active'), required=False, empty_label='Remove from current batch')
    form = TransferForm(request.POST or None)
    def save(form):
        svc.transfer(request.user, enrolment, form.cleaned_data['batch'])
        return reverse('tuition:enrolment', args=[enrolment.uid])
    return form_page(request, 'Assign or transfer batch', form, save)


@login_required
def schedule(request, uid):
    batch = get_object_or_404(m.Batch, uid=uid)
    perm.own(request.user, batch.lesson.teacher)
    form = f.RuleForm(request.POST or None, instance=m.ScheduleRule(batch=batch))
    def save(form):
        svc.lock_teacher(request.user, batch.lesson.teacher)
        rule = form.save()
        svc.generate(rule)
        svc.audit(request.user, rule, 'schedule')
        return reverse('tuition:batch', args=[batch.uid])
    return form_page(request, 'Add recurring class', form, save)


@login_required
@require_POST
def stop_rule(request, uid):
    rule = get_object_or_404(m.ScheduleRule, uid=uid)
    with transaction.atomic():
        svc.lock_teacher(request.user, rule.batch.lesson.teacher)
        rule.active = False
        rule.save()
        for session in m.ClassSession.objects.filter(rule=rule, start__gte=timezone.now(), status='scheduled'):
            session.status, session.reason = 'cancelled', 'Recurring schedule stopped'
            svc.save_session(request.user, session)
        svc.audit(request.user, rule, 'schedule_stopped')
    return redirect('tuition:batch', uid=rule.batch.uid)


@login_required
def session_edit(request, batch_id=None, uid=None):
    obj = get_object_or_404(m.ClassSession, uid=uid) if uid else m.ClassSession(batch=get_object_or_404(m.Batch, uid=batch_id))
    perm.own(request.user, obj.batch.lesson.teacher)
    form = f.SessionForm(request.POST or None, instance=obj)
    def save(form):
        session = svc.save_session(request.user, form.save(commit=False))
        return reverse('tuition:session', args=[session.uid])
    return form_page(request, 'Class schedule / cancellation', form, save)


def session_access(user, session):
    perm.active(user)
    if session.batch.lesson.teacher.owner_id == user.pk:
        perm.own(user, session.batch.lesson.teacher)
        return True
    if not session.participants.filter(eligible=True, enrolment__learner__in=perm.learners(user)).exists():
        raise PermissionDenied
    return False


@login_required
def session_detail(request, uid):
    session = get_object_or_404(m.ClassSession, uid=uid)
    manage = session_access(request.user, session)
    roster = session.participants.filter(eligible=True).select_related('enrolment__learner') if manage else None
    return page(request, 'Class details', session=session, manage=manage, roster=roster, attendance_choices=m.Attendance._meta.get_field('status').choices)


@login_required
def join(request, uid):
    session = get_object_or_404(m.ClassSession, uid=uid)
    manage = session_access(request.user, session)
    if session.status != 'scheduled' or session.batch.lesson.teacher.status != 'approved' or not session.batch.lesson.teacher.owner.is_active or session.mode == 'offline' or not session.meeting_url:
        raise PermissionDenied
    if not manage and not session.participants.filter(eligible=True, enrolment__status='active', enrolment__learner__in=perm.learners(request.user)).exists():
        raise PermissionDenied
    if not session.start - timedelta(minutes=15) <= timezone.now() <= session.end + timedelta(minutes=30):
        return page(request, 'Class not open yet', notice='Join opens 15 minutes before class and closes 30 minutes after it ends.')
    m.meeting_url(session.meeting_url)
    response = HttpResponseRedirect(session.meeting_url)
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


@login_required
@require_POST
def attendance(request, pk):
    person = get_object_or_404(m.SessionParticipant, pk=pk)
    try:
        svc.mark_attendance(request.user, person, request.POST.get('status'), request.POST.get('note', ''))
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    return redirect('tuition:session', uid=person.session.uid)


@login_required
def timetable(request):
    perm.active(request.user)
    sessions = m.ClassSession.objects.filter(Q(batch__lesson__teacher__owner=request.user) | Q(participants__enrolment__learner__in=perm.learners(request.user), participants__eligible=True)).distinct()
    if request.GET.get('today'):
        sessions = sessions.filter(start__date=timezone.localdate())
    else:
        sessions = sessions.filter(end__gte=timezone.now())
    return page(request, 'Timetable', sessions=sessions.order_by('start')[:200])


@login_required
def fee_create(request, uid):
    enrolment = get_object_or_404(m.Enrolment, uid=uid)
    perm.own(request.user, enrolment.lesson.teacher)
    form = f.FeeForm(request.POST or None, instance=m.FeeAgreement(enrolment=enrolment))
    def save(form):
        svc.save_agreement(request.user, form.save(commit=False))
        return reverse('tuition:enrolment', args=[enrolment.uid])
    return form_page(request, 'Student fee agreement', form, save)


@login_required
def invoice_create(request, uid):
    agreement = get_object_or_404(m.FeeAgreement, uid=uid)
    perm.own(request.user, agreement.enrolment.lesson.teacher)
    form = f.InvoiceForm(request.POST or None, instance=m.Invoice(agreement=agreement, amount=agreement.amount))
    def save(form):
        obj = svc.create_invoice(request.user, form.save(commit=False))
        return reverse('tuition:invoice', args=[obj.uid])
    return form_page(request, 'Create fee invoice', form, save)


@login_required
def invoice_detail(request, uid):
    invoice = get_object_or_404(m.Invoice, uid=uid)
    perm.enrolment_access(request.user, invoice.agreement.enrolment)
    manage = invoice.agreement.enrolment.lesson.teacher.owner_id == request.user.pk
    form = f.PaymentForm(request.POST or None) if manage else None
    def save(form):
        svc.record_payment(request.user, invoice, form.cleaned_data['amount'], form.cleaned_data['method'], form.cleaned_data['key'], form.cleaned_data['paid_at'])
        return reverse('tuition:invoice', args=[invoice.uid])
    if request.method == 'POST':
        if not manage:
            raise PermissionDenied
        return form_page(request, 'Record payment', form, save)
    return page(request, 'Fee invoice', invoice=invoice, payments=invoice.payments.order_by('paid_at'), manage=manage, form=form)


@login_required
@require_POST
def payment_reverse(request, uid):
    payment = get_object_or_404(m.Payment, uid=uid)
    svc.reverse_payment(request.user, payment)
    return redirect('tuition:invoice', uid=payment.invoice.uid)


@login_required
def progress_create(request, uid):
    enrolment = get_object_or_404(m.Enrolment, uid=uid)
    perm.own(request.user, enrolment.lesson.teacher)
    form = f.ProgressForm(request.POST or None, instance=m.ProgressEntry(enrolment=enrolment, actor=request.user))
    def save(form):
        obj = form.save()
        svc.audit(request.user, obj, 'progress')
        return reverse('tuition:enrolment', args=[enrolment.uid])
    return form_page(request, 'Record learning progress', form, save)


@login_required
def invitation_create(request, uid):
    lesson = get_object_or_404(m.Lesson, uid=uid)
    perm.own(request.user, lesson.teacher)
    class InviteForm(forms.Form):
        email = forms.EmailField()
    form = InviteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        token = svc.invite(request.user, lesson, form.cleaned_data['email'])
        return page(request, 'Invitation ready', notice='Share this one-time invitation with the intended adult. It expires in seven days.', invitation_link=request.build_absolute_uri(reverse('tuition:invitation_accept', args=[token])))
    return page(request, 'Invite an adult learner or guardian', form=form)


@login_required
def invitation_accept(request, token):
    perm.active(request.user)
    invitation = get_object_or_404(m.Invitation, token_hash=hashlib.sha256(token.encode()).hexdigest())
    if invitation.consumed_at or invitation.expires_at <= timezone.now() or invitation.teacher.status != 'approved':
        raise PermissionDenied
    # Possession of the secret invitation sent by the teacher proves control of that invitation;
    # it never grants guardian authority or automatic enrolment.
    if not request.user.email or request.user.email.casefold() != invitation.email.casefold():
        raise PermissionDenied('Sign in with the account addressed by the invitation.')
    if request.method == 'POST':
        with transaction.atomic():
            invitation = m.Invitation.objects.select_for_update().get(pk=invitation.pk)
            if invitation.consumed_at or invitation.expires_at <= timezone.now():
                raise PermissionDenied
            invitation.consumed_at = timezone.now()
            invitation.recipient = request.user
            invitation.save()
            svc.audit(request.user, invitation, 'invite_accepted')
        return redirect('tuition:apply', uid=invitation.lesson.uid)
    return page(request, 'Accept learning invitation', notice='Continue to apply using your authorized learner profile.', confirm=True)


@login_required
def media_upload(request, kind, uid):
    teacher = learner = None
    if kind == 'teacher':
        teacher = teacher_for(request, uid)
    elif kind == 'learner':
        learner = get_object_or_404(perm.learners(request.user), uid=uid)
    else:
        raise PermissionDenied
    class ImageForm(forms.Form):
        image = forms.FileField(help_text='JPG, PNG or WebP, maximum 10 MB. Student images remain private.')
    form = ImageForm(request.POST or None, request.FILES or None)
    def save(form):
        asset = upload_image(request.user, form.cleaned_data['image'], teacher=teacher, learner=learner)
        if teacher:
            teacher.status = 'pending'
            teacher.save(update_fields=['status'])
        svc.audit(request.user, asset, 'image_uploaded')
        return teacher_url(teacher) if teacher else reverse('tuition:learner', args=[learner.uid])
    return form_page(request, 'Upload photo / logo', form, save)


def media_file(request, uid):
    asset = get_object_or_404(m.MediaAsset, uid=uid)
    if asset.achievement_id or asset.event_id or asset.submission_id or asset.subjects.exists():
        from .activity_views import activity_file
        return activity_file(request, uid)
    if asset.teacher_id:
        if asset.teacher.status != 'approved' or not asset.teacher.owner.is_active or asset.moderation != 'approved' or not asset.subjects_complete or not asset.public_requested:
            if request.user.is_authenticated and (request.user.is_superuser or request.user.admin_role == 'super_admin'):
                perm.main_admin(request.user)
            else:
                perm.own(request.user, asset.teacher)
    else:
        perm.active(request.user)
        if not perm.learners(request.user).filter(pk=asset.learner_id).exists():
            if not asset.learner.enrolments.filter(status='active', lesson__teacher__owner=request.user,
                    lesson__teacher__status='approved').exists():
                raise PermissionDenied
    response = FileResponse(storage().open(asset.storage_key, 'rb'), content_type=asset.mime)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline; filename="photo.jpg"'
    return response


@login_required
def review(request):
    # Minimal Phase 3 activation and guardian verification; full moderation is Phase 4.
    perm.main_admin(request.user)
    if request.method == 'POST':
        with transaction.atomic():
            if request.POST.get('kind') == 'subject':
                subject_form = SubjectForm(request.POST)
                if subject_form.is_valid():
                    subject = subject_form.save()
                    svc.audit(request.user, subject, 'subject_created')
                else:
                    messages.error(request, str(subject_form.errors))
            elif request.POST.get('kind') == 'teacher':
                teacher = get_object_or_404(m.TeacherProfile.objects.select_for_update(), uid=request.POST.get('uid'))
                status = request.POST.get('status')
                if status not in ('approved', 'rejected', 'suspended'):
                    raise PermissionDenied
                teacher.status = status
                teacher.save()
                svc.audit(request.user, teacher, 'profile_review')
                svc.notify(f'teacher:{teacher.pk}:{teacher.updated_at.isoformat()}', 'Teacher profile reviewed', [teacher.owner_id], teacher_url(teacher))
            else:
                link = get_object_or_404(m.GuardianLink, uid=request.POST.get('uid'))
                try:
                    svc.review_guardian(request.user, link, request.POST.get('status'), request.POST.get('verification', ''))
                except ValidationError as exc:
                    messages.error(request, '; '.join(exc.messages))
        return redirect('tuition:review')
    return page(request, 'Teacher and guardian verification', subject_form=SubjectForm(),
        review_teachers=Paginator(m.TeacherProfile.objects.order_by('-created_at', '-pk'), 30).get_page(request.GET.get('teachers_page')),
        review_guardians=Paginator(m.GuardianLink.objects.select_related('learner', 'user').order_by('-created_at', '-pk'), 30).get_page(request.GET.get('guardians_page')))


class SubjectForm(forms.ModelForm):
    class Meta:
        model = m.Subject
        fields = ['name', 'slug']


@login_required
def enrolment_status(request, uid):
    enrolment = get_object_or_404(m.Enrolment, uid=uid)
    perm.own(request.user, enrolment.lesson.teacher)
    class StatusForm(forms.Form):
        status = forms.ChoiceField(choices=m.Enrolment._meta.get_field('status').choices)
    form = StatusForm(request.POST or None, initial={'status': enrolment.status})
    def save(form):
        svc.lock_teacher(request.user, enrolment.lesson.teacher)
        obj = m.Enrolment.objects.select_for_update().get(pk=enrolment.pk)
        status = form.cleaned_data['status']
        if status == 'active' and obj.status != 'active':
            if obj.lesson.enrolments.filter(status='active').count() >= obj.lesson.capacity:
                raise ValidationError('Lesson is full.')
            membership = m.BatchMembership.objects.filter(enrolment=obj).first()
            if membership and membership.batch_id and (membership.batch.status != 'active' or membership.batch.memberships.filter(enrolment__status='active').count() >= membership.batch.capacity):
                raise ValidationError('The assigned batch is unavailable or full.')
        obj.status = status
        obj.end_date = timezone.localdate() if status in ('completed', 'withdrawn') else None
        obj.full_clean(); obj.save()
        m.SessionParticipant.objects.filter(enrolment=obj, session__start__gte=timezone.now()).update(eligible=False)
        if status == 'active':
            membership = m.BatchMembership.objects.filter(enrolment=obj).first()
            if membership and membership.batch_id:
                svc.transfer(request.user, obj, membership.batch)
        svc.audit(request.user, obj, 'enrolment_status')
        return reverse('tuition:enrolment', args=[obj.uid])
    return form_page(request, 'Enrolment status', form, save)


@login_required
def fee_close(request, uid):
    agreement = get_object_or_404(m.FeeAgreement, uid=uid)
    perm.own(request.user, agreement.enrolment.lesson.teacher)
    class CloseForm(forms.Form):
        end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    form = CloseForm(request.POST or None)
    def save(form):
        svc.lock_teacher(request.user, agreement.enrolment.lesson.teacher)
        obj = m.FeeAgreement.objects.select_for_update().get(pk=agreement.pk)
        end = form.cleaned_data['end_date']
        if end < obj.start_date or obj.invoices.filter(period_end__gt=end).exists():
            raise ValidationError('End date must include the agreement start and all existing invoice periods.')
        obj.end_date = end
        svc.save_agreement(request.user, obj)
        return reverse('tuition:enrolment', args=[obj.enrolment.uid])
    return form_page(request, 'End fee agreement before changing fees', form, save)


@login_required
@require_POST
def notification_read(request, pk):
    perm.active(request.user)
    from jobs.models import UserNotification
    notification = get_object_or_404(UserNotification, pk=pk, user=request.user, link__startswith='/tuition/')
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    return redirect('tuition:dashboard')
