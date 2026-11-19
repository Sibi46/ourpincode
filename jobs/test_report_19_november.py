from django.test import TestCase, Client
from jobs.models import User, CompanyProfile, PaymentPlan, Wallet, WalletTransaction
from jobs.account import profile_features
from coupons.models import Salesman, Shop, CouponBatch, Coupon
from quiz.models import Quiz


class November19ReportTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user(username='report19',user_type='company')
        self.company=CompanyProfile.objects.create(user=self.owner,company_name='Test business')
        self.client.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')

    def test_account_services_excludes_sidebar_duplicates(self):
        names={x['name'] for x in profile_features(self.owner)}
        for duplicate in ['My dashboard','Business dashboard','Quiz','Billing','Wallet','Messages','Notifications','Advertise your business','Business coupons','Business gallery','Register Business','Job applications','Offers','Gift Vouchers']:
            self.assertNotIn(duplicate,names)
        self.assertIn('Shops and businesses',names)
        self.assertIn('Tuitions',names)
        response=self.client.get('/employer/dashboard/')
        for section in ['wallet','billing','business-profile','coupons','gallery','applications']:
            self.assertContains(response,f'data-sec="{section}"')

    def test_coupon_details_only_accessible_to_owning_business(self):
        seller=User.objects.create_user(username='report19-salesman')
        salesman=Salesman.objects.create(user=seller)
        shop=Shop.objects.create(business=self.owner,salesman=salesman,name='Local shop',pincode='600073')
        batch=CouponBatch.objects.create(shop=shop,salesman=salesman,quantity=1,start_number=1,end_number=1,category='S')
        coupon=Coupon.objects.create(batch=batch,code='opcs000001',number=1)
        url=f'/employer/coupons/{coupon.pk}/'
        self.assertContains(self.client.get('/employer/dashboard/'),url)
        response=self.client.get(url)
        for value in ['opcs000001','Silver','Local shop','Available','Not used yet']:
            self.assertContains(response,value)
        other=User.objects.create_user(username='report19-other',user_type='company')
        self.client.force_login(other,backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(self.client.get(url).status_code,404)

    def test_wallet_routes_explain_unavailability_without_changing_balance(self):
        wallet=Wallet.objects.create(user=self.owner,balance='125.00')
        for action in ['add-money','withdraw']:
            url=f'/wallet/{action}/'
            self.assertContains(self.client.get(url),'temporarily unavailable')
            self.assertEqual(self.client.post(url,{'amount':'500'}).status_code,405)
        wallet.refresh_from_db();self.assertEqual(str(wallet.balance),'125.00')
        self.assertFalse(WalletTransaction.objects.filter(wallet=wallet).exists())
        self.assertEqual(Client().get('/wallet/add-money/').status_code,302)

    def test_empty_quiz_has_one_create_action(self):
        response=self.client.get('/quiz/')
        self.assertContains(response,'Create First Quiz')
        self.assertNotContains(response,'+ New Quiz')
        Quiz.objects.create(created_by=self.owner,title='Test quiz')
        response=self.client.get('/quiz/')
        self.assertContains(response,'+ New Quiz')
        self.assertNotContains(response,'Create First Quiz')

    def test_published_plans_show_prices_features_and_valid_details_link(self):
        plan=PaymentPlan.objects.create(name='Test plan',plan_type='employer_basic',price=99,duration_days=30,job_posts=5,features='Five posts\nSupport')
        response=self.client.get('/employer/dashboard/')
        self.assertContains(response,'Test plan');self.assertContains(response,'Five posts')
        self.assertContains(self.client.get(f'/subscription/buy/{plan.pk}/'),'99.00')
        plan.is_active=False;plan.save()
        self.assertEqual(self.client.get(f'/subscription/buy/{plan.pk}/').status_code,404)
        self.assertContains(self.client.get('/employer/dashboard/'),'No employer plans are published yet')
