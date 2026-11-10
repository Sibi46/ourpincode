from django.test import TestCase
from .account import DashboardSeekerForm
from .models import CompanyProfile, Conversation, Job, Message, User
from vouchers.forms import BusinessRegistrationForm
from vouchers.models import Business


class NovemberReportTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user('report-reader', user_type='company')
        self.other = User.objects.create_user('ravi', first_name='Ravi', last_name='Kumar', user_type='company')
        self.stranger = User.objects.create_user('outsider')
        CompanyProfile.objects.create(user=self.other, company_name='Lotus Store')
        self.job = Job.objects.create(posted_by=self.other, title='Delivery Assistant')
        self.conv = Conversation.objects.create(user_a=self.me, user_b=self.other, job=self.job)
        Message.objects.create(conversation=self.conv, sender=self.other, receiver=self.me, content='Interview on Tuesday')
        Message.objects.create(conversation=self.conv, sender=self.me, receiver=self.other, content='Thank you')
        private = Conversation.objects.create(user_a=self.other, user_b=self.stranger)
        Message.objects.create(conversation=private, sender=self.stranger, receiver=self.other, content='Private Tuesday conversation')
        self.client.force_login(self.me, backend='django.contrib.auth.backends.ModelBackend')

    def test_search_matches_names_business_jobs_and_older_messages_without_leaking_private_threads(self):
        for query in ('Ravi Kumar', 'lotus', 'delivery', 'Tuesday', '  ravi  '):
            with self.subTest(query=query):
                response = self.client.get('/messages/', {'q': query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([r['conv'].pk for r in response.context['conversations']], [self.conv.pk])

    def test_live_search_response_and_no_results(self):
        response = self.client.get('/messages/', {'q': 'Tuesday'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.json()['count'], 1)
        self.assertNotIn('Private Tuesday', response.json()['html'])
        response = self.client.get('/messages/', {'q': 'unknown phrase'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.json()['count'], 0)
        self.assertIn('No matching conversations', response.json()['html'])

    def test_any_category_shows_and_accepts_both_job_types(self):
        for kind in ('driver', 'engineer'):
            form = DashboardSeekerForm({'job_category': 'any', 'blue_collar_type': kind})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data['blue_collar_type'], kind)
            self.assertIn(kind, dict(form.fields['blue_collar_type'].widget.choices))
        form = DashboardSeekerForm({'job_category': 'any', 'blue_collar_type': 'invented'})
        self.assertFalse(form.is_valid())

    def test_voucher_text_validation_reports_each_field_and_prevents_saving(self):
        data = {'business_name': 'Local Shop', 'owner_name': 'Owner 123', 'city': 'City 123',
                'state': 'State 123', 'mobile': '9876543210', 'email': 'owner@example.test',
                'address': 'Market Road', 'pincode': '600073'}
        form = BusinessRegistrationForm(data)
        self.assertFalse(form.is_valid())
        for field in ('owner_name', 'city', 'state'):
            self.assertIn(field, form.errors)
        response = self.client.post('/vouchers/business/register/', data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Use letters and spaces only.')
        self.assertFalse(Business.objects.exists())
        data.update(owner_name='Ravi Kumar', city='Chennai', state='Tamil Nadu')
        self.assertTrue(BusinessRegistrationForm(data).is_valid())
