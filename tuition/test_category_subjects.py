from django.test import TestCase
from . import forms, models as m, tests as fixtures


class CategorySubjectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def data(self):
        return dict(kind='teacher', name='Teacher', description='Classes', experience=0,
            min_age=0, max_age=100, mode='offline', pincode='600073', phone='9876543210',
            categories=['sports', 'music'], category_sports='Cricket,Football',
            category_music='Piano,Guitar', category_fitness='Ignored')

    def test_save_and_edit_preserve_category_mapping_and_search_subjects(self):
        form = forms.TeacherForm(self.data(), instance=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        teacher = form.save()
        teacher.refresh_from_db()
        self.assertEqual(teacher.category_subjects, {'sports': ['Cricket', 'Football'], 'music': ['Piano', 'Guitar']})
        self.assertEqual(set(teacher.subjects.values_list('name', flat=True)), {'Cricket', 'Football', 'Piano', 'Guitar'})
        edit = forms.TeacherForm(instance=teacher)
        self.assertEqual(edit.initial['category_music'], 'Piano,Guitar')
        self.assertEqual(edit.initial['new_subjects'], '')

    def test_disabled_and_excess_subjects_rejected(self):
        m.Subject.objects.create(name='Blocked', slug='blocked', active=False)
        for names in ('Blocked', ','.join('Sport' + str(i) for i in range(11))):
            form = forms.TeacherForm({**self.data(), 'category_sports': names}, instance=self.teacher)
            self.assertFalse(form.is_valid())
            self.assertIn('category_sports', form.errors)
