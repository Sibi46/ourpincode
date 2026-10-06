"""Private raster/video validation. No executable/PDF uploads or external URL fetching."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from . import models as m, activities as a, permissions as p
from .storage import storage, validate_image
from .services import audit
from django.core.files.base import ContentFile


def webm_header(data):
    """Read only bounded EBML header elements; require an actual WebM DocType."""
    def vint(offset, identifier=False):
        first = data[offset]
        if not first:
            raise ValueError
        length = 9 - first.bit_length()
        if length > (4 if identifier else 8) or offset+length > len(data):
            raise ValueError
        value = int.from_bytes(data[offset:offset+length], 'big')
        return (value if identifier else value & ((1 << (7*length))-1)), offset+length
    try:
        if not data.startswith(b'\x1aE\xdf\xa3'):
            return False
        length, offset = vint(4)
        end = offset+length
        if end > min(len(data), 4096):
            return False
        doc_types = []
        while offset < end:
            key, offset = vint(offset, True)
            size, offset = vint(offset)
            if offset+size > end:
                return False
            if key == 0x4282:
                doc_types.append(data[offset:offset+size])
            offset += size
        return doc_types == [b'webm']
    except (IndexError, ValueError):
        return False


def validate(file):
    extension = Path(file.name).suffix.lower()
    if extension in ('.jpg', '.jpeg', '.png', '.webp'):
        return validate_image(file), '.jpg', 'image/jpeg'
    if extension not in ('.mp4', '.webm') or file.size > 100 * 1024 * 1024:
        raise ValidationError('Use an image or an MP4/WebM video under 100 MB.')
    probe = getattr(settings, 'TUITION_FFPROBE', '') or shutil.which('ffprobe')
    if not probe:
        raise ValidationError('Video validation is not configured. Ask the administrator to install ffprobe; upload an image meanwhile.')
    data = file.read()
    if (extension == '.mp4' and (len(data) < 12 or data[4:8] != b'ftyp')) or (extension == '.webm' and not webm_header(data)):
        raise ValidationError('Video signature does not match its extension.')
    # Probe only a local temporary file; prohibit network protocols and bound runtime/output.
    with tempfile.TemporaryDirectory(prefix='tuition-video-') as directory:
        path = Path(directory) / ('input' + extension)
        path.write_bytes(data)
        try:
            result = subprocess.run([probe, '-v', 'error', '-protocol_whitelist', 'file', '-show_entries',
                'stream=codec_type,codec_name,width,height:format=duration,format_name', '-of', 'json', str(path)],
                capture_output=True, timeout=20, check=True)
            info = json.loads(result.stdout)
            streams = info.get('streams', [])
            duration = float(info.get('format', {}).get('duration', 0))
            allowed = {'vp8', 'vp9', 'av1', 'opus', 'vorbis'} if extension == '.webm' else {'h264', 'hevc', 'vp9', 'av1', 'aac', 'opus', 'mp3'}
            if not 0 < duration <= 7200 or not any(x.get('codec_type') == 'video' for x in streams):
                raise ValueError
            if any(x.get('codec_type') not in ('video', 'audio') or x.get('codec_name') not in allowed or x.get('width', 0) * x.get('height', 0) > 16_777_216 for x in streams):
                raise ValueError
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            raise ValidationError('The video could not be safely validated.')
    return data, extension, 'video/mp4' if extension == '.mp4' else 'video/webm'


@transaction.atomic
def upload(user, file, parent, title, public_requested, subjects):
    teacher = a.teacher_of(parent)
    if isinstance(parent, m.Submission):
        p.learner_access(user, parent.enrolment.learner)
        if teacher.status != 'approved' or not parent.assignment.active or not a.assignment_enrolments(parent.assignment).filter(pk=parent.enrolment_id).exists():
            raise PermissionDenied
        public_requested = False
    else:
        p.own(user, teacher)
    people = list(subjects)
    if any(not person.enrolments.filter(lesson__teacher=teacher).exists() for person in people):
        raise ValidationError('Media subjects must belong to this teacher.')
    data, suffix, mime = validate(file)
    key = storage().save(uuid.uuid4().hex + suffix, ContentFile(data))
    field = {m.TeacherProfile: 'teacher', m.Achievement: 'achievement', m.LearningEvent: 'event', m.Submission: 'submission'}[type(parent)]
    asset = m.MediaAsset.objects.create(**{field: parent}, uploader=user, title=title, public_requested=public_requested,
        storage_key=key, mime=mime, size=len(data), checksum=hashlib.sha256(data).hexdigest())
    for learner in people:
        m.MediaSubject.objects.create(asset=asset, learner=learner)
    audit(user, asset, 'media_uploaded')
    return asset
