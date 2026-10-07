from django.test import TestCase
from django.urls import reverse
from . import models as m, forms, tests as fixtures


class SubjectEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.TuitionTests.setUpTestData.__func__(cls)

    def profile_data(self, names):
        return dict(kind='teacher', name='Subject teacher', description='Classes', experience=1,
                    min_age=5, max_age=18, mode='online', pincode='600001', phone='9000000000', new_subjects=names)

    def test_teacher_can_type_and_reuse_subjects(self):
        existing = m.Subject.objects.create(name='Maths', slug='maths')
        self.client.force_login(self.other)
        response = self.client.post(reverse('tuition:register'), self.profile_data('maths, Piano, Piano, தமிழ்'))
        self.assertEqual(response.status_code, 302)
        teacher = m.TeacherProfile.objects.get(name='Subject teacher')
        self.assertEqual(set(teacher.subjects.values_list('name', flat=True)), {'Maths', 'Piano', 'தமிழ்'})
        self.assertIn(existing, teacher.subjects.all())
        self.assertEqual(teacher.status, 'pending')

    def test_invalid_form_does_not_create_subjects(self):
        form = forms.TeacherForm({**self.profile_data('New subject'), 'pincode': '1'})
        self.assertFalse(form.is_valid())
        self.assertFalse(m.Subject.objects.filter(name='New subject').exists())

    def test_disabled_and_oversized_subjects_rejected(self):
        m.Subject.objects.create(name='Disabled', slug='disabled', active=False)
        for text in ('disabled', 'a'*101, ','.join('Subject '+str(i) for i in range(11))):
            form = forms.TeacherForm(self.profile_data(text))
            self.assertFalse(form.is_valid())
            self.assertIn('new_subjects', form.errors)

    def test_lesson_entry_preserves_selected_subjects_and_owner_permission(self):
        existing = m.Subject.objects.create(name='Existing', slug='existing')
        form = forms.LessonForm(instance=self.lesson)
        data = {name: form[name].value() for name in form.fields if name not in ('subjects', 'new_subjects')}
        data = {name: value for name, value in data.items() if value is not None}
        data.update(subjects=[existing.pk], new_subjects='New lesson subject')
        url = reverse('tuition:lesson_edit', args=[self.lesson.uid])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url, data).status_code, 403)
        self.assertFalse(m.Subject.objects.filter(name='New lesson subject').exists())
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(set(self.lesson.subjects.values_list('name', flat=True)), {'Existing', 'New lesson subject'})
