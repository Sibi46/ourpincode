from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.utils import timezone

from jobs.models import Conversation, Message, User, UserNotification
from .models import NetworkConnection, NetworkPost
from .network_activities import detect_activity


class NetworkTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('9000000001', first_name='Asha', pincode='600001')
        self.neighbour = User.objects.create_user('9000000002', first_name='Ravi', pincode='600001')
        self.outsider = User.objects.create_user('9000000003', first_name='Meera', pincode='600002')
        self.post = NetworkPost.objects.create(author=self.author, pincode='600001',
                                               text='Anyone free for cricket?', activity='cricket')
        self.login(self.neighbour)

    def login(self, user):
        self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

    def connect(self, post=None):
        return self.client.post(f'/network/{(post or self.post).pk}/connect/')

    def test_anonymous_requests_require_login(self):
        self.client.logout()
        for path in ['/network/', f'/network/{self.post.pk}/connect/', f'/network/{self.post.pk}/close/']:
            self.assertEqual(self.client.get(path).status_code, 302)
            self.assertEqual(self.client.post(path, {'text': 'Hello'}).status_code, 302)
        self.assertEqual(NetworkPost.objects.count(), 1)
        self.assertFalse(NetworkConnection.objects.exists())

    def test_feed_only_shows_registered_pincode(self):
        NetworkPost.objects.create(author=self.outsider, pincode='600002', text='Private other area post')
        response = self.client.get('/network/?pincode=600002')
        self.assertContains(response, self.post.text)
        self.assertNotContains(response, 'Private other area post')
        self.assertContains(response, '🏏')
        self.assertNotContains(response, self.author.username)

    def test_post_uses_profile_pincode_and_detects_emoji(self):
        self.client.post('/network/', {'text': 'I am free, CRICKET anyone?', 'pincode': '600002', 'activity': 'coffee'})
        post = NetworkPost.objects.get(author=self.neighbour)
        self.assertEqual(post.pincode, '600001')
        self.assertEqual(post.activity, 'cricket')
        self.assertEqual(post.emoji, '🏏')
        self.assertTrue(post.is_open)

    def test_activity_detection_is_word_based_and_has_fallback(self):
        for text, activity in [('Cricket!', 'cricket'), ('soccer today', 'football'),
                               ('Anyone for a walk?', 'walking'), ('coffee with me', 'coffee'),
                               ('Hello neighbours', 'social'), ('cricketer', 'social'),
                               ('badminton and tennis', 'badminton')]:
            with self.subTest(text=text):
                self.assertEqual(detect_activity(text), activity)

    def test_missing_or_invalid_profile_pincode_cannot_browse_post_or_connect(self):
        for pin in ['', '123', 'abcdef', '000000']:
            User.objects.filter(pk=self.neighbour.pk).update(pincode=pin)
            response = self.client.get('/network/')
            self.assertContains(response, 'Start with your pincode')
            self.assertNotContains(response, self.post.text)
            self.assertEqual(self.client.post('/network/', {'text': 'Hello'}).status_code, 403)
            self.assertEqual(self.connect().status_code, 404)
        self.assertEqual(NetworkPost.objects.count(), 1)

    def test_cross_pincode_cannot_connect_even_with_forged_pin(self):
        self.login(self.outsider)
        response = self.client.post(f'/network/{self.post.pk}/connect/', {'pincode': '600001'})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(NetworkConnection.objects.exists())
        self.assertFalse(Conversation.objects.exists())

    def test_connect_opens_existing_chat_and_notifies_author_once(self):
        response = self.connect()
        connection = NetworkConnection.objects.get()
        self.assertRedirects(response, f'/messages/{connection.conversation_id}/', fetch_redirect_response=False)
        self.assertEqual({connection.conversation.user_a_id, connection.conversation.user_b_id},
                         {self.author.pk, self.neighbour.pk})
        self.assertEqual(Message.objects.get().sender, self.neighbour)
        self.assertEqual(Message.objects.get().receiver, self.author)
        self.assertIn(self.post.text, Message.objects.get().content)
        self.assertEqual(UserNotification.objects.get().user, self.author)
        self.assertEqual(self.connect().url, response.url)
        self.assertEqual(NetworkConnection.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(UserNotification.objects.count(), 1)
        self.assertContains(self.client.get('/network/'), 'Open chat')

    def test_other_posts_reuse_same_general_conversation(self):
        self.connect()
        second = NetworkPost.objects.create(author=self.author, pincode='600001', text='Coffee tomorrow?')
        self.connect(second)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(NetworkConnection.objects.count(), 2)

    def test_database_prevents_duplicate_connection(self):
        self.connect()
        with self.assertRaises(IntegrityError), transaction.atomic():
            NetworkConnection.objects.create(post=self.post, user=self.neighbour)

    def test_connection_failure_rolls_back_chat_and_notification(self):
        with patch('portal.network_views.UserNotification.objects.create', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                self.connect()
        self.assertFalse(NetworkConnection.objects.exists())
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(Message.objects.exists())

    def test_cannot_connect_to_own_post(self):
        self.login(self.author)
        self.assertEqual(self.connect().status_code, 403)
        self.assertFalse(NetworkConnection.objects.exists())

    def test_only_author_can_close_and_existing_chats_remain(self):
        self.connect()
        self.assertEqual(self.client.post(f'/network/{self.post.pk}/close/').status_code, 404)
        self.login(self.author)
        self.client.post(f'/network/{self.post.pk}/close/')
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_open)
        self.assertIsNotNone(self.post.closed_at)
        first_closed = self.post.closed_at
        self.client.post(f'/network/{self.post.pk}/close/')
        self.post.refresh_from_db()
        self.assertEqual(self.post.closed_at, first_closed)
        self.assertContains(self.client.get('/network/?tab=mine'), self.post.text)
        self.login(self.neighbour)
        self.assertNotContains(self.client.get('/network/'), self.post.text)
        self.assertEqual(self.connect().status_code, 404)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(self.client.get(f'/messages/{NetworkConnection.objects.get().conversation_id}/').status_code, 200)

    def test_post_does_not_expire_automatically(self):
        NetworkPost.objects.filter(pk=self.post.pk).update(created_at=timezone.now()-timedelta(days=90))
        self.assertContains(self.client.get('/network/'), self.post.text)
        self.assertEqual(self.connect().status_code, 302)

    def test_inactive_or_moved_author_posts_are_hidden(self):
        for values in [{'is_active': False}, {'is_active': True, 'pincode': '600002'}]:
            User.objects.filter(pk=self.author.pk).update(**values)
            self.assertNotContains(self.client.get('/network/'), self.post.text)
            self.assertEqual(self.connect().status_code, 404)

    def test_invalid_text_does_not_create_post(self):
        for text in ['', '   ', 'a'*501]:
            self.assertEqual(self.client.post('/network/', {'text': text}).status_code, 400)
        self.assertEqual(NetworkPost.objects.count(), 1)

    def test_text_is_escaped_and_phone_usernames_are_not_exposed(self):
        User.objects.filter(pk=self.author.pk).update(first_name='')
        NetworkPost.objects.filter(pk=self.post.pk).update(text='<script>alert(1)</script>')
        response = self.client.get('/network/')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertNotContains(response, self.author.username)

    def test_mutations_require_post_and_csrf(self):
        for action in ['connect', 'close']:
            self.assertEqual(self.client.get(f'/network/{self.post.pk}/{action}/').status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.neighbour, backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(client.post('/network/', {'text': 'Hi'}).status_code, 403)
        self.assertEqual(client.post(f'/network/{self.post.pk}/connect/').status_code, 403)

    def test_only_author_sees_responders(self):
        self.connect()
        self.assertNotContains(self.client.get('/network/'), 'People who connected with you')
        self.login(self.author)
        response = self.client.get('/network/?tab=mine')
        self.assertContains(response, 'People who connected with you')
        self.assertContains(response, 'Ravi')

    def test_feed_is_paginated(self):
        NetworkPost.objects.bulk_create([NetworkPost(author=self.author, pincode='600001', text=f'Plan {n}') for n in range(22)])
        self.assertEqual(len(self.client.get('/network/').context['page']), 20)
        self.assertEqual(len(self.client.get('/network/?page=2').context['page']), 3)
        self.assertEqual(self.client.get('/network/').context['page'][0].text, 'Plan 21')
