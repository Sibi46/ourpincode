"""Phase 5 checks; real codecs run only when explicitly configured locally."""
import json
import os
import subprocess
import tempfile
import io
from unittest.mock import patch
from pathlib import Path
from unittest import skipUnless
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from . import activity_storage, activities as a, models as m, messaging, services
from . import test_activities as fixtures


@skipUnless(os.environ.get('TUITION_AUDIT_FFMPEG') and os.environ.get('TUITION_FFPROBE'), 'Real FFmpeg/ffprobe paths not configured')
class RealVideoTests(SimpleTestCase):
    def clip(self, directory, suffix, codec):
        path = Path(directory) / ('sample'+suffix)
        subprocess.run([os.environ['TUITION_AUDIT_FFMPEG'], '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            'color=c=blue:s=160x120:r=5', '-t', '1', '-an', '-c:v', codec, str(path)], check=True, timeout=30, capture_output=True)
        return path.read_bytes()

    def test_real_mp4_and_webm(self):
        with tempfile.TemporaryDirectory() as root:
            for suffix, codec, mime in [('.mp4', 'libx264', 'video/mp4'), ('.webm', 'libvpx', 'video/webm')]:
                with self.subTest(suffix=suffix):
                    data = self.clip(root, suffix, codec)
                    validated, ext, actual = activity_storage.validate(SimpleUploadedFile('video'+suffix, data))
                    self.assertEqual((ext, actual), (suffix, mime)); self.assertEqual(validated, data)

    def test_corrupted_video_rejected(self):
        with self.assertRaises(ValidationError):
            activity_storage.validate(SimpleUploadedFile('corrupt.mp4', b'\x00\x00\x00\x18ftypisom'+b'not-a-video'*20))

    def test_matroska_disguised_as_webm_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.clip(root, '.mkv', 'libx264')
            with self.assertRaises(ValidationError):
                activity_storage.validate(SimpleUploadedFile('disguised.webm', data))

    def test_audio_only_mp4_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'audio.mp4'
            subprocess.run([os.environ['TUITION_AUDIT_FFMPEG'], '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                'sine=frequency=440:duration=1', '-c:a', 'aac', str(path)], check=True, timeout=30, capture_output=True)
            with self.assertRaises(ValidationError):
                activity_storage.validate(SimpleUploadedFile('audio.mp4', path.read_bytes()))


class ReadinessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.ActivityTests.setUpTestData.__func__(cls)

    def test_scheduler_command_due_notifications_and_retry(self):
        from django.core.management import call_command
        from jobs.models import UserNotification
        now = timezone.now()
        notice = a.save_announcement(self.owner, m.Announcement(teacher=self.teacher, lesson=self.lesson,
            title='Scheduled fixture', body='Synthetic', publish_at=now+timedelta(hours=1)))
        a.moderate(self.admin, notice, 'approved')
        self.assertFalse(UserNotification.objects.filter(title='New learning announcement').exists())
        m.Announcement.objects.filter(pk=notice.pk).update(publish_at=now-timedelta(minutes=1))
        event = fixtures.ActivityTests.event(self, start=now+timedelta(hours=20), end=now+timedelta(hours=21))
        a.register_event(self.parent, event, self.enrolment, True)
        today = timezone.localdate()
        fee = services.save_agreement(self.owner, m.FeeAgreement(enrolment=self.enrolment, start_date=today, amount=100))
        services.create_invoice(self.owner, m.Invoice(agreement=fee, period_start=today, period_end=today, due_date=today, amount=100))
        retry_event = m.NotificationEvent.objects.create(key='synthetic-pending-retry', title='Retry fixture', link='/tuition/learn/')
        delivery = m.NotificationDelivery.objects.create(event=retry_event, recipient=self.parent)
        with patch('tuition.management.commands.tuition_schedule.deliver', side_effect=RuntimeError('Synthetic delivery failure')):
            with self.assertRaisesMessage(RuntimeError, 'Synthetic delivery failure'):
                call_command('tuition_schedule', stdout=io.StringIO())
        delivery.refresh_from_db()
        self.assertEqual(delivery.state, 'pending')
        call_command('tuition_schedule', stdout=io.StringIO())
        delivery.refresh_from_db()
        self.assertEqual((delivery.state, delivery.attempts), ('sent', 1))
        for title in ('New learning announcement', 'Your learning event is coming up', 'Learning fees are due', 'Retry fixture'):
            self.assertEqual(UserNotification.objects.filter(user=self.parent, title=title).count(), 1, title)
        count = UserNotification.objects.count()
        call_command('tuition_schedule', stdout=io.StringIO())
        self.assertEqual(UserNotification.objects.count(), count)

    def test_cached_enrolment_cannot_register_after_withdrawal(self):
        now = timezone.now()
        event = m.LearningEvent.objects.create(teacher=self.teacher, kind='festival', title='Festival',
            start=now+timedelta(days=1), end=now+timedelta(days=2),
            registration_start=now-timedelta(days=1), registration_end=now+timedelta(hours=1),
            capacity=10, status='published', moderation='approved')
        m.Enrolment.objects.filter(pk=self.enrolment.pk).update(status='withdrawn')
        with self.assertRaises(ValidationError):
            a.register_event(self.parent, event, self.enrolment, True)
        self.assertFalse(event.participants.exists())

    def test_cached_message_thread_rechecks_enrolment(self):
        thread = messaging.start(self.parent, self.enrolment, self.parent)
        messaging.authorize(self.parent, thread)
        m.Enrolment.objects.filter(pk=self.enrolment.pk).update(status='withdrawn')
        with self.assertRaises(PermissionDenied):
            messaging.authorize(self.parent, thread)

    def test_scheduler_skips_inactive_teacher_account(self):
        day = timezone.localdate()+timedelta(days=1)
        rule = m.ScheduleRule.objects.create(batch=self.batch, weekday=day.weekday(), start_time='10:00',
            start_date=day, end_date=day, meeting_url='https://meet.google.com/test')
        self.owner.is_active = False; self.owner.save(update_fields=['is_active'])
        self.assertEqual(services.generate(rule), 0)
        self.assertFalse(m.ClassSession.objects.filter(rule=rule).exists())

    def test_student_photo_and_submission_never_public(self):
        photo = m.MediaAsset.objects.create(learner=self.child, uploader=self.parent, storage_key='private.jpg', mime='image/jpeg', size=1, checksum='a'*64, public_requested=True, moderation='approved', subjects_complete=True)
        self.assertFalse(a.public_allowed(photo))
        for name in ('file', 'activity_file'):
            self.assertEqual(self.client.get(reverse('tuition:'+name, args=[photo.uid])).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:file', args=[photo.uid])).status_code, 403)

    def test_private_root_rejects_public_or_checkout_paths(self):
        from .storage import storage
        from django.core.exceptions import ImproperlyConfigured
        for path in (settings.MEDIA_ROOT, settings.STATIC_ROOT, settings.BASE_DIR, settings.BASE_DIR/'private'):
            with self.subTest(path=path), override_settings(TUITION_PRIVATE_ROOT=path), self.assertRaises(ImproperlyConfigured): storage()

    def test_guardian_cannot_self_verify_in_post(self):
        self.client.force_login(self.parent)
        response = self.client.post(reverse('tuition:review'), {'kind': 'guardian', 'uid': self.guardian.uid, 'status': 'verified', 'verification': 'Self-approved'})
        self.assertEqual(response.status_code, 403)

    @skipUnless(os.environ.get('TUITION_AUDIT_UI'), 'Rendered UI export not requested')
    def test_export_synthetic_ui_for_browser_review(self):
        root = (Path(settings.BASE_DIR)/'.audit-tools/ui').resolve(); root.mkdir(parents=True, exist_ok=True)
        event = m.LearningEvent.objects.create(teacher=self.teacher, kind='festival', title='Annual learning festival', description='Synthetic audit programme', start=timezone.now()+timedelta(days=2), end=timezone.now()+timedelta(days=3), venue='Learning hall', registration_start=timezone.now(), registration_end=timezone.now()+timedelta(days=1), capacity=20, status='published', moderation='approved', public=True)
        achievement = m.Achievement.objects.create(teacher=self.teacher, enrolment=self.enrolment, kind='certificate', title='Music achievement', moderation='approved')
        pages = [('discover', None, 'discover', []), ('teacher', self.owner, 'teacher', [self.teacher.uid]),
            ('activities', self.owner, 'teacher_hub', [self.teacher.uid]), ('student', self.parent, 'learner_hub', []),
            ('event-form', self.owner, 'event_create', [self.teacher.uid]), ('event', None, 'event', [event.uid]),
            ('moderation', self.admin, 'admin_hub', []), ('certificate', self.parent, 'certificate', [achievement.uid])]
        for filename, user, route, args in pages:
            self.client.logout()
            if user: self.client.force_login(user)
            response = self.client.get(reverse('tuition:'+route, args=args))
            self.assertEqual(response.status_code, 200)
            (root/(filename+'.html')).write_bytes(response.content)
        (root/'manifest.json').write_text(json.dumps([x[0] for x in pages]))
