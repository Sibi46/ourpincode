import io
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from jobs.models import UserNotification
from . import models as m, services as svc


class TuitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='tuition-teacher', password='test')
        cls.other = User.objects.create_user(username='other-teacher', password='test')
        cls.parent = User.objects.create_user(username='parent', password='test', email='parent@example.com')
        cls.admin = User.objects.create_user(username='admin', password='test', admin_role='super_admin')
        cls.teacher = m.TeacherProfile.objects.create(owner=cls.owner, kind='teacher', name='Piano Academy', description='Music', pincode='999999', phone='9000000000', status='approved')
        cls.lesson = m.Lesson.objects.create(teacher=cls.teacher, name='Piano', description='Learn', mode='online', start_date=timezone.localdate(), capacity=3)
        cls.batch = m.Batch.objects.create(lesson=cls.lesson, name='Morning', mode='online', capacity=2)
        cls.child = m.Learner.objects.create(name='Child', created_by=cls.parent, pincode='999999', age=10)
        cls.guardian = m.GuardianLink.objects.create(learner=cls.child, user=cls.parent, relationship='Parent', attestation='Parent', status='verified')
        cls.application = m.Application.objects.create(teacher=cls.teacher, lesson=cls.lesson, learner=cls.child, applicant=cls.parent, name='Child', age=10, mobile='9000000001', email='parent@example.com', pincode='999999', preferred_days='Monday', preferred_timings='Morning', mode='online')

    def enrol(self):
        return svc.decide(self.owner, self.application, 'accepted')

    def invoice(self):
        enrolment = self.enrol()
        agreement = svc.save_agreement(self.owner, m.FeeAgreement(enrolment=enrolment, start_date=timezone.localdate(), amount=100))
        return svc.create_invoice(self.owner, m.Invoice(agreement=agreement, period_start=timezone.localdate(), period_end=timezone.localdate()+timedelta(days=29), due_date=timezone.localdate()+timedelta(days=5), amount=100))

    def session(self, past=False):
        enrolment = self.enrol()
        svc.transfer(self.owner, enrolment, self.batch)
        start = timezone.now() + timedelta(minutes=-10 if past else 60)
        return svc.save_session(self.owner, m.ClassSession(batch=self.batch, start=start, end=start+timedelta(minutes=60), mode='online', meeting_url='https://meet.google.com/abc-defg-hij'))

    def test_public_pin_discovery_accepts_unregistered_pin(self):
        response = self.client.get(reverse('tuition:discover'), {'pincode': '999999'})
        self.assertContains(response, 'Piano Academy')
        self.assertNotContains(self.client.get(reverse('tuition:discover'), {'pincode': '111111'}), 'Piano Academy')

    def test_service_area_and_pending_profile(self):
        m.ServiceArea.objects.create(teacher=self.teacher, pincode='111111')
        self.assertContains(self.client.get('/tuition/', {'pincode': '111111'}), 'Piano Academy')
        self.teacher.status = 'pending'; self.teacher.save()
        self.assertNotContains(self.client.get('/tuition/'), 'Piano Academy')

    def test_distance_and_invalid_coordinates(self):
        self.teacher.latitude = Decimal('13.0827'); self.teacher.longitude = Decimal('80.2707'); self.teacher.save()
        response = self.client.get('/tuition/', {'latitude': '13.0827', 'longitude': '80.2707', 'radius': 1})
        self.assertContains(response, 'Piano Academy')
        self.assertContains(self.client.get('/tuition/', {'radius': 1}), 'require latitude')

    def test_profile_hides_private_fees(self):
        response = self.client.get(reverse('tuition:profile', args=[self.teacher.slug]))
        self.assertContains(response, 'Apply to learn')
        self.assertNotContains(response, 'Monthly')

    def test_anonymous_dashboard_requires_login(self):
        self.assertEqual(self.client.get('/tuition/learn/').status_code, 302)

    def test_teacher_cannot_read_other_teacher(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:teacher', args=[self.teacher.uid])).status_code, 403)

    def test_acceptance_idempotent(self):
        enrolment = self.enrol()
        self.assertEqual(svc.decide(self.owner, self.application, 'accepted').pk, enrolment.pk)
        self.assertEqual(m.Enrolment.objects.count(), 1)
        self.assertTrue(UserNotification.objects.filter(user=self.parent).exists())

    def test_wrong_teacher_cannot_accept(self):
        with self.assertRaises(PermissionDenied): svc.decide(self.other, self.application, 'accepted')

    def test_unverified_guardian_cannot_enrol(self):
        self.guardian.status = 'pending'; self.guardian.save()
        with self.assertRaises(PermissionDenied): self.enrol()

    def test_anonymous_enquiry_cannot_be_auto_enrolled(self):
        self.application.applicant = None; self.application.learner = None; self.application.save()
        with self.assertRaises(ValidationError): self.enrol()

    def test_lesson_capacity(self):
        self.lesson.capacity = 1; self.lesson.save(); self.enrol()
        child = m.Learner.objects.create(name='Second', created_by=self.parent, pincode='999999', age=10)
        m.GuardianLink.objects.create(learner=child, user=self.parent, status='verified', relationship='Parent', attestation='Parent')
        self.application.pk = None; self.application.uid = uuid.uuid4(); self.application.learner = child; self.application.save()
        with self.assertRaises(ValidationError): self.enrol()

    def test_transfer_wrong_lesson(self):
        enrolment = self.enrol()
        lesson = m.Lesson.objects.create(teacher=self.teacher, name='Other', description='Other', mode='online', start_date=timezone.localdate())
        batch = m.Batch.objects.create(lesson=lesson, name='Other', mode='online')
        with self.assertRaises(ValidationError): svc.transfer(self.owner, enrolment, batch)

    def test_transfer_updates_future_roster(self):
        session = self.session()
        enrolment = m.Enrolment.objects.get(application=self.application)
        svc.transfer(self.owner, enrolment, None)
        self.assertFalse(session.participants.get().eligible)

    def test_guardian_revocation_blocks_private_views(self):
        enrolment = self.enrol(); self.client.force_login(self.parent)
        url = reverse('tuition:enrolment', args=[enrolment.uid])
        self.assertEqual(self.client.get(url).status_code, 200)
        svc.review_guardian(self.admin, self.guardian, 'revoked', 'Authority withdrawn')
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_student_cannot_write_payment(self):
        invoice = self.invoice(); self.client.force_login(self.parent)
        self.assertEqual(self.client.post(reverse('tuition:invoice', args=[invoice.uid]), {'amount': 1}).status_code, 403)

    def test_payment_idempotency_balance_and_reversal(self):
        invoice = self.invoice(); key = uuid.uuid4()
        payment = svc.record_payment(self.owner, invoice, Decimal('40'), 'cash', key)
        self.assertEqual(svc.record_payment(self.owner, invoice, Decimal('40'), 'cash', key).pk, payment.pk)
        self.assertEqual(invoice.balance, 60)
        self.assertEqual(invoice.status, 'Partially Paid')
        with self.assertRaises(ValidationError): svc.record_payment(self.owner, invoice, Decimal('61'), 'cash', uuid.uuid4())
        svc.reverse_payment(self.owner, payment); svc.reverse_payment(self.owner, payment)
        self.assertEqual(invoice.balance, 100)
        self.assertEqual(invoice.payments.count(), 2)

    def test_overdue_and_paid(self):
        invoice = self.invoice(); invoice.due_date = timezone.localdate()-timedelta(days=1); invoice.save()
        self.assertEqual(invoice.status, 'Overdue')
        svc.record_payment(self.owner, invoice, Decimal('100'), 'upi', uuid.uuid4())
        self.assertEqual(invoice.status, 'Paid')

    def test_invoice_overlap(self):
        invoice = self.invoice()
        with self.assertRaises(ValidationError): svc.create_invoice(self.owner, m.Invoice(agreement=invoice.agreement, period_start=invoice.period_start, period_end=invoice.period_end+timedelta(days=1), amount=100, due_date=invoice.due_date))

    def test_audit_failure_rolls_back_payment(self):
        invoice = self.invoice()
        with patch('tuition.services.audit', side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError): svc.record_payment(self.owner, invoice, Decimal('10'), 'cash', uuid.uuid4())
        self.assertEqual(invoice.payments.count(), 0)

    def test_attendance_permissions_and_cancelled_class(self):
        session = self.session(past=True); person = session.participants.get()
        with self.assertRaises(PermissionDenied): svc.mark_attendance(self.parent, person, 'present')
        svc.mark_attendance(self.owner, person, 'late'); svc.mark_attendance(self.owner, person, 'present')
        self.assertEqual(m.Attendance.objects.count(), 1)
        session.status = 'cancelled'; session.save()
        with self.assertRaises(ValidationError): svc.mark_attendance(self.owner, person, 'absent')

    def test_join_authorization_and_no_link_in_html(self):
        session = self.session(past=True); self.client.force_login(self.parent)
        self.assertNotContains(self.client.get(reverse('tuition:session', args=[session.uid])), 'meet.google.com')
        response = self.client.get(reverse('tuition:join', args=[session.uid]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:join', args=[session.uid])).status_code, 403)

    def test_meeting_url_validation(self):
        for url in ['http://meet.google.com/a', 'https://meet.google.com.evil.test/a', 'javascript:alert(1)', 'https://user@meet.google.com/a']:
            with self.assertRaises(ValidationError): m.meeting_url(url)

    def test_recurring_generation_is_idempotent(self):
        day = timezone.localdate()+timedelta(days=1)
        rule = m.ScheduleRule.objects.create(batch=self.batch, weekday=day.weekday(), start_time='10:00', start_date=day, end_date=day+timedelta(days=14), meeting_url='https://meet.google.com/test')
        rule.refresh_from_db()
        self.assertEqual(svc.generate(rule), 3)
        self.assertEqual(svc.generate(rule), 0)

    def test_session_overlap(self):
        session = self.session()
        with self.assertRaises(ValidationError): svc.save_session(self.owner, m.ClassSession(batch=self.batch, start=session.start, end=session.end, mode='online', meeting_url='https://meet.google.com/test'))

    def test_private_photo_rejects_other_users(self):
        from .storage import upload_image
        with tempfile.TemporaryDirectory() as directory, override_settings(TUITION_PRIVATE_ROOT=directory):
            buf = io.BytesIO(); Image.new('RGB', (3, 3)).save(buf, format='PNG')
            asset = upload_image(self.parent, SimpleUploadedFile('photo.png', buf.getvalue()), learner=self.child)
            url = reverse('tuition:file', args=[asset.uid])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(self.parent)
            response = self.client.get(url); self.assertEqual(response.status_code, 200)
            self.assertTrue(b''.join(response.streaming_content))
            self.guardian.status = 'revoked'; self.guardian.save()
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_invalid_upload(self):
        from .storage import upload_image
        with self.assertRaises(ValidationError): upload_image(self.parent, SimpleUploadedFile('evil.svg', b'<svg/>'), learner=self.child)

    def test_model_duplicate_constraint(self):
        self.enrol()
        with self.assertRaises(IntegrityError), transaction.atomic(): m.Enrolment.objects.create(learner=self.child, lesson=self.lesson)

    def test_guardian_review_requires_main_admin(self):
        with self.assertRaises(PermissionDenied): svc.review_guardian(self.owner, self.guardian, 'verified', 'claimed')

    def test_dashboard_templates(self):
        self.client.force_login(self.owner)
        for name, obj in [('teacher', self.teacher), ('lesson', self.lesson), ('batch', self.batch)]:
            self.assertEqual(self.client.get(reverse('tuition:'+name, args=[obj.uid])).status_code, 200)
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get('/tuition/learn/').status_code, 200)

    def test_public_apply_does_not_accept_arbitrary_learner(self):
        data = {'name': 'Child', 'age': 10, 'mobile': '9000000001', 'email': 'parent@example.com', 'pincode': '999999', 'preferred_days': 'Monday', 'preferred_timings': 'Morning', 'mode': 'online', 'learner': self.child.pk}
        response = self.client.post(reverse('tuition:apply', args=[self.lesson.uid]), data)
        self.assertContains(response, 'Select a valid choice')
        self.assertEqual(m.Application.objects.count(), 1)

    def test_guardian_cannot_change_identity_link(self):
        self.client.force_login(self.parent)
        data = {'name': 'Child Updated', 'age': 11, 'pincode': '999999', 'user': self.other.pk, 'created_by': self.other.pk}
        response = self.client.post(reverse('tuition:learner_edit', args=[self.child.uid]), data)
        self.assertEqual(response.status_code, 302)
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, 'Child Updated')
        self.assertIsNone(self.child.user_id)
        self.assertEqual(self.child.created_by_id, self.parent.pk)

    def test_public_enquiry_claim_requires_original_session(self):
        data = {'name': 'New learner', 'age': 20, 'mobile': '9000000002', 'email': 'new@example.com', 'pincode': '123456', 'preferred_days': 'Monday', 'preferred_timings': 'Evening', 'mode': 'online'}
        self.assertEqual(self.client.post(reverse('tuition:apply', args=[self.lesson.uid]), data).status_code, 302)
        app = m.Application.objects.get(name='New learner')
        self.client.force_login(self.parent)
        self.assertEqual(self.client.post(reverse('tuition:claim', args=[app.uid])).status_code, 302)
        app.refresh_from_db(); self.assertEqual(app.applicant_id, self.parent.pk)
        self.assertEqual(self.client.post(reverse('tuition:claim', args=[app.uid])).status_code, 403)

    def test_fake_claim_has_no_access(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('tuition:claim', args=[self.application.uid])).status_code, 403)

    def test_rejected_application_cannot_be_accepted(self):
        svc.decide(self.owner, self.application, 'rejected', 'No place')
        with self.assertRaises(ValidationError): self.enrol()

    def test_needs_information_response_then_accept(self):
        svc.decide(self.owner, self.application, 'needs_info', 'Choose time')
        self.client.force_login(self.parent)
        response = self.client.post(reverse('tuition:application', args=[self.application.uid]), {'response': 'Morning', 'decision': 'pending', 'learner': self.child.pk})
        self.assertEqual(response.status_code, 302)
        self.enrol()
        self.assertEqual(m.Enrolment.objects.count(), 1)

    def test_payment_key_mismatch_and_other_teacher(self):
        invoice = self.invoice(); key = uuid.uuid4()
        svc.record_payment(self.owner, invoice, Decimal('20'), 'cash', key)
        with self.assertRaises(ValidationError): svc.record_payment(self.owner, invoice, Decimal('21'), 'cash', key)
        with self.assertRaises(PermissionDenied): svc.record_payment(self.other, invoice, Decimal('20'), 'cash', uuid.uuid4())

    def test_pending_gateway_not_counted(self):
        invoice = self.invoice()
        m.Payment.objects.create(invoice=invoice, amount=40, method='card', source='gateway', state='pending', recorded_by=self.owner)
        self.assertEqual(invoice.balance, 100)

    def test_fee_agreement_overlap_and_close(self):
        invoice = self.invoice(); agreement = invoice.agreement
        with self.assertRaises(ValidationError): svc.save_agreement(self.owner, m.FeeAgreement(enrolment=agreement.enrolment, start_date=timezone.localdate(), amount=200))
        self.client.force_login(self.owner)
        response = self.client.post(reverse('tuition:fee_close', args=[agreement.uid]), {'end_date': invoice.period_end.isoformat()})
        self.assertEqual(response.status_code, 302)
        svc.save_agreement(self.owner, m.FeeAgreement(enrolment=agreement.enrolment, start_date=invoice.period_end+timedelta(days=1), amount=200))

    def test_stop_rule_keeps_rows_and_cancels_future(self):
        day = timezone.localdate()+timedelta(days=1)
        rule = m.ScheduleRule.objects.create(batch=self.batch, weekday=day.weekday(), start_time='10:00', start_date=day, end_date=day, meeting_url='https://meet.google.com/test')
        rule.refresh_from_db(); svc.generate(rule)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('tuition:stop_rule', args=[rule.uid])).status_code, 302)
        self.assertEqual(m.ClassSession.objects.get(rule=rule).status, 'cancelled')

    def test_invitation_is_single_use_and_does_not_grant_guardianship(self):
        token = svc.invite(self.owner, self.lesson, self.parent.email)
        self.client.force_login(self.parent)
        url = reverse('tuition:invitation_accept', args=[token])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertEqual(m.Enrolment.objects.count(), 0)

    def test_invitation_wrong_recipient_and_expiry(self):
        token = svc.invite(self.owner, self.lesson, self.parent.email)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:invitation_accept', args=[token])).status_code, 403)
        m.Invitation.objects.update(expires_at=timezone.now()-timedelta(days=1))
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(reverse('tuition:invitation_accept', args=[token])).status_code, 403)

    def test_csrf_required_for_public_application(self):
        from django.test import Client
        self.assertEqual(Client(enforce_csrf_checks=True).post(reverse('tuition:apply', args=[self.lesson.uid]), {}).status_code, 403)

    def test_time_filter_matches_overlap(self):
        day = timezone.localdate()+timedelta(days=1)
        rule = m.ScheduleRule.objects.create(batch=self.batch, weekday=day.weekday(), start_time='10:00', duration_minutes=60, start_date=day, end_date=day, meeting_url='https://meet.google.com/test')
        rule.refresh_from_db(); svc.generate(rule)
        self.assertContains(self.client.get('/tuition/', {'weekday': day.weekday(), 'start': '10:30', 'end': '11:30'}), 'Piano Academy')
        m.ClassSession.objects.update(status='cancelled')
        self.assertNotContains(self.client.get('/tuition/', {'weekday': day.weekday(), 'start': '10:30', 'end': '11:30'}), 'Piano Academy')

    def test_suspended_teacher_cannot_mutate(self):
        self.teacher.status = 'suspended'; self.teacher.save()
        with self.assertRaises(PermissionDenied): self.enrol()

    def test_form_pages_and_payment_history_render(self):
        invoice = self.invoice(); self.client.force_login(self.owner)
        for name, arg in [('invoice', invoice.uid), ('lesson_edit', self.lesson.uid), ('batch_edit', self.batch.uid), ('schedule', self.batch.uid), ('availability', self.teacher.uid), ('teacher_edit', self.teacher.uid)]:
            self.assertEqual(self.client.get(reverse('tuition:'+name, args=[arg])).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('tuition:review')).status_code, 200)

    def test_inactive_user_and_other_learner_data(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:learner', args=[self.child.uid])).status_code, 404)
        self.parent.is_active = False; self.parent.save()
        from .permissions import learners
        with self.assertRaises(PermissionDenied): learners(self.parent)

    def test_notification_delivery_is_idempotent(self):
        svc.notify('test-dedup', 'Class changed', [self.parent.pk])
        svc.notify('test-dedup', 'Class changed', [self.parent.pk])
        self.assertEqual(UserNotification.objects.filter(title='Class changed').count(), 1)

    def test_teacher_registration_cannot_self_approve_or_assign_owner(self):
        self.client.force_login(self.other)
        data = {'kind': 'academy', 'name': 'New academy', 'description': 'Learning', 'experience': 2, 'min_age': 5, 'max_age': 90, 'mode': 'online', 'pincode': '123456', 'phone': '9000000000', 'radius_km': 0, 'service_pins': '123457,123458', 'owner': self.owner.pk, 'status': 'approved'}
        self.assertEqual(self.client.post('/tuition/register/', data).status_code, 302)
        obj = m.TeacherProfile.objects.get(name='New academy')
        self.assertEqual(obj.owner_id, self.other.pk)
        self.assertEqual(obj.status, 'pending')
        self.assertEqual(obj.service_areas.count(), 2)

    def test_notification_read_is_recipient_only(self):
        svc.notify('private-notice', 'Private learning notice', [self.parent.pk])
        notice = UserNotification.objects.get(title='Private learning notice')
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('tuition:notification_read', args=[notice.pk])).status_code, 404)
        self.client.force_login(self.parent)
        self.assertEqual(self.client.post(reverse('tuition:notification_read', args=[notice.pk])).status_code, 302)
        notice.refresh_from_db(); self.assertTrue(notice.is_read)

    def test_future_payment_rejected(self):
        invoice = self.invoice()
        with self.assertRaises(ValidationError): svc.record_payment(self.owner, invoice, Decimal('10'), 'cash', uuid.uuid4(), timezone.now()+timedelta(days=1))

    def test_cancelled_class_cannot_join(self):
        session = self.session(past=True); session.status = 'cancelled'; session.save()
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(reverse('tuition:join', args=[session.uid])).status_code, 403)

    def test_individual_class_search_and_reschedule(self):
        session = self.session()
        local = timezone.localtime(session.start)
        response = self.client.get('/tuition/', {'weekday': local.weekday(), 'start': local.strftime('%H:%M')})
        self.assertContains(response, 'Piano Academy')
        old_count = m.ClassSession.objects.count()
        session.start += timedelta(days=1); session.end += timedelta(days=1)
        svc.save_session(self.owner, session)
        self.assertEqual(m.ClassSession.objects.count(), old_count)
        self.assertEqual(session.revision, 2)
