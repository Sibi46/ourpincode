import io

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from campus.models import Institution
from portal.models import Community, Event
from .models import Flick, User
from .person_names import valid_person_name


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class NovemberFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('form-author', password='example-password')
        self.client.force_login(self.user)

    def test_flick_upload_saves_file_and_appears_in_feed(self):
        data = io.BytesIO()
        Image.new('RGB', (8, 8), 'blue').save(data, format='PNG')
        response = self.client.post('/flicks/post/', {
            'title': 'Neighbourhood update', 'caption': 'New community garden',
            'image': SimpleUploadedFile('garden.png', data.getvalue(), content_type='image/png'),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.json(), {'success': True, 'url': '/flicks/'})
        flick = Flick.objects.get(user=self.user)
        self.assertTrue(flick.image.storage.exists(flick.image.name))
        self.assertContains(self.client.get('/flicks/'), flick.image.url)

    def test_empty_flick_reports_error_instead_of_false_success(self):
        response = self.client.post('/flicks/post/', {'caption': '  '},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertFalse(Flick.objects.exists())

    def test_text_and_video_flicks_keep_working(self):
        self.assertEqual(self.client.post('/flicks/post/', {'caption': 'Local update'}).status_code, 302)
        response = self.client.post('/flicks/post/', {
            'video': SimpleUploadedFile('clip.mp4', b'test video bytes', content_type='video/mp4')},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(response.json()['success'])
        self.assertTrue(Flick.objects.exclude(video='').exclude(video=None).exists())

    def test_event_title_keeps_numbers_and_contact_rejects_them(self):
        community = Community.objects.create(name='Neighbours', created_by=self.user,
            purpose='Local updates', description='Our local group', location='Vandavasi', pincode='604408')
        url = f'/portal/c/{community.page_id}/events/create/'
        data = {'name': 'Neighbourhood Unity Meeting – 2026', 'description': 'Community gathering',
            'date': '2026-12-01', 'time': '10:00', 'location': 'Community Hall', 'contact_person': 'Ravi 123'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Event.objects.exists())
        data['contact_person'] = 'Ravi Kumar'
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(Event.objects.get().name, data['name'])

    def test_student_signup_rejects_numeric_name_and_accepts_valid_name(self):
        self.client.logout()
        institution = Institution.objects.create(name='Test College', pincode='604408', status='verified')
        data = {'full_name': 'Student 123', 'phone': '9876543210', 'email': 'student@example.test',
            'pincode': '604408', 'institution_id': institution.pk,
            'password': 'example-password', 'password2': 'example-password'}
        response = self.client.post('/campus/student/signup/', data)
        self.assertContains(response, 'Student name must contain letters and spaces only.')
        self.assertFalse(User.objects.filter(phone=data['phone']).exists())
        data['full_name'] = 'Student Name'
        self.assertEqual(self.client.post('/campus/student/signup/', data).status_code, 302)
        self.assertTrue(User.objects.filter(phone=data['phone']).exists())

    def test_person_name_supports_local_scripts_without_accepting_digits(self):
        self.assertTrue(valid_person_name('தமிழ் பெயர்'))
        for invalid in ('Ravi 1', 'Ravi ௧', '123', '  '):
            self.assertFalse(valid_person_name(invalid))
