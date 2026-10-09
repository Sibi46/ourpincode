"""Owner-confirmed deletion of one teaching profile; never follows shared user/student FKs."""
import logging
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, F
from django.db.models.deletion import ProtectedError
from . import models as m
from .services import audit, lock_teacher
from .storage import storage

logger = logging.getLogger(__name__)


def deletion_plan(teacher):
    tid = teacher.pk
    media = m.MediaAsset.objects.filter(Q(teacher_id=tid) | Q(event__teacher_id=tid) | Q(achievement__teacher_id=tid) | Q(submission__assignment__lesson__teacher_id=tid))
    return [
        ('Complaint links', m.TuitionComplaint.objects.filter(teacher_id=tid)),
        ('Messaging links', m.TuitionConversation.objects.filter(enrolment__lesson__teacher_id=tid)),
        ('Publication consents', m.PublicationConsent.objects.filter(Q(asset__in=media) | Q(achievement__teacher_id=tid) | Q(programme__event__teacher_id=tid) | Q(result__participation__event__teacher_id=tid))),
        ('Media student links', m.MediaSubject.objects.filter(asset__in=media)),
        ('Photos and videos', media),
        ('Points history', m.PointEntry.objects.filter(enrolment__lesson__teacher_id=tid)),
        ('Achievements and certificates', m.Achievement.objects.filter(teacher_id=tid)),
        ('Competition results', m.EventResult.objects.filter(participation__event__teacher_id=tid)),
        ('Festival programmes', m.ProgrammeItem.objects.filter(event__teacher_id=tid)),
        ('Event registrations', m.EventParticipation.objects.filter(event__teacher_id=tid)),
        ('Announcements', m.Announcement.objects.filter(teacher_id=tid)),
        ('Events', m.LearningEvent.objects.filter(teacher_id=tid)),
        ('Assignment submissions', m.Submission.objects.filter(assignment__lesson__teacher_id=tid)),
        ('Assignments', m.Assignment.objects.filter(lesson__teacher_id=tid)),
        ('Payments and reversals', m.Payment.objects.filter(invoice__agreement__enrolment__lesson__teacher_id=tid)),
        ('Invoices', m.Invoice.objects.filter(agreement__enrolment__lesson__teacher_id=tid)),
        ('Fee agreements', m.FeeAgreement.objects.filter(enrolment__lesson__teacher_id=tid)),
        ('Attendance', m.Attendance.objects.filter(participant__session__batch__lesson__teacher_id=tid)),
        ('Class participants', m.SessionParticipant.objects.filter(session__batch__lesson__teacher_id=tid)),
        ('Class sessions', m.ClassSession.objects.filter(batch__lesson__teacher_id=tid)),
        ('Weekly schedules', m.ScheduleRule.objects.filter(batch__lesson__teacher_id=tid)),
        ('Student progress', m.ProgressEntry.objects.filter(enrolment__lesson__teacher_id=tid)),
        ('Group memberships', m.BatchMembership.objects.filter(enrolment__lesson__teacher_id=tid)),
        ('Enrolments', m.Enrolment.objects.filter(lesson__teacher_id=tid)),
        ('Applications', m.Application.objects.filter(teacher_id=tid)),
        ('Invitations', m.Invitation.objects.filter(teacher_id=tid)),
        ('Groups', m.Batch.objects.filter(lesson__teacher_id=tid)),
        ('Lessons', m.Lesson.objects.filter(teacher_id=tid)),
        ('Academy staff', m.AcademyStaff.objects.filter(academy_id=tid)),
        ('Points configuration', m.PointRule.objects.filter(teacher_id=tid)),
        ('Levels', m.LevelDefinition.objects.filter(teacher_id=tid)),
        ('Service areas', m.ServiceArea.objects.filter(teacher_id=tid)),
        ('Teaching hours', m.Availability.objects.filter(teacher_id=tid)),
    ]


def retry_file_deletions(limit=100):
    for pk in list(m.PendingFileDeletion.objects.order_by('pk').values_list('pk', flat=True)[:limit]):
        try:
            with transaction.atomic():
                task = m.PendingFileDeletion.objects.select_for_update().filter(pk=pk).first()
                if not task:
                    continue
                # Never delete a key still referenced by any surviving media record.
                if m.MediaAsset.objects.filter(storage_key=task.storage_key).exists():
                    continue
                storage().delete(task.storage_key)
                task.delete()
        except Exception:
            m.PendingFileDeletion.objects.filter(pk=pk).update(attempts=F('attempts')+1)
            logger.warning('Tuition file cleanup pending; task=%s', pk)


@transaction.atomic
def delete_teacher(user, teacher, confirmed_name, password, acknowledged):
    try:
        teacher = lock_teacher(user, teacher)
    except m.TeacherProfile.DoesNotExist:
        raise ValidationError('This profile has already been deleted. Refresh My Learning.')
    if not acknowledged or confirmed_name != teacher.name or not user.check_password(password):
        raise ValidationError('Confirm the profile name, account password and permanent deletion.')
    plan = deletion_plan(teacher)
    media = plan[4][1]
    if m.TeacherProfile.objects.exclude(pk=teacher.pk).filter(Q(profile_image__in=media) | Q(banner_image__in=media)).exists() or m.AcademyStaff.objects.exclude(academy=teacher).filter(photo__in=media).exists():
        raise ValidationError('Media is referenced by another profile; deletion was cancelled.')
    try:
        # Capture private keys before deleting their owning records. No filesystem work inside the transaction.
        for key in media.values_list('storage_key', flat=True):
            m.PendingFileDeletion.objects.get_or_create(storage_key=key)
        for label, records in plan:
            if records.model in (m.Payment, m.PointEntry):
                # Remove reversal rows first, preserving FK checks on all external references.
                records.filter(reverses__isnull=False).delete()
            records.delete()
        teacher.branches.update(parent_academy=None)
        audit(user, teacher, 'teacher_permanently_deleted')
        teacher.delete()
    except ProtectedError:
        raise ValidationError('An unexpected linked record prevents deletion. Nothing was deleted.')
    transaction.on_commit(retry_file_deletions)
