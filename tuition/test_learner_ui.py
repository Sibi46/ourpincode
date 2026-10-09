from django.test import TestCase
from django.urls import reverse
from . import tests as fixtures, forms, models as m


class LearnerUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_dashboard_preserves_authorized_links_and_privacy(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse('tuition:dashboard'))
        self.assertTemplateUsed(response, 'tuition/learn.html')
        self.assertContains(response, reverse('tuition:learner', args=[self.child.uid]))
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        self.client.force_login(self.other)
        response = self.client.get(reverse('tuition:dashboard'))
        self.assertNotContains(response, reverse('tuition:learner', args=[self.child.uid]))
        self.assertContains(response, 'Add your first student')

    def test_form_validation_and_guardian_request(self):
        self.client.force_login(self.other)
        url = reverse('tuition:learner_create')
        response = self.client.get(url)
        self.assertTemplateUsed(response, 'tuition/learner_form.html')
        form = forms.LearnerForm()
        self.assertEqual(set(form.fields), {field.name for _, fields in form.sections() for field in fields})
        data = dict(name='New child', age=10, pincode='600001')
        response = self.client.post(url, data)
        self.assertNotContains(response, 'Please check the highlighted fields')
        self.assertContains(response, 'Enter your relationship to this student')
        response = self.client.post(url, {**data, 'relationship': 'Parent', 'attestation': 'I am the parent'})
        self.assertRedirects(response, reverse('tuition:dashboard'))
        self.assertEqual(m.GuardianLink.objects.get(user=self.other).status, 'pending')

    def test_edit_omits_registration_only_fields(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse('tuition:learner_edit', args=[self.child.uid]))
        self.assertContains(response, 'Update student profile')
        self.assertNotContains(response, 'name="attestation"')
        self.assertNotContains(response, 'name="self_registration"')

    def test_teacher_has_direct_timetable_setup_links(self):
        self.client.force_login(self.owner)
        link = reverse('tuition:schedule', args=[self.batch.uid])
        for url in (reverse('tuition:dashboard'), reverse('tuition:teacher', args=[self.teacher.uid])):
            response = self.client.get(url)
            self.assertContains(response, 'Your groups')
            self.assertContains(response, link)
            self.assertContains(response, 'Set class days &amp; time')
        self.client.force_login(self.parent)
        self.assertNotContains(self.client.get(reverse('tuition:dashboard')), link)
        self.assertEqual(self.client.get(link).status_code, 403)

    def test_pending_profile_explains_missing_setup(self):
        self.teacher.status = 'pending'; self.teacher.save()
        self.client.force_login(self.owner)
        response = self.client.get(reverse('tuition:dashboard'))
        self.assertContains(response, 'An approved teacher profile is needed')
        self.assertNotContains(response, reverse('tuition:schedule', args=[self.batch.uid]))

    def test_export_synthetic_preview(self):
        import os
        if os.environ.get('TUITION_AUDIT_UI') != '1':
            self.skipTest('Optional synthetic browser preview')
        from pathlib import Path
        root = Path('.audit-tools/ui')
        root.mkdir(parents=True, exist_ok=True)
        self.client.force_login(self.parent)
        for name, route in [('learn', 'dashboard'), ('learner-form', 'learner_create')]:
            response = self.client.get(reverse('tuition:' + route))
            (root / (name + '.html')).write_bytes(response.content)
