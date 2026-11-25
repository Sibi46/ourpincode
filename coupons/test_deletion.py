from unittest.mock import patch
from django.test import Client, TestCase
from django.utils import timezone
from jobs.models import User, CompanyProfile, AdminActivity
from .models import Salesman,Shop,CouponBatch,Coupon,PointsWallet,MonthlyDraw,LuckyDrawEntry


class CouponDeletionTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_user('delete-admin',admin_role='super_admin')
        self.staff=User.objects.create_user('delete-staff',is_staff=True)
        self.owner=User.objects.create_user('delete-business',user_type='company')
        CompanyProfile.objects.create(user=self.owner,company_name='Delete Store')
        self.seller=User.objects.create_user('delete-salesman',password='salesman-password')
        self.sm=Salesman.objects.create(user=self.seller)
        self.shop=Shop.objects.create(salesman=self.sm,business=self.owner,name='Delete Store',pincode='600073')
        self.batch=CouponBatch.objects.create(shop=self.shop,salesman=self.sm,quantity=1,
            start_number=1,end_number=1,category='S')
        self.coupon=Coupon.objects.create(batch=self.batch,number=1,code='opcs000001')
        self.client.force_login(self.admin)

    def url(self,kind='coupon'):
        return f'/coupons/admin/{"coupons" if kind=="coupon" else "salesmen"}/{self.coupon.pk if kind=="coupon" else self.sm.pk}/delete/'

    def review(self,kind='coupon'):
        response=self.client.get(self.url(kind))
        self.assertEqual(response.status_code,200)
        return response.context['review_token']

    def delete(self,kind='coupon'):
        return self.client.post(self.url(kind),{'confirmation':'DELETE','review_token':self.review(kind)})

    def test_get_is_read_only_and_post_requires_typed_confirmation_and_review(self):
        token=self.review()
        self.coupon.refresh_from_db()
        self.assertIsNone(self.coupon.deleted_at)
        self.assertEqual(self.client.post(self.url(),{'confirmation':'DELETE'}).status_code,409)
        self.assertEqual(self.client.post(self.url(),{'confirmation':'NO','review_token':token}).status_code,400)
        self.coupon.refresh_from_db()
        self.assertIsNone(self.coupon.deleted_at)

    def test_only_super_admin_gets_delete_actions_and_permissions(self):
        for user in [self.staff,self.owner,self.seller]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url()).status_code,403)
            self.assertEqual(self.client.post(self.url('salesman'),{'confirmation':'DELETE'}).status_code,403)
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get('/coupons/admin/coupons/'),self.url())
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/coupons/admin/coupons/'),self.url())
        self.assertContains(self.client.get('/coupons/admin/salesmen/'),self.url('salesman'))

    def test_csrf_protects_delete(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.admin)
        self.assertEqual(client.post(self.url(),{'confirmation':'DELETE','review_token':self.review()}).status_code,403)
        self.coupon.refresh_from_db()
        self.assertIsNone(self.coupon.deleted_at)

    def test_deleted_coupon_is_hidden_blocked_and_number_stays_reserved(self):
        self.assertEqual(self.delete().status_code,302)
        self.coupon.refresh_from_db()
        self.assertIsNotNone(self.coupon.deleted_at)
        self.assertEqual(self.coupon.status,'cancelled')
        self.assertNotContains(self.client.get('/coupons/admin/coupons/'),self.coupon.code)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(f'/employer/coupons/{self.coupon.pk}/').status_code,404)
        self.client.post('/coupons/activate/',{'category':'S','number':'1'})
        self.assertNotIn('pending_coupon',self.client.session)
        session=self.client.session;session['pending_coupon']=self.coupon.pk;session.save()
        self.assertEqual(self.client.post('/coupons/api/spin/').status_code,400)
        self.client.force_login(self.seller)
        self.client.post('/coupons/salesman/give-coupons/',{
            'shop_id':self.shop.pk,'category':'G','start_number':'1','end_number':'1'})
        self.assertEqual(Coupon.objects.count(),1)
        self.assertEqual(CouponBatch.objects.count(),1)

    def test_earned_points_and_winning_draw_entry_are_preserved(self):
        self.coupon.status='activated';self.coupon.activated_by=self.owner
        self.coupon.activated_at=timezone.now();self.coupon.points_awarded=20;self.coupon.save()
        wallet=PointsWallet.get_or_create_for(self.owner);wallet.credit(20,'Earned coupon points',coupon=self.coupon)
        draw=MonthlyDraw.objects.create(month=timezone.localdate().replace(day=1),prize='A gift')
        entry=LuckyDrawEntry.objects.create(draw=draw,coupon=self.coupon,customer=self.owner)
        draw.winner=entry;draw.save()
        self.assertEqual(self.delete().status_code,302)
        wallet.refresh_from_db();draw.refresh_from_db()
        self.assertEqual(wallet.balance,20)
        self.assertEqual(wallet.transactions.count(),1)
        self.assertEqual(draw.winner_id,entry.pk)
        self.assertTrue(LuckyDrawEntry.objects.filter(pk=entry.pk).exists())

    def test_deleting_salesman_disables_access_without_removing_issued_coupons(self):
        self.assertEqual(self.delete('salesman').status_code,302)
        self.sm.refresh_from_db()
        self.assertFalse(self.sm.is_active)
        self.assertIsNotNone(self.sm.deleted_at)
        self.assertTrue(User.objects.filter(pk=self.seller.pk).exists())
        self.assertTrue(Shop.objects.filter(pk=self.shop.pk).exists())
        self.assertTrue(CouponBatch.objects.filter(pk=self.batch.pk).exists())
        self.coupon.refresh_from_db();self.assertEqual(self.coupon.status,'available')
        self.assertNotContains(self.client.get('/coupons/admin/salesmen/'),self.url('salesman'))
        self.assertEqual(self.client.post(f'/coupons/admin/salesmen/{self.sm.pk}/',{'action':'toggle'}).status_code,404)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get('/coupons/salesman/').url,'/coupons/salesman/login/')
        self.client.force_login(self.owner)
        self.client.post('/coupons/activate/',{'category':'S','number':'1'})
        self.assertEqual(self.client.session['pending_coupon'],self.coupon.pk)

    def test_changed_or_other_admin_review_cannot_be_reused(self):
        token=self.review()
        self.coupon.status='expired';self.coupon.save()
        self.assertEqual(self.client.post(self.url(),{'confirmation':'DELETE','review_token':token}).status_code,409)
        token=self.review()
        other=User.objects.create_user('another-admin',admin_role='super_admin')
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url(),{'confirmation':'DELETE','review_token':token}).status_code,409)

    def test_delete_is_audited_and_retry_has_no_duplicate_effect(self):
        self.delete()
        self.assertEqual(AdminActivity.objects.filter(action='delete_coupon').count(),1)
        self.assertEqual(self.client.post(self.url(),{'confirmation':'DELETE'}).status_code,404)
        self.assertEqual(AdminActivity.objects.filter(action='delete_coupon').count(),1)

    def test_audit_failure_rolls_back_deletion(self):
        token=self.review()
        with patch('coupons.deletion.AdminActivity.objects.create',side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url(),{'confirmation':'DELETE','review_token':token})
        self.coupon.refresh_from_db()
        self.assertIsNone(self.coupon.deleted_at)
        self.assertEqual(self.coupon.status,'available')
