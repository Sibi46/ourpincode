from django.test import TestCase
from django.urls import reverse
from . import tests as fixtures


class ProfileUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_profile_template_preserves_public_actions(self):
        response = self.client.get(reverse('tuition:profile', args=[self.teacher.slug]))
        self.assertTemplateUsed(response, 'tuition/profile.html')
        self.assertContains(response, reverse('tuition:apply', args=[self.lesson.uid]))
        self.assertContains(response, reverse('tuition:showcase', args=[self.teacher.slug]))
        self.assertContains(response, reverse('tuition:complaint_create', args=[self.teacher.uid]))
        self.assertNotContains(response, self.parent.email)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_fees_and_inactive_classes(self):
        self.lesson.fee = 1234; self.lesson.save()
        url = reverse('tuition:profile', args=[self.teacher.slug])
        self.assertNotContains(self.client.get(url), '₹1234')
        self.teacher.public_fees = True; self.teacher.save()
        self.assertContains(self.client.get(url), '₹1234')
        self.lesson.active = False; self.lesson.save()
        response = self.client.get(url)
        self.assertNotContains(response, reverse('tuition:apply', args=[self.lesson.uid]))
        self.assertContains(response, 'No active classes are listed yet')

    def test_unapproved_or_inactive_teacher_is_not_public(self):
        url = reverse('tuition:profile', args=[self.teacher.slug])
        self.teacher.status = 'pending'; self.teacher.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.teacher.status = 'approved'; self.teacher.save()
        self.owner.is_active = False; self.owner.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_export_synthetic_preview(self):
        import os
        if os.environ.get('TUITION_AUDIT_UI') != '1':
            self.skipTest('Optional synthetic browser preview')
        from pathlib import Path
        response = self.client.get(reverse('tuition:profile', args=[self.teacher.slug]))
        root = Path('.audit-tools/ui'); root.mkdir(parents=True, exist_ok=True)
        (root / 'profile.html').write_bytes(response.content)
