from django.test import TestCase
from jobs.models import User, CompanyProfile, ShopProfile, Industry
from jobs.account import BusinessDetailsForm


class BusinessCategoryTests(TestCase):
    def test_registration_lists_categories_and_shop_category_is_saved(self):
        response=self.client.get('/register/?type=company')
        for value in ['Ice Cream Shop','Bakery','Hair Salon','Mobile Repair Shop','Other']:
            self.assertContains(response, f'value="{value}"')
        response=self.client.post('/register/process/',{'user_type':'shop','phone':'9000000091','password':'new-password','owner_name':'Mary Jane','org_name':'Cool Treats','pincode':'600100','industry':'Ice Cream Shop'},HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(response.json()['success'],response.json())
        user=User.objects.get(phone='9000000091')
        self.assertEqual(CompanyProfile.objects.get(user=user).industry,'Ice Cream Shop')
        self.assertEqual(ShopProfile.objects.get(user=user).shop_type,'Ice Cream Shop')
        form=BusinessDetailsForm(instance=user.company)
        self.assertEqual(form['industry'].value(),'Ice Cream Shop')
        self.assertTrue(form.fields['industry'].valid_value('Ice Cream Shop'))

    def test_invalid_category_rejected_before_account_creation(self):
        response=self.client.post('/register/process/',{'user_type':'company','phone':'9000000092','password':'new-password','owner_name':'Mary Jane','org_name':'Test','industry':'12345'},HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(response.json()['success'])
        self.assertFalse(User.objects.filter(phone='9000000092').exists())

    def test_admin_categories_and_legacy_profiles_remain_supported(self):
        Industry.objects.create(name='Local Services')
        self.assertContains(self.client.get('/register/?type=company'),'Local Services')
        owner=User.objects.create_user(username='category-owner',user_type='company')
        company=CompanyProfile.objects.create(user=owner,company_name='Legacy Store',industry='Legacy Category')
        form=BusinessDetailsForm(instance=company)
        for value in ['Ice Cream Shop','Retail','Local Services','Legacy Category']:
            self.assertTrue(form.fields['industry'].valid_value(value))
