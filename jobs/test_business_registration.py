from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import User, CompanyProfile, ShopProfile


@override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BusinessRegistrationTests(TestCase):
    def post(self, **data):
        fields = {'user_type': 'shop', 'phone': '9000000001', 'password': 'new-password',
                  'org_name': 'Test shop', 'pincode': '600073'}
        fields.update(data)
        return self.client.post('/register/process/', fields,
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_anonymous_registration_cannot_take_over_existing_account(self):
        owner = User.objects.create_user('existing', password='original-password',
                phone='9000000001', email='owner@example.com', business_phone='9000000002')
        for fields in ({}, {'phone': '9000000002'},
                       {'phone': '9000000003', 'email': 'OWNER@example.com'}):
            response = self.post(**fields)
            self.assertFalse(response.json()['success'])
            owner.refresh_from_db()
            self.assertTrue(owner.check_password('original-password'))
            self.assertNotEqual(owner.user_type, 'shop')
            self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(CompanyProfile.objects.exists())

    def test_authenticated_owner_can_register_business(self):
        owner = User.objects.create_user('owner', phone='9000000001')
        self.client.force_login(owner, backend='django.contrib.auth.backends.ModelBackend')
        self.assertTrue(self.post().json()['success'])
        owner.refresh_from_db()
        self.assertEqual(owner.user_type, 'shop')
        self.assertTrue(owner.salesman_biz_id.startswith('BIZ'))
        self.assertEqual(User.objects.count(), 1)

    def test_registration_uploads_logo_and_banner(self):
        def image(name):
            stream = BytesIO()
            Image.new('RGB', (12, 12), 'blue').save(stream, format='PNG')
            return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            self.assertTrue(self.post(logo=image('logo.png'), banner_image=image('banner.png')).json()['success'])
            business = User.objects.get(phone='9000000001')
            self.assertTrue(business.salesman_biz_id)
            for profile in (CompanyProfile.objects.get(user=business), ShopProfile.objects.get(user=business)):
                self.assertTrue(profile.logo)
                self.assertTrue(profile.banner_image)
            response = self.client.get('/employer/dashboard/')
            self.assertContains(response, business.company.logo.url)
            self.assertContains(response, business.company.banner_image.url)
