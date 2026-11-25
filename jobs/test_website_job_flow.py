from django.test import TestCase
from .account import BusinessDetailsForm,business_profile_progress
from .models import User,CompanyProfile,Job


class BusinessWebsiteJobFlowTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user('website-job-owner',user_type='company',pincode='600073')
        self.company=CompanyProfile.objects.create(user=self.owner,company_name='Test Store',
            industry='Retail',company_size='Small',website='https://example.com')
        self.client.force_login(self.owner)
        self.job_data={'title':'Software Engineer','industry':'IT & Technology',
            'description':'Build useful services.','pincode':'600073','location':'Chennai',
            'vacancies':'1','salary_min':'15000','salary_max':'25000'}

    def test_blank_website_saves_and_does_not_block_job_posting(self):
        score=business_profile_progress(self.owner,self.company)
        response=self.client.post('/employer/dashboard/',{
            'profile_section':'business-profile','company_name':'Test Store',
            'industry':'Retail','company_size':'Small','website':''})
        self.assertEqual(response.status_code,302)
        self.company.refresh_from_db()
        self.assertEqual(self.company.website,'')
        self.assertEqual(score,business_profile_progress(self.owner,self.company))
        self.assertFalse(BusinessDetailsForm(instance=self.company).fields['website'].required)
        dashboard=self.client.get('/employer/dashboard/')
        self.assertFalse(dashboard.context['profile_incomplete'])
        self.assertEqual(self.client.get('/post-job/').status_code,200)
        self.assertEqual(self.client.post('/post-job/',self.job_data).status_code,302)
        job=Job.objects.get()
        self.assertFalse(job.is_approved)
        self.assertEqual(job.posted_by,self.owner)

    def test_new_business_does_not_need_a_website(self):
        self.company.website='';self.company.save()
        self.assertEqual(self.client.post('/post-job/',self.job_data).status_code,302)

    def test_bad_numbers_and_salary_ranges_are_reported_without_creating_jobs(self):
        cases=[('salary_min','abc'),('salary_min','-1'),('salary_min','15000.5'),
               ('salary_max','10000'),('vacancies','0'),('vacancies','-1'),
               ('vacancies','1.5'),('vacancies','10000')]
        for field,value in cases:
            response=self.client.post('/post-job/',{**self.job_data,field:value})
            self.assertEqual(response.status_code,400,(field,value))
            self.assertIn(field,response.context['job_errors'])
            self.assertEqual(response.context['posted_data']['industry'],'IT & Technology')
        self.assertFalse(Job.objects.exists())

    def test_zero_salary_and_valid_vacancies_are_preserved(self):
        response=self.client.post('/post-job/',{**self.job_data,'salary_min':'0','salary_max':'0','vacancies':'2'})
        self.assertEqual(response.status_code,302)
        job=Job.objects.get()
        self.assertEqual((job.salary_min,job.salary_max,job.vacancies),(0,0,2))

    def test_draft_flow_still_creates_a_draft(self):
        response=self.client.post('/post-job/',{**self.job_data,'action':'draft'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Job.objects.get().status,'draft')
