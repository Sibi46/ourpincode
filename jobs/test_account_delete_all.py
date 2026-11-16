import tempfile
import os
import uuid
import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from tuition import models as tm, tests as fixtures, services
from tuition.storage import storage
from quiz.models import PincodeDay, DayParticipant, DayGift
from .models import User, CompanyProfile, AccountFileDeletion, AdminActivity
from .account_deletion import cleanup_files


class DeleteEverythingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)
        cls.admin = User.objects.create_user(username='delete-all-admin', admin_role='super_admin')

    def setUp(self):
        test_root = Path(settings.BASE_DIR).parent/'.test-tmp/account-deletion-tests' if os.name == 'nt' else Path(tempfile.gettempdir())
        test_root.mkdir(parents=True, exist_ok=True)
        self.directory = test_root/('account-delete-'+uuid.uuid4().hex)
        self.directory.mkdir()
        def cleanup_directory():
            assert self.directory.resolve().is_relative_to(test_root.resolve())
            shutil.rmtree(self.directory)
        self.addCleanup(cleanup_directory)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory/'public', TUITION_PRIVATE_ROOT=self.directory/'private')
        self.settings_override.enable(); self.addCleanup(self.settings_override.disable)
        self.client.force_login(self.admin, backend='django.contrib.auth.backends.ModelBackend')
        self.url = reverse('super_admin_delete_all', args=[self.owner.pk])

    def confirmation(self):
        result = self.client.get(self.url)
        self.assertEqual(result.status_code, 200)
        return {'plan_token': result.context['plan_token'], 'confirmation': 'DELETE', 'acknowledge': 'yes'}

    def test_confirmed_deletion_removes_owned_data_and_files_preserving_other_users(self):
        enrolment = services.decide(self.owner, self.application, 'accepted')
        services.transfer(self.owner, enrolment, self.batch)
        agreement = tm.FeeAgreement.objects.create(enrolment=enrolment, start_date=self.lesson.start_date, amount=100)
        invoice = tm.Invoice.objects.create(agreement=agreement, period_start=self.lesson.start_date, period_end=self.lesson.start_date, due_date=self.lesson.start_date, amount=100)
        payment = tm.Payment.objects.create(invoice=invoice, amount=100, method='cash', recorded_by=self.owner)
        tm.Payment.objects.create(invoice=invoice, amount=100, method='cash', recorded_by=self.owner, reverses=payment)
        key = storage().save('owned.jpg', ContentFile(b'private test image'))
        tm.MediaAsset.objects.create(teacher=self.teacher, uploader=self.owner, storage_key=key, mime='image/jpeg', size=18, checksum='test')
        company = CompanyProfile.objects.create(user=self.owner, company_name='Owned Company')
        company.logo.save('logo.txt', ContentFile(b'logo'), save=True)
        logo = Path(company.logo.path)
        other_user_ids = set(User.objects.exclude(pk=self.owner.pk).values_list('pk', flat=True))
        data = self.confirmation()
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.owner.pk).exists())
        self.assertFalse(tm.TeacherProfile.objects.filter(pk=self.teacher.pk).exists())
        self.assertFalse(tm.Payment.objects.filter(pk=payment.pk).exists())
        self.assertFalse(tm.MediaAsset.objects.filter(storage_key=key).exists())
        self.assertTrue(tm.Learner.objects.filter(pk=self.child.pk).exists())
        self.assertTrue(other_user_ids.issubset(set(User.objects.values_list('pk', flat=True))))
        self.assertFalse(storage().exists(key))
        self.assertFalse(logo.exists())
        self.assertFalse(AccountFileDeletion.objects.exists())
        self.assertTrue(AdminActivity.objects.filter(action='user_permanently_deleted', target_id=str(self.owner.pk)).exists())

    def test_shared_student_and_quiz_gift_configuration_are_preserved(self):
        learner = tm.Learner.objects.create(user=self.other, created_by=self.owner, name='Shared learner', age=20, pincode='600073')
        now = timezone.now()
        event = PincodeDay.objects.create(starts_at=now, ends_at=now+timedelta(hours=8), quiz_opens_on=now.date(), quiz_closes_on=now.date())
        participant = DayParticipant.objects.create(event=event, user=self.owner, points=15)
        gift = DayGift.objects.create(event=event, name='Site gift', rank=1, winner=participant)
        data = self.confirmation()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
        learner.refresh_from_db(); gift.refresh_from_db()
        self.assertEqual(learner.created_by_id, self.other.pk)
        self.assertEqual(learner.user_id, self.other.pk)
        self.assertIsNone(gift.winner_id)
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())

    def test_confirmation_and_current_snapshot_required(self):
        data = self.confirmation()
        self.assertEqual(self.client.post(self.url, {}).status_code, 400)
        tm.TeacherProfile.objects.create(owner=self.owner, name='New profile', pincode='600073')
        result = self.client.post(self.url, data)
        self.assertEqual(result.status_code, 400)
        self.assertContains(result, 'linked records changed', status_code=400)
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        self.assertTrue(tm.TeacherProfile.objects.filter(pk=self.teacher.pk).exists())
        self.assertFalse(AccountFileDeletion.objects.exists())

    def test_shared_public_file_is_kept(self):
        company = CompanyProfile.objects.create(user=self.owner, company_name='Company')
        company.logo.save('shared.txt', ContentFile(b'shared'), save=True)
        CompanyProfile.objects.create(user=self.other, company_name='Other company', logo=company.logo.name)
        path = Path(company.logo.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url, self.confirmation())
        self.assertTrue(path.exists())
        self.assertTrue(CompanyProfile.objects.filter(user=self.other).exists())

    def test_failed_file_cleanup_is_retryable(self):
        key = storage().save('retry.jpg', ContentFile(b'photo'))
        tm.MediaAsset.objects.create(teacher=self.teacher, uploader=self.owner, storage_key=key, mime='image/jpeg', size=5, checksum='test')
        data = self.confirmation()
        with patch('django.core.files.storage.FileSystemStorage.delete', side_effect=OSError('test outage')):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(pk=self.owner.pk).exists())
        self.assertTrue(AccountFileDeletion.objects.exists())
        self.assertEqual(self.client.post(reverse('super_admin_retry_delete_files')).status_code, 302)
        self.assertFalse(AccountFileDeletion.objects.exists())
        self.assertFalse(storage().exists(key))

    def test_permissions_super_admin_and_csrf(self):
        data = self.confirmation()
        client = Client(enforce_csrf_checks=True); client.force_login(self.admin)
        self.assertEqual(client.post(self.url, data).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, data).status_code, 403)
        self.assertEqual(self.client.post(reverse('super_admin_retry_delete_files')).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('super_admin_delete_all', args=[self.admin.pk])).status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_monthly_draw_and_other_customers_are_preserved(self):
        from coupons.models import Salesman, Shop, CouponBatch, Coupon, MonthlyDraw, LuckyDrawEntry
        salesman = Salesman.objects.create(user=self.other, created_by=self.owner)
        shop = Shop.objects.create(salesman=salesman, business=self.parent, name='Other shop', pincode='600073')
        batch = CouponBatch.objects.create(shop=shop, salesman=salesman, quantity=2, start_number=1, end_number=2)
        first = Coupon.objects.create(batch=batch, number=1, code='DELETE-TEST-1', activated_by=self.owner)
        second = Coupon.objects.create(batch=batch, number=2, code='DELETE-TEST-2', activated_by=self.parent)
        draw = MonthlyDraw.objects.create(month=timezone.localdate().replace(day=1))
        entry = LuckyDrawEntry.objects.create(draw=draw, coupon=first, customer=self.owner)
        other_entry = LuckyDrawEntry.objects.create(draw=draw, coupon=second, customer=self.parent)
        draw.winner = entry; draw.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.url, self.confirmation()).status_code, 302)
        draw.refresh_from_db(); first.refresh_from_db()
        self.assertIsNone(draw.winner_id)
        self.assertIsNone(first.activated_by_id)
        self.assertTrue(LuckyDrawEntry.objects.filter(pk=other_entry.pk).exists())
        self.assertTrue(Salesman.objects.filter(pk=salesman.pk).exists())

    def test_nullable_news_contributor_uuid_and_private_files_are_removed(self):
        from django.core.files.storage import FileSystemStorage
        from newsdesk.models import NewsContributor
        from .models import State, District, PinCode
        state = State.objects.create(name='Deletion test state', code='DELTEST')
        district = District.objects.create(name='Deletion test district', state=state)
        pin = PinCode.objects.create(code='600073', district=district)
        fields = [NewsContributor._meta.get_field(name) for name in ('aadhaar', 'profile_photo')]
        store = FileSystemStorage(location=self.directory/'identity')
        with patch.object(fields[0], 'storage', store), patch.object(fields[1], 'storage', store):
            contributor = NewsContributor.objects.create(user=self.owner, phone='9000000099', name='Contributor',
                pincode=pin, address='Test address', phone_verified_at=timezone.now())
            contributor.aadhaar.save('id.pdf', ContentFile(b'private identity'), save=True)
            contributor.profile_photo.save('photo.jpg', ContentFile(b'private photo'), save=True)
            paths = [Path(contributor.aadhaar.path), Path(contributor.profile_photo.path)]
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post(self.url, self.confirmation()).status_code, 302)
            self.assertFalse(NewsContributor.objects.filter(pk=contributor.pk).exists())
            self.assertTrue(all(not path.exists() for path in paths))
            self.assertTrue(PinCode.objects.filter(pk=pin.pk).exists())

    def test_repeat_submission_is_safe(self):
        data = self.confirmation()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
        response = self.client.post(self.url, data, follow=True)
        self.assertContains(response, 'already been deleted')

    def test_audit_failure_rolls_back_all_deletion_and_file_tasks(self):
        key = storage().save('rollback.jpg', ContentFile(b'photo'))
        asset = tm.MediaAsset.objects.create(teacher=self.teacher, uploader=self.owner, storage_key=key, mime='image/jpeg', size=5, checksum='test')
        data = self.confirmation()
        with patch('jobs.account_deletion.AdminActivity.objects.create', side_effect=RuntimeError('test audit failure')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, data)
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        self.assertTrue(tm.TeacherProfile.objects.filter(pk=self.teacher.pk).exists())
        self.assertTrue(tm.MediaAsset.objects.filter(pk=asset.pk).exists())
        self.assertTrue(storage().exists(key))
        self.assertFalse(AccountFileDeletion.objects.exists())
