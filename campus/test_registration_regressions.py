from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from jobs.models import User
from .models import Institution,PlacementOfficer,Department,Student,CampusCompany
from .forms import InstitutionRegistrationForm


class CampusRegistrationRegressionTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('campus-register-owner',first_name='Existing')
        self.client.force_login(self.user)
        self.institute_data={'name':'Lotus Institute','affiliation':'Anna University','city':'Chennai',
            'district':'Chengalpattu','state':'Tamil Nadu','po_name':'Ravi Kumar','website':'',
            'institution_type':['engineering'],'phone':'9876543210','po_phone':'9876543210','pincode':'600073'}
        session=self.client.session
        session['campus_otp_verified']=True;session['campus_otp_phone']='9876543210';session.save()

    def test_numbers_in_each_institute_field_are_rejected_without_writes(self):
        for field in ['name','affiliation','city','district','state','po_name']:
            for value in ['Name123','１２３','Name ௧']:
                response=self.client.post(reverse('campus_institution_register'),{**self.institute_data,field:value})
                self.assertEqual(response.status_code,400,(field,value))
                self.assertIn(field,response.context['registration_form'].errors)
                self.assertFalse(Institution.objects.exists())
                self.assertFalse(PlacementOfficer.objects.exists())
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name,'Existing')

    def test_valid_institution_allows_blank_website_and_saves_officer_name(self):
        response=self.client.post(reverse('campus_institution_register'),self.institute_data)
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,reverse('campus_po_dashboard'))
        institute=Institution.objects.get()
        self.assertEqual(institute.website,'')
        self.assertEqual(institute.status,'pending')
        self.assertEqual(PlacementOfficer.objects.get().institution,institute)
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_full_name(),'Ravi Kumar')
        self.assertNotIn('campus_otp_verified',self.client.session)

    def test_unicode_and_legitimate_punctuation_are_supported(self):
        form=InstitutionRegistrationForm({**self.institute_data,'name':"St. Mary's Arts & Science",
            'affiliation':'தமிழ்நாடு பல்கலைக்கழகம்','po_name':'தமிழ் செல்வன்'})
        self.assertTrue(form.is_valid(),form.errors)

    def test_invalid_registration_preserves_values_type_and_verified_phone(self):
        response=self.client.post(reverse('campus_institution_register'),{**self.institute_data,'city':'Chennai123'})
        self.assertEqual(response.status_code,400)
        self.assertContains(response,'value="Lotus Institute"',status_code=400)
        self.assertContains(response,'value="Chennai123"',status_code=400)
        self.assertContains(response,'var phoneVerified = true;',status_code=400)
        self.assertIn('engineering',response.context['selected_types'])

    def test_otp_is_still_required_and_phone_must_match(self):
        for data in [{**self.institute_data,'phone':'9000000000'},self.institute_data]:
            if data==self.institute_data:
                session=self.client.session;session.pop('campus_otp_verified',None);session.save()
            self.client.post(reverse('campus_institution_register'),data)
            self.assertFalse(Institution.objects.exists())

    def test_institution_registration_is_atomic_and_repeated_submit_is_safe(self):
        with patch('campus.views.audit',side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('campus_institution_register'),self.institute_data)
        self.assertFalse(Institution.objects.exists())
        self.assertFalse(PlacementOfficer.objects.exists())
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name,'Existing')
        self.client.post(reverse('campus_institution_register'),self.institute_data)
        self.assertEqual(self.client.post(reverse('campus_institution_register'),self.institute_data).status_code,302)
        self.assertEqual(Institution.objects.count(),1)

    def test_company_numeric_contact_is_rejected_and_blank_optional_fields_work(self):
        url=reverse('campus_company_register')
        data={'company_name':'Local Company','phone':'9876543210','contact_person':'Ravi 123'}
        response=self.client.post(url,data)
        self.assertEqual(response.status_code,400)
        self.assertFalse(CampusCompany.objects.exists())
        self.assertContains(response,'Website (optional)',status_code=400)
        self.assertContains(response,'Logo (optional)',status_code=400)
        response=self.client.post(url,{**data,'contact_person':'Ravi Kumar','website':''})
        self.assertEqual(response.status_code,302)
        company=CampusCompany.objects.get()
        self.assertEqual(company.contact_person,'Ravi Kumar')
        self.assertFalse(company.website)
        self.assertFalse(company.logo)

    def test_missing_login_cannot_create_institution(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse('campus_institution_register'),self.institute_data).status_code,302)
        self.assertFalse(Institution.objects.exists())


class PlacementNavigationRegressionTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('po-navigation')
        self.other=User.objects.create_user('other-po')
        self.institute=Institution.objects.create(name='Our Institute',pincode='600073',status='pending')
        other=Institution.objects.create(name='Other Institute',pincode='600100')
        PlacementOfficer.objects.create(user=self.user,institution=self.institute)
        PlacementOfficer.objects.create(user=self.other,institution=other)
        self.dept=Department.objects.create(institution=self.institute,name='Our Department')
        other_dept=Department.objects.create(institution=other,name='Other Department')
        Student.objects.create(user=User.objects.create_user('our-student',first_name='Our Student'),
                               institution=self.institute,department=self.dept)
        Student.objects.create(user=User.objects.create_user('other-student',first_name='Other Student'),
                               institution=other,department=other_dept)
        self.client.force_login(self.user)

    def test_dashboard_links_lists_and_add_pages_work(self):
        dashboard=self.client.get(reverse('campus_po_dashboard'))
        for name in ['campus_po_departments','campus_po_students']:
            url=reverse(name)
            self.assertContains(dashboard,url)
            self.assertEqual(self.client.get(url).status_code,200)
        for name in ['campus_po_department_add','campus_po_student_add','campus_po_hod_add']:
            self.assertEqual(self.client.get(reverse(name)).status_code,200)
        self.assertContains(self.client.get(reverse('campus_po_departments')),reverse('campus_po_department_add'))
        self.assertContains(self.client.get(reverse('campus_po_students')),reverse('campus_po_student_add'))

    def test_old_singular_add_links_remain_usable(self):
        for path in ['department','student','hod']:
            self.assertEqual(self.client.get(f'/campus/po/{path}/add/').status_code,200)

    def test_department_and_student_creation_work_from_the_dashboard_forms(self):
        response=self.client.post(reverse('campus_po_department_add'),{'name':'New Department','code':'NEW'})
        self.assertEqual(response.status_code,302)
        department=Department.objects.get(name='New Department')
        self.assertEqual(department.institution,self.institute)
        page=self.client.get(reverse('campus_po_student_add'))
        self.assertContains(page,'name="full_name"')
        self.assertContains(page,'name="department_id"')
        response=self.client.post(reverse('campus_po_student_add'),{
            'full_name':'New Student','phone':'9000000001','department_id':department.pk,
            'roll_number':'NEW001','course':'Engineering','year':'1'})
        self.assertEqual(response.status_code,302)
        student=Student.objects.get(roll_number='NEW001')
        self.assertEqual(student.institution,self.institute)
        self.assertEqual(student.department,department)

    def test_student_cannot_be_added_to_another_institution_department(self):
        department=Department.objects.get(name='Other Department')
        response=self.client.post(reverse('campus_po_student_add'),{
            'full_name':'New Student','phone':'9000000002','department_id':department.pk})
        self.assertEqual(response.status_code,404)
        self.assertFalse(User.objects.filter(phone='9000000002').exists())

    def test_institution_lists_do_not_expose_another_institution(self):
        response=self.client.get(reverse('campus_po_departments'))
        self.assertContains(response,'Our Department')
        self.assertNotContains(response,'Other Department')
        response=self.client.get(reverse('campus_po_students'))
        self.assertContains(response,'Our Student')
        self.assertNotContains(response,'Other Student')
