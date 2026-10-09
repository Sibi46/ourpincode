from datetime import time, timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from jobs.models import UserNotification
from . import models as m, forms, tests as fixtures


class ParentNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def data(self):
        return dict(name='New student',age=17,mobile='',email='parent@example.com',pincode='123456',preferred_days='Monday',preferred_timings='Morning',mode='online')

    def test_minor_requires_parent_and_saves_contact(self):
        url=reverse('tuition:apply',args=[self.lesson.uid])
        response=self.client.post(url,self.data())
        self.assertContains(response,'Required for students under 18.')
        self.assertFalse(m.Application.objects.filter(name='New student').exists())
        response=self.client.post(url,{**self.data(),'parent_name':'Parent','parent_phone':'9876543210'})
        self.assertEqual(response.status_code,302)
        obj=m.Application.objects.get(name='New student')
        self.assertEqual(obj.parent_name,'Parent');self.assertEqual(obj.mobile,'9876543210')
        self.assertIsNone(obj.learner_id)

    def test_adult_and_invalid_parent_phone(self):
        form=forms.ApplicationForm({**self.data(),'parent_name':'Parent','parent_phone':'bad'})
        self.assertFalse(form.is_valid());self.assertIn('parent_phone',form.errors)
        response=self.client.post(reverse('tuition:apply',args=[self.lesson.uid]),{**self.data(),'age':18,'mobile':'9876543210'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(m.Application.objects.get(name='New student').parent_name,'')

    def test_notifications_paginate_and_are_private(self):
        self.client.force_login(self.owner)
        own=[UserNotification.objects.create(user=self.owner,title=f'Tuition {i}',message='Update',link='/tuition/learn/') for i in range(31)]
        other=UserNotification.objects.create(user=self.other,title='Other private',message='Secret',link='/tuition/learn/')
        UserNotification.objects.create(user=self.owner,title='Unrelated',message='Other',link='/jobs/')
        url=reverse('tuition:notifications')
        response=self.client.get(url)
        self.assertEqual(response.context['notification_page'].paginator.count,31)
        self.assertNotContains(response,'Other private');self.assertNotContains(response,'Unrelated')
        self.assertEqual(len(self.client.get(url+'?page=2').context['notification_page']),1)
        self.assertEqual(self.client.post(reverse('tuition:notification_read',args=[other.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('tuition:notification_read',args=[own[0].pk])).status_code,302)
        own[0].refresh_from_db();self.assertTrue(own[0].is_read)

    def test_public_slots_are_combined_by_day(self):
        today=timezone.localdate()
        for hour in (7,12):
            m.ScheduleRule.objects.create(batch=self.batch,weekday=0,start_time=time(hour),start_date=today,end_date=today+timedelta(days=30))
        response=self.client.get(reverse('tuition:profile',args=[self.teacher.slug]))
        self.assertContains(response,'7:00 AM, 12:00 PM')

    def test_existing_gallery_images_can_be_assigned_but_not_foreign_images(self):
        self.client.force_login(self.owner)
        asset=m.MediaAsset.objects.create(teacher=self.teacher,uploader=self.owner,title='Logo',storage_key='logo.jpg',mime='image/jpeg',size=1,checksum='x')
        from .test_simplified_forms import SimplifiedFormsTests
        data=SimplifiedFormsTests.data(self)
        data.update(existing_profile_image=asset.pk,existing_banner_image=asset.pk)
        response=self.client.post(reverse('tuition:teacher_edit',args=[self.teacher.uid]),data)
        self.assertEqual(response.status_code,302)
        self.teacher.refresh_from_db();self.assertEqual(self.teacher.profile_image_id,asset.pk)
        response=self.client.get(reverse('tuition:profile',args=[self.teacher.slug]))
        self.assertContains(response,'class="profile-banner"')
        other=m.TeacherProfile.objects.create(owner=self.other,kind='teacher',name='Other',pincode='123456',phone='9000000000')
        foreign=m.MediaAsset.objects.create(teacher=other,uploader=self.other,storage_key='other.jpg',mime='image/jpeg',size=1,checksum='x')
        response=self.client.post(reverse('tuition:teacher_edit',args=[self.teacher.uid]),{**data,'existing_profile_image':foreign.pk})
        self.assertEqual(response.status_code,200)
        self.assertIn('existing_profile_image',response.context['form'].errors)
