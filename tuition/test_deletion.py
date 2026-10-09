import io
from unittest.mock import patch
from django.test import TestCase, Client
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from . import models as m, services as svc, tests as fixtures
from .deletion import delete_teacher, retry_file_deletions


class TeacherDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.owner)
        self.url=reverse('tuition:delete_unused',args=['teacher',self.teacher.uid])
        self.confirm={'confirm':'on','profile_name':self.teacher.name,'password':'test'}

    def test_get_and_invalid_confirmation_preserve_records(self):
        self.assertContains(self.client.get(self.url),'Records to remove')
        for data in ({'confirm':'on'}, {**self.confirm,'password':'wrong'}, {**self.confirm,'profile_name':'wrong'}):
            self.assertEqual(self.client.post(self.url,data).status_code,200)
            self.assertTrue(m.TeacherProfile.objects.filter(pk=self.teacher.pk).exists())
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url,self.confirm).status_code,403)
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post(self.url,self.confirm).status_code,403)

    def test_linked_delete_preserves_students_other_profiles_and_branches(self):
        enrolment=svc.decide(self.owner,self.application,'accepted')
        svc.transfer(self.owner,enrolment,self.batch)
        today=self.lesson.start_date
        agreement=m.FeeAgreement.objects.create(enrolment=enrolment,start_date=today,amount=100)
        invoice=m.Invoice.objects.create(agreement=agreement,period_start=today,period_end=today,due_date=today,amount=100)
        payment=m.Payment.objects.create(invoice=invoice,amount=100,method='cash',recorded_by=self.owner)
        m.Payment.objects.create(invoice=invoice,amount=100,method='cash',recorded_by=self.owner,reverses=payment)
        branch=m.TeacherProfile.objects.create(owner=self.owner,kind='academy',parent_academy=self.teacher,name='Branch',pincode='123456',phone='9000000000')
        other=m.TeacherProfile.objects.create(owner=self.other,kind='teacher',name='Other',pincode='123456',phone='9000000000')
        m.MediaAsset.objects.create(teacher=self.teacher,uploader=self.owner,storage_key='delete-photo.jpg',mime='image/jpeg',size=1,checksum='x')
        with patch('tuition.deletion.storage') as store, self.captureOnCommitCallbacks(execute=True):
            response=self.client.post(self.url,self.confirm)
            self.assertEqual(response.status_code,302)
        store.return_value.delete.assert_called_once_with('delete-photo.jpg')
        self.assertFalse(m.TeacherProfile.objects.filter(pk=self.teacher.pk).exists())
        self.assertFalse(m.Payment.objects.filter(pk=payment.pk).exists())
        self.assertTrue(m.Learner.objects.filter(pk=self.child.pk).exists())
        self.assertTrue(m.GuardianLink.objects.filter(pk=self.guardian.pk).exists())
        self.assertTrue(m.TeacherProfile.objects.filter(pk=other.pk).exists())
        branch.refresh_from_db();self.assertIsNone(branch.parent_academy_id)

    def test_cleanup_failure_is_retryable(self):
        task=m.PendingFileDeletion.objects.create(storage_key='retry.jpg')
        with patch('tuition.deletion.storage') as store:
            store.return_value.delete.side_effect=OSError('unavailable')
            retry_file_deletions()
        task.refresh_from_db();self.assertEqual(task.attempts,1)
        with patch('tuition.deletion.storage') as store:
            retry_file_deletions()
        self.assertFalse(m.PendingFileDeletion.objects.filter(pk=task.pk).exists())

    def test_cross_profile_media_blocks_everything(self):
        asset=m.MediaAsset.objects.create(teacher=self.teacher,uploader=self.owner,storage_key='shared.jpg',mime='image/jpeg',size=1,checksum='x')
        m.TeacherProfile.objects.create(owner=self.other,kind='teacher',name='Other',pincode='123456',phone='9000000000',profile_image=asset)
        response=self.client.post(self.url,self.confirm)
        self.assertContains(response,'referenced by another profile')
        self.assertTrue(m.Application.objects.filter(pk=self.application.pk).exists())
        self.assertFalse(m.PendingFileDeletion.objects.exists())

    def test_unexpected_protected_link_rolls_back(self):
        foreign=m.TeacherProfile.objects.create(owner=self.other,kind='teacher',name='Other',pincode='123456',phone='9000000000')
        m.Application.objects.create(teacher=foreign,lesson=self.lesson,name='External',age=10,mobile='9000000000',email='x@example.com',pincode='123456',mode='online')
        response=self.client.post(self.url,self.confirm)
        self.assertContains(response,'Nothing was deleted')
        self.assertTrue(m.Application.objects.filter(pk=self.application.pk).exists())
        self.assertTrue(m.Lesson.objects.filter(pk=self.lesson.pk).exists())


class UploadErrorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_no_students_help_and_storage_error(self):
        self.client.force_login(self.owner)
        url=reverse('tuition:activity_upload',args=['teacher',self.teacher.uid])
        response=self.client.get(url)
        self.assertContains(response,'Students visible in this photo / video')
        self.assertContains(response,'No enrolled students')
        buffer=io.BytesIO();Image.new('RGB',(2,2)).save(buffer,format='PNG')
        with patch('tuition.activity_storage.storage') as store:
            store.return_value.save.side_effect=OSError('unavailable')
            response=self.client.post(url,{'title':'Example','students_confirmed':'on','file':SimpleUploadedFile('test.png',buffer.getvalue(),'image/png')})
        self.assertContains(response,'Upload storage is unavailable')
        self.assertEqual(m.MediaAsset.objects.count(),0)


class ActivityDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from . import test_activities as fixtures
        fixtures.ActivityTests.setUpTestData.__func__(cls)

    def test_activity_and_attendance_history_removed_with_shared_child_preserved(self):
        from datetime import timedelta
        from django.utils import timezone
        from . import test_activities as fixtures, activities as a
        now=timezone.now()
        event=fixtures.ActivityTests.event(self)
        person=a.register_event(self.parent,event,self.enrolment,consent=True)
        result=m.EventResult.objects.create(participation=person,award='winner',title='Winner')
        programme=m.ProgrammeItem.objects.create(event=event,title='Music',start=event.start,end=event.end,venue='Hall')
        programme.participants.add(person)
        achievement=a.save_achievement(self.owner,m.Achievement(teacher=self.teacher,enrolment=self.enrolment,result=result,kind='certificate',title='Award'))
        assignment=m.Assignment.objects.create(lesson=self.lesson,title='Practice',instructions='Practice',due_at=now)
        submission=m.Submission.objects.create(assignment=assignment,enrolment=self.enrolment)
        svc.transfer(self.owner,self.enrolment,self.batch)
        session=svc.save_session(self.owner,m.ClassSession(batch=self.batch,start=now-timedelta(minutes=10),end=now+timedelta(minutes=50),mode='online',meeting_url='https://meet.google.com/abc-defg-hij'))
        roster=session.participants.get()
        svc.mark_attendance(self.owner,roster,'present','')
        svc.mark_attendance(self.owner,roster,'absent','Correction')
        for index,parent in enumerate([{'event':event},{'achievement':achievement},{'submission':submission}]):
            asset=m.MediaAsset.objects.create(**parent,uploader=self.owner,storage_key=f'activity-{index}.jpg',mime='image/jpeg',size=1,checksum='x')
            m.MediaSubject.objects.create(asset=asset,learner=self.child)
        with patch('tuition.deletion.storage') as store, self.captureOnCommitCallbacks(execute=True):
            delete_teacher(self.owner,self.teacher,self.teacher.name,'test',True)
        self.assertEqual(store.return_value.delete.call_count,3)
        for model in [m.MediaAsset,m.PointEntry,m.Achievement,m.EventParticipation,m.EventResult,m.ProgrammeItem,m.Submission,m.Attendance,m.ClassSession]:
            self.assertEqual(model.objects.count(),0)
        self.assertTrue(m.Learner.objects.filter(pk=self.child.pk).exists())
