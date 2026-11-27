"""Move the existing launch event; leave all questions, scores and gifts linked."""
from datetime import date,datetime
from zoneinfo import ZoneInfo
from django.db import migrations,transaction


def reschedule_launch(apps,schema_editor):
    Event=apps.get_model('quiz','PincodeDay')
    Activity=apps.get_model('jobs','AdminActivity')
    alias=schema_editor.connection.alias
    tz=ZoneInfo('Asia/Kolkata')
    with transaction.atomic(using=alias):
        event=Event.objects.using(alias).select_for_update().filter(
            pk=1,title='PincodeDay',deleted_at__isnull=True,finalized_at__isnull=True,
            starts_at__gte=datetime(2026,12,20,tzinfo=tz),
            starts_at__lt=datetime(2026,12,21,tzinfo=tz)).first()
        if not event:
            return
        previous={'starts_at':event.starts_at.isoformat(),'ends_at':event.ends_at.isoformat(),
                  'quiz_closes_on':event.quiz_closes_on.isoformat()}
        duration=event.ends_at-event.starts_at
        event.starts_at=event.starts_at.astimezone(tz).replace(year=2027,month=1,day=29)
        event.ends_at=event.starts_at+duration
        event.quiz_closes_on=date(2027,1,28)
        for field in ['description','agenda']:
            text=getattr(event,field)
            text=text.replace('December 20, 2026','January 29, 2027').replace('20 December 2026','29 January 2027')
            setattr(event,field,text)
        event.save(using=alias,update_fields=['starts_at','ends_at','quiz_closes_on','description','agenda'])
        Activity.objects.using(alias).create(actor_name='Requested PincodeDay schedule update',
            section='quiz',action='reschedule_quiz_event',target_id=str(event.pk),target_name=event.title,
            details={'previous':previous,'new':{'starts_at':event.starts_at.isoformat(),
                'ends_at':event.ends_at.isoformat(),'quiz_closes_on':event.quiz_closes_on.isoformat()},
                'history_preserved':True})


class Migration(migrations.Migration):
    dependencies=[
        ('quiz','0005_dayquestion_deleted_at_pincodeday_deleted_at'),
        ('jobs','0064_flick_moderation'),
    ]
    operations=[migrations.RunPython(reschedule_launch,migrations.RunPython.noop)]
