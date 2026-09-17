import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import User, Job, JobSeekerProfile, JobApplication


@override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
                   CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ApplicationFlowTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = User.objects.create_user('candidate', user_type='employee')
        employer = User.objects.create_user('employer', user_type='company')
        self.job = Job.objects.create(title='Example', posted_by=employer,
                                      status='active', is_approved=True, job_plan='free')
        self.profile = JobSeekerProfile.objects.create(user=self.user, experience='Fresher',
                                                      job_category='blue', blue_collar_type='driver')
        self.url = f'/jobs/{self.job.pk}/apply/'
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')

    def test_apply_asks_for_work_type_and_resume(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="job_category" value="blue"')
        self.assertContains(response, 'name="job_category" value="white"')
        self.assertContains(response, 'name="application_resume"')

    def test_blue_collar_can_apply_without_resume_or_education(self):
        self.client.post(self.url, {'quick_apply': '1', 'job_category': 'blue'})
        self.assertEqual(JobApplication.objects.count(), 1)

    def test_white_collar_missing_fields_block_post(self):
        response = self.client.post(self.url, {'quick_apply': '1', 'job_category': 'white'})
        self.assertIn('/profile/edit/', response.url)
        self.assertFalse(JobApplication.objects.exists())
        response = self.client.get(response.url)
        self.assertIn('qualification', response.context['application_missing'])
        self.assertIn('primary_skill', response.context['application_missing'])
        self.assertIn('resume', response.context['application_missing'])

    def test_white_collar_can_upload_resume_and_apply(self):
        self.profile.education = 'Graduate'
        self.profile.primary_skill = 'Sales'
        self.profile.save()
        response = self.client.post(self.url, {
            'quick_apply': '1', 'job_category': 'white',
            'application_resume': SimpleUploadedFile('cv.pdf', b'%PDF-1.4\nexample'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(JobApplication.objects.get().application_resume)

    def test_missing_work_type_and_invalid_resume_are_rejected(self):
        self.client.post(self.url, {'quick_apply': '1'})
        self.assertFalse(JobApplication.objects.exists())
        self.client.post(self.url, {'job_category': 'blue',
                                   'application_resume': SimpleUploadedFile('bad.html', b'<script>')})
        self.assertFalse(JobApplication.objects.exists())

    def test_profile_post_stays_on_missing_fields(self):
        response = self.client.post('/profile/edit/?next=' + self.url, {
            'next': self.url, 'job_category': 'blue', 'experience': '', 'blue_collar_type': '',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('experience', response.context['application_missing'])
        self.assertIn('blue_collar_type', response.context['application_missing'])

    def test_anonymous_registration_pincode_lookup_is_public(self):
        self.client.logout()
        with patch('urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = json.dumps([{'Status': 'Success', 'PostOffice': [
                {'Name': 'Area', 'District': 'District', 'State': 'State'},
            ]}]).encode()
            response = self.client.get('/api/pincode/600073/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
