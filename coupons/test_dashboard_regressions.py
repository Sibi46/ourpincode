from django.test import TestCase
from django.utils import timezone
from jobs.models import User
from .models import Salesman, Shop, CouponBatch, Coupon


class CouponDashboardRegressionTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_user('dashboard-admin',is_staff=True)
        self.seller=User.objects.create_user('dashboard-salesman')
        self.salesman=Salesman.objects.create(user=self.seller)
        self.shop=Shop.objects.create(salesman=self.salesman,name='Dashboard Shop',pincode='600073')
        self.batch=CouponBatch.objects.create(shop=self.shop,salesman=self.salesman,quantity=2,start_number=1,end_number=2)

    def test_admin_dashboard_renders_activation_without_customer_account(self):
        Coupon.objects.create(code='OPC-000001',number=1,batch=self.batch,status='activated',
                              activated_by=None,activated_at=timezone.now(),points_awarded=25)
        self.client.force_login(self.admin)
        response=self.client.get('/coupons/admin/')
        self.assertContains(response,'Account unavailable')
        self.assertContains(response,'OPC-000001')
        self.assertEqual(response.context['total_activated'],1)

    def test_customer_deletion_does_not_break_activation_history(self):
        customer=User.objects.create_user('former-customer')
        coupon=Coupon.objects.create(code='OPC-000001',number=1,batch=self.batch,status='activated',
                                    activated_by=customer,activated_at=timezone.now())
        customer.delete()
        coupon.refresh_from_db()
        self.assertIsNone(coupon.activated_by)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/coupons/admin/'),'OPC-000001')

    def test_populated_salesman_dashboard_only_counts_own_distribution(self):
        Coupon.objects.create(code='OPC-000001',number=1,batch=self.batch,status='activated')
        other=Salesman.objects.create(user=User.objects.create_user('other-salesman'))
        other_shop=Shop.objects.create(salesman=other,name='Other Shop',pincode='600073')
        CouponBatch.objects.create(shop=other_shop,salesman=other,quantity=8,start_number=3,end_number=10)
        self.client.force_login(self.seller)
        response=self.client.get('/coupons/salesman/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Dashboard Shop')
        self.assertNotContains(response,'Other Shop')
        self.assertEqual(response.context['total_shops'],1)
        self.assertEqual(response.context['total_given'],2)
        self.assertEqual(response.context['activated'],1)

    def test_normal_user_cannot_open_coupon_admin(self):
        self.client.force_login(self.seller)
        response=self.client.get('/coupons/admin/')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,'/coupons/admin/login/')
