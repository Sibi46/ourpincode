from datetime import time, timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from . import models as m, activities as a, tests as fixtures


class SimplifiedFormsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.owner)

    def data(self):
        return dict(kind=self.teacher.kind,name=self.teacher.name,description=self.teacher.description,experience=0,min_age=0,max_age=100,mode=self.teacher.mode,address='',pincode=self.teacher.pincode,phone=self.teacher.phone,email='',new_subjects='',service_pins='',publish_brand_images='on')

    def test_brand_images_publish_and_photo_only_keeps_teacher_approval(self):
        asset=m.MediaAsset.objects.create(teacher=self.teacher,uploader=self.owner,storage_key='brand.jpg',mime='image/jpeg',size=1,checksum='x')
        self.teacher.profile_image=asset;self.teacher.banner_image=asset;self.teacher.public_fees=True;self.teacher.save()
        url=reverse('tuition:teacher_edit',args=[self.teacher.uid])
        response=self.client.get(url)
        self.assertNotContains(response,'Or select existing subjects')
        self.assertNotContains(response,'Show lesson fees on my public profile')
        response=self.client.post(url,self.data())
        self.assertEqual(response.status_code,302)
        asset.refresh_from_db();self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.status,'approved')
        self.assertTrue(self.teacher.public_fees)
        self.assertTrue(a.public_allowed(asset))
        self.assertContains(self.client.get(reverse('tuition:profile',args=[self.teacher.slug])),reverse('tuition:file',args=[asset.uid]))

    def test_teaching_changes_still_need_review(self):
        data=self.data();data['description']='Changed teaching details'
        self.assertEqual(self.client.post(reverse('tuition:teacher_edit',args=[self.teacher.uid]),data).status_code,302)
        self.teacher.refresh_from_db();self.assertEqual(self.teacher.status,'pending')

    def test_identified_students_cannot_be_published_as_branding(self):
        asset=m.MediaAsset.objects.create(teacher=self.teacher,uploader=self.owner,storage_key='student.jpg',mime='image/jpeg',size=1,checksum='x')
        m.MediaSubject.objects.create(asset=asset,learner=self.child)
        self.teacher.profile_image=asset;self.teacher.save()
        response=self.client.post(reverse('tuition:teacher_edit',args=[self.teacher.uid]),self.data())
        self.assertContains(response,'requires consent or administrator review')
        asset.refresh_from_db();self.assertEqual(asset.moderation,'pending')

    def test_group_shows_first_day_without_recurrence_end_or_history(self):
        first=timezone.localdate()
        end=first+timedelta(days=365)
        m.ScheduleRule.objects.create(batch=self.batch,weekday=0,start_time=time(22),start_date=first,end_date=end)
        response=self.client.get(reverse('tuition:batch',args=[self.batch.uid]))
        self.assertContains(response,'Monday 10.00 PM')
        self.assertNotContains(response,'<h2>Enrolments</h2>')
        self.assertNotContains(response,'No enrolments yet.')
        self.assertNotContains(response,str(end.year))
        self.assertEqual(self.batch.rules.get().end_date,end)
