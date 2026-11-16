from datetime import timedelta
from unittest.mock import patch
from django.db import IntegrityError
from django.test import Client, TestCase
from django.utils import timezone
from tuition.models import TeacherProfile, MediaAsset
from quiz.models import PincodeDay, DayParticipant, DayGift
from .models import User, CompanyProfile


class SuperAdminUserDeletionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='delete-admin', admin_role='super_admin')
        self.target = User.objects.create_user(username='delete-target', first_name='Target')
        self.client.force_login(self.admin, backend='django.contrib.auth.backends.ModelBackend')
        self.url = f'/super-admin/users/{self.target.pk}/delete/'

    def test_user_with_protected_tuition_records_returns_message_and_keeps_everything(self):
        teacher = TeacherProfile.objects.create(owner=self.target, kind='teacher', name='Test Tuition', description='Teaching', pincode='600073')
        asset = MediaAsset.objects.create(teacher=teacher, uploader=self.target, storage_key='test-asset', mime='image/jpeg', size=10, checksum='a'*64)
        company = CompanyProfile.objects.create(user=self.target, company_name='Test Business')
        response = self.client.post(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, '/super-admin/users/')
        self.assertContains(response, 'could not be deleted')
        self.assertContains(response, 'teacher profiles (1)')
        self.assertContains(response, 'media assets (1)')
        self.assertContains(response, 'No records were deleted.')
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        self.assertTrue(TeacherProfile.objects.filter(pk=teacher.pk).exists())
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertTrue(CompanyProfile.objects.filter(pk=company.pk).exists())

    def test_protection_message_does_not_call_related_object_string_method(self):
        TeacherProfile.objects.create(owner=self.target, kind='teacher', name='Test Tuition', pincode='600073')
        with patch.object(TeacherProfile, '__str__', side_effect=RuntimeError('broken record label')):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, 'teacher profiles (1)')
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())

    def test_quiz_gift_winner_remains_protected(self):
        now = timezone.now()
        event = PincodeDay.objects.create(starts_at=now, ends_at=now+timedelta(hours=8), quiz_opens_on=now.date(), quiz_closes_on=now.date())
        participant = DayParticipant.objects.create(event=event, user=self.target, points=15)
        gift = DayGift.objects.create(event=event, name='Winner gift', rank=1, winner=participant)
        response = self.client.post(self.url, follow=True)
        self.assertContains(response, 'could not be deleted')
        self.assertTrue(DayGift.objects.filter(pk=gift.pk, winner=participant).exists())
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())

    def test_unprotected_user_can_be_deleted(self):
        company = CompanyProfile.objects.create(user=self.target, company_name='Test Business')
        response = self.client.post(self.url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'deleted.')
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())
        self.assertFalse(CompanyProfile.objects.filter(pk=company.pk).exists())

    def test_database_constraint_failure_is_handled_without_deleting_user(self):
        with patch.object(User, 'delete', side_effect=IntegrityError('test constraint')):
            response = self.client.post(self.url, follow=True)
        self.assertContains(response, 'linked records still reference this account')
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())

    def test_only_super_admin_can_delete_and_get_is_read_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        self.client.force_login(self.target)
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        self.client.force_login(self.admin)
        self.client.post(f'/super-admin/users/{self.admin.pk}/delete/')
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(self.url).status_code, 403)
