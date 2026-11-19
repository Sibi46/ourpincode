"""Moderation, publication boundaries and private media regression tests."""
import io
import shutil
import uuid
from pathlib import Path
from PIL import Image
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from .flick_moderation import review_flick
from .models import AdminActivity, CompanyProfile, Flick, User, UserNotification


class FlickModerationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root=settings.BASE_DIR.parent/'.test-tmp'/('flick-review-'+uuid.uuid4().hex)
        cls.root.mkdir(parents=True)
        cls.config=override_settings(MEDIA_ROOT=cls.root/'public',FLICKS_PRIVATE_ROOT=cls.root/'private')
        cls.config.enable()

    @classmethod
    def tearDownClass(cls):
        cls.config.disable()
        shutil.rmtree(cls.root)
        super().tearDownClass()

    def setUp(self):
        self.owner=User.objects.create_user('flick-owner',password='example-password',user_type='company')
        self.admin=User.objects.create_user('reviewer',password='example-password',admin_role='super_admin')
        self.other=User.objects.create_user('other',password='example-password')
        self.company=CompanyProfile.objects.create(user=self.owner,company_name='Review Store')
        self.client.force_login(self.owner)

    def upload(self):
        image=io.BytesIO()
        Image.new('RGB',(8,8),'blue').save(image,format='PNG')
        return SimpleUploadedFile('review.png',image.getvalue(),content_type='image/png')

    def submit(self):
        response=self.client.post('/flicks/post/',{'caption':'Private review caption','image':self.upload(),
            'moderation_status':'approved','reviewed':'on','fc1':'on','fc2':'on','fc3':'on'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['status'],'pending')
        return Flick.objects.get()

    def test_consent_and_forged_status_cannot_publish(self):
        flick=self.submit()
        self.assertEqual(flick.moderation_status,'pending')
        self.assertIsNone(flick.reviewed_by)
        self.assertContains(self.client.get('/flicks/mine/'),'Waiting for admin approval')
        self.assertTrue(UserNotification.objects.filter(user=self.admin,title='Flick awaiting review').exists())
        self.assertFalse(str(flick.image.path).startswith(str(settings.MEDIA_ROOT)))
        self.assertTrue(flick.image.url.startswith('/flicks/media/'))

    def test_admin_review_then_rejection_removes_public_content(self):
        flick=self.submit()
        anonymous=Client()
        self.assertNotContains(anonymous.get('/flicks/'),flick.caption)
        self.assertEqual(anonymous.get(flick.image.url).status_code,404)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/super-admin/flicks/'),flick.caption)
        response=self.client.post('/super-admin/flicks/',{'action':'approve_flick','flick_id':flick.pk,'reviewed':'on'})
        self.assertEqual(response.status_code,302)
        flick.refresh_from_db()
        self.assertEqual(flick.moderation_status,'approved')
        self.assertEqual(flick.reviewed_by,self.admin)
        self.assertContains(anonymous.get('/flicks/'),flick.caption)
        media=anonymous.get(flick.image.url)
        self.assertEqual(media.status_code,200)
        b''.join(media.streaming_content)
        self.client.post('/super-admin/flicks/',{'action':'reject_flick','flick_id':flick.pk,'reviewed':'on','reason':'Violates the content guidelines.'})
        self.assertNotContains(anonymous.get('/flicks/'),flick.caption)
        self.assertEqual(anonymous.get(flick.image.url).status_code,404)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/flicks/mine/'),'Violates the content guidelines.')
        self.assertEqual(AdminActivity.objects.filter(section='flicks').count(),2)

    def test_reviewer_requires_acknowledgement_and_rejection_reason(self):
        flick=Flick.objects.create(user=self.owner,caption='Needs review')
        for status,reason,reviewed in [('approved','',False),('rejected','',True),('rejected','bad',True)]:
            with self.assertRaises(ValidationError):
                review_flick(self.admin,flick.pk,status,reason,reviewed)
        with self.assertRaises(ValidationError):
            review_flick(self.admin,'invalid','approved',reviewed=True)
        flick.refresh_from_db()
        self.assertEqual(flick.moderation_status,'pending')

    def test_review_is_idempotent_and_audited(self):
        flick=Flick.objects.create(user=self.owner,caption='Review once')
        for _ in range(2):
            review_flick(self.admin,flick.pk,'approved',reviewed=True)
        self.assertEqual(UserNotification.objects.filter(user=self.owner,title='Flick approved').count(),1)
        self.assertEqual(AdminActivity.objects.filter(action='flick_approved').count(),1)

    def test_other_users_and_staff_cannot_review_or_preview(self):
        flick=self.submit()
        self.other.is_staff=True;self.other.save()
        with self.assertRaises(PermissionDenied):
            review_flick(self.other,flick.pk,'approved',reviewed=True)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(flick.image.url).status_code,404)
        self.assertNotContains(self.client.get('/flicks/mine/'),flick.caption)
        self.client.post('/super-admin/flicks/',{'action':'approve_flick','flick_id':flick.pk,'reviewed':'on'})
        flick.refresh_from_db()
        self.assertEqual(flick.moderation_status,'pending')

    def test_csrf_blocks_review(self):
        flick=Flick.objects.create(user=self.owner,caption='CSRF protected')
        client=Client(enforce_csrf_checks=True);client.force_login(self.admin)
        self.assertEqual(client.post('/super-admin/flicks/',{'action':'approve_flick','flick_id':flick.pk,'reviewed':'on'}).status_code,403)
        flick.refresh_from_db()
        self.assertEqual(flick.moderation_status,'pending')

    def test_promoted_pending_is_hidden_from_feed_and_business_profile(self):
        flick=Flick.objects.create(user=self.owner,caption='Unreviewed promoted caption',is_promoted=True,advertise_plan='featured')
        self.assertFalse(flick.is_active_promoted())
        self.assertNotContains(self.client.get('/flicks/'),flick.caption)
        self.assertNotContains(self.client.get(self.company.get_absolute_url()),flick.caption)
        review_flick(self.admin,flick.pk,'approved',reviewed=True)
        self.assertContains(self.client.get(self.company.get_absolute_url()),flick.caption)

    def test_pending_cannot_receive_public_likes_comments_or_reports(self):
        flick=Flick.objects.create(user=self.owner,caption='Hidden')
        self.client.force_login(self.other)
        from django.urls import reverse
        for name in ('like_flick','comment_flick','report_flick'):
            self.assertEqual(self.client.post(reverse(name,args=[flick.pk]),{'text':'hello','reason':'spam'}).status_code,404)

    def test_owner_and_admin_preview_and_video_byte_ranges(self):
        flick=Flick.objects.create(user=self.owner,video=SimpleUploadedFile('review.mp4',b'0123456789',content_type='video/mp4'))
        response=self.client.get(flick.video.url,HTTP_RANGE='bytes=2-5')
        self.assertEqual(response.status_code,206)
        self.assertEqual(b''.join(response.streaming_content),b'2345')
        self.assertEqual(response['Content-Range'],'bytes 2-5/10')
        self.assertEqual(response['Cache-Control'],'private, no-store')
        response=self.client.head(flick.video.url,HTTP_RANGE='bytes=-3')
        self.assertEqual(response.status_code,206)
        self.assertEqual(response['Content-Length'],'3')
        self.assertEqual(response.content,b'')
        self.assertEqual(self.client.get(flick.video.url,HTTP_RANGE='bytes=90-99').status_code,416)
        self.client.force_login(self.admin)
        response=self.client.get(flick.video.url)
        self.assertEqual(b''.join(response.streaming_content),b'0123456789')

    def test_legacy_media_uses_same_authorization_and_shared_names_work(self):
        from django.core.files.storage import default_storage
        from django.core.files.base import ContentFile
        name=default_storage.save('flicks/videos/legacy.mp4',ContentFile(b'legacy'))
        flick=Flick.objects.create(user=self.owner,video=name)
        Flick.objects.create(user=self.other,video=name)
        self.assertEqual(Client().get(flick.video.url).status_code,404)
        response=self.client.get(flick.video.url)
        self.assertEqual(b''.join(response.streaming_content),b'legacy')
        review_flick(self.admin,flick.pk,'approved',reviewed=True)
        response=Client().get(flick.video.url)
        self.assertEqual(b''.join(response.streaming_content),b'legacy')
        self.owner.is_active=False;self.owner.save()
        self.assertEqual(Client().get(flick.video.url).status_code,404)

    def test_invalid_upload_and_empty_submission_are_rejected(self):
        for data in ({'caption':'   '},{'image':SimpleUploadedFile('fake.png',b'not an image',content_type='image/png')},
                     {'video':SimpleUploadedFile('script.html',b'bad',content_type='text/html')}):
            self.assertEqual(self.client.post('/flicks/post/',data,HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code,400)
        self.assertFalse(Flick.objects.exists())

    def test_model_defaults_all_creation_paths_to_pending(self):
        self.assertEqual(Flick.objects.create(user=self.owner,caption='Default').moderation_status,'pending')

