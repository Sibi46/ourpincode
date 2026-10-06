from unittest.mock import patch
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.test import SimpleTestCase, RequestFactory, override_settings
from . import views, activity_views


@override_settings(ALLOWED_HOSTS=['ourpincode.com'])
class FormPolicyTests(SimpleTestCase):
    def test_html_pages_allow_same_origin_referrer_only(self):
        for module in (views, activity_views):
            with self.subTest(module=module.__name__), patch.object(module, 'render', return_value=HttpResponse()):
                response = module.page(RequestFactory().get('/tuition/'), 'Test')
                self.assertEqual(response['Referrer-Policy'], 'same-origin')
                self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_csrf_accepts_same_origin_but_rejects_null_and_missing_token(self):
        factory = RequestFactory()
        source = factory.get('/', secure=True, HTTP_HOST='ourpincode.com')
        token = get_token(source)
        for origin, supplied, allowed in [('https://ourpincode.com', token, True), ('null', token, False), ('https://ourpincode.com', '', False)]:
            with self.subTest(origin=origin, token_supplied=bool(supplied)):
                request = factory.post('/tuition/register/', {'csrfmiddlewaretoken': supplied}, secure=True,
                                       HTTP_HOST='ourpincode.com', HTTP_ORIGIN=origin)
                request.COOKIES['csrftoken'] = source.META['CSRF_COOKIE']
                middleware = CsrfViewMiddleware(lambda r: HttpResponse())
                middleware.process_request(request)
                result = middleware.process_view(request, lambda r: HttpResponse(), (), {})
                self.assertEqual(result is None, allowed)
