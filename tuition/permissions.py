from django.core.exceptions import PermissionDenied
from django.db.models import Q, F
from .models import Learner


def active(user):
    if not user.is_authenticated or not user.is_active or user.user_type == 'marketing_agent' or user.admin_role == 'scoped_admin':
        raise PermissionDenied


def main_admin(user):
    active(user)
    if not (user.is_superuser or user.admin_role == 'super_admin'):
        raise PermissionDenied


def own(user, teacher):
    active(user)
    if teacher.owner_id != user.pk or teacher.status in ('suspended', 'rejected'):
        raise PermissionDenied


def learners(user):
    active(user)
    return Learner.objects.filter(Q(user=user) | Q(guardians__user=user, guardians__status='verified')).distinct()


def learner_access(user, learner):
    if not learners(user).filter(pk=learner.pk).exists():
        raise PermissionDenied


def enrolment_access(user, enrolment):
    active(user)
    if enrolment.lesson.teacher.owner_id == user.pk:
        own(user, enrolment.lesson.teacher)
    else:
        learner_access(user, enrolment.learner)


def recipients(learner):
    ids = list(learner.guardians.filter(status='verified', user__is_active=True).values_list('user_id', flat=True))
    if learner.user_id and learner.user.is_active:
        ids.append(learner.user_id)
    return set(ids)


def adult_authority(user, learner):
    """Publication and private teacher messaging require verified adult authority."""
    active(user)
    if learner.adult:
        return learner.user_id == user.pk and learner.identity_verified
    return learner.guardians.filter(user=user, status='verified', reviewed_by__isnull=False, reviewed_at__isnull=False).exists()


def admin_teachers(user):
    from .models import TeacherProfile
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    if user.is_superuser or user.admin_role == 'super_admin':
        return TeacherProfile.objects.all()
    if user.admin_role != 'scoped_admin':
        raise PermissionDenied
    from jobs.assigned_admin import profile_for
    profile = profile_for(user)
    if 'tuition' not in profile.sections:
        raise PermissionDenied
    if profile.all_states:
        return TeacherProfile.objects.all()
    return TeacherProfile.objects.filter(mapped_pin__code=F('pincode'), mapped_pin__is_active=True,
        mapped_pin__district__is_active=True, mapped_pin__district__state=profile.state,
        mapped_pin__district__state__is_active=True)


def moderate(user, teacher):
    if not admin_teachers(user).filter(pk=teacher.pk).exists():
        raise PermissionDenied
