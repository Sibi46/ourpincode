from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.template.loader import render_to_string

from jobs.models import User
from .models import Community, Badge


@override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class BadgeArtworkTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = User.objects.create_user('leader')
        self.community = Community.objects.create(name='Example', created_by=self.user,
                                                   purpose='Testing', pincode='600073')
        self.url = f'/portal/c/{self.community.slug}/badges/create/'
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')

    def image(self, name):
        stream = BytesIO()
        Image.new('RGB', (12, 12), 'blue').save(stream, format='PNG')
        return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')

    def test_create_and_render_both_uploads(self):
        response = self.client.post(self.url, {'action': 'create', 'name': 'Champion',
            'icon_image': self.image('icon.png'), 'image': self.image('badge.png')})
        self.assertEqual(response.status_code, 302)
        badge = Badge.objects.get()
        self.assertTrue(badge.icon_image)
        self.assertTrue(badge.image)
        html = render_to_string('portal/badge_artwork.html', {'badge': badge})
        self.assertIn(badge.icon_image.url, html)
        self.assertIn(badge.image.url, html)

    def test_sample_icon_without_upload_still_works(self):
        self.client.post(self.url, {'action': 'create', 'name': 'Star Contributor', 'icon': '⭐'})
        badge = Badge.objects.get()
        self.assertIn('⭐', render_to_string('portal/badge_artwork.html', {'badge': badge}))
        self.assertFalse(badge.image)

    def test_invalid_upload_does_not_create_badge(self):
        self.client.post(self.url, {'action': 'create', 'name': 'Invalid',
                                  'icon_image': SimpleUploadedFile('bad.png', b'not an image')})
        self.assertFalse(Badge.objects.exists())

    def test_other_member_cannot_create_badge(self):
        other = User.objects.create_user('other')
        self.client.force_login(other, backend='django.contrib.auth.backends.ModelBackend')
        self.client.post(self.url, {'action': 'create', 'name': 'Forbidden'})
        self.assertFalse(Badge.objects.exists())
