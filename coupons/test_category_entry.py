from django.test import TestCase

from jobs.models import User
from .models import Coupon, CouponBatch, Salesman, Shop, LuckyDrawEntry, PointsWallet, coupon_code


class CategoryEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('customer')
        salesman = Salesman.objects.create(user=User.objects.create_user('salesman'))
        shop = Shop.objects.create(salesman=salesman, name='Shop')
        self.coupons = {}
        for number, category in enumerate('SGPC', 1):
            batch = CouponBatch.objects.create(shop=shop, salesman=salesman, quantity=1,
                                               start_number=number, end_number=number, category=category)
            self.coupons[category] = Coupon.objects.create(batch=batch, number=number,
                                                          code=coupon_code(number, category))
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')

    def test_dropdown_and_numeric_field(self):
        response = self.client.get('/coupons/activate/')
        for label in ['Silver (S)', 'Gold (G)', 'Points (P)', 'Complimentary (C)']:
            self.assertContains(response, label)
        self.assertContains(response, 'inputmode="numeric"')
        self.assertContains(response, 'id="couponPrefix"')

    def test_all_categories_accept_number_only_with_or_without_padding(self):
        for category, coupon in self.coupons.items():
            for number in [str(coupon.number), f'{coupon.number:06d}']:
                with self.subTest(category=category, number=number):
                    response = self.client.post('/coupons/activate/', {'category': category, 'number': number})
                    self.assertRedirects(response, '/coupons/spin/', fetch_redirect_response=False)
                    self.assertEqual(self.client.session['pending_coupon'], coupon.pk)
        self.assertFalse(LuckyDrawEntry.objects.exists())
        self.assertFalse(PointsWallet.objects.exists())

    def test_invalid_category_numbers_and_wrong_category_clear_pending_coupon(self):
        invalid = [
            {'category': 'G', 'number': '1'}, {'category': 'X', 'number': '1'},
            {'category': '', 'number': '1'}, {'number': '1'}, {'category': 'S'},
            *[{'category': 'S', 'number': number} for number in ['', '0', '-1', '1.0', '1e0',
                                                              'opcs000001', '1-2', '2147483648', '9'*50]],
        ]
        for data in invalid:
            with self.subTest(data=data):
                self.client.post('/coupons/activate/', {'category': 'S', 'number': '1'})
                response = self.client.post('/coupons/activate/', data)
                self.assertIn(response.status_code, [200, 302])
                self.assertNotIn('pending_coupon', self.client.session)
                self.assertEqual(self.client.post('/coupons/api/spin/').status_code, 400)
        self.assertFalse(LuckyDrawEntry.objects.exists())

    def test_category_number_spin_keeps_one_time_usage_and_entry(self):
        self.client.post('/coupons/activate/', {'category': 'S', 'number': '000001'})
        result = self.client.post('/coupons/api/spin/')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['coupon_code'], 'opcs000001')
        self.client.post('/coupons/activate/', {'category': 'S', 'number': '1'})
        self.assertEqual(self.client.post('/coupons/api/spin/').status_code, 400)
        self.assertEqual(LuckyDrawEntry.objects.count(), 1)
        self.assertEqual(PointsWallet.objects.get(user=self.user).balance, 10)

    def test_old_category_codes_keep_printed_format_and_numeric_entry(self):
        coupon = self.coupons['G']
        coupon.code = 'Gopc000002'
        coupon.save()
        self.assertEqual(coupon.batch.start_code(), 'Gopc000002')
        self.assertEqual(coupon.batch.end_code(), 'Gopc000002')
        self.client.post('/coupons/activate/', {'category': 'G', 'number': '2'})
        self.assertEqual(self.client.session['pending_coupon'], coupon.pk)
        self.client.post('/coupons/activate/', {'code': 'gOPC000002'})
        self.assertEqual(self.client.session['pending_coupon'], coupon.pk)

    def test_new_full_code_is_case_insensitive_too(self):
        self.client.post('/coupons/activate/', {'code': 'OPCS000001'})
        self.assertEqual(self.client.session['pending_coupon'], self.coupons['S'].pk)
