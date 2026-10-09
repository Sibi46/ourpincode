from datetime import timedelta, time
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from . import models as m, forms, tests as fixtures


class ProfileManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.owner)

    def test_staff_owned_by_academy_private_phone_and_visibility(self):
        self.teacher.kind = 'academy'; self.teacher.save()
        url = reverse('tuition:staff_create', args=[self.teacher.uid])
        response = self.client.post(url, {'name':'English teacher', 'phone':'9876543210', 'new_subjects':['English','Tamil'], 'public':'on'})
        self.assertEqual(response.status_code,302)
        person = self.teacher.staff.get()
        self.assertEqual(set(person.subjects.values_list('name',flat=True)), {'English','Tamil'})
        self.client.logout()
        response = self.client.get(reverse('tuition:profile',args=[self.teacher.slug]))
        self.assertContains(response, 'English teacher')
        self.assertNotContains(response, '9876543210')
        person.public=False; person.save()
        self.assertNotContains(self.client.get(reverse('tuition:profile',args=[self.teacher.slug])), 'English teacher')
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('tuition:staff_edit',args=[person.uid]),{}).status_code,403)
        self.assertEqual(self.client.get(reverse('tuition:academy_staff',args=[self.teacher.uid])).status_code,403)

    def test_independent_teacher_cannot_create_academy_staff(self):
        self.assertEqual(self.client.get(reverse('tuition:staff_create',args=[self.teacher.uid])).status_code,403)

    def test_unused_group_delete_requires_confirmation_and_owner(self):
        group = m.Batch.objects.create(lesson=self.lesson,name='Unused',mode='offline')
        url = reverse('tuition:delete_unused',args=['group',group.uid])
        self.client.get(url)
        self.assertTrue(m.Batch.objects.filter(pk=group.pk).exists())
        self.client.post(url,{})
        self.assertTrue(m.Batch.objects.filter(pk=group.pk).exists())
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{'confirm':'on'}).status_code,403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url,{'confirm':'on'}).status_code,302)
        self.assertFalse(m.Batch.objects.filter(pk=group.pk).exists())

    def test_linked_group_and_teacher_cannot_be_deleted(self):
        today=timezone.localdate()
        m.ScheduleRule.objects.create(batch=self.batch,weekday=0,start_time=time(10),start_date=today,end_date=today+timedelta(days=30))
        for kind,obj in [('group',self.batch)]:
            response=self.client.post(reverse('tuition:delete_unused',args=[kind,obj.uid]),{'confirm':'on'})
            self.assertContains(response,'linked records exist')
            self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_public_class_days_and_moderation(self):
        today=timezone.localdate()
        for day in (0,2):
            m.ScheduleRule.objects.create(batch=self.batch,weekday=day,start_time=time(10),start_date=today,end_date=today+timedelta(days=30))
        asset=m.MediaAsset.objects.create(teacher=self.teacher,uploader=self.owner,storage_key='test-banner',mime='image/jpeg',size=1,checksum='x',public_requested=True,subjects_complete=True)
        self.teacher.banner_image=asset;self.teacher.save()
        url=reverse('tuition:profile',args=[self.teacher.slug])
        response=self.client.get(url)
        self.assertContains(response,'2 days per week')
        self.assertNotContains(response,reverse('tuition:file',args=[asset.uid]))
        asset.moderation='approved';asset.save()
        self.assertContains(self.client.get(url),reverse('tuition:file',args=[asset.uid]))

    def test_five_slots_blank_extras_and_repeated_subject_inputs(self):
        form=forms.GroupCreateForm()
        self.assertEqual(str(form['day_start_0']).count('type="time"'),5)
        from .test_groups import GroupWorkflowTests
        fixture=GroupWorkflowTests();fixture.owner=self.owner;fixture.teacher=self.teacher;fixture.client=self.client;fixture.setUp()
        day=fixture.date.weekday()
        data={**fixture.data,'new_subjects':['English','Tamil'],f'day_start_{day}':['10:00','','12:00','','']}
        self.assertEqual(self.client.post(fixture.url,data).status_code,302)
        batch=m.Batch.objects.get(name='Evening group')
        self.assertEqual(batch.rules.count(),2)
        self.assertEqual(set(batch.lesson.subjects.values_list('name',flat=True)), {'English','Tamil'})

    def test_profile_and_group_controls(self):
        response=self.client.get(reverse('tuition:teacher',args=[self.teacher.uid]))
        self.assertContains(response,reverse('tuition:activity_upload',args=['teacher',self.teacher.uid]))
        self.assertNotContains(response,'<th>Start</th>')
        response=self.client.get(reverse('tuition:teacher_edit',args=[self.teacher.uid]))
        self.assertContains(response,'name="profile_photo"')
        self.assertContains(response,'name="banner_photo"')
        self.assertContains(response,'data-add-subject')
