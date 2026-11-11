from unittest.mock import patch

from django.test import TestCase
from campus.models import Institution, CampusCompany, PlacementOfficer
from jobs.models import User, CompanyProfile


class November11ReportTests(TestCase):
    def hr_data(self, **changes):
        return {'full_name': 'Ravi Kumar', 'email': 'hr@example.test', 'company_name': 'Test Company',
                'phone': '9876543210', 'password': 'secure-test-password', 'password2': 'secure-test-password', **changes}

    def test_hr_signup_creates_company_and_signs_in(self):
        response = self.client.post('/campus/hr/signup/', self.hr_data())
        self.assertRedirects(response, '/campus/company/dashboard/', fetch_redirect_response=False)
        user = User.objects.get(email='hr@example.test')
        self.assertEqual(CampusCompany.objects.get(user=user).status, 'pending')
        self.assertEqual(self.client.session['_auth_user_id'], str(user.pk))

    def test_hr_company_failure_does_not_leave_orphan_user(self):
        with patch('campus.views.CampusCompany.objects.create', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/campus/hr/signup/', self.hr_data())
        self.assertFalse(User.objects.filter(email='hr@example.test').exists())

    def test_po_signup_selects_institution_and_signs_in(self):
        inst = Institution.objects.create(name='Verified College', status='verified', pincode='600073')
        data = self.hr_data(institution_id=str(inst.pk), pincode='600073')
        response = self.client.post('/campus/po/signup/', data)
        self.assertRedirects(response, '/campus/po/dashboard/', fetch_redirect_response=False)
        self.assertEqual(PlacementOfficer.objects.get().institution_id, inst.pk)
        self.assertIn('_auth_user_id', self.client.session)

    def test_institution_options_and_empty_state(self):
        for path in ('/campus/student/signup/', '/campus/po/signup/'):
            response = self.client.get(path)
            self.assertContains(response, 'No verified institutions available')
            self.assertContains(response, '/campus/institution/register/')
        Institution.objects.create(name='Verified College', status='verified', pincode='600073')
        Institution.objects.create(name='Pending College', status='pending', pincode='600073')
        for path in ('/campus/student/signup/', '/campus/po/signup/'):
            response = self.client.get(path)
            self.assertContains(response, 'Verified College')
            self.assertNotContains(response, 'Pending College')

    def test_profile_save_returns_inline_confirmation(self):
        user = User.objects.create_user(username='profile-report', user_type='company', pincode='600073', first_name='Ravi')
        CompanyProfile.objects.create(user=user, company_name='Test Company')
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')
        response = self.client.post('/employer/dashboard/', {'dashboard_profile': '1', 'first_name': 'Kumar'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Profile saved successfully.')
        user.refresh_from_db(); self.assertEqual(user.first_name, 'Kumar')
        response = self.client.post('/employer/dashboard/', {'dashboard_profile': '1', 'first_name': '123'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db(); self.assertEqual(user.first_name, 'Kumar')
