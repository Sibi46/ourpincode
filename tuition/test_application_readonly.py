from django.test import TestCase
from django.urls import reverse
from . import tests as fixtures, models as m


class ApplicationReadOnlyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_owner_can_read_but_cannot_respond(self):
        self.application.learner = None
        self.application.save()
        self.client.force_login(self.owner)
        url = reverse('tuition:application', args=[self.application.uid])
        response = self.client.get(url)
        self.assertContains(response, self.application.mobile)
        self.assertNotContains(response, 'name="decision"')
        self.assertNotContains(response, 'name="response"')
        for decision in ('accepted', 'rejected', 'needs_info'):
            self.assertEqual(self.client.post(url, {'decision': decision, 'response': 'Reply'}).status_code, 405)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, 'pending')
        self.assertEqual(self.application.response, '')
        self.assertFalse(m.Enrolment.objects.exists())

    def test_other_user_cannot_read_submission(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:application', args=[self.application.uid])).status_code, 403)
