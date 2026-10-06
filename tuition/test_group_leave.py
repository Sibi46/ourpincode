from datetime import timedelta
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from . import models as m, services as svc, tests as fixtures


class GroupLeaveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.enrolment = svc.decide(self.owner, self.application, 'accepted')
        svc.transfer(self.owner, self.enrolment, self.batch)
        self.start = timezone.now() + timedelta(days=1)
        self.session = svc.save_session(self.owner, m.ClassSession(batch=self.batch, start=self.start,
            end=self.start + timedelta(hours=1), mode='offline', location='Classroom'))
        self.day = timezone.localdate(self.start)

    def record(self, **kwargs):
        data = dict(user=self.owner, batch=self.batch, enrolment=self.enrolment,
                    start_date=self.day, end_date=self.day, status='excused', note='Family leave')
        data.update(kwargs)
        return svc.record_group_leave(**data)

    def test_future_leave_preserves_membership_and_rejects_overwrite(self):
        self.assertEqual(self.record(), 1)
        self.assertEqual(m.Attendance.objects.get().status, 'excused')
        self.assertEqual(m.BatchMembership.objects.get(enrolment=self.enrolment).batch_id, self.batch.pk)
        with self.assertRaises(ValidationError):
            self.record()
        self.assertEqual(m.Attendance.objects.count(), 1)

    def test_future_absence_and_invalid_ranges_rejected(self):
        for changes in ({'status': 'absent'}, {'end_date': self.day-timedelta(days=1)},
                        {'start_date': self.day+timedelta(days=2), 'end_date': self.day+timedelta(days=2)}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.record(**changes)
        self.assertFalse(m.Attendance.objects.exists())

    def test_permissions_and_approval(self):
        with self.assertRaises(PermissionDenied):
            self.record(user=self.other)
        self.teacher.status = 'pending'; self.teacher.save()
        with self.assertRaises(ValidationError):
            self.record()
        self.assertFalse(m.Attendance.objects.exists())

    def test_form_workflow_and_non_member_rejection(self):
        self.client.force_login(self.owner)
        url = reverse('tuition:group_leave', args=[self.batch.uid])
        response = self.client.post(url, dict(enrolment=self.enrolment.pk, start_date=self.day,
            end_date=self.day, status='excused', note='Appointment'))
        self.assertRedirects(response, reverse('tuition:batch', args=[self.batch.uid]))
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(url).status_code, 403)
        svc.transfer(self.owner, self.enrolment, None)
        with self.assertRaises(ValidationError):
            self.record()

    def test_past_absence(self):
        self.session.start = timezone.now()-timedelta(minutes=30)
        self.session.end = timezone.now()+timedelta(minutes=30)
        self.session.save()
        self.day = timezone.localdate(self.session.start)
        self.assertEqual(self.record(status='absent'), 1)
        self.assertEqual(m.Attendance.objects.get().status, 'absent')

    def test_cancelled_class_excluded(self):
        self.session.status = 'cancelled'; self.session.save()
        with self.assertRaises(ValidationError):
            self.record()
        self.assertFalse(m.Attendance.objects.exists())

    def test_mixed_past_and_future_absence_rolls_back(self):
        start = timezone.now()-timedelta(minutes=20)
        svc.save_session(self.owner, m.ClassSession(batch=self.batch, start=start,
            end=start+timedelta(hours=1), mode='offline', location='Classroom'))
        with self.assertRaises(ValidationError):
            self.record(start_date=timezone.localdate(start), status='absent')
        self.assertFalse(m.Attendance.objects.exists())
