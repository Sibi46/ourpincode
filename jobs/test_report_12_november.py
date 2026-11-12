from datetime import date
from django.test import TestCase
from .account import BusinessDetailsForm
from .models import User, CompanyProfile, Job, Industry


class November12ReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='nov12-owner', user_type='company', pincode='600073', city='Chennai', address='Test street')
        self.company = CompanyProfile.objects.create(user=self.user, company_name='Test Business', industry='Retail', company_size='Small')
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')

    def data(self, **changes):
        return {'title': 'Software Engineer', 'industry': 'Technology', 'description': 'Build useful products.',
            'pincode': '600073', 'location': 'Chennai', 'category': 'Engineer', 'collar_type': 'white',
            'latitude': '13', 'longitude': '80', **changes}

    def test_business_industry_is_dropdown_with_categories_and_legacy_value(self):
        Industry.objects.create(name='Local Services')
        form = BusinessDetailsForm(instance=self.company)
        self.assertEqual(form.fields['industry'].widget.input_type, 'select')
        choices = dict(form.fields['industry'].choices)
        for value in ['Food & Beverage', 'Healthcare', 'Education', 'Technology', 'Retail', 'Local Services']:
            self.assertIn(value, choices)
        self.company.industry = 'Existing Legacy Category'
        form = BusinessDetailsForm(instance=self.company)
        self.assertIn(self.company.industry, dict(form.fields['industry'].choices))
        response = self.client.post('/employer/dashboard/', {'profile_section': 'business-profile',
            'company_name': 'Test Business', 'industry': 'Healthcare', 'review_reward_percent': '0'})
        self.assertEqual(response.status_code, 302)
        self.company.refresh_from_db(); self.assertEqual(self.company.industry, 'Healthcare')

    def test_numeric_title_and_industry_cannot_be_saved(self):
        for field, value in [('title', '123456'), ('title', '１２３'), ('industry', '123'), ('industry', 'Retail, 123')]:
            with self.subTest(field=field, value=value):
                response = self.client.post('/post-job/', self.data(**{field: value}))
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.context['job_errors'])
        self.assertFalse(Job.objects.exists())
        self.assertEqual(self.client.post('/post-job/', self.data(title='3D Designer')).status_code, 302)

    def test_description_word_boundary_and_server_rejection(self):
        response = self.client.post('/post-job/', self.data(description='word '*151))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, '150 words', status_code=400)
        self.assertEqual(response.context['posted_data']['title'], 'Software Engineer')
        self.assertFalse(Job.objects.exists())
        self.assertEqual(self.client.post('/post-job/', self.data(description='word '*150)).status_code, 302)
        self.assertEqual(len(Job.objects.get().description.split()), 150)

    def test_deadline_four_digit_year_and_calendar_validation(self):
        for value in ['123456-11-20', '20/11/123456', '31/02/2026', 'invalid']:
            response = self.client.post('/post-job/', self.data(last_date=value))
            self.assertEqual(response.status_code, 400)
            self.assertIn('last_date', response.context['job_errors'])
        for value in ['20/12/2026', '2026-12-20']:
            self.assertEqual(self.client.post('/post-job/', self.data(last_date=value)).status_code, 302)
        self.assertEqual(list(Job.objects.values_list('last_date', flat=True)), [date(2026, 12, 20)]*2)

    def test_invalid_pincode_and_numeric_location_are_rejected(self):
        for field, value in [('pincode', 'abcdef'), ('pincode', '60007'), ('pincode', '6000734'), ('pincode', '000000'),
                             ('location', '123'), ('location', 'Area 123')]:
            response = self.client.post('/post-job/', self.data(**{field: value}))
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.context['job_errors'])
        self.assertFalse(Job.objects.exists())
        response = self.client.post('/post-job/', self.data(location='சென்னை', skills='Python, SQL'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Job.objects.get().skills, 'Python, SQL')
