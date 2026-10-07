from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from . import models as m, services as svc, tests as fixtures


class GroupWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.owner)
        self.date = timezone.localdate() + timedelta(days=7)
        self.data = dict(name='Evening group', description='Maths classes', min_age=5, max_age=18,
            mode='offline', location='Room 1', fee='1000', billing_period='Monthly', duration_minutes=60,
            capacity=10, start_date=self.date, end_date=self.date+timedelta(days=6),
            weekdays=[str(self.date.weekday())], start_time='17:00', new_subjects='Maths')
        self.url = reverse('tuition:group_create', args=[self.teacher.uid])
        self.data[f'day_date_{self.date.weekday()}'] = self.date

    def test_create_multiple_groups_with_subjects_and_timetable(self):
        for index, time in enumerate(('17:00', '18:00')):
            response = self.client.post(self.url, {**self.data, 'name': f'Group {index}', 'start_time': time})
            self.assertEqual(response.status_code, 302)
            batch = m.Batch.objects.get(name=f'Group {index}')
            self.assertEqual(batch.lesson.teacher_id, self.teacher.pk)
            self.assertEqual(batch.lesson.subjects.get().name, 'Maths')
            self.assertEqual(batch.rules.count(), 1)
            self.assertEqual(batch.sessions.count(), 1)
            self.assertEqual(batch.capacity, 10)

    def test_conflicting_timetable_rolls_back_entire_group(self):
        self.assertEqual(self.client.post(self.url, self.data).status_code, 302)
        counts = (m.Lesson.objects.count(), m.Batch.objects.count(), m.ScheduleRule.objects.count())
        response = self.client.post(self.url, {**self.data, 'new_subjects': 'Rollback subject'})
        self.assertContains(response, 'already has a class')
        self.assertEqual(counts, (m.Lesson.objects.count(), m.Batch.objects.count(), m.ScheduleRule.objects.count()))
        self.assertFalse(m.Subject.objects.filter(name='Rollback subject').exists())

    def test_approval_and_owner_required(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
        self.client.force_login(self.owner)
        self.teacher.status = 'pending'; self.teacher.save()
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)

    def test_invalid_schedule_creates_nothing(self):
        count = m.Batch.objects.count()
        for changes in ({'location': ''}, {'end_date': self.date-timedelta(days=1)}, {'weekdays': []}, {'start_time': '23:30'}):
            response = self.client.post(self.url, {**self.data, **changes})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(m.Batch.objects.count(), count)

    def test_accept_application_and_add_student(self):
        url = reverse('tuition:group_students', args=[self.batch.uid])
        response = self.client.post(url, {'application': self.application.pk})
        self.assertRedirects(response, reverse('tuition:batch', args=[self.batch.uid]))
        enrolment = m.Enrolment.objects.get(application=self.application)
        self.assertEqual(enrolment.membership.batch_id, self.batch.pk)

    def test_revoked_guardian_cannot_be_enrolled(self):
        self.guardian.status = 'revoked'; self.guardian.save()
        response = self.client.post(reverse('tuition:group_students', args=[self.batch.uid]), {'application': self.application.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(m.Enrolment.objects.filter(application=self.application).exists())

    def test_add_existing_enrolment_and_reject_unrelated_group(self):
        enrolment = svc.decide(self.owner, self.application, 'accepted')
        other_lesson = m.Lesson.objects.create(teacher=self.teacher, name='Other', description='Class', mode='offline', start_date=self.date)
        other_batch = m.Batch.objects.create(lesson=other_lesson, name='Other', mode='offline')
        response = self.client.post(reverse('tuition:group_students', args=[other_batch.uid]), {'enrolment': enrolment.pk})
        self.assertTrue(response.context['form'].errors)
        response = self.client.post(reverse('tuition:group_students', args=[self.batch.uid]), {'enrolment': enrolment.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(m.BatchMembership.objects.get(enrolment=enrolment).batch_id, self.batch.pk)
