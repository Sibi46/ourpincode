from django.test import TestCase
from django.urls import reverse
from . import models as m, tests as fixtures


class DiscoveryBrandingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_public_images_and_invitation_placement(self):
        asset = m.MediaAsset.objects.create(teacher=self.teacher, uploader=self.owner,
            storage_key='brand.jpg', mime='image/jpeg', size=1, checksum='x',
            public_requested=True, subjects_complete=True, moderation='approved')
        self.teacher.profile_image = asset
        self.teacher.banner_image = asset
        self.teacher.save()
        response = self.client.get(reverse('tuition:discover'))
        self.assertContains(response, reverse('tuition:file', args=[asset.uid]), count=2)
        html = response.content.decode()
        self.assertLess(html.index('SHARE WHAT YOU KNOW'), html.index('discovery-hero'))
        asset.public_requested = False
        asset.save()
        self.assertNotContains(self.client.get(reverse('tuition:discover')), reverse('tuition:file', args=[asset.uid]))

    def test_staff_management_requires_academy_owner(self):
        self.client.force_login(self.owner)
        url = reverse('tuition:academy_staff', args=[self.teacher.uid])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.teacher.kind = 'academy'
        self.teacher.save()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
