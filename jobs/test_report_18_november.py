from django.test import TestCase
from django.urls import reverse
from jobs.models import User, CompanyProfile, UserNotification
from jobs.account import BusinessDetailsForm
from tuition.models import TeacherProfile
from tuition.forms import TeacherForm


class November18ReportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='nov18', user_type='company', pincode='600100')
        self.admin = User.objects.create_user(username='nov18admin', admin_role='super_admin')
        self.client.force_login(self.owner, backend='django.contrib.auth.backends.ModelBackend')

    def teacher_data(self, **changes):
        return dict(kind='teacher', name='Mary Jane', description='Teaching locally', experience='2', min_age='5', max_age='18', mode='offline', pincode='600100', phone='9000000000', **changes)

    def test_business_can_save_and_clear_website(self):
        company = CompanyProfile.objects.create(user=self.owner, company_name='Local Store', website='https://example.com')
        form = BusinessDetailsForm(instance=company)
        self.assertFalse(form.fields['website'].required)
        response = self.client.post('/employer/dashboard/', {'profile_section':'business-profile', 'company_name':'Local Store', 'industry':'Retail', 'website':''})
        self.assertEqual(response.status_code,302)
        company.refresh_from_db(); self.assertEqual(company.website,'')
        self.assertContains(self.client.get('/employer/dashboard/'), 'Website (optional)')

    def test_teacher_and_academy_names_reject_numbers(self):
        for kind in ['teacher','academy']:
            data=self.teacher_data(); data.update(kind=kind,name='School123')
            form=TeacherForm(data)
            self.assertFalse(form.is_valid())
            self.assertIn('name',form.errors)
        data=self.teacher_data(); data['name']='தமிழ் அரசு'
        form=TeacherForm(data); self.assertTrue(form.is_valid(),form.errors)

    def test_new_profile_pending_message_admin_notification_and_review(self):
        response=self.client.post('/tuition/register/',self.teacher_data())
        self.assertEqual(response.status_code,302)
        teacher=TeacherProfile.objects.get(owner=self.owner)
        self.assertEqual(teacher.status,'pending')
        detail=self.client.get(response.url)
        self.assertContains(detail,'Waiting for admin approval.')
        self.assertTrue(UserNotification.objects.filter(user=self.admin,title__contains='Tuition approval requested').exists())
        self.assertEqual(self.client.get(reverse('tuition:review')).status_code,403)
        self.client.force_login(self.admin, backend='django.contrib.auth.backends.ModelBackend')
        queue=self.client.get(reverse('tuition:review'))
        self.assertContains(queue,teacher.name)
        self.assertEqual(queue.context['pending_teacher_count'],1)
        self.client.post(reverse('tuition:review'), {'kind':'teacher','uid':str(teacher.uid),'status':'approved'})
        teacher.refresh_from_db();self.assertEqual(teacher.status,'approved')
        self.client.force_login(self.owner, backend='django.contrib.auth.backends.ModelBackend')
        self.assertNotContains(self.client.get(response.url),'Waiting for admin approval.')

    def test_pending_profiles_sorted_before_recent_approved_profiles(self):
        pending=TeacherProfile.objects.create(owner=self.owner,name='Pending Teacher',status='pending')
        TeacherProfile.objects.create(owner=self.owner,name='Approved Teacher',status='approved')
        self.client.force_login(self.admin, backend='django.contrib.auth.backends.ModelBackend')
        response=self.client.get(reverse('tuition:review'))
        self.assertEqual(response.context['review_teachers'][0],pending)
