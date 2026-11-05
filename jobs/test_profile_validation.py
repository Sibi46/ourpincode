from django.test import TestCase

from .account import DashboardPersonalForm, DashboardSeekerForm, LocationPreferencesForm
from .models import User


class ProfileInputTests(TestCase):
    def test_personal_names_city_and_whatsapp_reject_wrong_characters(self):
        for field in ('first_name', 'last_name', 'city'):
            form = DashboardPersonalForm(data={field: 'Name 123'})
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)
        form = DashboardPersonalForm(data={'first_name': 'Ravi', 'last_name': 'Kumar',
            'city': 'Vandavasi', 'whatsapp': '98765abcde'})
        self.assertFalse(form.is_valid())
        self.assertIn('whatsapp', form.errors)
        form = DashboardPersonalForm(data={'first_name': 'Ravi', 'last_name': 'Kumar',
            'city': 'Vandavasi', 'whatsapp': '9876543210'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_all_requested_text_fields_reject_numbers(self):
        for field in DashboardSeekerForm.text_fields:
            with self.subTest(field=field):
                form = DashboardSeekerForm(data={'job_category': 'any', field: 'Example 123'})
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_white_collar_types_match_category(self):
        form = DashboardSeekerForm(data={'job_category': 'white', 'blue_collar_type': 'engineer',
            'education': 'Bachelor of Engineering', 'skills': 'C++, Python', 'languages': 'Tamil, English'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn(('engineer', 'Engineer'), list(form.fields['blue_collar_type'].widget.choices))
        form = DashboardSeekerForm(data={'job_category': 'white', 'blue_collar_type': 'driver'})
        self.assertFalse(form.is_valid())
        self.assertIn('blue_collar_type', form.errors)
        form = DashboardSeekerForm(data={'job_category': 'blue', 'blue_collar_type': 'construction'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_main_pincode_requires_six_digits(self):
        for value in ('abcdef', '6044ab', '12345'):
            form = LocationPreferencesForm(data={'pincode': value})
            self.assertFalse(form.is_valid())
        self.assertTrue(LocationPreferencesForm(data={'pincode': '604408'}).is_valid())

    def test_registration_rejects_numeric_owner_before_creating_account(self):
        response = self.client.post('/register/process/', {'user_type': 'company',
            'owner_name': 'Owner 123', 'first_name': 'Owner 123', 'phone': '9876543210',
            'password': 'example-password'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(response.json()['success'])
        self.assertIn('letters and spaces', response.json()['error'])
        self.assertFalse(User.objects.exists())
