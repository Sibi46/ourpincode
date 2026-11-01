from django.test import TestCase
from .models import CompanyProfile, JobSeekerProfile, User


class EmployerWorkspaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('workspace-owner', user_type='company', pincode='600073', first_name='Owner')
        self.company = CompanyProfile.objects.create(user=self.user, company_name='Existing business', logo='logos/existing.avif')
        self.seeker = JobSeekerProfile.objects.create(user=self.user, open_to_relocate=True)
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')

    def business_data(self, **changes):
        return {'profile_section': 'business-profile', 'company_name': 'Updated business', 'industry': 'Retail', 'review_reward_percent': '0', **changes}

    def test_business_save_preserves_personal_details_and_existing_logo(self):
        response = self.client.post('/employer/dashboard/', self.business_data())
        self.assertRedirects(response, '/employer/dashboard/#business-profile', fetch_redirect_response=False)
        self.company.refresh_from_db()
        self.user.refresh_from_db()
        self.seeker.refresh_from_db()
        self.assertEqual(self.company.company_name, 'Updated business')
        self.assertEqual(self.company.logo.name, 'logos/existing.avif')
        self.assertEqual(self.user.first_name, 'Owner')
        self.assertEqual(self.user.pincode, '600073')
        self.assertTrue(self.seeker.open_to_relocate)

    def test_invalid_business_submission_reopens_business_section_without_saving(self):
        response = self.client.post('/employer/dashboard/', self.business_data(business_phone='123'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context['profile_section'], 'business-profile')
        self.assertContains(response, 'unique 10-digit', status_code=400)
        self.company.refresh_from_db()
        self.assertEqual(self.company.company_name, 'Existing business')

    def test_dashboard_has_separate_forms_and_existing_logo_preview(self):
        response = self.client.get('/employer/dashboard/')
        self.assertContains(response, 'id="dashboard-business-form"')
        self.assertContains(response, 'id="dashboard-profile-form"')
        self.assertContains(response, 'class="business-logo-preview"')
        self.assertContains(response, 'logos/existing.avif')
        self.assertContains(response, 'aria-label="Dashboard sections"')
