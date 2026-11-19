"""Explicit Super Admin deletion plans. Never disables FK protection globally."""
import hashlib
import json
import logging
from collections import defaultdict, deque

from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.db.models.deletion import CASCADE, PROTECT, RESTRICT, ProtectedError, RestrictedError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
from django.views.decorators.http import require_http_methods, require_POST
from .models import AccountFileDeletion, AdminActivity

log = logging.getLogger(__name__)


def check_access(actor, target):
    if not actor.is_authenticated or not actor.is_active or actor.admin_role != 'super_admin':
        raise PermissionDenied
    if target.pk == actor.pk or target.admin_role == 'super_admin' or target.is_superuser:
        raise ValidationError('Super Admin accounts cannot be deleted.')


def make_plan(actor, target):
    check_access(actor, target)
    User = get_user_model()
    nodes, updates, seen, files = defaultdict(set), {}, set(), set()
    from .models import ManagedBusiness
    managed_ids = set(ManagedBusiness.objects.filter(owner=target).values_list('account_id', flat=True))
    owned_user_ids = {target.pk} | managed_ids
    for child in User.objects.filter(pk__in=managed_ids):
        check_access(actor, child)
    queue = deque([target] + list(User.objects.filter(pk__in=managed_ids)))
    while queue:
        obj = queue.popleft()
        model, pk = type(obj), obj.pk
        identity = (model, pk)
        if identity in seen:
            continue
        seen.add(identity)
        label = model._meta.label_lower
        # These are shared configuration/identity records, not the user's data.
        if label == 'quiz.daygift':
            updates[(model, pk)] = {'winner_id': None}
            continue
        if label == 'coupons.monthlydraw':
            updates[(model, pk)] = {'winner_id': None}
            continue
        if label == 'tuition.teacherprofile' and obj.owner_id not in owned_user_ids:
            updates[(model, pk)] = {'parent_academy_id': None}
            continue
        if label == 'tuition.learner' and obj.user_id not in owned_user_ids:
            other = obj.user_id or obj.guardians.filter(status='verified').exclude(user_id__in=owned_user_ids).values_list('user_id', flat=True).first()
            if other:
                updates[(model, pk)] = {'created_by_id': other}
                continue
        if model == User and pk not in owned_user_ids:
            raise ValidationError('This operation would remove another user account. Nothing was deleted.')
        nodes[model].add(pk)
        if label == 'tuition.mediaasset' and obj.storage_key:
            files.add((label, 'storage_key', obj.storage_key))
        for field in model._meta.concrete_fields:
            if isinstance(field, models.FileField):
                value = getattr(obj, field.name)
                if value and value.name:
                    files.add((label, field.name, value.name))
        for relation in model._meta.get_fields(include_hidden=True):
            if not relation.auto_created or relation.concrete or not (relation.one_to_many or relation.one_to_one):
                continue
            field = relation.field
            owned_nullable = model == User and field.name in {'user', 'owner', 'author', 'business', 'posted_by', 'submitted_by', 'uploader'}
            if field.remote_field.on_delete in (CASCADE, PROTECT, RESTRICT) or owned_nullable:
                queue.extend(relation.related_model._base_manager.filter(**{field.name: obj}))
    rows = sorted((model._meta.label_lower, sorted(ids)) for model, ids in nodes.items())
    changes = sorted((model._meta.label_lower, pk, values) for (model, pk), values in updates.items())
    fingerprint = hashlib.sha256(json.dumps([target.pk, target.get_full_name(), rows, changes, sorted(files)], sort_keys=True, default=str).encode()).hexdigest()
    return {'nodes': nodes, 'updates': updates, 'files': files, 'fingerprint': fingerprint,
        'summary': sorted([(str(model._meta.verbose_name_plural), len(ids)) for model, ids in nodes.items()]),
        'total': sum(len(ids) for ids in nodes.values()), 'preserved': len(updates)}


def storage_identity(storage):
    return (storage.__class__, getattr(storage, 'location', None), getattr(storage, 'bucket_name', None))


def cleanup_files(task_ids=None, limit=100):
    tasks = AccountFileDeletion.objects.order_by('pk')
    if task_ids is not None:
        tasks = tasks.filter(pk__in=task_ids)
    for task_id in list(tasks.values_list('pk', flat=True)[:limit]):
        try:
            with transaction.atomic():
                task = AccountFileDeletion.objects.select_for_update().filter(pk=task_id).first()
                if not task:
                    continue
                if task.storage_model == 'tuition.mediaasset' and task.storage_field == 'storage_key':
                    from tuition.models import MediaAsset
                    from tuition.storage import storage
                    store = storage()
                    shared = MediaAsset.objects.filter(storage_key=task.name).exists()
                else:
                    field = apps.get_model(task.storage_model)._meta.get_field(task.storage_field)
                    store = field.storage
                    shared = False
                    for model in apps.get_models():
                        for candidate in model._meta.concrete_fields:
                            if isinstance(candidate, models.FileField) and storage_identity(candidate.storage) == storage_identity(store):
                                if model._base_manager.filter(**{candidate.name: task.name}).exists():
                                    shared = True
                                    break
                        if shared:
                            break
                if not shared:
                    store.delete(task.name)
                task.delete()
        except Exception:
            AccountFileDeletion.objects.filter(pk=task_id).update(attempts=models.F('attempts')+1)
            log.warning('Account file cleanup pending: task_id=%s', task_id)


def perform_deletion(actor, target_id, expected_fingerprint):
    User = get_user_model()
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=target_id)
        check_access(actor, target)
        plan = make_plan(actor, target)
        if plan['fingerprint'] != expected_fingerprint:
            raise ValidationError('The linked records changed. Review the updated list and confirm again.')
        for model, ids in plan['nodes'].items():
            list(model._base_manager.select_for_update().filter(pk__in=ids).values_list('pk', flat=True))
        for (model, pk) in plan['updates']:
            list(model._base_manager.select_for_update().filter(pk=pk).values_list('pk', flat=True))
        locked = make_plan(actor, target)
        if locked['fingerprint'] != expected_fingerprint:
            raise ValidationError('The linked records changed. Review the updated list and confirm again.')
        task_ids = []
        for model_name, field_name, name in plan['files']:
            task, _ = AccountFileDeletion.objects.get_or_create(storage_model=model_name, storage_field=field_name,
                name=name, defaults={'user_id_snapshot': target_id})
            task_ids.append(task.pk)
        for (model, pk), values in plan['updates'].items():
            model._base_manager.filter(pk=pk).update(**values)
        remaining = {model: set(ids) for model, ids in plan['nodes'].items()}
        while any(remaining.values()):
            before = sum(len(ids) for ids in remaining.values())
            for model, ids in remaining.items():
                existing = set(model._base_manager.filter(pk__in=ids).values_list('pk', flat=True))
                if not existing:
                    ids.clear()
                    continue
                try:
                    with transaction.atomic():
                        model._base_manager.filter(pk__in=existing).delete()
                except (ProtectedError, RestrictedError) as error:
                    blockers = getattr(error, 'protected_objects', getattr(error, 'restricted_objects', ()))
                    for blocker in blockers:
                        if blocker.pk not in plan['nodes'].get(type(blocker), set()):
                            raise ValidationError('A new linked record prevents deletion. Review the updated list.')
                    # Self-referential reversal chains must be removed from leaves first.
                    if any(type(blocker) == model for blocker in blockers):
                        for pk in sorted(existing, reverse=True):
                            try:
                                with transaction.atomic():
                                    model._base_manager.filter(pk=pk).delete()
                            except (ProtectedError, RestrictedError):
                                pass
                ids.intersection_update(model._base_manager.filter(pk__in=ids).values_list('pk', flat=True))
            if sum(len(ids) for ids in remaining.values()) == before:
                raise ValidationError('The linked records contain a dependency that cannot be removed automatically. Nothing was deleted.')
        AdminActivity.objects.create(actor=actor, actor_name=actor.username, section='account',
            action='user_permanently_deleted', target_id=str(target_id), target_name=(target.get_full_name() or target.username)[:250],
            details={'deleted_counts': plan['summary'], 'preserved_shared_records': plan['preserved']}, state_name='All states')
        transaction.on_commit(lambda: cleanup_files(task_ids, limit=len(task_ids)))
        plan['task_ids'] = task_ids
    return plan


@login_required
@require_http_methods(['GET', 'POST'])
def delete_everything(request, user_id):
    if not request.user.is_active or request.user.admin_role != 'super_admin':
        raise PermissionDenied
    User = get_user_model()
    target = User.objects.filter(pk=user_id).first()
    if target is None:
        if request.method == 'POST':
            messages.info(request, 'This account has already been deleted.')
            return redirect('super_admin_users')
        raise Http404('User account not found.')
    error = ''
    try:
        check_access(request.user, target)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect('super_admin_users')
    if request.method == 'POST':
        try:
            if request.POST.get('confirmation') != 'DELETE' or request.POST.get('acknowledge') != 'yes':
                raise ValidationError('Type DELETE and tick the confirmation box to permanently remove this account.')
            token = signing.loads(request.POST.get('plan_token', ''), salt='account-delete-all', max_age=900)
            if token.get('actor') != request.user.pk or token.get('target') != target.pk:
                raise ValidationError('The confirmation belongs to a different account. Review this account again.')
            plan = perform_deletion(request.user, target.pk, token['fingerprint'])
        except signing.BadSignature:
            error = 'The confirmation expired. Review the list below and confirm again.'
        except User.DoesNotExist:
            messages.info(request, 'This account has already been deleted.')
            return redirect('super_admin_users')
        except (ValidationError, IntegrityError) as exc:
            error = exc.messages[0] if isinstance(exc, ValidationError) else 'A linked record changed. Nothing was deleted. Review and try again.'
        else:
            pending = AccountFileDeletion.objects.filter(pk__in=plan['task_ids']).count()
            text = f'Account and linked records permanently deleted ({plan["total"]} records).'
            if pending:
                text += f' {pending} uploaded files are queued for cleanup.'
            messages.success(request, text)
            return redirect('super_admin_users')
    try:
        plan = make_plan(request.user, target)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect('super_admin_users')
    token = signing.dumps({'actor': request.user.pk, 'target': target.pk, 'fingerprint': plan['fingerprint']}, salt='account-delete-all', compress=True)
    return render(request, 'admin_delete_account.html', {'target': target, 'deletion_plan': plan, 'plan_token': token, 'error': error}, status=400 if error else 200)


@login_required
@require_POST
def retry_uploaded_files(request):
    if not request.user.is_active or request.user.admin_role != 'super_admin':
        raise PermissionDenied
    cleanup_files()
    pending = AccountFileDeletion.objects.count()
    messages.info(request, f'File cleanup checked. Pending uploaded files: {pending}.')
    return redirect('super_admin_users')
