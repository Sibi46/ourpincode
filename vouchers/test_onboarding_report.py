from django.test import TestCase
from django.urls import reverse
from jobs.models import User,UserNotification
from vouchers.models import Business,VoucherSlotPurchase
from vouchers.forms import BusinessRegistrationForm


class VoucherOnboardingReportTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user(username='voucher-guide-owner',user_type='company')
        self.business=Business.objects.create(owner=self.owner,business_name='Local Gifts',status='pending')
        self.client.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')
        self.admin=User.objects.create_user(username='voucher-guide-admin',is_staff=True)

    def test_description_rejects_numeric_only_and_allows_text_with_numbers(self):
        data=dict(business_name='Local Gifts',owner_name='Mary Jane',mobile='9000000021',email='gifts@example.com',address='Main Street',pincode='600073',city='Tambaram',state='Tamil Nadu')
        for value in ['123456','１２３','123 456','₹123 !!!']:
            form=BusinessRegistrationForm({**data,'description':value});form.is_valid()
            self.assertIn('description',form.errors)
        for value in ['Ice cream and gifts','Open 24/7 for 10 years','தமிழ் பரிசுகள் 2026','']:
            form=BusinessRegistrationForm({**data,'description':value})
            self.assertTrue(form.is_valid(),form.errors)

    def test_pending_pages_explain_real_approval_sequence(self):
        for name in ['register_success','business_dashboard','slot_history']:
            response=self.client.get(reverse('vouchers:'+name))
            self.assertContains(response,'Your Business Registration is Pending Approval')
            for step in ['Buy Slots','Wait for Admin Approval','Create New Voucher','Create Branch','Publish the Voucher']:
                self.assertContains(response,step)
            self.assertContains(response,'After business approval')
            self.assertContains(response,'in-app notification')
            self.assertNotContains(response,'href="'+reverse('vouchers:slot_buy')+'"')
        self.assertRedirects(self.client.get(reverse('vouchers:slot_buy')),reverse('vouchers:business_dashboard'),fetch_redirect_response=False)

    def test_business_approval_notifies_only_owner_once_and_unlocks_dashboard(self):
        url=reverse('vouchers:admin_approve_business',args=[self.business.pk])
        self.client.post(url);self.business.refresh_from_db();self.assertEqual(self.business.status,'pending')
        self.client.force_login(self.admin,backend='django.contrib.auth.backends.ModelBackend')
        self.client.post(url);self.client.post(url)
        self.business.refresh_from_db();self.assertEqual(self.business.status,'approved')
        self.assertEqual(UserNotification.objects.filter(user=self.owner,title='Voucher business approved').count(),1)
        self.assertFalse(UserNotification.objects.filter(user=self.admin).exists())
        self.client.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')
        response=self.client.get(reverse('vouchers:business_dashboard'))
        self.assertNotContains(response,'Your Business Registration is Pending Approval')
        self.assertContains(response,reverse('vouchers:slot_buy'))

    def test_slot_request_guidance_and_notification_disappear_after_approval(self):
        self.business.status='approved';self.business.save()
        slot=VoucherSlotPurchase.objects.create(business=self.business,purchased_by=self.owner,slots_count=5,amount_paid=100,payment_reference='TEST-REFERENCE')
        response=self.client.get(reverse('vouchers:slot_history'))
        self.assertContains(response,'Your Slot Request is Pending Approval')
        self.assertContains(response,'TEST-REFERENCE')
        self.client.force_login(self.admin,backend='django.contrib.auth.backends.ModelBackend')
        url=reverse('vouchers:admin_approve_slot',args=[slot.pk])
        self.client.post(url);self.client.post(url)
        self.assertEqual(UserNotification.objects.filter(user=self.owner,title='Voucher slots approved').count(),1)
        self.client.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')
        self.assertNotContains(self.client.get(reverse('vouchers:slot_history')),'Your Slot Request is Pending Approval')

    def test_server_returns_visible_description_error_without_registering_business(self):
        applicant=User.objects.create_user(username='voucher-new-applicant',user_type='company')
        self.client.force_login(applicant,backend='django.contrib.auth.backends.ModelBackend')
        response=self.client.post(reverse('vouchers:business_register'),dict(business_name='New Gifts',owner_name='Mary Jane',mobile='9000000022',email='new@example.com',address='Main Street',pincode='600073',city='Tambaram',state='Tamil Nadu',description='123456'))
        self.assertContains(response,'Numbers alone are not allowed.')
        self.assertContains(response,'123456')
        self.assertFalse(Business.objects.filter(owner=applicant).exists())
