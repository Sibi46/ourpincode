from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from jobs.models import User
from .lucky_draw import select_winner
from .models import (Coupon, CouponBatch, LuckyDrawEntry, MonthlyDraw,
                     PointsWallet, Salesman, Shop, SpinWheelSlot)


class LuckyDrawTests(TestCase):
    def setUp(self):
        self.salesman = Salesman.objects.create(user=User.objects.create_user('salesman'))
        self.shop = Shop.objects.create(salesman=self.salesman, name='Shop')
        self.customer = User.objects.create_user('customer')
        self.admin = User.objects.create_user('admin', is_staff=True)
        self.batch = CouponBatch.objects.create(shop=self.shop, salesman=self.salesman,
                                               quantity=3, start_number=1, end_number=3)
        self.coupons = [Coupon.objects.create(batch=self.batch, number=n, code=f'OPC-{n:06d}')
                        for n in range(1, 4)]
        SpinWheelSlot.objects.create(label='25 points', points=25, probability=100)
        self.login(self.customer)

    def login(self, user):
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

    def spin(self, coupon):
        self.client.post('/coupons/activate/', {'code': coupon.code.lower()})
        return self.client.post('/coupons/api/spin/')

    def test_all_categories_assignment_and_existing_number_overlap(self):
        self.login(self.salesman.user)
        for number, category in enumerate('SGPC', 10):
            response = self.client.post('/coupons/salesman/give-coupons/', {
                'shop_id': self.shop.pk, 'start_number': number * 10,
                'end_number': number * 10 + 1, 'category': category,
            })
            self.assertEqual(response.status_code, 302)
            batch = CouponBatch.objects.get(start_number=number * 10)
            self.assertEqual(batch.category, category)
            self.assertEqual(batch.coupons.count(), 2)
            for coupon in batch.coupons.all():
                self.assertEqual(coupon.category, category)
                self.assertEqual(coupon.code, f'opc{category.lower()}{coupon.number:06d}')
            self.assertEqual(batch.start_code(), f'opc{category.lower()}{number * 10:06d}')
            self.assertEqual(batch.end_code(), f'opc{category.lower()}{number * 10 + 1:06d}')
        before = Coupon.objects.count()
        for category, start in [('X', 200), ('G', 1), ('P', 100)]:
            self.client.post('/coupons/salesman/give-coupons/', {
                'shop_id': self.shop.pk, 'start_number': start, 'end_number': start, 'category': category,
            })
        self.assertEqual(Coupon.objects.count(), before)
        self.assertEqual(self.batch.start_code(), 'OPC-000001')

    def test_category_rewards_and_case_insensitive_code(self):
        self.batch.category = 'G'
        self.batch.save()
        coupon = self.coupons[0]
        coupon.code = 'Gopc000001'
        coupon.save()
        SpinWheelSlot.objects.create(category='G', label='Gold gift', points=100,
                                     probability=100, is_surprise=True, surprise_gift_name='Gift')
        SpinWheelSlot.objects.create(category='S', label='Silver', points=50, probability=100)
        self.client.post('/coupons/activate/', {'code': 'gOPC000001'})
        page = self.client.get('/coupons/spin/')
        self.assertEqual([slot.label for slot in page.context['slots']], ['Gold gift'])
        result = self.client.post('/coupons/api/spin/').json()
        self.assertEqual(result['points'], 100)
        self.assertEqual(result['surprise_gift_name'], 'Gift')
        self.assertEqual(PointsWallet.objects.get(user=self.customer).balance, 100)

    def test_category_without_slots_uses_existing_rewards(self):
        self.batch.category = 'C'
        self.batch.save()
        self.assertEqual(self.spin(self.coupons[0]).json()['points'], 25)

    def test_one_use_one_entry_and_multiple_coupons_per_customer(self):
        coupon = self.coupons[0]
        data = self.spin(coupon).json()
        entry = LuckyDrawEntry.objects.get(pk=data['lucky_draw_entry_id'])
        self.assertEqual(entry.customer, self.customer)
        self.assertEqual(entry.coupon, coupon)
        self.assertEqual(entry.draw.month, timezone.localdate().replace(day=1))
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, Coupon.STATUS_USED)
        self.assertEqual(coupon.transactions.count(), 1)
        self.assertEqual(self.client.post('/coupons/api/spin/').status_code, 400)
        other = User.objects.create_user('other')
        self.login(other)
        session = self.client.session
        session['pending_coupon'] = coupon.pk  # A second customer's previously staged spin.
        session.save()
        self.assertEqual(self.client.post('/coupons/api/spin/').status_code, 400)
        self.assertEqual(LuckyDrawEntry.objects.count(), 1)
        self.assertFalse(PointsWallet.objects.filter(user=other).exists())
        self.login(self.customer)
        self.spin(self.coupons[1])
        self.assertEqual(LuckyDrawEntry.objects.count(), 2)
        self.assertEqual(MonthlyDraw.objects.count(), 1)
        self.assertEqual(PointsWallet.objects.get(user=self.customer).balance, 50)

    def test_invalid_expired_cancelled_and_used_do_not_enter(self):
        self.client.post('/coupons/activate/', {'code': self.coupons[0].code})
        self.client.post('/coupons/activate/', {'code': 'INVALID'})
        self.assertEqual(self.client.post('/coupons/api/spin/').status_code, 400)
        for coupon, status in zip(self.coupons, ['expired', 'cancelled', 'activated']):
            coupon.status = status
            coupon.save()
            self.assertEqual(self.spin(coupon).status_code, 400)
        self.assertFalse(LuckyDrawEntry.objects.exists())
        self.assertFalse(PointsWallet.objects.exists())

    def test_database_prevents_duplicate_entries_across_months(self):
        self.spin(self.coupons[0])
        previous = timezone.localdate().replace(day=1) - timedelta(days=1)
        draw = MonthlyDraw.objects.create(month=previous.replace(day=1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            LuckyDrawEntry.objects.create(draw=draw, coupon=self.coupons[0], customer=self.customer)

    def test_entry_failure_rolls_back_reward_and_usage(self):
        with patch('coupons.views.LuckyDrawEntry.objects.create', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                self.spin(self.coupons[0])
        self.coupons[0].refresh_from_db()
        self.assertEqual(self.coupons[0].status, Coupon.STATUS_AVAILABLE)
        self.assertFalse(PointsWallet.objects.exists())
        self.assertFalse(LuckyDrawEntry.objects.exists())
        self.assertFalse(MonthlyDraw.objects.exists())

    def test_local_month_boundary(self):
        # UTC August 31 is already September 1 in Asia/Kolkata.
        with patch('django.utils.timezone.now', return_value=datetime(2026, 8, 31, 19, tzinfo=dt_timezone.utc)):
            data = self.spin(self.coupons[0]).json()
        self.assertEqual(data['lucky_draw_month'], '2026-09-01')

    def past_draw(self):
        previous = timezone.localdate().replace(day=1) - timedelta(days=1)
        when = timezone.make_aware(datetime(previous.year, previous.month, 15, 12))
        with patch('django.utils.timezone.now', return_value=when):
            for coupon in self.coupons:
                self.spin(coupon)
        draw = MonthlyDraw.objects.get()
        draw.prize = 'Bicycle'
        draw.save()
        return draw

    def test_monthly_selection_valid_entries_only_and_no_redraw(self):
        draw = self.past_draw()
        Coupon.objects.filter(pk=self.coupons[0].pk).update(status='cancelled')
        with patch('coupons.lucky_draw.secrets.randbelow', return_value=1) as choose:
            selected = select_winner(draw.pk)
        choose.assert_called_once_with(2)
        self.assertEqual(selected.winner.coupon_id, self.coupons[2].pk)
        self.assertEqual(select_winner(draw.pk).winner_id, selected.winner_id)
        call_command('select_monthly_draws', stdout=StringIO())
        draw.refresh_from_db()
        self.assertEqual(draw.winner_id, selected.winner_id)

    def test_current_future_empty_and_unconfigured_draws_cannot_select(self):
        month = timezone.localdate().replace(day=1)
        for date in (month, (month + timedelta(days=32)).replace(day=1)):
            draw = MonthlyDraw.objects.create(month=date, prize='Gift')
            with self.assertRaises(ValueError):
                select_winner(draw.pk)
        past = MonthlyDraw.objects.create(month=(month - timedelta(days=1)).replace(day=1))
        with self.assertRaises(ValueError):
            select_winner(past.pk)
        past.prize = 'Gift'
        past.save()
        with self.assertRaises(ValueError):
            select_winner(past.pk)

    def test_scheduled_command_selects_completed_month(self):
        draw = self.past_draw()
        call_command('select_monthly_draws', stdout=StringIO())
        draw.refresh_from_db()
        self.assertIsNotNone(draw.winner_id)

    def test_winner_excludes_wrong_customer_and_wrong_month(self):
        draw = self.past_draw()
        other = User.objects.create_user('other')
        Coupon.objects.filter(pk=self.coupons[0].pk).update(activated_by=other)
        Coupon.objects.filter(pk=self.coupons[1].pk).update(activated_at=timezone.now())
        self.assertEqual(select_winner(draw.pk).winner.coupon_id, self.coupons[2].pk)

    def test_month_must_start_on_first_day(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MonthlyDraw.objects.create(month=timezone.localdate().replace(day=2))

    def test_admin_configuration_eligible_customers_selection_and_claim(self):
        draw = self.past_draw()
        self.assertEqual(self.client.post('/coupons/admin/lucky-draws/', {'action': 'select', 'draw_id': draw.pk}).status_code, 302)
        draw.refresh_from_db()
        self.assertIsNone(draw.winner_id)
        self.login(self.admin)
        url = '/coupons/admin/lucky-draws/'
        self.client.post(url, {'action': 'configure', 'month': draw.month.strftime('%Y-%m'), 'prize': 'Gold coin'})
        self.assertContains(self.client.get(f'{url}?draw={draw.pk}'), self.customer.username)
        self.assertContains(self.client.get(url), 'Gold coin')
        self.client.post(url, {'action': 'award', 'draw_id': draw.pk})
        draw.refresh_from_db()
        self.assertIsNone(draw.awarded_at)
        self.client.post(url, {'action': 'select', 'draw_id': draw.pk})
        self.client.post(url, {'action': 'award', 'draw_id': draw.pk})
        draw.refresh_from_db()
        self.assertIsNotNone(draw.winner_id)
        self.assertIsNotNone(draw.awarded_at)
        self.client.post(url, {'action': 'configure', 'month': draw.month.strftime('%Y-%m'), 'prize': 'Changed'})
        draw.refresh_from_db()
        self.assertEqual(draw.prize, 'Gold coin')

    def test_animation_only_revealed_by_success_response(self):
        self.client.post('/coupons/activate/', {'code': self.coupons[0].code})
        page = self.client.get('/coupons/spin/')
        self.assertContains(page, 'id="luckyDraw" hidden')
        self.assertContains(page, 'if(data.lucky_draw_entry_id)')
        self.assertFalse(LuckyDrawEntry.objects.exists())
