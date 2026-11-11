from django.conf import settings
from django.test import Client, TestCase
from django.utils import timezone
from .models import AdPost, Advertiser, User
from .templatetags.interface_language import TAMIL


class LanguageAndAdvertiserTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('language-preview', user_type='company')
        Advertiser.objects.create(user=self.user, business_name='Lotus Business', status='approved')
        AdPost.objects.create(user=self.user, company_name='LongBusinessName' * 10,
            image='ad_posts/example.png', description='Offer details', status='approved',
            approved_at=timezone.now(), expires_at=timezone.localdate())

    def test_anonymous_language_selection_persists_and_can_return_to_english(self):
        response = self.client.post('/language/', {'language': 'ta', 'next': '/'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'ta')
        self.assertContains(self.client.get('/'), TAMIL['Home'])
        self.assertContains(self.client.get('/businesses/'), TAMIL['Businesses near you'])
        self.client.post('/language/', {'language': 'en', 'next': '/'})
        self.assertContains(self.client.get('/'), '<span>Home</span>', html=False)

    def test_advertiser_dashboard_translates_labels_and_preserves_business_data(self):
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')
        self.client.post('/language/', {'language': 'ta', 'next': '/advertiser/dashboard/'})
        response = self.client.get('/advertiser/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TAMIL['My Advertisements'])
        self.assertContains(response, TAMIL['Sign out'])
        self.assertContains(response, 'Lotus Business')
        self.assertContains(response, 'advertiser-responsive.css')
        self.assertContains(response, '<html lang="ta">', html=False)

    def test_language_post_requires_csrf_and_rejects_external_redirect(self):
        client = Client(enforce_csrf_checks=True)
        client.get('/')
        self.assertEqual(client.post('/language/', {'language': 'ta'}).status_code, 403)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post('/language/', {'language': 'ta', 'next': 'https://outside.example/'}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')
