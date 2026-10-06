import uuid
from decimal import Decimal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.db.models import Q, F, Sum
from django.utils import timezone

PIN = RegexValidator(r'^[0-9]{6}$', 'Enter a six-digit PIN code.')
MODES = [('offline', 'In person'), ('online', 'Online'), ('hybrid', 'Hybrid')]
DAYS = list(enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']))
USER = settings.AUTH_USER_MODEL


def identifier():
    return uuid.uuid4().hex


def meeting_url(value):
    if not value:
        return
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        raise ValidationError('Invalid meeting URL.')
    hosts = getattr(settings, 'TUITION_MEETING_HOSTS', ('meet.google.com', 'zoom.us', 'teams.microsoft.com'))
    if parsed.scheme != 'https' or parsed.username or parsed.password or port not in (None, 443) or not any(parsed.hostname == h or (parsed.hostname or '').endswith('.' + h) for h in hosts):
        raise ValidationError('Use an HTTPS meeting link from an approved conferencing provider.')


class Record(models.Model):
    uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    active = models.BooleanField(default=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)

    def __str__(self):
        return self.name


class TeacherProfile(Record):
    owner = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='tuition_profiles')
    kind = models.CharField(max_length=12, choices=[('teacher', 'Teacher'), ('academy', 'Academy')])
    name = models.CharField(max_length=180)
    slug = models.SlugField(default=identifier, unique=True, editable=False)
    description = models.TextField()
    qualifications = models.TextField(blank=True)
    experience = models.PositiveSmallIntegerField(default=0)
    subjects = models.ManyToManyField(Subject, blank=True)
    min_age = models.PositiveSmallIntegerField(default=0)
    max_age = models.PositiveSmallIntegerField(default=100)
    mode = models.CharField(max_length=10, choices=MODES, default='offline')
    address = models.TextField(blank=True)
    pincode = models.CharField(max_length=6, validators=[PIN], db_index=True)
    mapped_pin = models.ForeignKey('jobs.PinCode', null=True, blank=True, on_delete=models.SET_NULL)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    location_source = models.CharField(max_length=100, blank=True)
    radius_km = models.PositiveSmallIntegerField(default=0)
    public_fees = models.BooleanField(default=False)
    status = models.CharField(max_length=12, default='pending', choices=[(x, x.title()) for x in ['pending', 'approved', 'rejected', 'suspended']], db_index=True)

    def clean(self):
        if self.min_age > self.max_age:
            raise ValidationError('Minimum age must not exceed maximum age.')
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError('Provide both latitude and longitude.')

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(min_age__lte=F('max_age')), name='tuition_teacher_ages')]

    def __str__(self):
        return self.name


class ServiceArea(models.Model):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='service_areas')
    pincode = models.CharField(max_length=6, validators=[PIN], db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['teacher', 'pincode'], name='tuition_service_pin')]


class Availability(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='availability')
    weekday = models.PositiveSmallIntegerField(choices=DAYS)
    start = models.TimeField()
    end = models.TimeField()

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gt=F('start')), name='tuition_available_times')]


class Learner(Record):
    name = models.CharField(max_length=150)
    user = models.OneToOneField(USER, null=True, blank=True, on_delete=models.PROTECT, related_name='tuition_learner')
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name='created_learners')
    family_member = models.OneToOneField('community.FamilyMember', null=True, blank=True, on_delete=models.SET_NULL)
    dob = models.DateField(null=True, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MaxValueValidator(120)])
    age_as_of = models.DateField(default=timezone.localdate)
    guardian_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    pincode = models.CharField(max_length=6, validators=[PIN])
    interests = models.ManyToManyField(Subject, blank=True)
    identity_verified = models.BooleanField(default=False)

    def clean(self):
        if self.dob and self.dob > timezone.localdate():
            raise ValidationError('Date of birth cannot be in the future.')

    @property
    def adult(self):
        today = timezone.localdate()
        return bool(self.dob and (today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))) >= 18)

    def __str__(self):
        return self.name


class GuardianLink(Record):
    learner = models.ForeignKey(Learner, on_delete=models.PROTECT, related_name='guardians')
    user = models.ForeignKey(USER, on_delete=models.PROTECT)
    relationship = models.CharField(max_length=80)
    attestation = models.TextField()
    status = models.CharField(max_length=10, default='pending', choices=[(x, x.title()) for x in ['pending', 'verified', 'revoked', 'disputed']])
    reviewed_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    verification = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['learner', 'user'], name='tuition_guardian_unique')]


class Lesson(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='lessons')
    name = models.CharField(max_length=150)
    description = models.TextField()
    subjects = models.ManyToManyField(Subject, blank=True)
    min_age = models.PositiveSmallIntegerField(default=0)
    max_age = models.PositiveSmallIntegerField(default=100)
    skill_level = models.CharField(max_length=60, default='Beginner')
    mode = models.CharField(max_length=10, choices=MODES)
    location = models.TextField(blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    billing_period = models.CharField(max_length=30, default='Monthly')
    duration_minutes = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(1)])
    capacity = models.PositiveIntegerField(default=20, validators=[MinValueValidator(1)])
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(min_age__lte=F('max_age')), name='tuition_lesson_ages'), models.CheckConstraint(condition=Q(end_date__isnull=True) | Q(end_date__gte=F('start_date')), name='tuition_lesson_dates'), models.CheckConstraint(condition=Q(fee__gte=0) & Q(capacity__gt=0) & Q(duration_minutes__gt=0), name='tuition_lesson_positive')]

    def __str__(self):
        return self.name


class Batch(Record):
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name='batches')
    name = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(default=20, validators=[MinValueValidator(1)])
    location = models.TextField(blank=True)
    mode = models.CharField(max_length=10, choices=MODES)
    status = models.CharField(max_length=10, default='active', choices=[(x, x.title()) for x in ['active', 'cancelled', 'archived']])

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(capacity__gt=0), name='tuition_batch_capacity')]

    def __str__(self):
        return f'{self.lesson.name}: {self.name}'


class Application(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='applications')
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT)
    learner = models.ForeignKey(Learner, null=True, blank=True, on_delete=models.PROTECT)
    applicant = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    age = models.PositiveSmallIntegerField(validators=[MaxValueValidator(120)])
    mobile = models.CharField(max_length=20, validators=[RegexValidator(r'^\+?[0-9]{10,15}$')])
    email = models.EmailField()
    pincode = models.CharField(max_length=6, validators=[PIN])
    preferred_days = models.CharField(max_length=150)
    preferred_timings = models.CharField(max_length=150)
    mode = models.CharField(max_length=10, choices=MODES)
    message = models.TextField(blank=True)
    response = models.TextField(blank=True)
    status = models.CharField(max_length=12, default='pending', choices=[(x, x.replace('_', ' ').title()) for x in ['pending', 'needs_info', 'accepted', 'rejected', 'withdrawn']])


class Invitation(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT)
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT)
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)
    recipient = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT)


class Enrolment(Record):
    learner = models.ForeignKey(Learner, on_delete=models.PROTECT, related_name='enrolments')
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name='enrolments')
    application = models.OneToOneField(Application, null=True, blank=True, on_delete=models.PROTECT)
    joining_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, default='active', choices=[(x, x.title()) for x in ['active', 'paused', 'completed', 'withdrawn']])
    level = models.CharField(max_length=100, default='Beginner')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['learner', 'lesson'], name='tuition_enrol_unique'), models.CheckConstraint(condition=Q(end_date__isnull=True) | Q(end_date__gte=F('joining_date')), name='tuition_enrol_dates')]

    def __str__(self):
        return f'{self.learner.name} — {self.lesson.name}'


class BatchMembership(models.Model):
    enrolment = models.OneToOneField(Enrolment, on_delete=models.PROTECT, related_name='membership')
    batch = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT, related_name='memberships')


class ProgressEntry(Record):
    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT, related_name='progress')
    actor = models.ForeignKey(USER, on_delete=models.PROTECT)
    date = models.DateField(default=timezone.localdate)
    assessment = models.CharField(max_length=200)
    comments = models.TextField(blank=True)


class ScheduleRule(Record):
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name='rules')
    weekday = models.PositiveSmallIntegerField(choices=DAYS)
    start_time = models.TimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(1)])
    timezone_name = models.CharField(max_length=60, default='Asia/Kolkata')
    start_date = models.DateField()
    end_date = models.DateField()
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    meeting_url = models.URLField(blank=True, validators=[meeting_url])

    def clean(self):
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValidationError('Enter a valid timezone.')
        if self.start_time and self.duration_minutes and self.start_time.hour * 60 + self.start_time.minute + self.duration_minutes >= 1440:
            raise ValidationError('Split overnight recurring classes into separate day schedules.')

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end_date__gte=F('start_date')) & Q(duration_minutes__gt=0), name='tuition_rule_dates')]


class ClassSession(Record):
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name='sessions')
    rule = models.ForeignKey(ScheduleRule, null=True, blank=True, on_delete=models.PROTECT)
    original_start = models.DateTimeField(null=True, blank=True)
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField()
    mode = models.CharField(max_length=10, choices=MODES)
    location = models.TextField(blank=True)
    meeting_url = models.URLField(blank=True, validators=[meeting_url])
    status = models.CharField(max_length=12, default='scheduled', choices=[('scheduled', 'Scheduled'), ('cancelled', 'Cancelled')])
    revision = models.PositiveIntegerField(default=1)
    reason = models.CharField(max_length=250, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['rule', 'original_start'], name='tuition_occurrence_unique'), models.CheckConstraint(condition=Q(end__gt=F('start')), name='tuition_session_dates')]


class SessionParticipant(models.Model):
    session = models.ForeignKey(ClassSession, on_delete=models.PROTECT, related_name='participants')
    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT)
    eligible = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'enrolment'], name='tuition_roster_unique')]


class Attendance(Record):
    participant = models.OneToOneField(SessionParticipant, on_delete=models.PROTECT, related_name='attendance')
    status = models.CharField(max_length=10, choices=[(s, s.title()) for s in ['present', 'absent', 'late', 'excused']])
    marked_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    note = models.CharField(max_length=250, blank=True)


class FeeAgreement(Record):
    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT, related_name='fees')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    cadence = models.CharField(max_length=40, default='Monthly')
    currency = models.CharField(max_length=3, default='INR', editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gte=0), name='tuition_fee_positive'), models.CheckConstraint(condition=Q(end_date__isnull=True) | Q(end_date__gte=F('start_date')), name='tuition_fee_dates')]


class Invoice(Record):
    agreement = models.ForeignKey(FeeAgreement, on_delete=models.PROTECT, related_name='invoices')
    period_start = models.DateField()
    period_end = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    state = models.CharField(max_length=8, default='open', choices=[('open', 'Open'), ('void', 'Void')])
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['agreement', 'period_start', 'period_end'], name='tuition_invoice_period'), models.CheckConstraint(condition=Q(amount__gte=0) & Q(period_end__gte=F('period_start')), name='tuition_invoice_valid')]

    @property
    def paid(self):
        credit = self.payments.filter(state='confirmed', reverses__isnull=True).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        debit = self.payments.filter(state='confirmed', reverses__isnull=False).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        return credit - debit

    @property
    def balance(self):
        return self.amount - self.paid

    @property
    def status(self):
        if self.state == 'void':
            return 'Void'
        if self.balance == 0:
            return 'Paid'
        if self.due_date < timezone.localdate():
            return 'Overdue'
        return 'Partially Paid' if self.paid else 'Pending'


class Payment(Record):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    paid_at = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=20, choices=[(x, x.title()) for x in ['cash', 'bank', 'upi', 'card', 'other']])
    source = models.CharField(max_length=10, default='manual', choices=[('manual', 'Manual'), ('gateway', 'Gateway')])
    state = models.CharField(max_length=10, default='confirmed', choices=[(x, x.title()) for x in ['pending', 'confirmed', 'failed']])
    provider = models.CharField(max_length=50, blank=True)
    external_reference = models.CharField(max_length=150, null=True, blank=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True)
    recorded_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    reverses = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversal')

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='tuition_payment_positive'), models.UniqueConstraint(fields=['provider', 'external_reference'], name='tuition_provider_reference')]


class MediaAsset(Record):
    teacher = models.ForeignKey(TeacherProfile, null=True, blank=True, on_delete=models.PROTECT)
    learner = models.ForeignKey(Learner, null=True, blank=True, on_delete=models.PROTECT)
    uploader = models.ForeignKey(USER, on_delete=models.PROTECT)
    storage_key = models.CharField(max_length=100, unique=True)
    mime = models.CharField(max_length=50)
    size = models.PositiveIntegerField()
    checksum = models.CharField(max_length=64)
    achievement = models.ForeignKey('Achievement', null=True, blank=True, on_delete=models.PROTECT, related_name='media')
    event = models.ForeignKey('LearningEvent', null=True, blank=True, on_delete=models.PROTECT, related_name='media')
    submission = models.ForeignKey('Submission', null=True, blank=True, on_delete=models.PROTECT, related_name='media')
    title = models.CharField(max_length=150, blank=True)
    moderation = models.CharField(max_length=10, default='pending', choices=[(s, s.title()) for s in ['pending', 'approved', 'rejected']])
    public_requested = models.BooleanField(default=False)
    subjects_complete = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.CheckConstraint(condition=(
            Q(teacher__isnull=False, learner__isnull=True, achievement__isnull=True, event__isnull=True, submission__isnull=True) |
            Q(teacher__isnull=True, learner__isnull=False, achievement__isnull=True, event__isnull=True, submission__isnull=True) |
            Q(teacher__isnull=True, learner__isnull=True, achievement__isnull=False, event__isnull=True, submission__isnull=True) |
            Q(teacher__isnull=True, learner__isnull=True, achievement__isnull=True, event__isnull=False, submission__isnull=True) |
            Q(teacher__isnull=True, learner__isnull=True, achievement__isnull=True, event__isnull=True, submission__isnull=False)
        ), name='tuition_media_parent_v2')]


class NotificationEvent(Record):
    key = models.CharField(max_length=180, unique=True)
    title = models.CharField(max_length=200)
    link = models.CharField(max_length=200)


class NotificationDelivery(models.Model):
    event = models.ForeignKey(NotificationEvent, on_delete=models.PROTECT)
    recipient = models.ForeignKey(USER, on_delete=models.PROTECT)
    channel = models.CharField(max_length=20, default='in_app')
    state = models.CharField(max_length=10, default='pending')
    attempts = models.PositiveIntegerField(default=0)
    inbox = models.OneToOneField('jobs.UserNotification', null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'recipient', 'channel'], name='tuition_delivery_unique')]


class LearningEvent(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='events')
    kind = models.CharField(max_length=20, choices=[(s, s.replace('_', ' ').title()) for s in ['annual_day', 'performance', 'workshop', 'examination', 'exhibition', 'sports_day', 'trip', 'competition', 'festival']])
    title = models.CharField(max_length=180)
    description = models.TextField()
    start = models.DateTimeField()
    end = models.DateTimeField()
    venue = models.CharField(max_length=250)
    mode = models.CharField(max_length=10, choices=MODES, default='offline')
    registration_start = models.DateTimeField()
    registration_end = models.DateTimeField()
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    public = models.BooleanField(default=False)
    status = models.CharField(max_length=12, default='draft', choices=[(s, s.title()) for s in ['draft', 'published', 'cancelled', 'completed']])
    moderation = models.CharField(max_length=10, default='pending', choices=[(s, s.title()) for s in ['pending', 'approved', 'rejected']])
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gt=F('start')) & Q(registration_end__gte=F('registration_start')) & Q(registration_end__lte=F('end')) & Q(capacity__gt=0), name='tuition_event_dates')]

    def __str__(self):
        return self.title


class EventParticipation(Record):
    event = models.ForeignKey(LearningEvent, on_delete=models.PROTECT, related_name='participants')
    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT)
    learner = models.ForeignKey(Learner, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, default='invited', choices=[(s, s.title()) for s in ['invited', 'registered', 'accepted', 'withdrawn']])
    confirmed_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT)
    safety_consent = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'learner'], name='tuition_event_learner')]


class ProgrammeItem(Record):
    event = models.ForeignKey(LearningEvent, on_delete=models.PROTECT, related_name='programme')
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    venue = models.CharField(max_length=250)
    participants = models.ManyToManyField(EventParticipation, blank=True)
    revision = models.PositiveIntegerField(default=1)
    moderation = models.CharField(max_length=10, default='pending')

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gt=F('start')), name='tuition_programme_dates')]


class EventResult(Record):
    participation = models.ForeignKey(EventParticipation, on_delete=models.PROTECT, related_name='results')
    award = models.CharField(max_length=16, choices=[(s, s.replace('_', ' ').title()) for s in ['winner', 'runner_up', 'participation', 'special']])
    title = models.CharField(max_length=180)
    placement = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)
    moderation = models.CharField(max_length=10, default='pending')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['participation', 'award'], name='tuition_participant_award')]


class Assignment(Record):
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name='assignments')
    batch = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=180)
    instructions = models.TextField()
    due_at = models.DateTimeField()
    active = models.BooleanField(default=True)


class Submission(Record):
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT, related_name='submissions')
    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT)
    body = models.TextField(blank=True)
    feedback = models.TextField(blank=True)
    status = models.CharField(max_length=12, default='submitted', choices=[(s, s.title()) for s in ['submitted', 'completed', 'returned']])
    reviewed_by = models.ForeignKey(USER, null=True, blank=True, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['assignment', 'enrolment'], name='tuition_submission_unique')]


class PointRule(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='point_rules')
    source = models.CharField(max_length=20, choices=[(s, s.title()) for s in ['attendance', 'assignment', 'performance', 'competition', 'achievement']])
    value = models.PositiveIntegerField(default=10)
    version = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['teacher', 'source'], name='tuition_point_rule')]


class LevelDefinition(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='levels')
    name = models.CharField(max_length=60)
    threshold = models.PositiveIntegerField()

    class Meta:
        ordering = ['threshold']
        constraints = [models.UniqueConstraint(fields=['teacher', 'name'], name='tuition_level_name'), models.UniqueConstraint(fields=['teacher', 'threshold'], name='tuition_level_threshold')]


class Achievement(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='achievements')
    enrolment = models.ForeignKey(Enrolment, null=True, blank=True, on_delete=models.PROTECT, related_name='achievements')
    kind = models.CharField(max_length=20, choices=[(s, s.replace('_', ' ').title()) for s in ['certificate', 'level_completion', 'attendance_award', 'performance', 'competition', 'other']])
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    date = models.DateField(default=timezone.localdate)
    result = models.ForeignKey(EventResult, null=True, blank=True, on_delete=models.PROTECT)
    level = models.ForeignKey(LevelDefinition, null=True, blank=True, on_delete=models.PROTECT)
    public_requested = models.BooleanField(default=False)
    moderation = models.CharField(max_length=10, default='pending')
    revision = models.PositiveIntegerField(default=1)


class PointEntry(Record):
    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT, related_name='point_entries')
    rule = models.ForeignKey(PointRule, on_delete=models.PROTECT)
    rule_version = models.PositiveIntegerField()
    delta = models.IntegerField()
    reason = models.CharField(max_length=180)
    attendance = models.ForeignKey(Attendance, null=True, blank=True, on_delete=models.PROTECT)
    submission = models.ForeignKey(Submission, null=True, blank=True, on_delete=models.PROTECT)
    result = models.ForeignKey(EventResult, null=True, blank=True, on_delete=models.PROTECT)
    achievement = models.ForeignKey(Achievement, null=True, blank=True, on_delete=models.PROTECT)
    source_revision = models.CharField(max_length=60)
    action_key = models.CharField(max_length=180, unique=True)
    reverses = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversal')

    class Meta:
        constraints = [models.CheckConstraint(condition=(
            Q(attendance__isnull=False, submission__isnull=True, result__isnull=True, achievement__isnull=True) |
            Q(attendance__isnull=True, submission__isnull=False, result__isnull=True, achievement__isnull=True) |
            Q(attendance__isnull=True, submission__isnull=True, result__isnull=False, achievement__isnull=True) |
            Q(attendance__isnull=True, submission__isnull=True, result__isnull=True, achievement__isnull=False)
        ), name='tuition_point_source')]


class MediaSubject(models.Model):
    asset = models.ForeignKey(MediaAsset, on_delete=models.PROTECT, related_name='subjects')
    learner = models.ForeignKey(Learner, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['asset', 'learner'], name='tuition_media_subject')]


class PublicationConsent(Record):
    learner = models.ForeignKey(Learner, on_delete=models.PROTECT)
    authority = models.ForeignKey(USER, on_delete=models.PROTECT)
    achievement = models.ForeignKey(Achievement, null=True, blank=True, on_delete=models.PROTECT)
    asset = models.ForeignKey(MediaAsset, null=True, blank=True, on_delete=models.PROTECT)
    programme = models.ForeignKey(ProgrammeItem, null=True, blank=True, on_delete=models.PROTECT)
    result = models.ForeignKey(EventResult, null=True, blank=True, on_delete=models.PROTECT)
    target_revision = models.PositiveIntegerField()
    display_name = models.CharField(max_length=80, blank=True)
    allow_media = models.BooleanField(default=False)
    policy_version = models.CharField(max_length=20, default='1')
    adult_self = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=(
            Q(achievement__isnull=False, asset__isnull=True, programme__isnull=True, result__isnull=True) |
            Q(achievement__isnull=True, asset__isnull=False, programme__isnull=True, result__isnull=True) |
            Q(achievement__isnull=True, asset__isnull=True, programme__isnull=False, result__isnull=True) |
            Q(achievement__isnull=True, asset__isnull=True, programme__isnull=True, result__isnull=False)
        ), name='tuition_consent_target')]


class Announcement(Record):
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT, related_name='announcements')
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.PROTECT)
    batch = models.ForeignKey(Batch, null=True, blank=True, on_delete=models.PROTECT)
    event = models.ForeignKey(LearningEvent, null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=180)
    body = models.TextField()
    publish_at = models.DateTimeField(default=timezone.now)
    moderation = models.CharField(max_length=10, default='pending')


class TuitionConversation(Record):
    conversation = models.OneToOneField('jobs.Conversation', on_delete=models.PROTECT, related_name='tuition_context')
    enrolment = models.ForeignKey(Enrolment, on_delete=models.PROTECT)
    adult = models.ForeignKey(USER, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['enrolment', 'adult'], name='tuition_thread_unique')]


class TuitionComplaint(Record):
    complaint = models.OneToOneField('jobs.Complaint', on_delete=models.PROTECT, related_name='tuition_context')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT)
    enrolment = models.ForeignKey(Enrolment, null=True, blank=True, on_delete=models.PROTECT)
    event = models.ForeignKey(LearningEvent, null=True, blank=True, on_delete=models.PROTECT)
    asset = models.ForeignKey(MediaAsset, null=True, blank=True, on_delete=models.PROTECT)
