import hashlib
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from jobs.models import AdminActivity, UserNotification
from . import permissions as perm
from .models import (TeacherProfile, Lesson, Batch, Enrolment, BatchMembership, Application,
                     ClassSession, ScheduleRule, SessionParticipant, Attendance, FeeAgreement,
                     Invoice, Payment, NotificationEvent, NotificationDelivery, Invitation, GuardianLink)


def audit(user, obj, action):
    from .activities import teacher_of
    try:
        teacher = teacher_of(obj)
    except ValidationError:
        teacher = None
    AdminActivity.objects.create(actor=user, actor_name=user.username, section='tuition', action=action,
                                target_id=str(getattr(obj, 'uid', obj.pk)), target_name=obj._meta.label,
                                details={'teacher_uid': str(teacher.uid)} if teacher else {}, state_name='')


def notify(key, title, ids, link='/tuition/learn/'):
    event, _ = NotificationEvent.objects.get_or_create(key=key, defaults={'title': title, 'link': link})
    for user_id in set(ids):
        delivery, _ = NotificationDelivery.objects.get_or_create(event=event, recipient_id=user_id)
        deliver(delivery.pk)


@transaction.atomic
def deliver(pk):
    delivery = NotificationDelivery.objects.select_for_update().select_related('event').get(pk=pk)
    if delivery.state == 'sent' or delivery.channel != 'in_app':
        return
    delivery.inbox = UserNotification.objects.create(user_id=delivery.recipient_id, title=delivery.event.title,
        message='Open your learning dashboard for details.', link=delivery.event.link)
    delivery.state = 'sent'
    delivery.attempts += 1
    delivery.save()


def lock_teacher(user, teacher):
    teacher = TeacherProfile.objects.select_for_update().get(pk=teacher.pk)
    perm.own(user, teacher)
    return teacher


@transaction.atomic
def decide(user, application, decision, response=''):
    lock_teacher(user, application.teacher)
    app = Application.objects.select_for_update().get(pk=application.pk)
    if app.status in ('accepted', 'withdrawn', 'rejected'):
        if app.status == 'accepted' and decision == 'accepted':
            return Enrolment.objects.get(application=app)
        raise ValidationError('This application is already closed.')
    if decision not in ('accepted', 'rejected', 'needs_info'):
        raise ValidationError('Invalid decision.')
    result = None
    if decision == 'accepted':
        if not app.learner_id or not app.applicant_id:
            raise ValidationError('Applicant must sign in and attach an authorized learner before enrolment.')
        perm.learner_access(app.applicant, app.learner)
        lesson = Lesson.objects.select_for_update().get(pk=app.lesson_id, teacher=app.teacher)
        if not lesson.active:
            raise ValidationError('Lesson is inactive.')
        today = timezone.localdate()
        if lesson.end_date and lesson.end_date < today:
            raise ValidationError('This lesson has ended.')
        age = app.learner.age
        if app.learner.dob:
            dob = app.learner.dob
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age is None or not max(lesson.min_age, app.teacher.min_age) <= age <= min(lesson.max_age, app.teacher.max_age):
            raise ValidationError('Learner age is required and must match the lesson age group.')
        result = Enrolment.objects.filter(learner=app.learner, lesson=lesson).first()
        if not result or result.status != 'active':
            if lesson.enrolments.filter(status='active').count() >= lesson.capacity:
                raise ValidationError('Lesson is full.')
        if result and result.application_id and result.application_id != app.pk and result.status == 'active':
            raise ValidationError('Learner is already enrolled.')
        if not result:
            result = Enrolment(learner=app.learner, lesson=lesson)
        result.status = 'active'
        result.application = app
        result.end_date = None
        result.full_clean()
        result.save()
        BatchMembership.objects.get_or_create(enrolment=result)
    app.status, app.response = decision, response
    app.save()
    audit(user, app, decision)
    if app.applicant_id:
        notify(f'application:{app.pk}:{app.updated_at.isoformat()}', 'Your learning application was updated', [app.applicant_id])
    return result


@transaction.atomic
def transfer(user, enrolment, batch=None):
    lock_teacher(user, enrolment.lesson.teacher)
    enrolment = Enrolment.objects.select_for_update().get(pk=enrolment.pk)
    if enrolment.status != 'active':
        raise ValidationError('Only active enrolments may join a batch.')
    if batch:
        batch = Batch.objects.select_for_update().get(pk=batch.pk)
        if batch.lesson_id != enrolment.lesson_id or batch.status != 'active':
            raise ValidationError('Choose an active batch in the same lesson.')
        if batch.memberships.filter(enrolment__status='active').exclude(enrolment=enrolment).count() >= batch.capacity:
            raise ValidationError('Batch is full.')
    membership, _ = BatchMembership.objects.get_or_create(enrolment=enrolment)
    membership.batch = batch
    membership.save()
    SessionParticipant.objects.filter(enrolment=enrolment, session__start__gte=timezone.now()).update(eligible=False)
    if batch:
        for session in batch.sessions.filter(start__gte=timezone.now(), status='scheduled'):
            SessionParticipant.objects.update_or_create(session=session, enrolment=enrolment, defaults={'eligible': True})
    audit(user, enrolment, 'transfer')
    notify(f'transfer:{enrolment.pk}:{timezone.now().isoformat()}', 'Your class group was updated', perm.recipients(enrolment.learner))


def sync_roster(session):
    for membership in session.batch.memberships.filter(enrolment__status='active').select_related('enrolment'):
        if membership.enrolment.joining_date <= session.start.date():
            SessionParticipant.objects.get_or_create(session=session, enrolment=membership.enrolment)


def validate_session(session):
    session.full_clean()
    if session.batch.status != 'active' or not session.batch.lesson.active:
        raise ValidationError('Batch or lesson is inactive.')
    lesson = session.batch.lesson
    if session.start.date() < lesson.start_date or (lesson.end_date and session.end.date() > lesson.end_date):
        raise ValidationError('Class must fall within the lesson dates.')
    if session.mode in ('online', 'hybrid') and not session.meeting_url:
        raise ValidationError('Online and hybrid classes require a meeting link.')
    if session.mode in ('offline', 'hybrid') and not session.location:
        raise ValidationError('In-person classes require a location.')
    if session.status == 'scheduled' and ClassSession.objects.filter(batch__lesson__teacher=session.batch.lesson.teacher,
        status='scheduled', start__lt=session.end, end__gt=session.start).exclude(pk=session.pk).exists():
        raise ValidationError('This teacher already has a class at that time.')


@transaction.atomic
def save_session(user, session):
    lock_teacher(user, session.batch.lesson.teacher)
    if session.pk:
        old = ClassSession.objects.select_for_update().get(pk=session.pk)
        if old.start < timezone.now():
            raise ValidationError('Past classes cannot be rescheduled or cancelled.')
        session.revision = old.revision + 1
    validate_session(session)
    session.save()
    sync_roster(session)
    audit(user, session, 'class_updated')
    ids = set()
    for person in session.participants.filter(eligible=True).select_related('enrolment__learner'):
        ids.update(perm.recipients(person.enrolment.learner))
    notify(f'class:{session.pk}:{session.revision}', 'Class schedule updated', ids)
    return session


@transaction.atomic
def generate(rule, until=None):
    teacher = TeacherProfile.objects.select_for_update().get(pk=rule.batch.lesson.teacher_id)
    if not rule.active or teacher.status != 'approved' or not teacher.owner.is_active or rule.batch.status != 'active':
        return 0
    rule.full_clean()
    day = max(rule.start_date, timezone.localdate())
    end = min(rule.end_date, until or (day + timedelta(days=90)))
    count = 0
    zone = ZoneInfo(rule.timezone_name)
    while day <= end:
        if day.weekday() == rule.weekday:
            naive = datetime.combine(day, rule.start_time)
            start = naive.replace(tzinfo=zone)
            if start.utcoffset() != naive.replace(tzinfo=zone, fold=1).utcoffset() or start.astimezone(dt_timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
                raise ValidationError('Ambiguous/nonexistent local time: create an individual class with an explicit offset.')
            if not ClassSession.objects.filter(rule=rule, original_start=start).exists():
                session = ClassSession(batch=rule.batch, rule=rule, original_start=start, start=start,
                    end=start + timedelta(minutes=rule.duration_minutes), mode=rule.batch.mode,
                    location=rule.batch.location or rule.batch.lesson.location, meeting_url=rule.meeting_url)
                save_session(teacher.owner, session)
                count += 1
        day += timedelta(days=1)
    return count


@transaction.atomic
def mark_attendance(user, participant, status, note=''):
    lock_teacher(user, participant.session.batch.lesson.teacher)
    participant = SessionParticipant.objects.select_for_update().select_related('session').get(pk=participant.pk)
    if not participant.eligible or participant.session.status == 'cancelled' or (participant.session.start > timezone.now() and status != 'excused'):
        raise ValidationError('Attendance requires an eligible student and a class that has started. Only excused leave can be recorded in advance.')
    obj, _ = Attendance.objects.get_or_create(participant=participant, defaults={'status': status, 'marked_by': user})
    obj.status, obj.note, obj.marked_by = status, note, user
    obj.full_clean()
    obj.save()
    audit(user, obj, 'attendance')
    from .activities import award
    award(participant.enrolment, 'attendance', 'attendance', obj, status in ('present', 'late'), obj.updated_at.isoformat())
    return obj


@transaction.atomic
def record_group_leave(user, batch, enrolment, start_date, end_date, status, note):
    teacher = lock_teacher(user, batch.lesson.teacher)
    if teacher.status != 'approved':
        raise ValidationError('Teacher approval is required.')
    if status not in ('excused', 'absent') or start_date > end_date:
        raise ValidationError('Choose a valid leave/absence status and date range.')
    if not Enrolment.objects.filter(pk=enrolment.pk, lesson=batch.lesson, membership__batch=batch, status='active').exists():
        raise ValidationError('Select an active student in this group.')
    people = list(SessionParticipant.objects.select_for_update().filter(
        enrolment=enrolment, eligible=True, session__batch=batch, session__status='scheduled',
        session__start__date__gte=start_date, session__start__date__lte=end_date).select_related('session'))
    if not people:
        raise ValidationError('No scheduled classes for this student in these dates. Create the timetable first.')
    if Attendance.objects.filter(participant__in=people).exists():
        raise ValidationError('Some classes already have attendance or leave. Review and update those classes individually.')
    for person in people:
        mark_attendance(user, person, status, note)
    return len(people)


@transaction.atomic
def save_agreement(user, agreement):
    lock_teacher(user, agreement.enrolment.lesson.teacher)
    agreement.full_clean()
    existing = FeeAgreement.objects.filter(enrolment=agreement.enrolment).exclude(pk=agreement.pk)
    if agreement.end_date:
        existing = existing.filter(start_date__lte=agreement.end_date)
    if existing.filter(Q(end_date__isnull=True) | Q(end_date__gte=agreement.start_date)).exists():
        raise ValidationError('Fee agreement dates overlap.')
    agreement.save()
    audit(user, agreement, 'fee_agreement')
    return agreement


@transaction.atomic
def create_invoice(user, invoice):
    lock_teacher(user, invoice.agreement.enrolment.lesson.teacher)
    if invoice.pk:
        raise ValidationError('Invoices cannot be overwritten.')
    invoice.full_clean()
    if invoice.period_start < invoice.agreement.start_date or (invoice.agreement.end_date and invoice.period_end > invoice.agreement.end_date):
        raise ValidationError('Invoice period must fall within the fee agreement.')
    if invoice.agreement.invoices.filter(state='open', period_start__lte=invoice.period_end, period_end__gte=invoice.period_start).exists():
        raise ValidationError('An invoice already covers this period.')
    invoice.save()
    audit(user, invoice, 'invoice')
    notify(f'invoice:{invoice.pk}', 'A learning fee is due', perm.recipients(invoice.agreement.enrolment.learner))
    return invoice


@transaction.atomic
def record_payment(user, invoice, amount, method, key, paid_at=None):
    lock_teacher(user, invoice.agreement.enrolment.lesson.teacher)
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    prior = Payment.objects.filter(idempotency_key=key).first()
    if prior:
        if prior.invoice_id != invoice.pk or prior.amount != amount or prior.method != method:
            raise ValidationError('Payment reference already used.')
        return prior
    if invoice.state != 'open' or amount <= 0 or amount > invoice.balance:
        raise ValidationError('Payment must be positive and no greater than the balance.')
    if paid_at and paid_at > timezone.now() + timedelta(minutes=5):
        raise ValidationError('Payment date cannot be in the future.')
    obj = Payment(invoice=invoice, amount=amount, method=method, idempotency_key=key, recorded_by=user, paid_at=paid_at or timezone.now())
    obj.full_clean()
    obj.save()
    audit(user, obj, 'payment')
    notify(f'payment:{obj.pk}', 'Learning payment recorded', perm.recipients(invoice.agreement.enrolment.learner))
    return obj


@transaction.atomic
def reverse_payment(user, payment):
    lock_teacher(user, payment.invoice.agreement.enrolment.lesson.teacher)
    Invoice.objects.select_for_update().get(pk=payment.invoice_id)
    if payment.reverses_id or payment.state != 'confirmed':
        raise ValidationError('Only confirmed payments can be reversed.')
    obj, created = Payment.objects.get_or_create(reverses=payment, defaults={'invoice': payment.invoice, 'amount': payment.amount, 'method': payment.method, 'recorded_by': user})
    if created:
        audit(user, obj, 'payment_reversal')
        notify(f'reversal:{obj.pk}', 'Learning payment corrected', perm.recipients(payment.invoice.agreement.enrolment.learner))
    return obj


@transaction.atomic
def invite(user, lesson, email):
    lock_teacher(user, lesson.teacher)
    token = secrets.token_urlsafe(32)
    obj = Invitation.objects.create(teacher=lesson.teacher, lesson=lesson, email=email,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=timezone.now() + timedelta(days=7))
    audit(user, obj, 'invitation')
    return token


@transaction.atomic
def review_guardian(user, link, status, verification):
    perm.main_admin(user)
    if status not in ('verified', 'revoked', 'disputed') or not verification.strip():
        raise ValidationError('Record the verification method and outcome.')
    link = GuardianLink.objects.select_for_update().get(pk=link.pk)
    link.status, link.verification, link.reviewed_by, link.reviewed_at = status, verification, user, timezone.now()
    link.save()
    audit(user, link, 'guardian_review')
    notify(f'guardian:{link.pk}:{link.updated_at.isoformat()}', 'Learning access reviewed', [link.user_id])
