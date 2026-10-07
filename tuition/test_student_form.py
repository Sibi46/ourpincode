from datetime import date
from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from . import forms, models as m, tests as fixtures


class StudentFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_dob_overrides_supplied_age_and_accepts_unlisted_pin(self):
        self.client.force_login(self.other)
        with patch('django.utils.timezone.localdate', return_value=date(2026, 10, 7)):
            response = self.client.post(reverse('tuition:learner_create'), dict(name='Student example', dob='2010-10-08', age=99,
                pincode='123456', interests='Music, Maths', relationship='Parent', attestation='I am the parent'))
        self.assertEqual(response.status_code, 302)
        student = m.Learner.objects.get(name='Student example')
        self.assertEqual(student.age, 15)
        self.assertEqual(student.age_as_of, date(2026, 10, 7))
        self.assertEqual(set(student.interests.values_list('name', flat=True)), {'Music', 'Maths'})
        self.assertEqual(student.guardians.get().status, 'pending')
        self.assertNotContains(self.client.get(reverse('tuition:dashboard')), reverse('tuition:learner', args=[student.uid]))

    def test_edit_interests_text_and_future_birth_rejected(self):
        subject = m.Subject.objects.create(name='Music', slug='music')
        self.child.interests.add(subject)
        self.assertEqual(forms.LearnerForm(instance=self.child)['interests'].value(), 'Music')
        form = forms.LearnerForm(dict(name='Student', dob='2999-01-01', pincode='123456', self_registration=True))
        self.assertFalse(form.is_valid())

    def test_student_page_uses_opt_out_and_no_separate_guardian_section(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse('tuition:learner_create'))
        self.assertContains(response, 'Add student')
        self.assertContains(response, 'data-pin-lookup="off"')
        self.assertContains(response, 'name="interests"')
        self.assertNotContains(response, 'Guardian verification')
        self.assertContains(response, 'name="attestation"')
