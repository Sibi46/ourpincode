from django.test import TestCase
from jobs.models import User
from community.models import School
from portal.models import Community


class November16ReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='report16', pincode='600100')
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')

    def test_school_rejects_numbers_in_each_principal_name(self):
        for field in ['principal_name', 'vice_principal']:
            with self.subTest(field=field):
                response = self.client.post('/community/school-corner/register/', {'name': 'Test School', field: 'Name123'})
                self.assertContains(response, 'letters and spaces only', status_code=400)
        self.assertFalse(School.objects.exists())

    def test_school_accepts_unicode_names(self):
        response = self.client.post('/community/school-corner/register/', {'name': 'Test School', 'principal_name': 'தமிழ் அரசு', 'vice_principal': 'Mary Jane'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(School.objects.get().principal_name, 'தமிழ் அரசு')

    def test_published_communities_visible_across_pincodes_and_private_hidden(self):
        visible = Community.objects.create(name='Published Outside Area', pincode='600001', is_verified=True, created_by=self.user)
        Community.objects.create(name='Pending Community', pincode='600100', created_by=self.user)
        Community.objects.create(name='Inactive Community', pincode='600100', is_verified=True, is_active=False)
        for url in ['/portal/', '/portal/communities/', '/portal/create/']:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, visible.name)
                self.assertNotContains(response, 'Pending Community')
                self.assertNotContains(response, 'Inactive Community')
        response = self.client.get('/portal/communities/?pincode=600100')
        self.assertNotContains(response, visible.name)
        response = self.client.get('/portal/communities/?pincode=600001')
        self.assertContains(response, visible.name)

    def test_registration_eye_controls_and_office_lookup(self):
        self.assertContains(self.client.get('/register/?type=company'), 'data-password-eye')
        response = self.client.get('/portal/create/')
        self.assertContains(response, "fetch('/api/pincode/'")
        self.assertNotContains(response, 'var place = po.Block')
