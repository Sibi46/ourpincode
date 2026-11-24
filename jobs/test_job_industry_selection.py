from django.test import TestCase
from .models import User, CompanyProfile, Industry, Job
from .job_post_validation import JobPostingValidationForm


class IndustrySelectionTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user('industry-owner',user_type='company',pincode='600073',city='Chennai',address='Test Street')
        CompanyProfile.objects.create(user=self.owner,company_name='Test Company',industry='Retail',company_size='Small')
        self.client.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')

    def test_numeric_mixed_numeric_and_unknown_industries_cannot_create_job(self):
        for industry in ['12345','IT123','Unknown invented industry','IT & Technology,123','１２３']:
            response=self.client.post('/post-job/',{'title':'Engineer','industry':industry})
            self.assertEqual(response.status_code,400)
            self.assertIn('industry',response.context['job_errors'])
        self.assertFalse(Job.objects.exists())

    def test_available_fallback_industry_saves_canonical_selection(self):
        response=self.client.post('/post-job/',{'title':'Engineer','industry':'it & technology'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Job.objects.get().industry,'IT & Technology')

    def test_admin_options_replace_fallback_and_inactive_choices_are_rejected(self):
        Industry.objects.create(name='Technology')
        Industry.objects.create(name='Inactive Industry',is_active=False)
        for value in ['IT & Technology','Inactive Industry','123']:
            self.assertFalse(JobPostingValidationForm({'title':'Engineer','industry':value}).is_valid())
        form=JobPostingValidationForm({'title':'Engineer','industry':'Technology'})
        self.assertTrue(form.is_valid(),form.errors)

    def test_selection_limit(self):
        for name in ['Healthcare','Education','Retail','Technology']:
            Industry.objects.create(name=name)
        form=JobPostingValidationForm({'title':'Engineer','industry':'Healthcare, Education, Retail, Technology'})
        self.assertFalse(form.is_valid())
        self.assertIn('industry',form.errors)

    def test_edit_cannot_bypass_validation_or_change_existing_job(self):
        job=Job.objects.create(posted_by=self.owner,title='Engineer',industry='IT & Technology')
        response=self.client.post(f'/jobs/{job.pk}/edit/',{'industry':'12345','title':'Changed title'})
        self.assertEqual(response.status_code,400)
        self.assertContains(response,'Select up to three valid industries',status_code=400)
        job.refresh_from_db()
        self.assertEqual(job.title,'Engineer')
        self.assertEqual(job.industry,'IT & Technology')

    def test_edit_accepts_valid_selection(self):
        job=Job.objects.create(posted_by=self.owner,title='Engineer',industry='IT & Technology')
        response=self.client.post(f'/jobs/{job.pk}/edit/',{'industry':'Construction'})
        self.assertEqual(response.status_code,302)
        job.refresh_from_db()
        self.assertEqual(job.industry,'Construction')
