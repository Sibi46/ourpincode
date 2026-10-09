from datetime import time
from django.test import TestCase
from django.urls import reverse
from . import models as m, tests as fixtures


class AcademyRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def data(self):
        return dict(kind='academy',name='New academy',description='Music',experience=1,min_age=5,max_age=90,mode='offline',pincode='123456',phone='9876543210',opening_days=['0','2'],opening_time='09:00',closing_time='18:00')

    def test_registration_saves_hours_and_branch_parent(self):
        self.client.force_login(self.owner)
        self.teacher.kind='academy';self.teacher.save()
        response=self.client.post(reverse('tuition:branch_create',args=[self.teacher.uid]),self.data())
        self.assertEqual(response.status_code,302)
        branch=self.teacher.branches.get()
        self.assertEqual(branch.owner,self.owner)
        self.assertEqual(branch.status,'pending')
        self.assertEqual(list(branch.availability.order_by('weekday').values_list('weekday','start','end')),[(0,time(9),time(18)),(2,time(9),time(18))])
        url=reverse('tuition:profile',args=[self.teacher.slug])
        self.assertNotContains(self.client.get(url),reverse('tuition:profile',args=[branch.slug]))
        branch.status='approved';branch.save()
        self.assertContains(self.client.get(url),reverse('tuition:profile',args=[branch.slug]))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('tuition:branch_create',args=[self.teacher.uid])).status_code,403)

    def test_bad_timings_rejected(self):
        self.client.force_login(self.owner)
        for changes in ({'opening_days':[]},{'closing_time':'08:00'}):
            response=self.client.post(reverse('tuition:register'),{**self.data(),**changes})
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['form'].errors)
        self.assertFalse(m.TeacherProfile.objects.filter(name='New academy').exists())

    def test_application_uses_student_name_without_selector(self):
        self.client.force_login(self.other)
        response=self.client.get(reverse('tuition:apply',args=[self.lesson.uid]))
        self.assertContains(response, 'Student name')
        self.assertNotContains(response, 'name="learner"')
        self.assertNotContains(response, reverse('tuition:learner_create'))

    def test_unused_student_delete_and_linked_records_protection(self):
        student=m.Learner.objects.create(created_by=self.parent,name='Unused',age=10,pincode='123456')
        m.GuardianLink.objects.create(user=self.parent,learner=student,relationship='Parent',attestation='Parent')
        url=reverse('tuition:student_delete',args=[student.uid])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{'confirm':'on'}).status_code,404)
        self.client.force_login(self.parent)
        self.client.get(url)
        self.assertTrue(m.Learner.objects.filter(pk=student.pk).exists())
        self.assertEqual(self.client.post(url,{'confirm':'on'}).status_code,302)
        self.assertFalse(m.Learner.objects.filter(pk=student.pk).exists())
        response=self.client.post(reverse('tuition:student_delete',args=[self.child.uid]),{'confirm':'on'})
        self.assertContains(response,'linked student records exist')
        self.assertTrue(m.Learner.objects.filter(pk=self.child.pk).exists())
