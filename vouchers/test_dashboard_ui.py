from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from jobs.models import User
from vouchers.models import Business,GiftVoucher,VoucherPurchase,VoucherRedemption


class VoucherDashboardUITests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user(username='voucher-ui-owner',user_type='company')
        self.business=Business.objects.create(owner=self.owner,business_name='Local Gifts',status='approved')
        self.client.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')
        today=timezone.localdate()
        self.voucher=GiftVoucher.objects.create(business=self.business,created_by=self.owner,voucher_name='Local Gift',product_service_name='Gift',voucher_value=100,valid_from=today,expiry_date=today+timedelta(days=30),total_quantity=50,status='published')
        self.url=reverse('vouchers:business_dashboard')

    def purchase(self,code,status='paid',amount=100,voucher=None):
        return VoucherPurchase.objects.create(gift_voucher=voucher or self.voucher,voucher_code=code,buyer_name='Buyer',receiver_name='Receiver',amount_paid=amount,status=status)

    def test_dashboard_uses_real_totals_and_existing_actions(self):
        for i,status in enumerate(['paid','sent','redeemed','pending']):
            self.purchase('UI'+str(i),status)
        response=self.client.get(self.url)
        self.assertEqual(response.context['total_revenue'],Decimal('300'))
        self.assertEqual(response.context['purchase_stats']['total'],4)
        self.assertEqual(response.context['voucher_stats']['published'],1)
        for name in ['voucher_create','slot_buy','redeem_lookup','branch_list','employee_list','marketplace']:
            self.assertContains(response,reverse('vouchers:'+name))
        self.assertContains(response,'vouchers/dashboard.css')
        self.assertContains(response,'Recent Gift Vouchers')
        self.assertContains(response,'Recent Purchases')
        self.assertContains(response,'Recent Redemptions')

    def test_histories_are_paginated_and_never_include_another_business(self):
        for i in range(22):self.purchase('HISTORY'+str(i))
        own=self.purchase('OWN-REDEEMED','redeemed')
        VoucherRedemption.objects.create(purchase=own,redeemed_by=self.owner)
        other=User.objects.create_user(username='voucher-other',user_type='company')
        business=Business.objects.create(owner=other,business_name='Other Gifts',status='approved')
        self.voucher.pk=None;self.voucher.business=business;self.voucher.voucher_name='Private Other Voucher';self.voucher.save()
        purchase=self.purchase('PRIVATE-OTHER','redeemed',10000,self.voucher)
        VoucherRedemption.objects.create(purchase=purchase,redeemed_by=other)
        for activity in ['purchases','redemptions']:
            response=self.client.get(self.url,{'activity':activity})
            self.assertNotContains(response,'PRIVATE-OTHER')
            self.assertNotContains(response,'Private Other Voucher')
        response=self.client.get(self.url,{'activity':'purchases'})
        self.assertEqual(len(response.context['activity_history']),20)
        self.assertEqual(response.context['activity_history'].paginator.count,23)
        self.assertTrue(response.context['activity_history'].has_next())
        self.assertEqual(self.client.get(self.url,{'activity':'purchases','page':2}).status_code,200)

    def test_pending_business_sees_status_and_no_active_creation_buttons(self):
        self.business.status='pending';self.business.save()
        response=self.client.get(self.url)
        self.assertContains(response,'under review')
        self.assertNotContains(response,reverse('vouchers:voucher_create'))
        self.assertNotContains(response,reverse('vouchers:slot_buy'))
        self.assertEqual(self.client.get(self.url,{'activity':'invalid'}).status_code,200)

    def test_revenue_keeps_paise_instead_of_rounding_money(self):
        self.purchase('PAISE','paid',Decimal('99.50'))
        self.assertContains(self.client.get(self.url),'₹99.50')
