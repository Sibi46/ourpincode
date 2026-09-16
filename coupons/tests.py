from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from jobs.models import ShopProfile
from .models import PointsTransaction, PointsWallet, Redemption, RedemptionCounter, Reward


@override_settings(
    ALLOWED_HOSTS=['testserver'],
    SECURE_SSL_REDIRECT=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class ShopRedemptionSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.customer = User.objects.create_user('customer', user_type='employee')
        cls.owner = User.objects.create_user('owner', user_type='shop')
        cls.other_owner = User.objects.create_user('other', user_type='shop')
        cls.shop = ShopProfile.objects.create(user=cls.owner, shop_name='Same name')
        ShopProfile.objects.create(user=cls.other_owner, shop_name='Same name')
        cls.reward = Reward.objects.create(
            name='Tea', business_name='Same name', points_required=10,
            redemption_shop=cls.shop,
        )
        cls.redemption = Redemption.objects.create(
            code='OPC-RED-000001', user=cls.customer, reward=cls.reward, points_used=10,
        )
        RedemptionCounter.objects.create(pk=1, last_number=1)

    def login(self, user, client=None):
        (client or self.client).force_login(user, backend='django.contrib.auth.backends.ModelBackend')

    def redeem(self, client=None):
        return (client or self.client).post('/coupons/verify/', {
            'code': self.redemption.code, 'action': 'mark_redeemed',
        })

    def assert_pending(self):
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, 'pending')
        self.assertFalse(self.redemption.verified_by_shop)
        self.assertIsNone(self.redemption.redeemed_at)

    def test_anonymous_lookup_and_redemption_require_login(self):
        for response in (
            self.client.get('/coupons/verify/', {'q': self.redemption.code}),
            self.redeem(),
            self.client.post(f'/coupons/rewards/{self.reward.pk}/redeem/'),
        ):
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith('/login/?next='))
        self.assert_pending()

    def test_customer_cannot_lookup_or_fulfil_redemption(self):
        self.login(self.customer)
        self.assertEqual(self.client.get('/coupons/verify/').status_code, 403)
        self.assertEqual(self.redeem().status_code, 403)
        self.assert_pending()

    def test_shop_role_without_profile_is_denied(self):
        user = get_user_model().objects.create_user('unlinked', user_type='shop')
        self.login(user)
        self.assertEqual(self.redeem().status_code, 403)
        self.assert_pending()

    def test_other_shop_cannot_lookup_or_redeem_even_with_same_name(self):
        self.login(self.other_owner)
        for response in (
            self.client.get('/coupons/verify/', {'q': self.redemption.code}),
            self.redeem(),
        ):
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.context['redemption'])
            self.assertEqual(response.context['error'], 'Redemption code not found.')
        self.assert_pending()

    def test_unassigned_reward_is_denied(self):
        self.reward.redemption_shop = None
        self.reward.save()
        self.login(self.owner)
        self.assertIsNone(self.redeem().context['redemption'])
        self.assert_pending()

    def test_assigned_shop_can_lookup_and_redeem_once(self):
        self.login(self.owner)
        response = self.client.get('/coupons/verify/', {'q': self.redemption.code})
        self.assertEqual(response.context['redemption'].pk, self.redemption.pk)
        self.assert_pending()
        self.assertEqual(self.redeem().status_code, 200)
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, 'redeemed')
        self.assertTrue(self.redemption.verified_by_shop)
        redeemed_at = self.redemption.redeemed_at
        self.assertIsNotNone(redeemed_at)
        self.assertEqual(self.redeem().context['error'], 'This code is no longer pending.')
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.redeemed_at, redeemed_at)

    def test_expired_redemption_cannot_be_fulfilled(self):
        self.redemption.status = 'expired'
        self.redemption.save()
        self.login(self.owner)
        self.redeem()
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, 'expired')
        self.assertFalse(self.redemption.verified_by_shop)

    def test_inactive_shop_is_denied(self):
        self.login(self.owner)
        self.owner.is_active = False
        self.owner.save()
        self.assertEqual(self.redeem().status_code, 302)
        self.assert_pending()

    def test_csrf_required_for_assigned_shop(self):
        client = Client(enforce_csrf_checks=True)
        self.login(self.owner, client)
        self.assertEqual(self.redeem(client).status_code, 403)
        self.assert_pending()

    def test_customer_cannot_assign_reward_shop(self):
        self.login(self.customer)
        response = self.client.post(f'/coupons/admin/rewards/{self.reward.pk}/edit/', {
            'redemption_shop': '',
        })
        self.assertEqual(response.status_code, 302)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.redemption_shop_id, self.shop.pk)

    def test_admin_can_assign_and_revoke_shop_access(self):
        admin = get_user_model().objects.create_user('admin', is_staff=True)
        self.login(admin)
        url = f'/coupons/admin/rewards/{self.reward.pk}/edit/'
        response = self.client.get(url)
        self.assertContains(response, 'Authorized Redemption Shop')
        other_shop = self.other_owner.shop
        self.assertEqual(self.client.post(url, {
            'redemption_shop': other_shop.pk, 'is_active': 'on',
        }).status_code, 302)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.redemption_shop_id, other_shop.pk)
        self.login(self.owner)
        self.assertIsNone(self.redeem().context['redemption'])
        self.assert_pending()
        self.login(admin)
        self.assertEqual(self.client.post(url, {
            'redemption_shop': '', 'is_active': 'on',
        }).status_code, 302)
        self.reward.refresh_from_db()
        self.assertIsNone(self.reward.redemption_shop_id)

    def test_admin_cannot_assign_inactive_shop(self):
        admin = get_user_model().objects.create_user('admin', is_staff=True)
        self.other_owner.is_active = False
        self.other_owner.save()
        self.login(admin)
        response = self.client.post(f'/coupons/admin/rewards/{self.reward.pk}/edit/', {
            'redemption_shop': self.other_owner.shop.pk,
        })
        self.assertEqual(response.status_code, 404)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.redemption_shop_id, self.shop.pk)

    def test_admin_can_create_reward_with_assigned_shop(self):
        admin = get_user_model().objects.create_user('admin', is_staff=True)
        self.login(admin)
        response = self.client.post('/coupons/admin/rewards/create/', {
            'name': 'Coffee', 'business_name': 'Same name',
            'points_required': 20, 'redemption_shop': self.shop.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Reward.objects.get(name='Coffee').redemption_shop_id, self.shop.pk)

    def test_reward_expiry_date_boundaries(self):
        today = timezone.localdate()
        for expiry, available in [(None, True), (today, True),
                                  (today + timedelta(days=1), True),
                                  (today - timedelta(days=1), False)]:
            with self.subTest(expiry=expiry):
                self.reward.expiry = expiry
                self.assertEqual(self.reward.is_available(), available)

    def test_expired_rewards_hidden_and_direct_redemption_blocked(self):
        self.reward.expiry = timezone.localdate() - timedelta(days=1)
        self.reward.save()
        wallet = PointsWallet.objects.create(user=self.customer, balance=100)
        self.login(self.customer)
        response = self.client.get('/coupons/rewards/')
        self.assertNotIn(self.reward, response.context['rewards'])
        url = f'/coupons/rewards/{self.reward.pk}/redeem/'
        for response in (self.client.get(url), self.client.post(url)):
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, '/coupons/rewards/')
        wallet.refresh_from_db()
        self.reward.refresh_from_db()
        self.assertEqual(wallet.balance, 100)
        self.assertEqual(self.reward.quantity_redeemed, 0)
        self.assertEqual(Redemption.objects.count(), 1)
        self.assertFalse(PointsTransaction.objects.exists())

    def test_shop_cannot_fulfil_expired_reward(self):
        self.reward.expiry = timezone.localdate() - timedelta(days=1)
        self.reward.save()
        self.login(self.owner)
        for response in (self.client.get('/coupons/verify/', {'q': self.redemption.code}),
                         self.redeem()):
            self.assertIsNone(response.context['redemption'])
            self.assertNotContains(response, 'VALID REDEMPTION')
        self.assert_pending()

    def test_today_future_and_undated_rewards_remain_redeemable(self):
        today = timezone.localdate()
        PointsWallet.objects.create(user=self.customer, balance=100)
        self.login(self.customer)
        for expiry in (None, today, today + timedelta(days=1)):
            with self.subTest(expiry=expiry):
                self.reward.expiry = expiry
                self.reward.save(update_fields=['expiry'])
                response = self.client.get('/coupons/rewards/')
                self.assertIn(self.reward, response.context['rewards'])
                with patch('coupons.views._notify_user'):
                    response = self.client.post(f'/coupons/rewards/{self.reward.pk}/redeem/')
                self.assertEqual(response.status_code, 302)
                self.assertIn('/success/', response.url)
        self.assertEqual(PointsWallet.objects.get(user=self.customer).balance, 70)

    def test_shop_can_fulfil_reward_on_expiry_date(self):
        self.reward.expiry = timezone.localdate()
        self.reward.save()
        self.login(self.owner)
        self.redeem()
        self.redemption.refresh_from_db()
        self.assertEqual(self.redemption.status, 'redeemed')
