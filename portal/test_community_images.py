import io
import tempfile

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from jobs.models import User
from .models import Community


class CommunityImageTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.settings_override.disable)
        self.owner = User.objects.create_user(username='community-owner', password='test-password')
        self.client.force_login(self.owner)

    def image(self, name):
        data = io.BytesIO()
        Image.new('RGB', (40, 20), 'green').save(data, 'PNG')
        return SimpleUploadedFile(name, data.getvalue(), content_type='image/png')

    def test_creation_form_exposes_both_images_and_uploads_them(self):
        url = reverse('portal_create_community')
        page = self.client.get(url)
        self.assertContains(page, 'name="logo"')
        self.assertContains(page, 'name="cover"')
        response = self.client.post(url, {'name': 'Image community', 'purpose': 'Neighbours',
            'description': 'Local community', 'location': 'Vandavasi', 'pincode': '604408',
            'join_mode': 'open', 'logo': self.image('logo.png'), 'cover': self.image('banner.png')})
        self.assertEqual(response.status_code, 302)
        community = Community.objects.get(created_by=self.owner)
        for field in (community.logo, community.cover):
            self.assertTrue(field.storage.exists(field.name))
        page = self.client.get(response.url)
        self.assertContains(page, community.logo.url)
        self.assertContains(page, community.cover.url)

    def test_edit_uploads_originals_without_cropping_and_preserves_on_later_save(self):
        community = Community.objects.create(name='Existing', created_by=self.owner,
            purpose='Neighbours', description='Local community', location='Vandavasi', pincode='604408')
        url = reverse('portal_edit_community', args=[community.page_id])
        page = self.client.get(url)
        self.assertContains(page, 'name="logo" id="logoFileInput"')
        self.assertContains(page, 'name="cover" id="coverFileInput"')
        response = self.client.post(url, {'logo': self.image('new-logo.png'),
            'cover': self.image('new-banner.png'), 'logo_cropped': '', 'cover_cropped': ''})
        self.assertEqual(response.status_code, 302)
        community.refresh_from_db()
        names = (community.logo.name, community.cover.name)
        for field in (community.logo, community.cover):
            self.assertTrue(field.storage.exists(field.name))
        self.client.post(url, {'name': 'Updated'})
        community.refresh_from_db()
        self.assertEqual(names, (community.logo.name, community.cover.name))
