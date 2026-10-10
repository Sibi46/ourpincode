from django.test import TestCase
from django.urls import reverse
from . import tests as fixtures, models as m


class NamedStudentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_name_creates_private_group_record(self):
        self.client.force_login(self.owner)
        url = reverse('tuition:group_students', args=[self.batch.uid])
        self.assertNotContains(self.client.get(url), 'name="application"')
        self.assertEqual(self.client.post(url, {'name': 'Child'}).status_code, 302)
        enrolment = m.Enrolment.objects.get(lesson=self.lesson)
        self.assertNotEqual(enrolment.learner_id, self.child.pk)
        self.assertIsNone(enrolment.learner.user_id)
        self.assertFalse(enrolment.learner.guardians.exists())
        self.assertEqual(enrolment.membership.batch, self.batch)

    def test_permissions_capacity_and_empty_name(self):
        url = reverse('tuition:group_students', args=[self.batch.uid])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, {'name': 'Student'}).status_code, 403)
        self.client.force_login(self.owner)
        self.client.post(url, {'name': '   '})
        self.assertFalse(m.Enrolment.objects.exists())
        self.batch.capacity = 1
        self.batch.save()
        self.client.post(url, {'name': 'First'})
        count = m.Learner.objects.count()
        self.assertContains(self.client.post(url, {'name': 'Second'}), 'Group is full.')
        self.assertEqual(m.Learner.objects.count(), count)
