from unittest.mock import patch

from django.test import TestCase, override_settings

from jobs.models import User, CompanyProfile, ShopProfile
from .models import Salesman, Shop, Coupon, PointsWallet, SpinWheelSlot


@override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DistributionFlowTests(TestCase):
    def setUp(self):
        self.business = User.objects.create_user('business', user_type='shop',
                                                 pincode='600073', salesman_biz_id='BIZ123456')
        CompanyProfile.objects.create(user=self.business, company_name='Test Shop')
        ShopProfile.objects.create(user=self.business, shop_name='Test Shop')
        self.salesman = Salesman.objects.create(user=User.objects.create_user('salesman'))

    def login(self, user):
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

    def link_shop(self):
        self.login(self.salesman.user)
        self.client.post('/coupons/salesman/shops/add-from-biz/', {'biz_id': 'BIZ123456'})
        return Shop.objects.get(business=self.business)

    def distribute(self, shop):
        return self.client.post('/coupons/salesman/give-coupons/', {
            'shop_id': shop.pk, 'start_number': '100', 'end_number': '102',
        })

    @patch('coupons.views._notify_user')
    def test_business_to_customer_points_and_dashboard_isolation(self, notify):
        shop = self.link_shop()
        self.assertEqual(self.distribute(shop).status_code, 302)
        self.distribute(shop)  # Overlapping range must not create duplicates.
        self.assertEqual(Coupon.objects.count(), 3)
        customer = User.objects.create_user('customer')
        self.login(customer)
        self.client.post('/coupons/activate/', {'code': 'OPC-000100'})
        self.assertFalse(PointsWallet.objects.filter(user=customer).exists())
        SpinWheelSlot.objects.create(label='25 points', points=25, probability=100)
        self.assertEqual(self.client.post('/coupons/api/spin/').json()['points'], 25)
        self.assertEqual(self.client.post('/coupons/api/spin/').status_code, 400)
        self.assertEqual(PointsWallet.objects.get(user=customer).balance, 25)
        coupon = Coupon.objects.get(code='OPC-000100')
        self.assertEqual(coupon.batch.shop.business, self.business)
        self.assertEqual(coupon.activated_by, customer)
        other_customer = User.objects.create_user('other-customer')
        self.login(other_customer)
        self.client.post('/coupons/activate/', {'code': coupon.code})
        self.assertEqual(self.client.post('/coupons/api/spin/').status_code, 400)
        self.login(self.business)
        response = self.client.get('/employer/dashboard/')
        self.assertContains(response, 'OPC-000100')
        self.assertContains(response, '/coupons/verify/')
        self.assertEqual(response.context['coupon_used'], 1)
        self.assertEqual(response.context['coupon_available'], 2)
        other_business = User.objects.create_user('other-business', user_type='company')
        self.login(other_business)
        response = self.client.get('/employer/dashboard/')
        self.assertNotContains(response, 'OPC-000100')
        self.assertNotContains(response, '/coupons/verify/')

    def test_business_identity_survives_rename_and_name_collision(self):
        shop = self.link_shop()
        CompanyProfile.objects.filter(user=self.business).update(company_name='Renamed')
        self.assertEqual(self.link_shop().pk, shop.pk)
        other = User.objects.create_user('other', user_type='shop', pincode='600073',
                                         salesman_biz_id='BIZ654321')
        CompanyProfile.objects.create(user=other, company_name='Test Shop')
        self.client.post('/coupons/salesman/shops/add-from-biz/', {'biz_id': other.salesman_biz_id})
        self.assertEqual(Shop.objects.count(), 2)
        self.assertNotEqual(Shop.objects.get(business=other).pk, shop.pk)

    def test_deactivation_blocks_existing_session(self):
        shop = self.link_shop()
        Salesman.objects.filter(pk=self.salesman.pk).update(is_active=False)
        for path in ['/coupons/salesman/', '/coupons/salesman/shops/',
                     '/coupons/salesman/give-coupons/', '/coupons/salesman/coupon-history/']:
            self.assertRedirects(self.client.get(path), '/coupons/salesman/login/',
                                 fetch_redirect_response=False)
        self.assertRedirects(self.distribute(shop), '/coupons/salesman/login/',
                             fetch_redirect_response=False)
        self.assertFalse(Coupon.objects.exists())

    def test_inactive_business_cannot_be_linked(self):
        self.login(self.salesman.user)
        User.objects.filter(pk=self.business.pk).update(is_active=False)
        self.client.post('/coupons/salesman/shops/add-from-biz/', {'biz_id': 'BIZ123456'})
        self.assertFalse(Shop.objects.exists())

    def test_anonymous_customer_cannot_activate_or_spin(self):
        shop = self.link_shop()
        self.distribute(shop)
        self.client.logout()
        for path, data in [('/coupons/activate/', {'code': 'OPC-000100'}),
                           ('/coupons/api/spin/', {})]:
            response = self.client.post(path, data)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith('/login/'))
        self.assertFalse(Coupon.objects.exclude(status='available').exists())
        self.assertFalse(PointsWallet.objects.exists())
