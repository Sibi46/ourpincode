from django.test import TestCase
from django.urls import reverse
from . import forms, models as m, tests as fixtures


class RegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def test_registration_template_has_no_coordinate_fields(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('tuition:register'))
        self.assertTemplateUsed(response, 'tuition/register.html')
        for name in ('latitude', 'longitude', 'location_source', 'radius_km'):
            self.assertNotContains(response, 'name="' + name + '"')
        self.assertContains(response, 'Location &amp; contact')
        self.assertEqual(set(forms.TeacherForm().fields), {field.name for _, fields in forms.TeacherForm().sections() for field in fields})

    def test_create_without_coordinates_and_show_invalid_fields(self):
        self.client.force_login(self.other)
        data = dict(kind='teacher', name='New tutor', description='Maths lessons', experience=1,
                    min_age=5, max_age=18, mode='offline', pincode='600001', phone='9000000000')
        invalid = self.client.post(reverse('tuition:register'), {**data, 'pincode': '123'})
        self.assertContains(invalid, 'Please check the highlighted fields')
        self.assertIn('pincode', invalid.context['form'].errors)
        response = self.client.post(reverse('tuition:register'), {**data, 'latitude': '12', 'longitude': '80'})
        self.assertEqual(response.status_code, 302)
        teacher = m.TeacherProfile.objects.get(name='New tutor')
        self.assertIsNone(teacher.latitude)
        self.assertIsNone(teacher.longitude)
        self.assertEqual(teacher.status, 'pending')

    def test_edit_preserves_coordinates_and_requires_owner(self):
        self.teacher.latitude = 12
        self.teacher.longitude = 80
        self.teacher.save()
        form = forms.TeacherForm(instance=self.teacher)
        data = {name: form[name].value() for name in form.fields if name not in ('subjects', 'service_pins')}
        data['name'] = 'Updated teacher'
        self.client.force_login(self.owner)
        url = reverse('tuition:teacher_edit', args=[self.teacher.uid])
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.latitude, 12)
        self.assertEqual(self.teacher.longitude, 80)
        self.client.force_login(self.other)
        self.assertIn(self.client.post(url, data).status_code, (403, 404))
