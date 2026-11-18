from datetime import time
from django.test import TestCase
from django.urls import reverse
from jobs.models import User
from tuition.models import TeacherProfile
from tuition.forms import TeacherForm


class TeachingHoursReportTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user(username='hours-owner')
        self.client.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')

    def data(self, **changes):
        data=dict(kind='teacher',name='Mary Jane',description='Local teaching',experience='2',min_age='5',max_age='18',mode='offline',pincode='600100',phone='9000000000')
        data.update(changes);return data

    def test_teacher_registration_saves_hours_and_shows_them_to_students_after_approval(self):
        response=self.client.post(reverse('tuition:register'),self.data(opening_days=['0','2'],opening_time='09:00',closing_time='12:30'))
        self.assertEqual(response.status_code,302)
        teacher=TeacherProfile.objects.get(owner=self.owner)
        self.assertEqual(list(teacher.availability.order_by('weekday').values_list('weekday','start','end')),[(0,time(9),time(12,30)),(2,time(9),time(12,30))])
        self.assertEqual(teacher.status,'pending')
        self.assertContains(self.client.get(response.url),'Add the days and times you are available')
        teacher.status='approved';teacher.save()
        public=self.client.get(reverse('tuition:profile',args=[teacher.slug]))
        self.assertContains(public,'Monday');self.assertContains(public,'Wednesday');self.assertContains(public,'12:30 PM')

    def test_teacher_hours_optional_but_partial_or_invalid_hours_rejected(self):
        self.assertTrue(TeacherForm(self.data()).is_valid())
        for change in [{'opening_days':['0']},{'opening_time':'09:00'},{'opening_days':['0'],'opening_time':'12:00','closing_time':'09:00'}]:
            form=TeacherForm(self.data(**change));self.assertFalse(form.is_valid())
        form=TeacherForm(self.data(kind='academy'));self.assertFalse(form.is_valid())

    def test_existing_teacher_can_add_availability_but_other_user_cannot(self):
        teacher=TeacherProfile.objects.create(owner=self.owner,name='Existing Teacher',status='pending')
        url=reverse('tuition:availability',args=[teacher.uid])
        response=self.client.post(url,{'weekday':'1','start':'15:00','end':'18:00'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(teacher.availability.get().start,time(15))
        other=User.objects.create_user(username='hours-other');self.client.force_login(other,backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(self.client.post(url,{'weekday':'2','start':'15:00','end':'18:00'}).status_code,403)
