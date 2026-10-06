import io
import json
import tempfile
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from jobs.models import AdminProfile, State, District, PinCode, Complaint, Message, UserNotification
from . import models as m, activities as a, services as svc, permissions as p, messaging
from . import activity_storage
from . import tests as core_tests


class ActivityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        core_tests.TuitionTests.setUpTestData.__func__(cls)
        cls.guardian.reviewed_by = cls.admin
        cls.guardian.reviewed_at = timezone.now()
        cls.guardian.save()
        cls.enrolment = svc.decide(cls.owner, cls.application, 'accepted')

    def event(self, **kwargs):
        now = timezone.now()
        values = dict(teacher=self.teacher, kind='competition', title='Music competition', description='Play a tune',
            start=now+timedelta(hours=6), end=now+timedelta(hours=9), venue='Academy hall',
            registration_start=now-timedelta(days=1), registration_end=now+timedelta(hours=5), capacity=2,
            public=True, status='published')
        values.update(kwargs)
        obj = a.save_event(self.owner, m.LearningEvent(**values))
        a.moderate(self.admin, obj, 'approved')
        return obj

    def participant(self, event=None):
        return a.register_event(self.parent, event or self.event(), self.enrolment, consent=True)

    def achievement(self, **kwargs):
        values = dict(teacher=self.teacher, enrolment=self.enrolment, kind='certificate', title='Piano award', public_requested=True)
        values.update(kwargs)
        return a.save_achievement(self.owner, m.Achievement(**values))

    def grant(self, target, learner=None, user=None, **kwargs):
        values = dict(display_name='Young musician', allow_media=True, expires_at=timezone.now()+timedelta(days=30))
        values.update(kwargs)
        return a.consent(user or self.parent, target, learner or self.child, **values)

    def image(self):
        content = io.BytesIO(); Image.new('RGB', (8, 8)).save(content, 'PNG')
        return SimpleUploadedFile('photo.png', content.getvalue(), content_type='image/png')

    def asset(self, **kwargs):
        values = dict(teacher=self.teacher, uploader=self.owner, title='Group performance', storage_key='test.jpg',
            mime='image/jpeg', size=10, checksum='a'*64, public_requested=True, subjects_complete=True, moderation='approved')
        values.update(kwargs)
        obj = m.MediaAsset.objects.create(**values)
        m.MediaSubject.objects.create(asset=obj, learner=self.child)
        return obj

    def scoped(self):
        state = State.objects.create(name='Delhi', code='DL')
        district = District.objects.create(state=state, name='Central Delhi')
        pin = PinCode.objects.create(district=district, code='110001')
        self.teacher.pincode = pin.code; self.teacher.mapped_pin = pin; self.teacher.save()
        user = get_user_model().objects.create_user(username='tuition-state-admin', admin_role='scoped_admin')
        profile = AdminProfile.objects.create(user=user, role='scoped_admin', state=state, sections=['tuition'])
        return user, profile

    def test_all_event_types_and_public_view_no_roster(self):
        self.child.name = 'Private learner 84729'; self.child.save()
        for kind in dict(m.LearningEvent._meta.get_field('kind').choices):
            event = self.event(kind=kind)
            self.participant(event)
            response = self.client.get(reverse('tuition:event', args=[event.uid]))
            self.assertContains(response, event.title)
            self.assertNotContains(response, self.child.name)
            self.assertNotContains(response, self.parent.email)

    def test_event_owner_and_date_constraints(self):
        event = self.event()
        with self.assertRaises(PermissionDenied): a.save_event(self.other, event)
        event.end = event.start
        with self.assertRaises(ValidationError): a.save_event(self.owner, event)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.LearningEvent.objects.filter(pk=event.pk).update(end=event.start)

    def test_registration_requires_verified_adult_and_open_window(self):
        event = self.event()
        with self.assertRaises(ValidationError): a.register_event(self.parent, event, self.enrolment)
        with self.assertRaises(PermissionDenied): a.register_event(self.other, event, self.enrolment, True)
        self.guardian.reviewed_by = None; self.guardian.save()
        with self.assertRaises(PermissionDenied): a.register_event(self.parent, event, self.enrolment, True)
        self.guardian.reviewed_by = self.admin; self.guardian.save()
        event.registration_end = timezone.now()-timedelta(minutes=1); event.save()
        with self.assertRaises(ValidationError): a.register_event(self.parent, event, self.enrolment, True)

    def test_event_capacity_duplicate_and_invitation_not_consent(self):
        event = self.event(capacity=1)
        invitation = a.register_event(self.owner, event, self.enrolment, invite=True)
        with self.assertRaises(ValidationError): a.manage_participant(self.owner, invitation, 'accepted')
        person = self.participant(event)
        self.assertEqual(self.participant(event).pk, person.pk)
        child = m.Learner.objects.create(name='Sibling', created_by=self.parent, pincode='999999')
        m.GuardianLink.objects.create(learner=child, user=self.parent, relationship='Parent', attestation='Reviewed', status='verified', reviewed_by=self.admin, reviewed_at=timezone.now())
        enrolment = m.Enrolment.objects.create(learner=child, lesson=self.lesson)
        with self.assertRaises(ValidationError): a.register_event(self.parent, event, enrolment, True)
        self.assertEqual(event.participants.count(), 1)
        a.manage_participant(self.owner, person, 'accepted')
        self.assertEqual(a.register_event(self.parent, event, self.enrolment, withdraw=True).status, 'withdrawn')
        self.assertEqual(a.register_event(self.parent, event, enrolment, True).status, 'registered')

    def test_registration_cross_teacher_and_pending_event_rejected(self):
        event = self.event()
        teacher = m.TeacherProfile.objects.create(owner=self.other, name='Other school', pincode='999999')
        event.teacher = teacher; event.save()
        with self.assertRaises(ValidationError): a.register_event(self.parent, event, self.enrolment, True)
        event.teacher = self.teacher; event.moderation = 'pending'; event.save()
        with self.assertRaises(ValidationError): a.register_event(self.parent, event, self.enrolment, True)

    def test_festival_programme_bounds_and_participant_tenant(self):
        event = self.event(kind='festival'); person = self.participant(event)
        item = m.ProgrammeItem(event=event, title='Opening recital', start=event.start, end=event.end, venue='Stage')
        other = self.participant(self.event())
        with self.assertRaises(ValidationError): a.save_programme(self.owner, item, [other])
        item.start -= timedelta(hours=1)
        with self.assertRaises(ValidationError): a.save_programme(self.owner, item, [person])
        item.start = event.start
        a.save_programme(self.owner, item, [person])
        self.assertEqual(a.target_learners(item), [self.child])
        self.client.force_login(self.parent)
        self.assertContains(self.client.get(reverse('tuition:event', args=[event.uid])), item.title)
        a.moderate(self.admin, item, 'approved'); self.assertFalse(a.public_allowed(item))
        self.grant(item); self.assertTrue(a.public_allowed(item))
        a.manage_participant(self.owner, person, 'withdrawn'); self.assertFalse(a.public_allowed(item))

    def test_programme_edit_invalidates_consent(self):
        person = self.participant(); event = person.event
        item = a.save_programme(self.owner, m.ProgrammeItem(event=event, title='Recital', start=event.start, end=event.end, venue='Hall'), [person])
        a.moderate(self.admin, item, 'approved'); self.grant(item)
        a.save_programme(self.owner, item, [person]); a.moderate(self.admin, item, 'approved')
        self.assertFalse(a.public_allowed(item))

    def test_results_awards_points_idempotency_and_withdrawal(self):
        person = self.participant()
        for award in ('winner', 'runner_up', 'participation', 'special'):
            result = a.save_result(self.owner, m.EventResult(participation=person, award=award, title=award))
            a.save_result(self.owner, result)
        self.assertEqual(a.points(self.enrolment), 80)
        with self.assertRaises(ValidationError): a.save_result(self.owner, m.EventResult(participation=person, award='winner', title='Duplicate'))
        a.manage_participant(self.owner, person, 'withdrawn')
        self.assertEqual(a.points(self.enrolment), 0)
        self.assertEqual(m.PointEntry.objects.count(), 8)

    def test_result_publication_and_rejection(self):
        person = self.participant()
        result = a.save_result(self.owner, m.EventResult(participation=person, award='winner', title='Winner'))
        a.moderate(self.admin, result, 'approved'); self.assertFalse(a.public_allowed(result))
        self.grant(result); self.assertTrue(a.public_allowed(result))
        a.moderate(self.admin, result, 'rejected'); self.assertFalse(a.public_allowed(result)); self.assertEqual(a.points(self.enrolment), 0)
        a.moderate(self.admin, result, 'approved'); self.assertEqual(a.points(self.enrolment), 20)

    def test_assignment_review_reversal_preserves_original_points(self):
        assignment = a.save_assignment(self.owner, m.Assignment(lesson=self.lesson, title='Practice', instructions='Play', due_at=timezone.now()+timedelta(days=1)))
        submission = a.submit(self.parent, assignment, self.enrolment, 'Completed practice')
        with self.assertRaises(PermissionDenied): a.review_submission(self.other, submission, 'completed', '')
        a.review_submission(self.owner, submission, 'completed', 'Good')
        a.review_submission(self.owner, submission, 'completed', 'Good')
        self.assertEqual(a.points(self.enrolment), 10)
        rule = self.teacher.point_rules.get(source='assignment'); rule.value = 99; rule.version += 1; rule.save()
        a.review_submission(self.owner, submission, 'returned', 'Retry'); self.assertEqual(a.points(self.enrolment), 0)
        a.review_submission(self.owner, submission, 'completed', 'Now complete'); self.assertEqual(a.points(self.enrolment), 10)
        a.submit(self.parent, assignment, self.enrolment, 'Revision'); self.assertEqual(a.points(self.enrolment), 0)

    def test_assignment_batch_and_authorization(self):
        assignment = a.save_assignment(self.owner, m.Assignment(lesson=self.lesson, batch=self.batch, title='Group task', instructions='Practice', due_at=timezone.now()))
        with self.assertRaises(PermissionDenied): a.submit(self.parent, assignment, self.enrolment, 'Not in batch')
        svc.transfer(self.owner, self.enrolment, self.batch)
        a.submit(self.parent, assignment, self.enrolment, 'In batch')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:assignment', args=[assignment.uid])).status_code, 403)

    def test_attendance_points_corrections(self):
        svc.transfer(self.owner, self.enrolment, self.batch)
        now = timezone.now()
        session = svc.save_session(self.owner, m.ClassSession(batch=self.batch, start=now-timedelta(minutes=10), end=now+timedelta(minutes=50), mode='online', meeting_url='https://meet.google.com/abc-defg-hij'))
        roster = session.participants.get(enrolment=self.enrolment)
        for status, points in [('present', 5), ('late', 5), ('absent', 0), ('excused', 0), ('present', 5)]:
            svc.mark_attendance(self.owner, roster, status)
            self.assertEqual(a.points(self.enrolment), points)

    def test_custom_levels_and_future_rules(self):
        first = self.achievement()
        rule = self.teacher.point_rules.get(source='achievement'); rule.value = 100; rule.version += 1; rule.save()
        m.LevelDefinition.objects.create(teacher=self.teacher, name='Star', threshold=120)
        self.achievement(title='New achievement')
        self.assertEqual(a.points(self.enrolment), 125)
        self.enrolment.refresh_from_db(); self.assertEqual(self.enrolment.level, 'Star')
        a.save_achievement(self.owner, first); self.assertEqual(a.points(self.enrolment), 125)
        rule.active = False; rule.save()
        self.achievement(title='No new points'); self.assertEqual(a.points(self.enrolment), 125)

    def test_achievement_cannot_be_reassigned(self):
        obj = self.achievement(); obj.enrolment = None
        with self.assertRaises(ValidationError): a.save_achievement(self.owner, obj)
        obj.refresh_from_db(); self.assertEqual(obj.enrolment, self.enrolment)

    def test_achievement_consent_revision_revoke_expiry(self):
        obj = self.achievement(); a.moderate(self.admin, obj, 'approved')
        self.assertFalse(a.public_allowed(obj)); grant = self.grant(obj); self.assertTrue(a.public_allowed(obj))
        a.revoke(self.parent, grant); self.assertFalse(a.public_allowed(obj))
        grant = self.grant(obj); grant.expires_at = timezone.now()-timedelta(seconds=1); grant.save()
        self.assertFalse(a.public_allowed(obj))
        self.grant(obj); obj.title = 'Edited'; a.save_achievement(self.owner, obj); a.moderate(self.admin, obj, 'approved')
        self.assertFalse(a.public_allowed(obj))

    def test_teacher_and_unrelated_parent_cannot_consent(self):
        obj = self.achievement()
        for user in (self.owner, self.other):
            with self.assertRaises(PermissionDenied): self.grant(obj, user=user)
        with self.assertRaises(ValidationError): self.grant(obj, expires_at=timezone.now()+timedelta(days=400))
        self.client.force_login(self.owner)
        response = self.client.post(reverse('tuition:consent', args=['achievement', obj.uid]), {'learner': self.child.pk, 'confirm': True, 'expires_at': (timezone.now()+timedelta(days=1)).isoformat()})
        self.assertEqual(response.status_code, 200); self.assertFalse(m.PublicationConsent.objects.exists())

    def test_guardian_revocation_and_adult_transition_close_publication(self):
        obj = self.achievement(); a.moderate(self.admin, obj, 'approved'); self.grant(obj)
        self.guardian.status = 'revoked'; self.guardian.save(); self.assertFalse(a.public_allowed(obj))
        self.guardian.status = 'verified'; self.guardian.save()
        self.child.dob = date(1990, 1, 1); self.child.user = self.parent; self.child.save()
        obj = m.Achievement.objects.get(pk=obj.pk)
        self.assertFalse(a.public_allowed(obj))
        with self.assertRaises(PermissionDenied): self.grant(obj)
        self.child.identity_verified = True; self.child.save(); self.grant(obj)
        self.assertTrue(a.public_allowed(m.Achievement.objects.get(pk=obj.pk)))

    def test_group_media_requires_every_subject(self):
        obj = self.asset(); self.grant(obj); self.assertTrue(a.public_allowed(obj))
        child = m.Learner.objects.create(name='Second child', created_by=self.other, pincode='999999')
        m.MediaSubject.objects.create(asset=obj, learner=child)
        self.assertFalse(a.public_allowed(obj))
        m.GuardianLink.objects.create(learner=child, user=self.other, relationship='Parent', attestation='Verified', status='verified', reviewed_by=self.admin, reviewed_at=timezone.now())
        self.grant(obj, learner=child, user=self.other); self.assertTrue(a.public_allowed(obj))
        obj.subjects_complete = False; obj.save(); self.assertFalse(a.public_allowed(obj))

    def test_media_optin_and_suspension(self):
        obj = self.asset(); self.grant(obj, allow_media=False); self.assertFalse(a.public_allowed(obj))
        self.grant(obj); self.assertTrue(a.public_allowed(obj))
        self.teacher.status = 'suspended'; self.teacher.save(); self.assertFalse(a.public_allowed(obj))

    def test_private_certificate_and_public_pseudonym(self):
        obj = self.achievement(); a.moderate(self.admin, obj, 'approved'); self.grant(obj)
        response = self.client.get(reverse('tuition:achievement', args=[obj.uid]))
        self.assertContains(response, 'Young musician'); self.assertNotContains(response, '>Child<')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:certificate', args=[obj.uid])).status_code, 403)
        self.client.force_login(self.parent)
        response = self.client.get(reverse('tuition:certificate', args=[obj.uid])); self.assertContains(response, 'Child')
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_private_upload_and_both_download_routes_recheck_consent(self):
        with tempfile.TemporaryDirectory() as root, override_settings(TUITION_PRIVATE_ROOT=root):
            obj = activity_storage.upload(self.owner, self.image(), self.teacher, 'Picture', True, [self.child])
            obj.subjects_complete = True; obj.save(); a.moderate(self.admin, obj, 'approved')
            for route in ('activity_file', 'file'):
                self.assertIn(self.client.get(reverse('tuition:'+route, args=[obj.uid])).status_code, (302, 403))
            grant = self.grant(obj)
            for route in ('activity_file', 'file'):
                response = self.client.get(reverse('tuition:'+route, args=[obj.uid])); self.assertEqual(response.status_code, 200)
                self.assertTrue(b''.join(response.streaming_content))
            a.revoke(self.parent, grant)
            self.assertEqual(self.client.get(reverse('tuition:activity_file', args=[obj.uid])).status_code, 403)

    def test_upload_invalid_type_wrong_owner_and_review_required(self):
        with self.assertRaises(PermissionDenied): activity_storage.upload(self.other, self.image(), self.teacher, 'Bad', True, [])
        with self.assertRaises(ValidationError): activity_storage.validate(SimpleUploadedFile('bad.svg', b'<svg/>'))
        with self.assertRaises(ValidationError): activity_storage.validate(SimpleUploadedFile('bad.jpg', b'<script/>'))
        asset = self.asset(subjects_complete=False)
        with self.assertRaises(ValidationError): a.moderate(self.admin, asset, 'approved')

    @patch('tuition.activity_storage.shutil.which', return_value=None)
    def test_video_fails_closed_without_validator(self, unused):
        with override_settings(TUITION_FFPROBE=''), self.assertRaisesMessage(ValidationError, 'not configured'):
            activity_storage.validate(SimpleUploadedFile('film.mp4', b'\x00\x00\x00\x18ftypisom'))

    @override_settings(TUITION_FFPROBE='test-ffprobe')
    def test_video_probe_validation_and_protocol_restriction(self):
        info = {'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 320, 'height': 240}], 'format': {'duration': '5'}}
        with patch('tuition.activity_storage.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(info).encode())) as run:
            self.assertEqual(activity_storage.validate(SimpleUploadedFile('film.mp4', b'\x00\x00\x00\x18ftypisom'))[2], 'video/mp4')
            self.assertIn('-protocol_whitelist', run.call_args.args[0])
        with patch('tuition.activity_storage.subprocess.run', return_value=SimpleNamespace(stdout=b'{}')), self.assertRaises(ValidationError):
            activity_storage.validate(SimpleUploadedFile('film.mp4', b'\x00\x00\x00\x18ftypisom'))

    def test_messaging_reuses_records_and_revocation_blocks_legacy(self):
        thread = messaging.start(self.owner, self.enrolment, self.parent)
        self.assertEqual(messaging.start(self.parent, self.enrolment, self.parent).pk, thread.pk)
        message = messaging.send(self.owner, thread, 'Private tuition message')
        self.assertEqual(Message.objects.get(pk=message.pk).conversation, thread.conversation)
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(reverse('chat_room', args=[thread.conversation_id])).status_code, 302)
        self.assertEqual(self.client.post(reverse('send_message'), {'conv_id': thread.conversation_id, 'content': 'Bypass'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('poll_messages', args=[thread.conversation_id])).status_code, 403)
        self.guardian.status = 'revoked'; self.guardian.save()
        self.assertEqual(self.client.get(reverse('tuition:thread', args=[thread.uid])).status_code, 403)
        self.assertEqual(self.client.get(reverse('chat_room', args=[thread.conversation_id])).status_code, 403)

    def test_unverified_minor_or_other_user_cannot_message(self):
        self.child.user = self.other; self.child.save()
        with self.assertRaises(PermissionDenied): messaging.start(self.other, self.enrolment, self.other)
        thread = messaging.start(self.owner, self.enrolment, self.parent)
        with self.assertRaises(PermissionDenied): messaging.send(self.other, thread, 'Attack')
        self.enrolment.status = 'withdrawn'; self.enrolment.save()
        thread = m.TuitionConversation.objects.get(pk=thread.pk)
        with self.assertRaises(PermissionDenied): messaging.send(self.parent, thread, 'After withdrawal')

    def test_legacy_django_admin_excludes_tuition_contexts(self):
        thread = messaging.start(self.owner, self.enrolment, self.parent)
        message = messaging.send(self.parent, thread, 'Private')
        complaint = Complaint.objects.create(submitted_by=self.parent, subject='Concern', description='Private', complaint_type='other')
        m.TuitionComplaint.objects.create(teacher=self.teacher, complaint=complaint)
        request = RequestFactory().get('/admin/'); request.user = self.admin
        self.assertFalse(django_admin.site._registry[Message].get_queryset(request).filter(pk=message.pk).exists())
        self.assertFalse(django_admin.site._registry[Complaint].get_queryset(request).filter(pk=complaint.pk).exists())

    def test_announcements_scheduled_scoped_and_idempotent(self):
        obj = a.save_announcement(self.owner, m.Announcement(teacher=self.teacher, lesson=self.lesson, title='Lesson announcement', body='Private lesson details', publish_at=timezone.now()+timedelta(days=1)))
        a.moderate(self.admin, obj, 'approved'); a.scheduled_notifications()
        self.assertFalse(UserNotification.objects.filter(title='New learning announcement').exists())
        obj.publish_at = timezone.now()-timedelta(minutes=1); obj.save()
        a.scheduled_notifications(); a.scheduled_notifications()
        self.assertEqual(UserNotification.objects.filter(title='New learning announcement').count(), 1)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:announcement', args=[obj.uid])).status_code, 403)
        self.client.force_login(self.parent); self.assertContains(self.client.get(reverse('tuition:announcement', args=[obj.uid])), obj.body)

    def test_scheduler_event_reminder_deduplicated(self):
        self.participant()
        call_command('tuition_schedule', stdout=io.StringIO()); call_command('tuition_schedule', stdout=io.StringIO())
        self.assertEqual(UserNotification.objects.filter(title='Your learning event is coming up').count(), 1)

    def test_moderation_section_and_geography_enforced(self):
        user, profile = self.scoped()
        obj = self.achievement(); a.moderate(user, obj, 'approved')
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('tuition:admin_hub')), 'Piano Academy')
        self.teacher.pincode = '999999'; self.teacher.save()
        self.assertFalse(p.admin_teachers(user).exists())
        self.assertEqual(self.client.post(reverse('tuition:content_review', args=['achievement', obj.uid]), {'decision': 'approved'}).status_code, 404)
        profile.sections = ['jobs']; profile.save()
        self.assertEqual(self.client.get(reverse('tuition:admin_hub')).status_code, 403)

    def test_complaint_uses_existing_lifecycle_and_scope(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.client.post(reverse('tuition:complaint_create', args=[self.teacher.uid]), {'subject': 'Tuition concern', 'description': 'Please review'}).status_code, 302)
        context = m.TuitionComplaint.objects.get()
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse('tuition:my_complaints')), 'Tuition concern')
        self.assertEqual(self.client.post(reverse('tuition:complaint_review', args=[context.uid]), {'status': 'resolved', 'resolution': 'Done'}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('tuition:complaint_review', args=[context.uid]), {'status': 'resolved', 'resolution': 'Reviewed privately'}).status_code, 302)
        context.complaint.refresh_from_db(); self.assertEqual(context.complaint.status, 'resolved')
        self.assertEqual(self.client.post(reverse('resolve_complaint', args=[context.complaint_id]), {'resolution': 'Bypass'}).status_code, 403)

    def test_database_rejects_invalid_consent_and_point_sources(self):
        obj = self.achievement(); rule = self.teacher.point_rules.get(source='achievement')
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.PublicationConsent.objects.create(learner=self.child, authority=self.parent, target_revision=1, expires_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.PointEntry.objects.create(enrolment=self.enrolment, rule=rule, rule_version=1, delta=5, reason='Bad', source_revision='1', action_key='invalid')

    def test_dashboard_and_form_routes_render_and_owner_enforcement(self):
        obj = self.achievement(); event = self.event(); person = self.participant(event)
        self.client.force_login(self.owner)
        routes = [('teacher_hub', self.teacher.uid), ('event_create', self.teacher.uid), ('event_edit', event.uid),
            ('point_settings', self.teacher.uid), ('achievement_edit', obj.uid), ('programme_create', event.uid),
            ('assignment_create', self.lesson.uid), ('announcement_create', self.teacher.uid), ('participant_review', person.uid)]
        for name, uid in routes:
            with self.subTest(route=name): self.assertEqual(self.client.get(reverse('tuition:'+name, args=[uid])).status_code, 200)
        self.client.force_login(self.other)
        for name, uid in routes:
            with self.subTest(route=name): self.assertEqual(self.client.get(reverse('tuition:'+name, args=[uid])).status_code, 403)
        self.client.force_login(self.parent)
        self.assertContains(self.client.get(reverse('tuition:learner_hub')), 'Piano award')

    def test_audit_failure_rolls_back_event(self):
        with patch('tuition.activities.audit', side_effect=RuntimeError('Audit unavailable')), self.assertRaises(RuntimeError): self.event()
        self.assertFalse(m.LearningEvent.objects.exists())

    def test_event_post_workflow_and_revalidation(self):
        event = self.event(); self.client.force_login(self.owner)
        data = {key: getattr(event, key) for key in ('kind', 'title', 'description', 'start', 'end', 'venue', 'mode', 'registration_start', 'registration_end', 'capacity', 'public', 'status')}
        data.update(title='Updated festival', kind='festival', moderation='approved', teacher=self.other.pk)
        self.assertEqual(self.client.post(reverse('tuition:event_edit', args=[event.uid]), data).status_code, 302)
        event.refresh_from_db(); self.assertEqual(event.teacher, self.teacher); self.assertEqual(event.moderation, 'pending')
        self.assertFalse(a.event_public(event))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('tuition:content_review', args=['event', event.uid]), {'decision': 'approved', 'version': event.revision}).status_code, 302)
        event.refresh_from_db(); self.assertTrue(a.event_public(event))

    def test_post_assignment_submission_and_review(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('tuition:assignment_create', args=[self.lesson.uid]), {'title': 'Daily practice', 'instructions': 'Play a scale', 'due_at': (timezone.now()+timedelta(days=1)).isoformat(), 'active': True}).status_code, 302)
        assignment = m.Assignment.objects.get()
        self.client.force_login(self.parent)
        self.assertEqual(self.client.post(reverse('tuition:assignment', args=[assignment.uid]), {'enrolment': self.enrolment.pk, 'body': 'Practised today'}).status_code, 302)
        submission = m.Submission.objects.get()
        self.assertEqual(self.client.post(reverse('tuition:submission', args=[submission.uid]), {'status': 'completed'}).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('tuition:submission', args=[submission.uid]), {'status': 'completed', 'feedback': 'Good'}).status_code, 302)
        self.assertEqual(a.points(self.enrolment), 10)

    def test_post_consent_and_stale_revision(self):
        obj = self.achievement(); a.moderate(self.admin, obj, 'approved')
        self.client.force_login(self.parent)
        url = reverse('tuition:consent', args=['achievement', obj.uid])
        self.assertContains(self.client.get(url), 'Review the exact content')
        data = {'learner': self.child.pk, 'revision': obj.revision, 'display_name': 'Stage name', 'expires_at': (timezone.now()+timedelta(days=10)).isoformat(), 'confirm': True}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        a.save_achievement(self.owner, obj)
        self.assertContains(self.client.post(url, data), 'Content changed')
        self.assertEqual(m.PublicationConsent.objects.count(), 1)
        grant = m.PublicationConsent.objects.get()
        self.assertEqual(self.client.get(reverse('tuition:revoke_consent', args=[grant.uid])).status_code, 405)
        self.assertEqual(self.client.post(reverse('tuition:revoke_consent', args=[grant.uid])).status_code, 302)
        grant.refresh_from_db(); self.assertIsNotNone(grant.revoked_at)

    def test_scope_moderation_reports_exclude_other_states(self):
        user, profile = self.scoped()
        remote = m.TeacherProfile.objects.create(owner=self.other, name='Secret remote academy', pincode='600001')
        remote_achievement = m.Achievement.objects.create(teacher=remote, title='Remote achievement')
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse('tuition:admin_hub')), remote.name)
        self.assertNotContains(self.client.get(reverse('tuition:admin_hub')+'?kind=achievement'), remote_achievement.title)
        self.assertEqual(self.client.get(reverse('tuition:teacher_review', args=[remote.uid])).status_code, 404)
        profile.all_states = True; profile.save()
        self.assertContains(self.client.get(reverse('tuition:admin_hub')), remote.name)

    def test_admin_pagination_and_teacher_cannot_moderate(self):
        for index in range(32):
            m.Achievement.objects.create(teacher=self.teacher, kind='other', title=f'Academy award {index}')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('tuition:admin_hub'), {'kind': 'achievement'})
        self.assertContains(response, 'Next content')
        response = self.client.get(reverse('tuition:admin_hub'), {'kind': 'achievement', 'content_page': 2})
        self.assertContains(response, 'Academy award 0')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('tuition:admin_hub')).status_code, 403)

    def test_student_moderation_main_only_adult_identity(self):
        self.child.dob = date(1990, 1, 1); self.child.user = self.parent; self.child.save()
        user, unused = self.scoped(); self.client.force_login(user)
        url = reverse('tuition:student_review', args=[self.enrolment.uid])
        self.assertEqual(self.client.post(url, {'status': 'paused', 'identity_verified': True}).status_code, 403)
        self.enrolment.refresh_from_db(); self.assertEqual(self.enrolment.status, 'active')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(url, {'status': 'active', 'identity_verified': True}).status_code, 302)
        self.child.refresh_from_db(); self.assertTrue(self.child.identity_verified)

    def test_reactivating_student_preserves_transfer_roster(self):
        svc.transfer(self.owner, self.enrolment, self.batch)
        start = timezone.now()+timedelta(days=1)
        old = svc.save_session(self.owner, m.ClassSession(batch=self.batch, start=start, end=start+timedelta(hours=1), mode='offline', location='Hall'))
        batch = m.Batch.objects.create(lesson=self.lesson, name='Afternoon', capacity=3)
        svc.transfer(self.owner, self.enrolment, batch)
        new = svc.save_session(self.owner, m.ClassSession(batch=batch, start=start+timedelta(hours=2), end=start+timedelta(hours=3), mode='offline', location='Hall'))
        self.client.force_login(self.admin)
        url = reverse('tuition:student_review', args=[self.enrolment.uid])
        self.assertEqual(self.client.post(url, {'status': 'paused'}).status_code, 302)
        self.assertEqual(self.client.post(url, {'status': 'active'}).status_code, 302)
        self.assertFalse(old.participants.get(enrolment=self.enrolment).eligible)
        self.assertTrue(new.participants.get(enrolment=self.enrolment).eligible)

    def test_category_cycle_rejected(self):
        parent = m.Subject.objects.create(name='Arts', slug='arts')
        child = m.Subject.objects.create(name='Music', slug='music', parent=parent)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('tuition:subject_edit', args=[parent.pk]), {'name': parent.name, 'slug': parent.slug, 'parent': child.pk, 'active': True})
        self.assertContains(response, 'cannot contain a cycle')
        parent.refresh_from_db(); self.assertIsNone(parent.parent_id)

    def test_void_and_paid_invoices_not_reminded(self):
        agreement = svc.save_agreement(self.owner, m.FeeAgreement(enrolment=self.enrolment, start_date=timezone.localdate(), amount=100))
        invoice = svc.create_invoice(self.owner, m.Invoice(agreement=agreement, period_start=timezone.localdate(), period_end=timezone.localdate(), due_date=timezone.localdate(), amount=100))
        invoice.state = 'void'; invoice.save(); a.scheduled_notifications()
        self.assertFalse(UserNotification.objects.filter(title='Learning fees are due').exists())
        invoice.state = 'open'; invoice.save(); a.scheduled_notifications(); a.scheduled_notifications()
        self.assertEqual(UserNotification.objects.filter(title='Learning fees are due').count(), 1)

    def test_points_configuration_http_and_cross_teacher_rejected(self):
        a.defaults(self.teacher); rule = self.teacher.point_rules.get(source='attendance')
        self.client.force_login(self.owner)
        url = reverse('tuition:point_edit', args=[rule.uid])
        self.assertEqual(self.client.post(url, {'source': 'attendance', 'value': 12, 'active': True}).status_code, 302)
        rule.refresh_from_db(); self.assertEqual(rule.value, 12); self.assertEqual(rule.version, 2)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, {'source': 'attendance', 'value': 99, 'active': True}).status_code, 403)

    def test_messaging_pagination_and_separate_legacy_conversation(self):
        from jobs.views import _get_or_create_conv
        thread = messaging.start(self.owner, self.enrolment, self.parent)
        legacy = _get_or_create_conv(self.owner, self.parent)
        self.assertNotEqual(legacy.pk, thread.conversation_id)
        Message.objects.bulk_create([Message(conversation=thread.conversation, sender=self.owner, receiver=self.parent, content=f'Learning message {i}') for i in range(52)])
        self.client.force_login(self.parent)
        self.assertContains(self.client.get(reverse('tuition:thread', args=[thread.uid])), 'Learning message 51')
        self.assertContains(self.client.get(reverse('tuition:thread', args=[thread.uid])+'?page=2'), 'Learning message 0')

    def test_brand_asset_not_public_without_optin(self):
        obj = m.MediaAsset.objects.create(teacher=self.teacher, uploader=self.owner, storage_key='unused.jpg', mime='image/jpeg', size=10, checksum='a'*64, subjects_complete=True, moderation='approved')
        self.assertFalse(a.public_allowed(obj))
        self.assertEqual(self.client.get(reverse('tuition:file', args=[obj.uid])).status_code, 403)

    def test_replacement_consent_supersedes_previous_media_permission(self):
        asset = self.asset(); first = self.grant(asset)
        self.assertTrue(a.public_allowed(asset))
        self.grant(asset, allow_media=False)
        first.refresh_from_db(); self.assertIsNotNone(first.revoked_at)
        self.assertFalse(a.public_allowed(asset))

    def test_moderator_must_review_current_revision(self):
        obj = self.achievement(); old_revision = obj.revision
        a.save_achievement(self.owner, obj)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('tuition:content_review', args=['achievement', obj.uid]), {'decision': 'approved', 'version': old_revision})
        self.assertContains(response, 'Content changed')
        obj.refresh_from_db(); self.assertEqual(obj.moderation, 'pending')

    def test_duplicate_point_rule_returns_validation_error(self):
        a.defaults(self.teacher); self.client.force_login(self.owner)
        response = self.client.post(reverse('tuition:point_create', args=[self.teacher.uid]), {'source': 'attendance', 'value': 10, 'active': True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(self.teacher.point_rules.filter(source='attendance').count(), 1)

    def test_mark_learning_messages_read_requires_current_access_and_post(self):
        thread = messaging.start(self.owner, self.enrolment, self.parent)
        message = messaging.send(self.owner, thread, 'Hello')
        url = reverse('tuition:thread_read', args=[thread.uid])
        self.client.force_login(self.other); self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.parent); self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        message.refresh_from_db(); self.assertTrue(message.is_read)

    def test_generic_admin_cannot_attach_messages_to_tuition_conversation(self):
        thread = messaging.start(self.owner, self.enrolment, self.parent)
        request = RequestFactory().get('/admin/jobs/message/add/'); request.user = self.admin
        field = django_admin.site._registry[Message].formfield_for_foreignkey(Message._meta.get_field('conversation'), request)
        self.assertFalse(field.queryset.filter(pk=thread.conversation_id).exists())

    def test_profile_images_do_not_render_video_as_image(self):
        asset = m.MediaAsset.objects.create(teacher=self.teacher, uploader=self.owner, title='Teacher video', mime='video/mp4', storage_key='video.mp4', size=12, checksum='a'*64, moderation='approved', subjects_complete=True, public_requested=True)
        response = self.client.get(reverse('tuition:profile', args=[self.teacher.slug]))
        self.assertNotContains(response, reverse('tuition:file', args=[asset.uid]))
        self.assertContains(self.client.get(reverse('tuition:showcase', args=[self.teacher.slug])), asset.title)

    def test_teacher_sees_own_students_points(self):
        self.achievement()
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('tuition:teacher_hub', args=[self.teacher.uid])), '25 points')
