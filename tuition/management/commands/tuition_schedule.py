from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from tuition.models import ScheduleRule, NotificationDelivery
from tuition.services import generate, deliver
from tuition.activities import scheduled_notifications


class Command(BaseCommand):
    help = 'Generate upcoming tuition occurrences and retry in-app notification delivery (idempotent).'

    def handle(self, **options):
        from tuition.deletion import retry_file_deletions
        retry_file_deletions()
        count = 0
        for rule in ScheduleRule.objects.filter(active=True):
            try:
                count += generate(rule)
            except ValidationError as exc:
                self.stderr.write(f'Rule {rule.uid}: {"; ".join(exc.messages)}')
        scheduled_notifications()
        for pk in NotificationDelivery.objects.filter(state='pending', channel='in_app').values_list('pk', flat=True):
            deliver(pk)
        self.stdout.write(f'Generated {count} sessions.')
