from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache
from .models import User, ShopProfile, MarketingAccess, LocalOffer, Flick


class MarketingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = User.objects.create_user('agent', password='Agent-password-123', user_type='marketing_agent', phone='9000000001', pincode='600001')
        self.shop = User.objects.create_user('shop', password='Shop-password-123', user_type='shop', phone='9000000002')
        ShopProfile.objects.create(user=self.shop, shop_name='My shop')
        self.other = User.objects.create_user('other', password='Other-password-123', user_type='shop', phone='9000000003')
        self.grant = MarketingAccess.objects.create(agent=self.agent, shop=self.shop)
        self.client.force_login(self.agent)

    def unlock(self):
        return self.client.post(reverse('marketing_open', args=[self.shop.pk]), {'phone': self.shop.phone, 'password': 'Shop-password-123'})

    def test_dashboard_and_unlock(self):
        self.assertContains(self.client.get(reverse('marketing_dashboard')), 'My shop')
        self.assertRedirects(self.unlock(), reverse('marketing_workspace'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.agent.pk)
        self.assertContains(self.client.get(reverse('marketing_workspace')), 'Business coupons')

    def test_wrong_password_and_unassigned_shop(self):
        self.client.post(reverse('marketing_open', args=[self.shop.pk]), {'phone': self.shop.phone, 'password': 'wrong'})
        self.assertNotIn('marketing_shop', self.client.session)
        self.assertEqual(self.client.get(reverse('marketing_open', args=[self.other.pk])).status_code, 404)
        self.assertRedirects(self.client.get(reverse('offer_post')), reverse('marketing_dashboard'))

    def test_posting_uses_shop_and_blocks_other_accounts(self):
        self.unlock()
        self.client.post(reverse('offer_post'), {'title': 'Discount', 'business_name': 'My shop', 'category': 'other'})
        self.assertEqual(LocalOffer.objects.get().owner, self.shop)
        self.client.post(reverse('post_flick'), {'caption': 'Shop video'})
        self.assertEqual(Flick.objects.get().user, self.shop)
        other_video = Flick.objects.create(user=self.other, caption='Other shop')
        self.assertEqual(self.client.post(reverse('delete_flick', args=[other_video.pk])).status_code, 404)
        self.assertRedirects(self.client.get(reverse('employer_dashboard')), reverse('marketing_dashboard'))
        self.assertRedirects(self.client.get(reverse('marketing_admin')), reverse('marketing_dashboard'))

    def test_revocation_and_password_change(self):
        self.unlock()
        self.shop.set_password('New-password-123')
        self.shop.save()
        self.assertRedirects(self.client.get(reverse('my_offers')), reverse('marketing_dashboard'))
        self.shop.set_password('Shop-password-123')
        self.shop.save()
        self.unlock()
        self.grant.delete()
        self.assertRedirects(self.client.get(reverse('my_offers')), reverse('marketing_dashboard'))

    def test_owner_grants_and_revokes(self):
        self.grant.delete()
        self.client.force_login(self.shop)
        self.client.post(reverse('marketing_access'), {'username': self.agent.username})
        grant = MarketingAccess.objects.get()
        self.client.post(reverse('marketing_access'), {'action': 'revoke', 'grant': grant.pk})
        self.assertFalse(MarketingAccess.objects.exists())

    def test_admin_creation(self):
        self.client.force_login(self.shop)
        self.assertEqual(self.client.get(reverse('marketing_admin')).status_code, 403)
        admin = User.objects.create_user('admin', admin_role='super_admin')
        self.client.force_login(admin)
        response = self.client.post(reverse('marketing_admin'), {'username': 'newagent', 'phone': '9000000004', 'pincode': '600001', 'password1': 'Strong-secret-123', 'password2': 'Strong-secret-123'})
        self.assertRedirects(response, reverse('marketing_admin'))
        agent = User.objects.get(username='newagent')
        self.assertEqual(agent.user_type, 'marketing_agent')
        self.assertTrue(agent.check_password('Strong-secret-123'))

    def test_expired_session(self):
        self.unlock()
        session = self.client.session
        state = session['marketing_shop']
        state['expires'] = 0
        session['marketing_shop'] = state
        session.save()
        self.assertRedirects(self.client.get(reverse('offer_post')), reverse('marketing_dashboard'))

    def test_voucher_isolation_and_coupon_access(self):
        from vouchers.models import Business, GiftVoucher
        from datetime import date
        own = Business.objects.create(owner=self.shop, business_name='Own business', status='approved')
        other = Business.objects.create(owner=self.other, business_name='Other business', status='approved')
        voucher = GiftVoucher.objects.create(business=other, voucher_name='Private voucher', voucher_value=100, valid_from=date.today(), expiry_date=date.today(), total_quantity=10)
        self.unlock()
        self.assertEqual(self.client.get(reverse('vouchers:voucher_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('vouchers:voucher_edit', args=[voucher.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('opc_verify_redemption')).status_code, 200)

    def test_unlock_requires_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.agent)
        self.assertEqual(client.post(reverse('marketing_open', args=[self.shop.pk]), {'phone': self.shop.phone, 'password': 'Shop-password-123'}).status_code, 403)
