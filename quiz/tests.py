import re

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.template.loader import get_template
from django.template.loader_tags import IncludeNode

from .models import Quiz, QuizQuestion, UserQuizAnswer


@override_settings(
    ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class QuizPincodeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.business = User.objects.create_user('business', user_type='shop', pincode='600001')
        cls.customer = User.objects.create_user('customer', pincode='600001')
        cls.quiz = Quiz.objects.create(created_by=cls.business, title='Local quiz', pincode='600001')
        cls.question = QuizQuestion.objects.create(
            quiz=cls.quiz, question_text='Question?', option_a_text='One',
            option_b_text='Two', option_c_text='Three', option_d_text='Four', correct_answer='A',
        )

    def login(self, user):
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

    def test_create_requires_valid_pincode(self):
        self.login(self.business)
        for pincode in ('', '60001', '6000011', 'abcdef', '000001'):
            with self.subTest(pincode=pincode):
                response = self.client.post('/quiz/create/', {'title': 'New quiz', 'pincode': pincode})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Quiz.objects.count(), 1)
        response = self.client.post('/quiz/create/', {'title': 'New quiz', 'pincode': '600002'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Quiz.objects.get(title='New quiz').pincode, '600002')

    def test_nonbusiness_cannot_create_quiz(self):
        self.login(self.customer)
        self.client.post('/quiz/create/', {'title': 'Forbidden', 'pincode': '600001'})
        self.assertFalse(Quiz.objects.filter(title='Forbidden').exists())

    def test_exactly_four_correct_answer_options_on_add_and_edit(self):
        self.login(self.business)
        for path in (f'/quiz/{self.quiz.pk}/questions/add/',
                     f'/quiz/{self.quiz.pk}/questions/{self.question.pk}/edit/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            options = re.findall(r'name="correct_answer" value="([^"]*)"', response.content.decode())
            self.assertEqual(options, ['A', 'B', 'C', 'D'])

    def test_matching_user_gets_four_options_and_can_answer(self):
        self.login(self.customer)
        data = self.client.get('/quiz/api/next/').json()
        self.assertEqual(data['id'], self.question.pk)
        self.assertEqual(list(data['options']), ['A', 'B', 'C', 'D'])
        response = self.client.post('/quiz/api/answer/', {
            'question_id': self.question.pk, 'answer': 'A',
        }, content_type='application/json')
        self.assertTrue(response.json()['correct'])
        self.assertTrue(self.client.get('/quiz/api/next/').json()['done'])

    def test_other_pincode_cannot_fetch_or_answer(self):
        self.customer.pincode = '600002'
        self.customer.save()
        self.login(self.customer)
        self.assertTrue(self.client.get('/quiz/api/next/').json()['done'])
        response = self.client.post('/quiz/api/answer/', {
            'question_id': self.question.pk, 'answer': 'A',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(UserQuizAnswer.objects.exists())

    def test_missing_user_pincode_cannot_fetch_or_answer(self):
        self.customer.pincode = ''
        self.customer.save()
        self.login(self.customer)
        self.assertTrue(self.client.get('/quiz/api/next/').json()['done'])
        response = self.client.post('/quiz/api/answer/', {
            'question_id': self.question.pk, 'answer': '',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserQuizAnswer.objects.exists())

    def test_legacy_quiz_without_pincode_is_not_delivered(self):
        self.quiz.pincode = ''
        self.quiz.save()
        self.login(self.customer)
        self.assertTrue(self.client.get('/quiz/api/next/').json()['done'])

    def test_logged_in_homepage_contains_quiz_popup(self):
        self.login(self.customer)
        response = self.client.get('/')
        self.assertContains(response, 'id="opc-quiz-overlay"', count=1)
        self.assertContains(response, 'setTimeout(loadQuestion, 3000)')
        self.assertIn('csrftoken', response.cookies)

    def test_anonymous_homepage_has_no_quiz_popup(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'id="opc-quiz-overlay"')

    def test_main_layouts_include_the_shared_popup_once(self):
        for name in ('base.html', 'index.html', 'jobseeker_dashboard.html',
                     'employer_dashboard.html', 'job_list.html', 'portal/base_portal.html'):
            with self.subTest(template=name):
                template = get_template(name).template
                includes = template.nodelist.get_nodes_by_type(IncludeNode)
                popup_includes = [node for node in includes
                                  if node.template.token.strip('\"\'') == 'includes/quiz_popup.html']
                self.assertEqual(len(popup_includes), 1)
