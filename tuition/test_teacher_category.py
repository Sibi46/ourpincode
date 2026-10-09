from django.test import SimpleTestCase
from django.core.exceptions import ValidationError
from .forms import TeacherForm
from .models import TeacherProfile


class TeacherCategoryTests(SimpleTestCase):
    def test_category_precedes_subjects_and_supports_requested_choices(self):
        form = TeacherForm()
        sections = list(form.sections())
        titles = [title for title, fields in sections]
        self.assertEqual(titles.index('Teaching category') + 1, titles.index('What you teach'))
        choices = dict(form.fields['category'].choices)
        for value in ('sports', 'fitness', 'cooking', 'skills'):
            self.assertIn(value, choices)
            self.assertEqual(form.fields['category'].clean(value), value)

    def test_existing_profiles_allow_blank_and_invalid_values_are_rejected(self):
        field = TeacherForm().fields['category']
        self.assertEqual(field.clean(''), '')
        with self.assertRaises(ValidationError):
            field.clean('invalid-category')
        self.assertEqual(TeacherProfile().category, '')
        self.assertEqual(TeacherForm(instance=TeacherProfile(category='sports')).initial['category'], 'sports')
