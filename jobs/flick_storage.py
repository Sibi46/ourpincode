"""Private Flick files with protected application URLs and read-only legacy fallback."""
import os
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import FileSystemStorage, default_storage
from django.urls import reverse
from django.utils.deconstruct import deconstructible


@deconstructible
class FlickMediaStorage(FileSystemStorage):
    @property
    def location(self):
        root = Path(settings.FLICKS_PRIVATE_ROOT).resolve()
        public = Path(settings.MEDIA_ROOT).resolve()
        if root == public or public in root.parents:
            raise ImproperlyConfigured('FLICKS_PRIVATE_ROOT must be outside MEDIA_ROOT.')
        return str(root)

    @property
    def base_location(self):
        return self.location

    def url(self, name):
        return reverse('flick_media', kwargs={'name': name})

    def _open(self, name, mode='rb'):
        if super().exists(name):
            return super()._open(name, mode)
        return default_storage.open(name, mode)

    def exists(self, name):
        return super().exists(name) or default_storage.exists(name)

    def size(self, name):
        return super().size(name) if super().exists(name) else default_storage.size(name)

    def delete(self, name):
        if super().exists(name):
            super().delete(name)
        # Legacy copies can still be referenced by another public-media model.
        if default_storage.exists(name):
            from django.apps import apps
            from django.db import models
            for model in apps.get_models():
                for field in model._meta.concrete_fields:
                    if isinstance(field, models.FileField) and not isinstance(field.storage, FlickMediaStorage):
                        if model._base_manager.filter(**{field.name: name}).exists():
                            return
            default_storage.delete(name)
