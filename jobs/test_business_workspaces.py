import uuid
from django.core import signing
from django.test import TestCase, Client
from django.urls import reverse
from jobs.models import User, CompanyProfile, ShopProfile, ManagedBusiness, Wallet, Job
from jobs.account_deletion import make_plan, perform_deletion


class BusinessWorkspaceTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user(username='workspace-owner',password='original-password',phone='9000000031',user_type='shop',pincode='600100',first_name='Mary')
        self.primary=CompanyProfile.objects.create(user=self.owner,company_name='Original Ice Cream Shop',industry='Ice Cream Shop')
        self.shop=ShopProfile.objects.create(user=self.owner,shop_name='Original Ice Cream Shop')
        self.wallet=Wallet.objects.create(user=self.owner,balance=125)
        self.client.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')

    def data(self, **changes):
        token=self.client.get(reverse('add_another_business')).context['form']['token'].value()
        return {'name':'Second Bakery','business_type':'shop','category':'Bakery','pincode':'600073','area':'Selaiyur','address':'Test street','token':token,**changes}

    def add(self):
        data=self.data();response=self.client.post(reverse('add_another_business'),data)
        self.assertEqual(response.status_code,302)
        return ManagedBusiness.objects.get(owner=self.owner),data

    def test_add_preserves_original_and_switches_into_isolated_business(self):
        link,data=self.add();child=link.account
        self.primary.refresh_from_db();self.owner.refresh_from_db();self.wallet.refresh_from_db()
        self.assertEqual((self.primary.company_name,self.primary.industry),('Original Ice Cream Shop','Ice Cream Shop'))
        self.assertEqual((self.owner.phone,self.owner.pincode),('9000000031','600100'))
        self.assertTrue(self.owner.check_password('original-password'))
        self.assertEqual(self.wallet.balance,125)
        self.assertTrue(child.salesman_biz_id);self.assertFalse(child.has_usable_password());self.assertFalse(child.is_staff);self.assertFalse(child.admin_role)
        self.assertEqual((child.company.company_name,child.company.industry,child.pincode),('Second Bakery','Bakery','600073'))
        self.assertEqual(child.shop.shop_name,'Second Bakery')
        response=self.client.get('/employer/dashboard/')
        self.assertEqual(response.context['request'].user.pk,child.pk)
        self.assertEqual(response.context['wallet'].balance,0)
        self.assertContains(response,'+ Add another business')
        self.assertContains(response,'Switch to Original Ice Cream Shop')
        self.client.post(reverse('switch_business',args=[self.owner.pk]))
        self.assertEqual(self.client.get('/employer/dashboard/').context['request'].user.pk,self.owner.pk)
        self.client.post(reverse('switch_business',args=[child.pk]))
        self.assertEqual(self.client.get('/employer/dashboard/').context['request'].user.pk,child.pk)

    def test_repeat_submission_is_idempotent(self):
        data=self.data();self.client.post(reverse('add_another_business'),data)
        self.client.post(reverse('add_another_business'),data)
        self.assertEqual(ManagedBusiness.objects.filter(owner=self.owner).count(),1)

    def test_cannot_switch_another_owners_business_or_use_get(self):
        link,data=self.add()
        other=User.objects.create_user(username='workspace-other',user_type='company')
        self.assertEqual(self.client.post(reverse('switch_business',args=[other.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('switch_business',args=[self.owner.pk])).status_code,405)
        token=signing.dumps({'owner':other.pk,'nonce':str(uuid.uuid4())},salt='add-business')
        self.assertEqual(self.client.post(reverse('add_another_business'),{**data,'token':token}).status_code,403)

    def test_child_session_requires_owner_grant_and_owner_password_changes_revoke_it(self):
        link,data=self.add()
        direct=Client();direct.force_login(link.account,backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(direct.get('/employer/dashboard/').status_code,302)
        self.assertNotIn('_auth_user_id',direct.session)
        self.owner.set_password('changed-password');self.owner.save()
        self.assertEqual(self.client.get('/employer/dashboard/').status_code,302)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_inactive_owner_or_child_cannot_be_used(self):
        link,data=self.add()
        self.client.post(reverse('switch_business',args=[self.owner.pk]))
        link.account.is_active=False;link.account.save()
        self.assertEqual(self.client.post(reverse('switch_business',args=[link.account_id])).status_code,404)
        link.account.is_active=True;link.account.save()
        self.client.post(reverse('switch_business',args=[link.account_id]))
        self.owner.is_active=False;self.owner.save()
        self.assertEqual(self.client.get('/employer/dashboard/').status_code,302)

    def test_invalid_registration_changes_nothing(self):
        data=self.data(category='Invalid category',pincode='123')
        self.assertEqual(self.client.post(reverse('add_another_business'),data).status_code,200)
        self.assertFalse(ManagedBusiness.objects.exists())
        self.primary.refresh_from_db();self.assertEqual(self.primary.company_name,'Original Ice Cream Shop')

    def test_super_admin_delete_all_includes_owned_workspaces_but_not_other_users(self):
        link,data=self.add()
        admin=User.objects.create_user(username='workspace-admin',admin_role='super_admin')
        unrelated=User.objects.create_user(username='workspace-unrelated')
        plan=make_plan(admin,self.owner)
        self.assertEqual(plan['nodes'][User],{self.owner.pk,link.account_id})
        perform_deletion(admin,self.owner.pk,plan['fingerprint'])
        self.assertFalse(User.objects.filter(pk__in=[self.owner.pk,link.account_id]).exists())
        self.assertTrue(User.objects.filter(pk=unrelated.pk).exists())

    def test_registered_business_page_and_my_accounts_have_add_button(self):
        self.assertContains(self.client.get('/register/?type=shop'),'Add another business')
        self.assertContains(self.client.get('/my-accounts/'),'Add another business')
        self.assertEqual(Client().get(reverse('add_another_business')).status_code,302)

    def test_switch_requires_csrf_and_tampered_grant_is_rejected(self):
        link,data=self.add()
        self.client.post(reverse('switch_business',args=[self.owner.pk]))
        csrf=Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner,backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(csrf.post(reverse('switch_business',args=[link.account_id])).status_code,403)
        self.client.post(reverse('switch_business',args=[link.account_id]))
        session=self.client.session;session['managed_business_owner']='tampered';session.save()
        self.assertEqual(self.client.get('/employer/dashboard/').status_code,302)
        self.assertNotIn('_auth_user_id',self.client.session)
