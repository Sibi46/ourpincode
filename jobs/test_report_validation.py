from django.test import TestCase
from .account import DashboardPersonalForm, DashboardSeekerForm, LocationPreferencesForm
from .models import Advertiser, CompanyProfile, JobSeekerProfile, User


class ReportValidationTests(TestCase):
    def registration(self, **changes):
        data = {'user_type': 'company', 'owner_name': 'Ravi Kumar', 'first_name': 'Ravi Kumar',
                'company_name': 'Local Business', 'phone': '9876543210', 'password': 'abcdefgh',
                'confirm_password': 'abcdefgh', 'pincode': '600073', **changes}
        return self.client.post('/register/process/', data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_registration_rejects_numeric_owner_and_short_password_before_creating_user(self):
        for changes in ({'owner_name': 'Ravi 123'}, {'first_name': '123'},
                        {'password': '1234567', 'confirm_password': '1234567'},
                        {'confirm_password': 'different'}):
            self.assertFalse(self.registration(**changes).json()['success'])
            self.assertFalse(User.objects.exists())

    def test_registration_accepts_eight_character_password(self):
        self.assertTrue(self.registration().json()['success'])
        self.assertTrue(User.objects.get(phone='9876543210').check_password('abcdefgh'))

    def test_short_password_does_not_change_existing_account(self):
        user = User.objects.create_user('existing', password='original-secret', user_type='individual')
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')
        self.assertFalse(self.registration(password='short').json()['success'])
        user.refresh_from_db()
        self.assertEqual(user.user_type, 'individual')
        self.assertTrue(user.check_password('original-secret'))
        self.assertFalse(CompanyProfile.objects.exists())

    def test_advertiser_name_rejected_on_registration_and_reapplication(self):
        user = User.objects.create_user('advertiser-owner', user_type='company')
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')
        data = {'business_name': 'Local Business', 'contact_person': 'Ravi 123', 'description': 'Local services'}
        self.assertEqual(self.client.post('/advertise/register/', data).status_code, 400)
        self.assertFalse(Advertiser.objects.exists())
        advertiser = Advertiser.objects.create(user=user, business_name='Original', contact_person='Ravi', status='rejected')
        self.assertEqual(self.client.post('/advertise/register/', data).status_code, 400)
        advertiser.refresh_from_db()
        self.assertEqual(advertiser.business_name, 'Original')
        data['contact_person'] = 'Ravi Kumar'
        self.assertEqual(self.client.post('/advertise/register/', data).status_code, 302)

    def test_profile_text_and_numeric_validation(self):
        for field in ('first_name', 'last_name', 'city'):
            form = DashboardPersonalForm({field: 'Invalid 123'}, instance=User())
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)
        form = DashboardPersonalForm({'whatsapp': 'abc123'}, instance=User())
        self.assertFalse(form.is_valid())
        self.assertIn('whatsapp', form.errors)
        self.assertFalse(LocationPreferencesForm({'pincode': 'ABCDEF'}).is_valid())
        for field in DashboardSeekerForm.text_fields:
            form = DashboardSeekerForm({'job_category': 'white', field: 'Invalid 123'}, instance=JobSeekerProfile())
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)

    def test_job_types_follow_category_and_reject_mismatched_submission(self):
        for category, kind in [('blue', 'driver'), ('white', 'it')]:
            form = DashboardSeekerForm({'job_category': category, 'blue_collar_type': kind}, instance=JobSeekerProfile())
            self.assertTrue(form.is_valid(), form.errors)
        form = DashboardSeekerForm({'job_category': 'white', 'blue_collar_type': 'driver'}, instance=JobSeekerProfile())
        self.assertFalse(form.is_valid())
        self.assertIn('blue_collar_type', form.errors)
