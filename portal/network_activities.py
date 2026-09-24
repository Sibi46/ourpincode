"""Shared activity vocabulary for server detection and the composer preview."""
import re

ACTIVITIES = [
    {'key': 'cricket', 'label': 'Cricket', 'emoji': '🏏', 'words': ['cricket']},
    {'key': 'football', 'label': 'Football', 'emoji': '⚽', 'words': ['football', 'soccer']},
    {'key': 'badminton', 'label': 'Badminton', 'emoji': '🏸', 'words': ['badminton', 'shuttle']},
    {'key': 'basketball', 'label': 'Basketball', 'emoji': '🏀', 'words': ['basketball']},
    {'key': 'tennis', 'label': 'Tennis', 'emoji': '🎾', 'words': ['tennis']},
    {'key': 'chess', 'label': 'Chess', 'emoji': '♟️', 'words': ['chess']},
    {'key': 'walking', 'label': 'Walking', 'emoji': '🚶', 'words': ['walk', 'walking', 'walks']},
    {'key': 'cycling', 'label': 'Cycling', 'emoji': '🚲', 'words': ['cycle', 'cycling', 'bicycle']},
    {'key': 'running', 'label': 'Running', 'emoji': '🏃', 'words': ['running', 'jogging', 'jog']},
    {'key': 'coffee', 'label': 'Coffee', 'emoji': '☕', 'words': ['coffee', 'tea']},
    {'key': 'gaming', 'label': 'Gaming', 'emoji': '🎮', 'words': ['gaming', 'video games', 'videogames']},
    {'key': 'social', 'label': 'Connect', 'emoji': '👋', 'words': []},
]
ACTIVITY_CHOICES = [(item['key'], item['label']) for item in ACTIVITIES]


def detect_activity(text):
    for item in ACTIVITIES:
        for word in item['words']:
            if re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text, re.IGNORECASE):
                return item['key']
    return 'social'


def activity_emoji(key):
    return next((item['emoji'] for item in ACTIVITIES if item['key'] == key), '👋')


def network_name(user):
    # Registration commonly uses a phone number as username; don't publish it.
    return user.get_full_name().strip() or f'Neighbour {user.pk}'
