"""Synthetic localhost MySQL + private-media recovery rehearsal; never production.

Run: python -m tuition.audit_recovery
Requires the already provisioned disposable MySQL audit instance on 127.0.0.1:13317.
Creates unique databases/directories; retains everything. No drop/delete/overwrite.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import zipfile
from datetime import timedelta
from decimal import Decimal


def main():
    root = Path(__file__).resolve().parents[1]
    run = uuid.uuid4().hex[:12]
    output = root / '.audit-tools' / ('recovery-' + run)
    output.mkdir(parents=True, exist_ok=False)
    private = Path(tempfile.mkdtemp(prefix='tuition-synthetic-recovery-'))
    source_media = private / 'source'
    restored_media = private / 'restored'
    source_media.mkdir(); restored_media.mkdir()
    binaries = root / '.audit-tools/mysql/mysql-8.4.11-winx64/bin'
    source, target = 'tuition_recovery_src_' + run, 'tuition_recovery_dst_' + run
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tuition.audit_mysql_settings'
    from django.conf import settings
    settings.DATABASES['default']['NAME'] = source
    settings.TUITION_PRIVATE_ROOT = source_media
    import django
    django.setup()
    from django.db import connection, connections
    # Connect directly to the dedicated audit server only; never read project DB credentials.
    import MySQLdb
    admin = MySQLdb.connect(host='127.0.0.1', port=13317, user='root', passwd='')
    with admin.cursor() as cursor:
        cursor.execute('SELECT @@port, @@bind_address, VERSION()')
        port, host, version = cursor.fetchone()
        assert port == 13317 and host == '127.0.0.1', 'Not the isolated audit server'
        for name in (source, target):
            cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
    admin.close()
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    from .test_activities import ActivityTests
    class Fixture:
        pass
    ActivityTests.setUpTestData.__func__(Fixture)
    f = Fixture
    from . import models as m, services as svc, activities as a
    from .storage import upload_image
    from django.utils import timezone
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    from jobs.models import UserNotification
    photo = io.BytesIO(); Image.new('RGB', (8, 8), 'blue').save(photo, 'PNG')
    asset = upload_image(f.parent, SimpleUploadedFile('synthetic.png', photo.getvalue()), learner=f.child)
    today = timezone.localdate()
    fee = svc.save_agreement(f.owner, m.FeeAgreement(enrolment=f.enrolment, start_date=today, amount=100))
    invoice = svc.create_invoice(f.owner, m.Invoice(agreement=fee, period_start=today,
        period_end=today, due_date=today, amount=100))
    svc.record_payment(f.owner, invoice, Decimal('40'), 'cash', uuid.uuid4())
    svc.transfer(f.owner, f.enrolment, f.batch)
    day = today+timedelta(days=1)
    m.ScheduleRule.objects.create(batch=f.batch, weekday=day.weekday(), start_time='10:00',
        start_date=day, end_date=day, meeting_url='https://meet.google.com/synthetic')
    notice = a.save_announcement(f.owner, m.Announcement(teacher=f.teacher, lesson=f.lesson,
        title='Synthetic recovery notice', body='No real student data', publish_at=timezone.now()-timedelta(minutes=1)))
    a.moderate(f.admin, notice, 'approved')
    schedule_output = io.StringIO()
    call_command('tuition_schedule', stdout=schedule_output)
    initial = (m.ClassSession.objects.count(), UserNotification.objects.count())
    call_command('tuition_schedule', stdout=schedule_output)
    assert initial == (m.ClassSession.objects.count(), UserNotification.objects.count())
    assert initial[0] == 1 and UserNotification.objects.filter(title='New learning announcement').count() == 1

    def database_manifest():
        result = {}
        with connection.cursor() as cursor:
            for table in sorted(connection.introspection.table_names()):
                cursor.execute('SELECT * FROM ' + connection.ops.quote_name(table))
                rows = sorted(repr(row) for row in cursor.fetchall())
                result[table] = {'rows': len(rows), 'sha256': hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
        return result

    def media_manifest(directory):
        return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(directory.rglob('*')) if p.is_file()}

    before = database_manifest()
    media_before = media_manifest(source_media)
    args = ['--no-defaults', '--protocol=TCP', '--host=127.0.0.1', '--port=13317', '--user=root']
    started = time.monotonic()
    with (output/'database.sql').open('xb') as stream:
        subprocess.run([str(binaries/'mysqldump.exe'), *args, '--single-transaction', '--quick',
            '--set-gtid-purged=OFF', '--no-tablespaces', '--skip-add-drop-table', '--skip-add-locks',
            '--skip-disable-keys', source], stdout=stream, stderr=subprocess.PIPE, check=True, timeout=120)
    with zipfile.ZipFile(output/'media.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in media_before:
            archive.write(source_media/name, name)
    backup_seconds = time.monotonic()-started
    started = time.monotonic()
    with (output/'database.sql').open('rb') as stream:
        subprocess.run([str(binaries/'mysql.exe'), *args, target], stdin=stream,
            capture_output=True, check=True, timeout=120)
    with zipfile.ZipFile(output/'media.zip') as archive:
        # Accept only manifest entries, no traversal/symlinks; exclusive creation.
        assert set(archive.namelist()) == set(media_before)
        for name in media_before:
            destination = (restored_media/name).resolve()
            assert destination.is_relative_to(restored_media.resolve())
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(archive.read(name))
    connections.close_all()
    connection.settings_dict['NAME'] = target
    settings.TUITION_PRIVATE_ROOT = restored_media
    assert database_manifest() == before, 'Database row/checksum mismatch'
    assert media_manifest(restored_media) == media_before, 'Media checksum mismatch'
    assert m.Invoice.objects.get(pk=invoice.pk).balance == Decimal('60')
    restore_seconds = time.monotonic()-started
    from django.test import Client
    from django.urls import reverse
    client = Client()
    routes = [reverse('tuition:'+name, args=[asset.uid]) for name in ('file', 'activity_file')]
    for url in routes:
        assert client.get(url).status_code in (302, 403)
    client.force_login(f.other)
    for url in routes:
        assert client.get(url).status_code == 403
    client.force_login(f.parent)
    for url in routes:
        response = client.get(url)
        assert response.status_code == 200
        assert response['Cache-Control'] == 'private, no-store'
        assert hashlib.sha256(b''.join(response.streaming_content)).hexdigest() == media_before[asset.storage_key]
    # Synthetic fixture-only revocation proves restored authorization is live.
    svc.review_guardian(f.admin, m.GuardianLink.objects.get(pk=f.guardian.pk), 'revoked', 'Synthetic recovery check')
    for url in routes:
        assert client.get(url).status_code == 403
    result = {'status': 'PASS', 'mysql': version, 'source_database': source, 'restored_database': target,
        'tables': len(before), 'rows': sum(x['rows'] for x in before.values()), 'media_files': len(media_before),
        'database_manifest': before, 'media_manifest': media_before,
        'backup_seconds': round(backup_seconds, 3), 'restore_verify_seconds': round(restore_seconds, 3),
        'private_fixture_root': str(private), 'scheduler': 'PASS: two command runs, no duplicate sessions/notifications',
        'restored_authorization': 'PASS: anonymous/unrelated/revoked denied; guardian content/hash/no-store verified',
        'limitations': 'Synthetic tiny dataset, unencrypted local artifacts; not production backup, scale, encryption or RPO/RTO proof'}
    (output/'evidence.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    connections.close_all()
    print(json.dumps({k:v for k,v in result.items() if k not in ('database_manifest','media_manifest')}, indent=2))
    print('Evidence:', output/'evidence.json')


if __name__ == '__main__':
    main()
