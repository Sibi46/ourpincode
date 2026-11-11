from datetime import date, datetime
from zoneinfo import ZoneInfo
from django.db import migrations


def create_launch(apps, schema_editor):
    Event = apps.get_model('quiz', 'PincodeDay')
    tz = ZoneInfo('Asia/Kolkata')
    Event.objects.get_or_create(title='PincodeDay', starts_at=datetime(2026, 12, 20, 10, tzinfo=tz), defaults={
        'ends_at': datetime(2026, 12, 20, 18, tzinfo=tz),
        'quiz_opens_on': date(2026, 11, 11), 'quiz_closes_on': date(2026, 12, 19),
        'description': 'Answer three new questions daily and earn points. Gifts go to the highest scorers at PincodeDay on December 20, 2026.',
        'published': False,
    })


class Migration(migrations.Migration):
    dependencies = [('quiz', '0003_pincodeday_dayparticipant_dayquestion_daygift_and_more')]
    operations = [migrations.RunPython(create_launch, migrations.RunPython.noop)]
