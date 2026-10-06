"""Phase 4 mutations. All cross-tenant and financial/progress history stays server-owned."""
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from . import models as m, permissions as p
from .services import audit, notify, lock_teacher


def teacher_of(obj):
    if isinstance(obj, m.TeacherProfile):
        return obj
    if isinstance(obj, m.MediaAsset):
        if obj.teacher_id:
            return obj.teacher
        if obj.achievement_id:
            return obj.achievement.teacher
        if obj.event_id:
            return obj.event.teacher
        if obj.submission_id:
            return obj.submission.assignment.lesson.teacher
        return None
    if isinstance(obj, (m.Achievement, m.LearningEvent, m.PointRule, m.LevelDefinition, m.Announcement, m.TuitionComplaint)):
        return obj.teacher
    if isinstance(obj, (m.ProgrammeItem, m.EventParticipation)):
        return obj.event.teacher
    if isinstance(obj, m.EventResult):
        return obj.participation.event.teacher
    if isinstance(obj, m.Assignment):
        return obj.lesson.teacher
    if isinstance(obj, m.Submission):
        return obj.assignment.lesson.teacher
    if isinstance(obj, m.Enrolment):
        return obj.lesson.teacher
    if isinstance(obj, (m.Lesson, m.Application, m.Invitation, m.ServiceArea, m.Availability)):
        return obj.teacher
    if isinstance(obj, m.Batch):
        return obj.lesson.teacher
    if isinstance(obj, (m.ScheduleRule, m.ClassSession)):
        return obj.batch.lesson.teacher
    if isinstance(obj, (m.ProgressEntry, m.FeeAgreement, m.BatchMembership, m.TuitionConversation)):
        return obj.enrolment.lesson.teacher
    if isinstance(obj, m.SessionParticipant):
        return obj.session.batch.lesson.teacher
    if isinstance(obj, m.Attendance):
        return teacher_of(obj.participant)
    if isinstance(obj, m.Invoice):
        return teacher_of(obj.agreement)
    if isinstance(obj, m.Payment):
        return teacher_of(obj.invoice)
    if isinstance(obj, m.PublicationConsent):
        return teacher_of(obj.achievement or obj.asset or obj.programme or obj.result)
    raise ValidationError('Unsupported record.')


def event_audience(event):
    return m.Enrolment.objects.filter(lesson__teacher=event.teacher, status='active').select_related('learner')


def inform(enrolments, key, title):
    ids = set()
    for enrolment in enrolments:
        ids.update(p.recipients(enrolment.learner))
    notify(key, title, ids)


@transaction.atomic
def defaults(teacher):
    for source, value in [('attendance', 5), ('assignment', 10), ('performance', 15), ('competition', 20), ('achievement', 25)]:
        m.PointRule.objects.get_or_create(teacher=teacher, source=source, defaults={'value': value})
    if not teacher.levels.exists():
        for name, threshold in [('Beginner', 0), ('Explorer', 100), ('Skilled', 250), ('Advanced', 500), ('Champion', 1000)]:
            m.LevelDefinition.objects.get_or_create(teacher=teacher, threshold=threshold, defaults={'name': name})


def points(enrolment):
    return enrolment.point_entries.aggregate(total=Sum('delta'))['total'] or 0


def update_level(enrolment):
    level = enrolment.lesson.teacher.levels.filter(threshold__lte=points(enrolment)).order_by('-threshold').first()
    name = level.name if level else 'Beginner'
    m.Enrolment.objects.filter(pk=enrolment.pk).update(level=name)
    enrolment.level = name


@transaction.atomic
def award(enrolment, source, field, obj, eligible, revision):
    m.TeacherProfile.objects.select_for_update().get(pk=enrolment.lesson.teacher_id)
    defaults(enrolment.lesson.teacher)
    rule = m.PointRule.objects.get(teacher=enrolment.lesson.teacher, source=source)
    lookup = {field: obj, 'enrolment': enrolment}
    entries = m.PointEntry.objects.filter(**lookup)
    live = entries.filter(reverses__isnull=True, reversal__isnull=True).first()
    if live and eligible:
        return live
    if live:
        m.PointEntry.objects.get_or_create(action_key=f'reverse:{live.pk}', defaults={**lookup, 'rule': live.rule,
            'rule_version': live.rule_version, 'delta': -live.delta, 'reason': 'Source corrected',
            'source_revision': str(revision), 'reverses': live})
    if eligible and rule.active:
        original = entries.filter(reverses__isnull=True).order_by('pk').first()
        amount = original.delta if original else rule.value
        m.PointEntry.objects.get_or_create(action_key=f'{field}:{obj.pk}:{revision}', defaults={**lookup, 'rule': rule,
            'rule_version': original.rule_version if original else rule.version, 'delta': amount,
            'reason': source.title(), 'source_revision': str(revision)})
    update_level(enrolment)


@transaction.atomic
def save_event(user, obj):
    lock_teacher(user, obj.teacher)
    old = m.LearningEvent.objects.select_for_update().filter(pk=obj.pk).first() if obj.pk else None
    if old:
        if obj.capacity < obj.participants.filter(status__in=['registered', 'accepted']).count():
            raise ValidationError('Capacity is below registered participants.')
        if obj.programme.filter(Q(start__lt=obj.start) | Q(end__gt=obj.end)).exists():
            raise ValidationError('Move programme items inside the revised event dates first.')
        obj.revision = old.revision + 1
    obj.moderation = 'pending'
    obj.full_clean(); obj.save()
    audit(user, obj, 'event_saved')
    inform(event_audience(obj), f'event:{obj.pk}:{obj.revision}', 'Learning event updated')
    return obj


@transaction.atomic
def register_event(user, event, enrolment, consent=False, invite=False, withdraw=False):
    m.TeacherProfile.objects.select_for_update().get(pk=event.teacher_id)
    event = m.LearningEvent.objects.select_for_update().get(pk=event.pk)
    enrolment = m.Enrolment.objects.select_for_update().get(pk=enrolment.pk)
    if enrolment.lesson.teacher_id != event.teacher_id or enrolment.status != 'active':
        raise ValidationError('Choose an active enrolment with this teacher.')
    if invite:
        p.own(user, event.teacher)
    else:
        p.learner_access(user, enrolment.learner)
        if not p.adult_authority(user, enrolment.learner):
            raise PermissionDenied('A verified adult learner or guardian must register.')
    if not withdraw and (event.status != 'published' or event.moderation != 'approved' or event.teacher.status != 'approved'):
        raise ValidationError('This event is not open.')
    current = m.EventParticipation.objects.filter(event=event, learner=enrolment.learner).first()
    if not invite and not withdraw:
        if not event.registration_start <= timezone.now() <= event.registration_end:
            raise ValidationError('Registration is closed.')
        if not consent:
            raise ValidationError('Confirm participation and safety consent. This does not permit publication.')
        if (not current or current.status not in ('registered', 'accepted')) and event.participants.filter(status__in=['registered', 'accepted']).count() >= event.capacity:
            raise ValidationError('Event is full.')
    if current and invite and not withdraw and current.status in ('registered', 'accepted'):
        return current
    obj = current or m.EventParticipation(event=event, learner=enrolment.learner, enrolment=enrolment)
    obj.status = 'withdrawn' if withdraw else 'invited' if invite else 'registered'
    if not invite:
        obj.confirmed_by, obj.safety_consent = user, consent and not withdraw
    obj.full_clean(); obj.save()
    if withdraw:
        for result in obj.results.all():
            award(obj.enrolment, 'competition' if event.kind == 'competition' else 'performance', 'result', result, False, f'withdraw:{obj.updated_at.isoformat()}')
    audit(user, obj, 'event_participation')
    notify(f'participation:{obj.pk}:{obj.updated_at.isoformat()}', 'Learning event participation updated', p.recipients(obj.learner) | {event.teacher.owner_id})
    return obj


@transaction.atomic
def save_programme(user, obj, participants):
    lock_teacher(user, obj.event.teacher)
    people = list(participants)
    if any(x.event_id != obj.event_id or x.status not in ('registered', 'accepted') for x in people):
        raise ValidationError('Select registered participants from this event.')
    if obj.start < obj.event.start or obj.end > obj.event.end:
        raise ValidationError('Programme must fit inside the event dates.')
    if obj.pk:
        obj.revision = m.ProgrammeItem.objects.get(pk=obj.pk).revision + 1
    obj.moderation = 'pending'
    obj.full_clean(); obj.save(); obj.participants.set(people)
    audit(user, obj, 'programme_saved')
    inform(event_audience(obj.event), f'programme:{obj.pk}:{obj.revision}', 'Festival programme updated')
    return obj


@transaction.atomic
def manage_participant(user, person, status):
    lock_teacher(user, person.event.teacher)
    person = m.EventParticipation.objects.select_for_update().get(pk=person.pk)
    if status not in ('accepted', 'withdrawn'):
        raise ValidationError('Choose accepted or withdrawn.')
    if status == 'accepted' and (person.status not in ('registered', 'accepted') or not person.safety_consent or not person.confirmed_by_id):
        raise ValidationError('An invitation needs verified adult registration before acceptance.')
    person.status = status; person.save()
    if status == 'withdrawn':
        for result in person.results.all():
            award(person.enrolment, 'competition' if person.event.kind == 'competition' else 'performance', 'result', result, False, person.updated_at.isoformat())
    audit(user, person, 'participant_review')
    inform([person.enrolment], f'participant-review:{person.pk}:{person.updated_at.isoformat()}', 'Event registration reviewed')
    return person


@transaction.atomic
def save_result(user, obj):
    person = obj.participation
    lock_teacher(user, person.event.teacher)
    if person.status not in ('registered', 'accepted'):
        raise ValidationError('Results require an active participant.')
    if obj.pk:
        obj.revision = m.EventResult.objects.get(pk=obj.pk).revision + 1
    obj.moderation = 'pending'
    obj.full_clean(); obj.save()
    audit(user, obj, 'result_saved')
    source = 'competition' if person.event.kind == 'competition' else 'performance'
    award(person.enrolment, source, 'result', obj, True, obj.revision)
    inform([person.enrolment], f'result:{obj.pk}:{obj.revision}', 'Your event result is ready')
    return obj


@transaction.atomic
def save_achievement(user, obj):
    lock_teacher(user, obj.teacher)
    if obj.pk:
        previous = m.Achievement.objects.get(pk=obj.pk)
        if previous.enrolment_id != obj.enrolment_id or previous.result_id != obj.result_id:
            raise ValidationError('The student and source result cannot change after issue. Reject this record and issue a correction instead.')
    if obj.enrolment_id and obj.enrolment.lesson.teacher_id != obj.teacher_id:
        raise ValidationError('Student belongs to another teacher.')
    if obj.result_id and (teacher_of(obj.result).pk != obj.teacher_id or obj.result.participation.enrolment_id != obj.enrolment_id):
        raise ValidationError('Result must belong to this student and teacher.')
    if obj.level_id and obj.level.teacher_id != obj.teacher_id:
        raise ValidationError('Level belongs to another teacher.')
    if obj.pk:
        obj.revision = m.Achievement.objects.get(pk=obj.pk).revision + 1
    obj.moderation = 'pending'
    obj.full_clean(); obj.save()
    if obj.enrolment_id:
        award(obj.enrolment, 'achievement', 'achievement', obj, True, obj.revision)
        inform([obj.enrolment], f'achievement:{obj.pk}:{obj.revision}', 'A learning achievement is ready')
    audit(user, obj, 'achievement_saved')
    return obj


@transaction.atomic
def save_assignment(user, obj):
    lock_teacher(user, obj.lesson.teacher)
    if obj.batch_id and obj.batch.lesson_id != obj.lesson_id:
        raise ValidationError('Batch must belong to this lesson.')
    obj.full_clean(); obj.save()
    audit(user, obj, 'assignment_saved')
    inform(assignment_enrolments(obj), f'assignment:{obj.pk}:{obj.updated_at.isoformat()}', 'Learning assignment updated')
    return obj


def assignment_enrolments(assignment):
    qs = assignment.lesson.enrolments.filter(status='active')
    return qs.filter(membership__batch=assignment.batch) if assignment.batch_id else qs


@transaction.atomic
def submit(user, assignment, enrolment, body):
    p.learner_access(user, enrolment.learner)
    lock = m.TeacherProfile.objects.select_for_update().get(pk=assignment.lesson.teacher_id)
    if lock.status != 'approved' or not assignment.active or not assignment_enrolments(assignment).filter(pk=enrolment.pk).exists():
        raise PermissionDenied
    obj, _ = m.Submission.objects.get_or_create(assignment=assignment, enrolment=enrolment)
    obj.body, obj.status, obj.reviewed_by = body, 'submitted', None
    obj.revision += 1
    obj.full_clean(); obj.save()
    award(enrolment, 'assignment', 'submission', obj, False, obj.revision)
    audit(user, obj, 'assignment_submitted')
    notify(f'submission:{obj.pk}:{obj.revision}', 'Assignment submitted', [lock.owner_id])
    return obj


@transaction.atomic
def review_submission(user, obj, status, feedback):
    lock_teacher(user, obj.assignment.lesson.teacher)
    obj = m.Submission.objects.select_for_update().get(pk=obj.pk)
    if status not in ('completed', 'returned'):
        raise ValidationError('Choose completed or returned.')
    if obj.status == status and obj.feedback == feedback:
        return obj
    obj.status, obj.feedback, obj.reviewed_by = status, feedback, user
    obj.revision += 1
    obj.save()
    award(obj.enrolment, 'assignment', 'submission', obj, status == 'completed', obj.revision)
    audit(user, obj, 'assignment_review')
    inform([obj.enrolment], f'assignment-review:{obj.pk}:{obj.revision}', 'Assignment reviewed')
    return obj


def target_field(target):
    return {m.Achievement: 'achievement', m.MediaAsset: 'asset', m.ProgrammeItem: 'programme', m.EventResult: 'result'}[type(target)]


def target_learners(target):
    if isinstance(target, m.Achievement):
        return [target.enrolment.learner] if target.enrolment_id else []
    if isinstance(target, m.EventResult):
        return [target.participation.learner]
    if isinstance(target, m.ProgrammeItem):
        return list(m.Learner.objects.filter(eventparticipation__programmeitem=target).distinct())
    if isinstance(target, m.MediaAsset):
        ids = set(target.subjects.values_list('learner_id', flat=True))
        if target.achievement_id and target.achievement.enrolment_id:
            ids.add(target.achievement.enrolment.learner_id)
        if target.learner_id:
            ids.add(target.learner_id)
        return list(m.Learner.objects.filter(pk__in=ids))
    return []


def valid_consent(target, learner):
    qs = m.PublicationConsent.objects.filter(**{target_field(target): target}, learner=learner,
        target_revision=target.revision, revoked_at__isnull=True, expires_at__gt=timezone.now()).select_related('authority')
    for consent in qs:
        if consent.adult_self != learner.adult or not consent.authority.is_active:
            continue
        if isinstance(target, m.MediaAsset) and not consent.allow_media:
            continue
        try:
            if p.adult_authority(consent.authority, learner):
                return consent
        except PermissionDenied:
            continue
    return None


def public_allowed(target):
    teacher = teacher_of(target)
    if not teacher or teacher.status != 'approved' or not teacher.owner.is_active or target.moderation != 'approved':
        return False
    if isinstance(target, m.Achievement) and not target.public_requested:
        return False
    if isinstance(target, m.MediaAsset):
        if not target.public_requested or not target.subjects_complete or target.learner_id or target.submission_id:
            return False
        if target.achievement_id and not public_allowed(target.achievement):
            return False
        if target.event_id and not event_public(target.event):
            return False
    if isinstance(target, (m.ProgrammeItem, m.EventResult)):
        event = target.event if isinstance(target, m.ProgrammeItem) else target.participation.event
        if not event_public(event):
            return False
        if isinstance(target, m.EventResult) and target.participation.status not in ('registered', 'accepted'):
            return False
        if isinstance(target, m.ProgrammeItem) and target.participants.exclude(status__in=['registered', 'accepted']).exists():
            return False
    return all(valid_consent(target, learner) for learner in target_learners(target))


def event_public(event):
    return event.public and event.status in ('published', 'completed') and event.moderation == 'approved' and event.teacher.status == 'approved' and event.teacher.owner.is_active


@transaction.atomic
def consent(user, target, learner, display_name, allow_media, expires_at):
    # Lock learner so revocation/review and a new grant cannot silently race.
    learner = m.Learner.objects.select_for_update().get(pk=learner.pk)
    current = type(target).objects.select_for_update().get(pk=target.pk)
    if current.revision != target.revision:
        raise ValidationError('Content changed. Review the current version before granting consent.')
    target = current
    if not p.adult_authority(user, learner) or learner.pk not in {x.pk for x in target_learners(target)}:
        raise PermissionDenied
    if not timezone.now() < expires_at <= timezone.now() + timedelta(days=366):
        raise ValidationError('Consent must expire within one year.')
    obj = m.PublicationConsent(learner=learner, authority=user, **{target_field(target): target}, target_revision=target.revision,
        display_name=display_name, allow_media=allow_media, expires_at=expires_at, adult_self=learner.adult)
    obj.full_clean()
    # A replacement choice supersedes prior grants; opting out cannot leave an older grant active.
    m.PublicationConsent.objects.filter(learner=learner, **{target_field(target): target}, revoked_at__isnull=True).update(revoked_at=timezone.now())
    obj.save()
    audit(user, obj, 'consent_granted')
    return obj


@transaction.atomic
def revoke(user, obj):
    m.Learner.objects.select_for_update().get(pk=obj.learner_id)
    if obj.authority_id != user.pk and not p.adult_authority(user, obj.learner):
        raise PermissionDenied
    p.active(user)
    obj.revoked_at = timezone.now(); obj.save(update_fields=['revoked_at'])
    audit(user, obj, 'consent_revoked')


def announcement_audience(obj):
    qs = m.Enrolment.objects.filter(lesson__teacher=obj.teacher, status='active')
    if obj.lesson_id:
        qs = qs.filter(lesson=obj.lesson)
    if obj.batch_id:
        qs = qs.filter(membership__batch=obj.batch)
    if obj.event_id:
        qs = qs.filter(eventparticipation__event=obj.event, eventparticipation__status__in=['registered', 'accepted'])
    return qs.distinct()


@transaction.atomic
def save_announcement(user, obj):
    lock_teacher(user, obj.teacher)
    for related in [obj.lesson, obj.batch.lesson if obj.batch_id else None, obj.event]:
        if related and related.teacher_id != obj.teacher_id:
            raise ValidationError('Audience belongs to another teacher.')
    if obj.lesson_id and obj.batch_id and obj.batch.lesson_id != obj.lesson_id:
        raise ValidationError('Batch must belong to the selected lesson.')
    obj.moderation = 'pending'
    obj.full_clean(); obj.save()
    audit(user, obj, 'announcement_saved')
    return obj


@transaction.atomic
def moderate(user, obj, decision):
    teacher = teacher_of(obj)
    m.TeacherProfile.objects.select_for_update().get(pk=teacher.pk)
    p.moderate(user, teacher)
    current = type(obj).objects.select_for_update().get(pk=obj.pk)
    if getattr(current, 'revision', current.updated_at) != getattr(obj, 'revision', obj.updated_at):
        raise ValidationError('Content changed. Review the current version before moderating.')
    if decision not in ('approved', 'rejected'):
        raise ValidationError('Invalid moderation outcome.')
    if isinstance(obj, m.MediaAsset) and decision == 'approved' and not obj.subjects_complete:
        raise ValidationError('Review and confirm all recognizable students before approval.')
    obj.moderation = decision; obj.save(update_fields=['moderation'])
    if isinstance(obj, m.Achievement) and obj.enrolment_id:
        award(obj.enrolment, 'achievement', 'achievement', obj, decision == 'approved', f'review:{timezone.now().isoformat()}')
    if isinstance(obj, m.EventResult):
        award(obj.participation.enrolment, 'competition' if obj.participation.event.kind == 'competition' else 'performance', 'result', obj,
              decision == 'approved' and obj.participation.status in ('registered', 'accepted'), f'review:{timezone.now().isoformat()}')
    audit(user, obj, 'content_review')
    if isinstance(obj, m.Announcement) and decision == 'approved' and obj.publish_at <= timezone.now():
        inform(announcement_audience(obj), f'announcement:{obj.pk}:{obj.updated_at.isoformat()}', 'New learning announcement')
    notify(f'moderation:{obj._meta.model_name}:{obj.pk}:{timezone.now().isoformat()}', 'Learning content reviewed', [teacher.owner_id])


def scheduled_notifications():
    """Idempotent reminders; no private content in the shared inbox."""
    now = timezone.now()
    for obj in m.Announcement.objects.filter(moderation='approved', publish_at__lte=now, teacher__status='approved', teacher__owner__is_active=True):
        inform(announcement_audience(obj), f'announcement:{obj.pk}:{obj.updated_at.isoformat()}', 'New learning announcement')
    for event in m.LearningEvent.objects.filter(status='published', moderation='approved', start__gte=now, start__lte=now+timedelta(days=1), teacher__status='approved', teacher__owner__is_active=True):
        audience = m.Enrolment.objects.filter(eventparticipation__event=event, eventparticipation__status__in=['registered', 'accepted'], status='active')
        inform(audience, f'event-reminder:{event.pk}:{event.revision}', 'Your learning event is coming up')
    for invoice in m.Invoice.objects.filter(state='open', due_date__lte=timezone.localdate(), agreement__enrolment__status='active', agreement__enrolment__lesson__teacher__status='approved', agreement__enrolment__lesson__teacher__owner__is_active=True):
        if invoice.balance > 0:
            inform([invoice.agreement.enrolment], f'fee-reminder:{invoice.pk}:{timezone.localdate()}', 'Learning fees are due')
