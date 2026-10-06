import hashlib
import io
import uuid
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from .models import MediaAsset


def storage():
    root = Path(settings.TUITION_PRIVATE_ROOT).resolve()
    for public in (settings.MEDIA_ROOT, settings.STATIC_ROOT, settings.BASE_DIR):
        public = Path(public).resolve()
        if root == public or root in public.parents or public in root.parents:
            raise ImproperlyConfigured('Tuition private storage must not overlap public storage or the checkout.')
    return FileSystemStorage(location=root)


def upload_image(user, file, teacher=None, learner=None):
    from . import permissions as perm
    if bool(teacher) == bool(learner):
        raise ValidationError('Choose exactly one image owner.')
    if teacher:
        perm.own(user, teacher)
    else:
        perm.learner_access(user, learner)
    data = validate_image(file)
    key = storage().save(uuid.uuid4().hex + '.jpg', ContentFile(data))
    return MediaAsset.objects.create(uploader=user, teacher=teacher, learner=learner, public_requested=bool(teacher), storage_key=key,
        mime='image/jpeg', size=len(data), checksum=hashlib.sha256(data).hexdigest())


def validate_image(file):
    if file.size > 10 * 1024 * 1024 or Path(file.name).suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise ValidationError('Use a JPG, PNG or WebP image under 10 MB.')
    try:
        image = Image.open(file)
        if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 20_000_000:
            raise ValidationError('Unsupported image or more than 20 megapixels.')
        image.load()
        out = io.BytesIO()
        image.convert('RGB').save(out, format='JPEG', quality=88)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('Invalid image.')
    return out.getvalue()
