from django.core.management.base import BaseCommand
from jobs.account_deletion import cleanup_files
from jobs.models import AccountFileDeletion


class Command(BaseCommand):
    help = 'Retry queued file cleanup after confirmed account deletions.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        cleanup_files(limit=max(1, options['limit']))
        self.stdout.write(f'Pending files: {AccountFileDeletion.objects.count()}')
