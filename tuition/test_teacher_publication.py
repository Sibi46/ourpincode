import io
from unittest.mock import patch
from PIL import Image
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from . import models as m, activities as a, services as svc, tests as fixtures


class TeacherPublicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.owner)

    def photo(self):
        data=io.BytesIO();Image.new('RGB',(2,2)).save(data,format='PNG')
        return SimpleUploadedFile('photo.png',data.getvalue(),'image/png')

    def test_teacher_photo_public_without_admin_and_private_optout(self):
        url=reverse('tuition:activity_upload',args=['teacher',self.teacher.uid])
        for public in (True,False):
            with patch('tuition.activity_storage.storage') as store:
                store.return_value.save.return_value=f'photo-{public}.jpg'
                data={'title':'Photo','file':self.photo(),'students_confirmed':'on'}
                if public: data['public_requested']='on'
                self.assertEqual(self.client.post(url,data).status_code,302)
            asset=m.MediaAsset.objects.get(storage_key=f'photo-{public}.jpg')
            self.assertEqual(asset.moderation,'approved')
            self.assertEqual(a.public_allowed(asset),public)

    def test_student_consent_and_identification_still_required(self):
        svc.decide(self.owner,self.application,'accepted')
        url=reverse('tuition:activity_upload',args=['teacher',self.teacher.uid])
        with patch('tuition.activity_storage.storage') as store:
            store.return_value.save.return_value='child.jpg'
            response=self.client.post(url,{'title':'Child','file':self.photo(),'public_requested':'on','students_confirmed':'on','subjects':[self.child.pk]})
        self.assertEqual(response.status_code,302)
        asset=m.MediaAsset.objects.get(storage_key='child.jpg')
        self.assertFalse(a.public_allowed(asset))
        response=self.client.post(reverse('tuition:publish_media',args=[asset.uid]),{'students_confirmed':'on'})
        self.assertContains(response,'Previously identified students must remain selected')
        self.assertTrue(asset.subjects.filter(learner=self.child).exists())

    def test_existing_pending_can_publish_but_rejected_and_other_owner_cannot(self):
        asset=m.MediaAsset.objects.create(teacher=self.teacher,uploader=self.owner,storage_key='old.jpg',mime='image/jpeg',size=1,checksum='x')
        url=reverse('tuition:publish_media',args=[asset.uid])
        self.client.get(url);asset.refresh_from_db();self.assertEqual(asset.moderation,'pending')
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{'students_confirmed':'on'}).status_code,403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url,{'students_confirmed':'on'}).status_code,302)
        asset.refresh_from_db();self.assertTrue(a.public_allowed(asset))
        asset.moderation='rejected';asset.save()
        self.assertEqual(self.client.post(url,{'students_confirmed':'on'}).status_code,403)

    def test_confirmation_required_and_teacher_approval_remains(self):
        url=reverse('tuition:activity_upload',args=['teacher',self.teacher.uid])
        response=self.client.post(url,{'title':'Photo','file':self.photo(),'public_requested':'on'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(m.MediaAsset.objects.exists())
        self.teacher.status='pending';self.teacher.save()
        asset=m.MediaAsset.objects.create(teacher=self.teacher,uploader=self.owner,storage_key='pending.jpg',mime='image/jpeg',size=1,checksum='x',moderation='approved',subjects_complete=True,public_requested=True)
        self.assertFalse(a.public_allowed(asset))
