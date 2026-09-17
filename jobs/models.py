from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    USER_TYPES = [
        # ── Employer types ───────────────────────────────
        ('company',             'Company'),
        ('shop',                'Shop'),
        ('recruiter',           'Recruiter / Placement Agency'),
        ('factory',             'Factory'),
        ('startup',             'Startup'),
        ('institution',         'Institution'),
        ('ngo',                 'NGO'),
        ('hospital',            'Hospital'),
        ('hotel',               'Hotel / Restaurant'),
        ('farm',                'Farm'),
        ('individual_employer', 'Individual Employer'),
        # ── Job-seeker types ─────────────────────────────
        ('employee',            'Employee'),
        ('individual',          'Individual'),
        ('freelancer',          'Freelancer'),
        # ── Advertiser ────────────────────────────────────
        ('advertiser',          'Advertiser'),
        ('family_child',        'Family Child Account'),
    ]

    EMPLOYER_TYPES = [
        'company', 'shop', 'recruiter', 'factory', 'startup',
        'institution', 'ngo', 'hospital', 'hotel',
        'farm', 'individual_employer',
    ]

    ADMIN_ROLES = [
        ('',               'Regular User'),
        ('super_admin',    'Super Admin'),
        ('state_admin',    'State Admin'),
        ('district_admin', 'District Admin'),
    ]
    user_type     = models.CharField(max_length=20, choices=USER_TYPES, default='employee')
    admin_role    = models.CharField(max_length=20, choices=ADMIN_ROLES, blank=True, default='')
    phone          = models.CharField(max_length=10, blank=True)
    business_phone = models.CharField(max_length=10, blank=True, help_text='Business/shop phone — can also be used to login')
    whatsapp       = models.CharField(max_length=10, blank=True)
    address       = models.TextField(blank=True)
    city          = models.CharField(max_length=100, blank=True)
    pincode       = models.CharField(max_length=6, blank=True)
    referral_code = models.CharField(max_length=12, unique=True, blank=True, null=True)
    salesman_biz_id = models.CharField(max_length=16, unique=True, blank=True, null=True,
                                       help_text='Unique ID shared with salesman for business linkage')

    def __str__(self):
        return self.username

    def is_employer(self):       return self.user_type in self.EMPLOYER_TYPES
    def is_super_admin(self):    return self.admin_role == 'super_admin'
    def is_state_admin(self):    return self.admin_role == 'state_admin'
    def is_district_admin(self): return self.admin_role == 'district_admin'
    def is_any_admin(self):      return bool(self.admin_role)


class CompanyProfile(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name='company')
    company_name = models.CharField(max_length=200)
    industry     = models.CharField(max_length=100, blank=True)
    website      = models.URLField(blank=True)
    company_size = models.CharField(max_length=50, blank=True)
    company_id   = models.CharField(max_length=20, unique=True, blank=True, db_index=True)
    logo         = models.ImageField(upload_to='business_logos/', blank=True, null=True)
    banner_image = models.ImageField(upload_to='business_banners/', blank=True, null=True)

    def __str__(self):
        return self.company_name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.company_id:
            self.company_id = f'CO-{self.pk:06d}'
            CompanyProfile.objects.filter(pk=self.pk).update(company_id=self.company_id)


class ShopProfile(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name='shop')
    shop_name    = models.CharField(max_length=200)
    shop_type    = models.CharField(max_length=100, blank=True)
    owner_name   = models.CharField(max_length=100, blank=True)
    website      = models.URLField(blank=True)
    logo         = models.ImageField(upload_to='business_logos/', blank=True, null=True)
    banner_image = models.ImageField(upload_to='business_banners/', blank=True, null=True)

    def __str__(self):
        return self.shop_name


class JobSeekerProfile(models.Model):
    COLLAR = [('white', 'White Collar'), ('blue', 'Blue Collar'), ('any', 'Any')]
    GENDER = [
        ('male',       'Male'),
        ('female',     'Female'),
        ('other',      'Other'),
        ('prefer_not', 'Prefer not to say'),
    ]
    AVAILABILITY = [
        ('immediate',      'Immediate Joiner'),
        ('within_1month',  'Within 1 Month'),
        ('within_3months', 'Within 3 Months'),
        ('not_looking',    'Not Actively Looking'),
    ]
    SALARY_TYPE = [('month', 'Per Month'), ('day', 'Per Day'), ('hour', 'Per Hour')]

    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seeker')
    seeker_id  = models.CharField(max_length=20, unique=True, blank=True, db_index=True)

    # ── Personal ──────────────────────────────────
    photo      = models.ImageField(upload_to='seeker_photos/', blank=True, null=True)
    dob        = models.DateField(null=True, blank=True)
    gender     = models.CharField(max_length=15, choices=GENDER, blank=True)

    # ── Location ──────────────────────────────────
    district   = models.ForeignKey('District', null=True, blank=True, on_delete=models.SET_NULL, related_name='seekers')
    state      = models.ForeignKey('State',    null=True, blank=True, on_delete=models.SET_NULL, related_name='seekers')
    preferred_location = models.CharField(max_length=500, blank=True)
    preferred_pincode  = models.CharField(max_length=200, blank=True)
    open_to_relocate   = models.BooleanField(default=False)

    # ── Career Preferences ────────────────────────
    job_category      = models.CharField(max_length=10, choices=COLLAR, default='any')
    blue_collar_type  = models.CharField(max_length=30, blank=True)
    industry          = models.CharField(max_length=300, blank=True)
    preferred_roles   = models.CharField(max_length=500, blank=True)
    availability    = models.CharField(max_length=20, choices=AVAILABILITY, default='immediate')

    # ── Compensation ──────────────────────────────
    salary_min  = models.IntegerField(null=True, blank=True)
    salary_max  = models.IntegerField(null=True, blank=True)
    salary_type = models.CharField(max_length=10, choices=SALARY_TYPE, default='month')
    rate        = models.CharField(max_length=100, blank=True)   # freelancer rate

    # ── Qualifications ────────────────────────────
    education         = models.CharField(max_length=100, blank=True)
    education_details = models.TextField(blank=True)
    experience        = models.CharField(max_length=50, blank=True)
    skills            = models.TextField(blank=True)
    languages         = models.CharField(max_length=300, blank=True)
    primary_skill     = models.CharField(max_length=100, blank=True)

    # ── Documents ─────────────────────────────────
    resume           = models.FileField(upload_to='resumes/',    blank=True, null=True)
    driving_license  = models.FileField(upload_to='licenses/',   blank=True, null=True)
    portfolio_url    = models.URLField(blank=True)
    portfolio_file   = models.FileField(upload_to='portfolios/', blank=True, null=True)

    # ── Meta ──────────────────────────────────────
    is_verified        = models.BooleanField(default=False)
    profile_completed  = models.BooleanField(default=False)
    updated_at         = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.primary_skill or self.industry or 'Job Seeker'}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.seeker_id:
            self.seeker_id = f'JS-{self.pk:06d}'
            JobSeekerProfile.objects.filter(pk=self.pk).update(seeker_id=self.seeker_id)

    def completion_percent(self):
        fields = [
            self.photo, self.dob, self.gender,
            self.district_id, self.preferred_location,
            self.industry, self.preferred_roles,
            self.education, self.experience,
            self.skills, self.languages,
            self.resume,
        ]
        filled = sum(1 for f in fields if f)
        return int((filled / len(fields)) * 100)


class SeekerCertificate(models.Model):
    seeker      = models.ForeignKey(JobSeekerProfile, on_delete=models.CASCADE, related_name='certificates')
    title       = models.CharField(max_length=200)
    issued_by   = models.CharField(max_length=200, blank=True)
    issued_year = models.CharField(max_length=4, blank=True)
    file        = models.FileField(upload_to='certificates/', blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} — {self.seeker.user.get_full_name()}"


class Job(models.Model):
    COLLAR   = [('white', 'White Collar'), ('blue', 'Blue Collar')]
    JOB_TYPE = [
        ('full_time',  'Full Time'),
        ('part_time',  'Part Time'),
        ('contract',   'Contract'),
        ('daily_wage', 'Daily Wage'),
        ('internship', 'Internship'),
    ]
    GENDER = [('any', 'Any'), ('male', 'Male Only'), ('female', 'Female Only')]
    SHIFT  = [
        ('day',   'Day Shift'),
        ('night', 'Night Shift'),
        ('rotational', 'Rotational'),
        ('flexible',   'Flexible'),
    ]
    SALARY_TYPE = [('month', 'Per Month'), ('day', 'Per Day'), ('hour', 'Per Hour')]
    STATUS = [('active', 'Active'), ('closed', 'Closed'), ('draft', 'Draft')]
    INTERVIEW_TYPE = [('walkin', 'Walk-in Drive'), ('online', 'Online Interview')]

    is_approved        = models.BooleanField(default=False)
    JOB_PLAN = [('', 'No Plan'), ('free', '1 Week Free'), ('paid_pending', 'Payment Under Review'), ('paid', '12 Weeks Paid'), ('free_expired', 'Free Plan Expired')]
    job_plan           = models.CharField(max_length=15, choices=JOB_PLAN, default='', blank=True)
    payment_screenshot = models.ImageField(upload_to='payment_proofs/', null=True, blank=True)
    plan_expires_at    = models.DateField(null=True, blank=True)

    # Core
    posted_by     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='jobs')
    title         = models.CharField(max_length=200)
    collar_type   = models.CharField(max_length=10, choices=COLLAR)
    industry      = models.CharField(max_length=100, blank=True)
    category      = models.CharField(max_length=100)       # Job Role
    job_type      = models.CharField(max_length=20, choices=JOB_TYPE, default='full_time')
    description   = models.TextField(blank=True)

    # Requirements
    experience        = models.CharField(max_length=50, blank=True)
    education         = models.CharField(max_length=100, blank=True)
    gender_preference = models.CharField(max_length=10, choices=GENDER, default='any')
    age_min           = models.IntegerField(null=True, blank=True)
    age_max           = models.IntegerField(null=True, blank=True)
    skills            = models.CharField(max_length=500, blank=True)
    language          = models.CharField(max_length=100, default='Any')

    # Compensation
    salary_min  = models.IntegerField(null=True, blank=True)
    salary_max  = models.IntegerField(null=True, blank=True)
    salary_type = models.CharField(max_length=10, choices=SALARY_TYPE, default='month')
    benefits    = models.TextField(blank=True)

    # Work details
    vacancies    = models.IntegerField(default=1)
    shift        = models.CharField(max_length=20, choices=SHIFT, default='day')
    working_days = models.CharField(max_length=100, blank=True)

    # Perks
    accommodation  = models.BooleanField(default=False)
    food_provided  = models.BooleanField(default=False)
    transport      = models.BooleanField(default=False)

    # Location
    location  = models.CharField(max_length=200, blank=True)
    pincode   = models.CharField(max_length=6, blank=True)
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Other
    contact_phone  = models.CharField(max_length=10, blank=True)
    is_urgent      = models.BooleanField(default=False)
    interview_type = models.CharField(max_length=10, choices=INTERVIEW_TYPE, default='walkin', blank=True)
    last_date      = models.DateField(null=True, blank=True)
    status        = models.CharField(max_length=10, choices=STATUS, default='active')
    created_at    = models.DateTimeField(auto_now_add=True)
    job_id        = models.CharField(max_length=20, unique=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def salary_display(self):
        unit = {'month': '/mo', 'day': '/day', 'hour': '/hr'}.get(self.salary_type, '')
        if self.salary_min and self.salary_max:
            return f"₹{self.salary_min:,} – ₹{self.salary_max:,}{unit}"
        if self.salary_min:
            return f"₹{self.salary_min:,}+{unit}"
        return "Negotiable"

    def save(self, *args, **kwargs):
        # Auto-geocode when pincode is present and coordinates are missing
        if self.pincode and (self.latitude is None or self.longitude is None):
            try:
                from .utils import geocode_pincode
                lat, lng = geocode_pincode(self.pincode)
                if lat is not None:
                    self.latitude = lat
                    self.longitude = lng
            except Exception:
                pass
        super().save(*args, **kwargs)
        if not self.job_id:
            self.job_id = f'JOB-{self.pk:06d}'
            Job.objects.filter(pk=self.pk).update(job_id=self.job_id)


class JobApplication(models.Model):
    STATUS = [
        ('pending',              'Pending'),
        ('shortlisted',          'Shortlisted'),
        ('interview_scheduled',  'Interview Scheduled'),
        ('interview_accepted',   'Interview Accepted'),
        ('interview_rejected',   'Interview Rejected'),
        ('offer_sent',           'Offer Sent'),
        ('hired',                'Hired'),
        ('rejected',             'Rejected'),
        ('withdrawn',            'Withdrawn'),
    ]
    EMPLOYMENT_TYPE = [('full_time','Full-time'),('part_time','Part-time'),('contract','Contract'),('internship','Internship')]

    job        = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='applications')
    applicant  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    cover_note = models.TextField(blank=True)
    status     = models.CharField(max_length=30, choices=STATUS, default='pending')
    applied_at = models.DateTimeField(auto_now_add=True)

    # ── Application-specific fields ───────────────
    expected_salary   = models.CharField(max_length=100, blank=True)
    notice_period     = models.CharField(max_length=50, blank=True)
    employment_type   = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE, blank=True)
    why_join          = models.TextField(blank=True)
    why_suitable      = models.TextField(blank=True)
    currently_employed = models.BooleanField(default=False)
    how_heard         = models.CharField(max_length=100, blank=True)
    application_resume = models.FileField(upload_to='application_resumes/', blank=True, null=True)
    cover_letter_file  = models.FileField(upload_to='cover_letters/', blank=True, null=True)
    declared          = models.BooleanField(default=False)

    class Meta:
        unique_together = ['job', 'applicant']
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.applicant.get_full_name()} → {self.job.title}"


class SavedJob(models.Model):
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_jobs')
    job      = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='saved_by')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'job']

    def __str__(self):
        return f"{self.user.username} saved {self.job.title}"


class Interview(models.Model):
    MODE   = [('in_person', 'In Person'), ('phone', 'Phone Call'), ('video', 'Video Call')]
    STATUS = [('scheduled', 'Scheduled'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('done', 'Completed')]

    application = models.OneToOneField(JobApplication, on_delete=models.CASCADE, related_name='interview')
    date        = models.DateField()
    time        = models.TimeField()
    mode        = models.CharField(max_length=20, choices=MODE, default='in_person')
    location    = models.CharField(max_length=300, blank=True)
    link        = models.URLField(blank=True)
    notes       = models.TextField(blank=True)
    status      = models.CharField(max_length=20, choices=STATUS, default='scheduled')
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Interview for {self.application}"


class Conversation(models.Model):
    TYPES = [
        ('job_inquiry',      'Job Inquiry'),
        ('interview_invite', 'Interview Invitation'),
        ('support',          'Support / Complaint'),
        ('general',          'General'),
    ]
    # user_a.pk is always < user_b.pk — enforced in get_or_create helper
    user_a     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conv_as_a')
    user_b     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conv_as_b')
    job        = models.ForeignKey(Job, null=True, blank=True, on_delete=models.SET_NULL, related_name='conversations')
    conv_type  = models.CharField(max_length=20, choices=TYPES, default='general')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['user_a', 'user_b', 'job']]
        ordering = ['-updated_at']

    def other_user(self, me):
        return self.user_b if self.user_a_id == me.id else self.user_a

    def unread_for(self, user):
        return self.messages.filter(is_read=False).exclude(sender=user).count()

    def last_msg(self):
        return self.messages.order_by('-sent_at').first()

    def __str__(self):
        return f"{self.user_a} ↔ {self.user_b}"


class Message(models.Model):
    MSG_TYPES = [
        ('text',             'Text'),
        ('image',            'Image'),
        ('file',             'File / PDF'),
        ('resume',           'Resume'),
        ('interview_invite', 'Interview Invitation'),
    ]
    INVITE_STATUS = [
        ('pending',  'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE,
                                     related_name='messages', null=True, blank=True)
    sender   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE,
                                 related_name='received_messages', null=True, blank=True)
    job      = models.ForeignKey(Job, on_delete=models.CASCADE,
                                 null=True, blank=True, related_name='messages')

    msg_type  = models.CharField(max_length=20, choices=MSG_TYPES, default='text')
    content   = models.TextField(blank=True)

    # Attachment
    file      = models.FileField(upload_to='chat_files/%Y/%m/', blank=True, null=True)
    file_name = models.CharField(max_length=255, blank=True)

    # Interview invite payload (only when msg_type='interview_invite')
    invite_date     = models.DateField(null=True, blank=True)
    invite_time     = models.TimeField(null=True, blank=True)
    invite_mode     = models.CharField(max_length=20, blank=True,
                                       choices=[('in_person','In Person'),
                                                ('phone','Phone Call'),
                                                ('video','Video Call')])
    invite_location = models.CharField(max_length=300, blank=True)
    invite_link     = models.URLField(blank=True)
    invite_notes    = models.TextField(blank=True)
    invite_status   = models.CharField(max_length=20, choices=INVITE_STATUS,
                                       default='pending', blank=True)

    is_read  = models.BooleanField(default=False)
    read_at  = models.DateTimeField(null=True, blank=True)
    sent_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f"{self.sender.username} [{self.msg_type}]: {self.content[:40]}"

    def is_image(self):
        return self.msg_type == 'image'

    def is_file(self):
        return self.msg_type in ('file', 'resume')

    def is_invite(self):
        return self.msg_type == 'interview_invite'


class OfferLetter(models.Model):
    application  = models.OneToOneField(JobApplication, on_delete=models.CASCADE, related_name='offer_letter')
    position     = models.CharField(max_length=200)
    salary       = models.CharField(max_length=100)
    joining_date = models.DateField()
    content      = models.TextField()
    issued_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Offer: {self.position} → {self.application.applicant.get_full_name()}"


# ============================================================
# ADVERTISER MODULE
# ============================================================

class Advertiser(models.Model):
    ADVERTISER_STATUS = [
        ('pending',   'Pending Approval'),
        ('approved',  'Approved'),
        ('rejected',  'Rejected'),
        ('suspended', 'Suspended'),
    ]
    user           = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='advertiser')
    business_name  = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100)
    phone          = models.CharField(max_length=10)
    email          = models.EmailField()
    address        = models.TextField()
    description    = models.TextField(blank=True, help_text='About your business / what you offer')
    gst            = models.CharField(max_length=15, blank=True)
    website        = models.URLField(blank=True)
    banner_image   = models.ImageField(upload_to='advertiser_banners/', blank=True, null=True)
    status         = models.CharField(max_length=20, choices=ADVERTISER_STATUS, default='pending')
    rejection_note = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    approved_at    = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.business_name


class AdPackage(models.Model):
    AD_TYPES = [
        ('homepage_banner',    'Homepage Banner'),
        ('district_banner',    'District Banner'),
        ('state_banner',       'State Banner'),
        ('featured_employer',  'Featured Employer'),
        ('featured_job',       'Featured Job'),
        ('sidebar',            'Sidebar Ad'),
        ('dashboard_banner',   'Dashboard Banner'),
        ('popup',              'Popup Ad'),
        ('sponsored_job',      'Sponsored Job'),
        ('sponsored_employer', 'Sponsored Employer'),
    ]
    name          = models.CharField(max_length=100)
    ad_type       = models.CharField(max_length=30, choices=AD_TYPES)
    duration_days = models.IntegerField(default=30)
    price         = models.DecimalField(max_digits=10, decimal_places=2)
    description   = models.TextField(blank=True)
    size_specs    = models.CharField(max_length=100, blank=True)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ad_type', 'price']

    def __str__(self):
        return f"{self.name} — ₹{self.price}/{self.duration_days}d"


class Advertisement(models.Model):
    AD_STATUS = [
        ('draft',           'Draft'),
        ('pending_payment', 'Pending Payment'),
        ('pending_review',  'Pending Review'),
        ('active',          'Active'),
        ('paused',          'Paused'),
        ('expired',         'Expired'),
        ('rejected',        'Rejected'),
    ]
    advertiser = models.ForeignKey(Advertiser, on_delete=models.CASCADE, related_name='ads')
    package    = models.ForeignKey(AdPackage, on_delete=models.CASCADE)
    title      = models.CharField(max_length=200)
    image      = models.ImageField(upload_to='ads/', blank=True)
    link_url   = models.URLField(blank=True)
    content    = models.TextField(blank=True)
    district   = models.CharField(max_length=100, blank=True)
    state      = models.CharField(max_length=100, blank=True)
    status     = models.CharField(max_length=20, choices=AD_STATUS, default='draft')
    start_date = models.DateField(null=True, blank=True)
    end_date   = models.DateField(null=True, blank=True)
    views      = models.IntegerField(default=0)
    clicks     = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} [{self.package.get_ad_type_display()}]"

    def ctr(self):
        return round((self.clicks / self.views) * 100, 2) if self.views else 0

    def days_remaining(self):
        from django.utils import timezone
        if self.end_date:
            return max(0, (self.end_date - timezone.now().date()).days)
        return 0

    def is_expiring_soon(self):
        return 0 < self.days_remaining() <= 7


class AdPayment(models.Model):
    PAYMENT_STATUS = [
        ('pending',  'Pending'),
        ('paid',     'Paid'),
        ('failed',   'Failed'),
        ('refunded', 'Refunded'),
    ]
    advertisement  = models.OneToOneField(Advertisement, on_delete=models.CASCADE, related_name='payment')
    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    gst_amount     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status         = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    invoice_number = models.CharField(max_length=50, blank=True)
    paid_at        = models.DateTimeField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"INV-{self.invoice_number} ₹{self.total_amount} [{self.status}]"


# ============================================================
# ADMIN HIERARCHY MODULE
# ============================================================

class State(models.Model):
    name      = models.CharField(max_length=100, unique=True)
    code      = models.CharField(max_length=5, unique=True)
    is_active = models.BooleanField(default=True)
    created_at= models.DateTimeField(auto_now_add=True)
    created_by= models.ForeignKey('User', null=True, blank=True, on_delete=models.SET_NULL, related_name='created_states')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

    def district_count(self):
        return self.districts.count()

    def active_jobs_count(self):
        return Job.objects.filter(pincode__in=self.districts.values_list('pincodes__code', flat=True), status='active').count()


class District(models.Model):
    state     = models.ForeignKey(State, on_delete=models.CASCADE, related_name='districts')
    name      = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at= models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('state', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name}, {self.state.name}"


class PinCode(models.Model):
    district  = models.ForeignKey(District, on_delete=models.CASCADE, related_name='pincodes')
    code      = models.CharField(max_length=6, unique=True)
    area_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} — {self.area_name}"


class AdminProfile(models.Model):
    ADMIN_ROLES = [
        ('super_admin',    'Super Admin'),
        ('state_admin',    'State Admin'),
        ('district_admin', 'District Admin'),
    ]
    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    role         = models.CharField(max_length=20, choices=ADMIN_ROLES)
    state        = models.ForeignKey(State, null=True, blank=True, on_delete=models.SET_NULL, related_name='state_admin_profiles')
    district     = models.ForeignKey(District, null=True, blank=True, on_delete=models.SET_NULL, related_name='district_admin_profiles')
    appointed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='appointed_admins')
    notes        = models.TextField(blank=True)
    is_active    = models.BooleanField(default=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_role_display()} — {self.user.get_full_name() or self.user.username}"


class Industry(models.Model):
    COLLAR_TYPES = [('white', 'White Collar'), ('blue', 'Blue Collar'), ('both', 'Both')]
    name      = models.CharField(max_length=100, unique=True)
    collar    = models.CharField(max_length=10, choices=COLLAR_TYPES, default='both')
    icon      = models.CharField(max_length=50, blank=True, default='fas fa-industry')
    is_active = models.BooleanField(default=True)
    order     = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class JobRole(models.Model):
    industry  = models.ForeignKey(Industry, on_delete=models.CASCADE, related_name='roles')
    name      = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('industry', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.industry.name})"


class PaymentPlan(models.Model):
    PLAN_TYPES = [
        ('employer_basic',      'Employer Basic'),
        ('employer_pro',        'Employer Pro'),
        ('employer_enterprise', 'Employer Enterprise'),
        ('advertiser_basic',    'Advertiser Basic'),
        ('advertiser_pro',      'Advertiser Pro'),
    ]
    name          = models.CharField(max_length=100)
    plan_type     = models.CharField(max_length=30, choices=PLAN_TYPES)
    price         = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField(default=30)
    job_posts     = models.IntegerField(default=5, help_text='0 = unlimited')
    features      = models.TextField(blank=True, help_text='One feature per line')
    is_active     = models.BooleanField(default=True)
    is_featured   = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f"{self.name} — ₹{self.price}"

    def feature_list(self):
        return [f.strip() for f in self.features.splitlines() if f.strip()]


class Discount(models.Model):
    DISCOUNT_TYPES = [('percent', 'Percentage'), ('flat', 'Flat Amount')]
    code          = models.CharField(max_length=20, unique=True)
    description   = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPES, default='percent')
    value         = models.DecimalField(max_digits=8, decimal_places=2)
    min_amount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_uses      = models.IntegerField(default=0, help_text='0 = unlimited')
    used_count    = models.IntegerField(default=0)
    valid_from    = models.DateField(null=True, blank=True)
    valid_until   = models.DateField(null=True, blank=True)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.value}{'%' if self.discount_type == 'percent' else '₹'} off)"

    def is_valid(self):
        from django.utils import timezone
        today = timezone.now().date()
        if not self.is_active:
            return False
        if self.valid_from and today < self.valid_from:
            return False
        if self.valid_until and today > self.valid_until:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True


class Complaint(models.Model):
    COMPLAINT_STATUS = [
        ('open',      'Open'),
        ('in_review', 'In Review'),
        ('resolved',  'Resolved'),
        ('closed',    'Closed'),
    ]
    COMPLAINT_TYPES = [
        ('job',        'Misleading Job'),
        ('employer',   'Employer Misconduct'),
        ('payment',    'Payment Issue'),
        ('harassment', 'Harassment'),
        ('spam',       'Spam / Fake'),
        ('other',      'Other'),
    ]
    submitted_by   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='complaints')
    complaint_type = models.CharField(max_length=20, choices=COMPLAINT_TYPES, default='other')
    subject        = models.CharField(max_length=200)
    description    = models.TextField()
    district       = models.ForeignKey(District, null=True, blank=True, on_delete=models.SET_NULL, related_name='complaints')
    status         = models.CharField(max_length=20, choices=COMPLAINT_STATUS, default='open')
    assigned_to    = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_complaints')
    resolution     = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    resolved_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_complaint_type_display()}] {self.subject}"


class SystemNotification(models.Model):
    NOTIF_TYPES = [
        ('info',    'Info'),
        ('warning', 'Warning'),
        ('success', 'Success'),
        ('alert',   'Alert'),
    ]
    title      = models.CharField(max_length=200)
    message    = models.TextField()
    notif_type = models.CharField(max_length=10, choices=NOTIF_TYPES, default='info')
    target_role= models.CharField(max_length=20, blank=True, help_text='Leave blank for all users')
    is_active  = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


# ============================================================
# EMPLOYER DASHBOARD MODELS
# ============================================================

class UserNotification(models.Model):
    TYPES = [
        ('info',    'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('alert',   'Alert'),
    ]
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title      = models.CharField(max_length=200)
    message    = models.TextField()
    notif_type = models.CharField(max_length=10, choices=TYPES, default='info')
    link       = models.CharField(max_length=200, blank=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class SavedCandidate(models.Model):
    employer  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_candidates')
    candidate = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_by_employers')
    note      = models.CharField(max_length=200, blank=True)
    saved_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['employer', 'candidate']
        ordering = ['-saved_at']

    def __str__(self):
        return f"{self.employer.username} saved {self.candidate.get_full_name()}"


class Wallet(models.Model):
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} — ₹{self.balance}"


class WalletTransaction(models.Model):
    TYPES = [('credit', 'Credit'), ('debit', 'Debit')]
    wallet      = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    txn_type    = models.CharField(max_length=10, choices=TYPES)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=200)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.txn_type} ₹{self.amount} — {self.description}"


class EmployerSubscription(models.Model):
    STATUS = [
        ('active',    'Active'),
        ('expired',   'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    employer    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    plan        = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE)
    status      = models.CharField(max_length=20, choices=STATUS, default='active')
    start_date  = models.DateField()
    end_date    = models.DateField()
    jobs_used   = models.IntegerField(default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def days_remaining(self):
        from django.utils import timezone
        return max(0, (self.end_date - timezone.now().date()).days)

    def jobs_remaining(self):
        if self.plan.job_posts == 0:
            return 'Unlimited'
        return max(0, self.plan.job_posts - self.jobs_used)

    def __str__(self):
        return f"{self.employer.username} — {self.plan.name} [{self.status}]"


class BillingRecord(models.Model):
    STATUS = [('paid', 'Paid'), ('pending', 'Pending'), ('failed', 'Failed')]
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='billing_records')
    description    = models.CharField(max_length=200)
    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    status         = models.CharField(max_length=10, choices=STATUS, default='pending')
    invoice_number = models.CharField(max_length=50, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    paid_at        = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"INV-{self.invoice_number} ₹{self.amount} [{self.status}]"


# ── REFERRAL SYSTEM ───────────────────────────────────────────────────────────

class PointsWallet(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name='points_wallet')
    balance      = models.IntegerField(default=0)
    total_earned = models.IntegerField(default=0)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} — {self.balance} pts"


class PointsTransaction(models.Model):
    TYPES = [
        ('referral_signup', 'Referral Signup Bonus'),
        ('referral_job',    'Referral Job Posted Bonus'),
        ('referral_apply',  'Referral Application Bonus'),
        ('redeemed',        'Points Redeemed'),
    ]
    wallet      = models.ForeignKey(PointsWallet, on_delete=models.CASCADE, related_name='transactions')
    amount      = models.IntegerField()
    txn_type    = models.CharField(max_length=20, choices=TYPES)
    description = models.CharField(max_length=300)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.amount > 0 else ''
        return f"{sign}{self.amount} pts — {self.description}"


class Referral(models.Model):
    referrer        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referrals_made')
    referred        = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referred_by')
    bonus_signup    = models.BooleanField(default=False)
    bonus_action    = models.BooleanField(default=False)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.referrer.username} → {self.referred.username}"


# ── FLICKS ────────────────────────────────────────────────────────────────────

class FlickAdSettings(models.Model):
    upi_id       = models.CharField(max_length=100, default='mypincod@upi')
    price        = models.DecimalField(max_digits=10, decimal_places=2, default=499)
    duration_days = models.IntegerField(default=84)

    class Meta:
        verbose_name = 'Flick Ad Settings'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"₹{self.price} / {self.duration_days} days — UPI: {self.upi_id}"


class Flick(models.Model):
    PLAN_CHOICES = [('', 'No Plan'), ('basic', 'Basic'), ('premium', 'Premium'), ('featured', 'Featured')]
    CAT_CHOICES  = [('general', 'General'), ('health', 'Health'), ('job', 'Job'), ('business', 'Business')]
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flicks')
    title          = models.CharField(max_length=150, blank=True)
    caption        = models.TextField(blank=True)
    category       = models.CharField(max_length=20, choices=CAT_CHOICES, default='general')
    video          = models.FileField(upload_to='flicks/videos/', blank=True, null=True)
    image          = models.ImageField(upload_to='flicks/images/', blank=True, null=True)
    views          = models.PositiveIntegerField(default=0)
    is_promoted    = models.BooleanField(default=False)
    advertise_plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='', blank=True)
    promoted_until = models.DateField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.title or 'Flick'}"

    def like_count(self):
        return self.likes.count()

    def comment_count(self):
        return self.comments.count()

    def is_active_promoted(self):
        from django.utils import timezone
        if self.promoted_until and self.promoted_until >= timezone.now().date():
            return True
        return self.is_promoted


class FlickAdPayment(models.Model):
    STATUS = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    flick          = models.ForeignKey(Flick, on_delete=models.CASCADE, related_name='ad_payments')
    user           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flick_ad_payments')
    transaction_id = models.CharField(max_length=100)
    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days  = models.IntegerField(default=84)
    status         = models.CharField(max_length=20, choices=STATUS, default='pending')
    created_at     = models.DateTimeField(auto_now_add=True)
    approved_at    = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.flick} — ₹{self.amount} [{self.status}]"


class FlickLike(models.Model):
    flick      = models.ForeignKey(Flick, on_delete=models.CASCADE, related_name='likes')
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flick_likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('flick', 'user')


class FlickComment(models.Model):
    flick      = models.ForeignKey(Flick, on_delete=models.CASCADE, related_name='comments')
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flick_comments')
    text       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.username}: {self.text[:40]}"


class FlickReport(models.Model):
    REASONS = [
        ('inappropriate', 'Inappropriate Content'),
        ('spam',          'Spam or Misleading'),
        ('violence',      'Violence or Dangerous'),
        ('harassment',    'Harassment or Bullying'),
        ('misinformation','False Information'),
        ('other',         'Other'),
    ]
    STATUS = [('pending', 'Pending'), ('reviewed', 'Reviewed'), ('dismissed', 'Dismissed')]
    flick      = models.ForeignKey(Flick, on_delete=models.CASCADE, related_name='reports')
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flick_reports')
    reason     = models.CharField(max_length=20, choices=REASONS)
    note       = models.TextField(blank=True)
    status     = models.CharField(max_length=20, choices=STATUS, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('flick', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} reported {self.flick} — {self.reason}"


# ── SIMPLE ADS ────────────────────────────────────────────────────────────────

class AdSettings(models.Model):
    upi_id        = models.CharField(max_length=100, blank=True)
    renewal_price = models.PositiveIntegerField(default=199)
    renewal_days  = models.PositiveIntegerField(default=30)

    class Meta:
        verbose_name = 'Ad Settings'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Ad Settings'


class AdPost(models.Model):
    STATUS = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    user         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ad_posts')
    company_name = models.CharField(max_length=200)
    pincode      = models.CharField(max_length=10, blank=True)
    description  = models.TextField()
    image        = models.ImageField(upload_to='ad_posts/')
    website      = models.URLField(blank=True)
    status       = models.CharField(max_length=20, choices=STATUS, default='pending')
    reject_note  = models.TextField(blank=True)
    views        = models.PositiveIntegerField(default=0)
    clicks       = models.PositiveIntegerField(default=0)
    created_at   = models.DateTimeField(auto_now_add=True)
    approved_at  = models.DateTimeField(null=True, blank=True)
    expires_at   = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.company_name} [{self.status}]"

    @property
    def is_live(self):
        from django.utils import timezone
        if self.status != 'approved':
            return False
        if not self.expires_at:
            return True
        return self.expires_at >= timezone.now().date()

    @property
    def is_expired(self):
        from django.utils import timezone
        if self.status != 'approved' or not self.expires_at:
            return False
        return self.expires_at < timezone.now().date()

    @property
    def pending_renewal(self):
        return self.renewals.filter(status='pending').exists()


class AdRenewal(models.Model):
    STATUS = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    ad             = models.ForeignKey(AdPost, on_delete=models.CASCADE, related_name='renewals')
    transaction_id = models.CharField(max_length=200)
    screenshot     = models.ImageField(upload_to='ad_renewals/')
    amount         = models.PositiveIntegerField()
    status         = models.CharField(max_length=20, choices=STATUS, default='pending')
    reject_note    = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    approved_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ad.company_name} renewal [{self.status}]"


class SpinGift(models.Model):
    name        = models.CharField(max_length=200)
    image       = models.ImageField(upload_to='spin_gifts/')
    address     = models.TextField(blank=True)
    win_pct     = models.FloatField(default=10.0, help_text="Chance of winning (0-100)")
    code        = models.CharField(max_length=6, help_text="6-digit claim code")
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserSpin(models.Model):
    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='spins')
    date        = models.DateField()
    won         = models.BooleanField(default=False)
    gift        = models.ForeignKey(SpinGift, null=True, blank=True, on_delete=models.SET_NULL)
    code_shown  = models.CharField(max_length=6, blank=True)
    spun_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'date')
        ordering = ['-spun_at']

    def __str__(self):
        return f"{self.user} {self.date} {'WIN' if self.won else 'LOSE'}"


class BusinessGalleryImage(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gallery_images')
    image      = models.ImageField(upload_to='business_gallery/')
    caption    = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} gallery image"


class LocalOffer(models.Model):
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='local_offers')
    CATEGORY_CHOICES = [
        ('food',     'Food & Drinks'),
        ('salon',    'Salon & Beauty'),
        ('health',   'Health & Pharmacy'),
        ('shop',     'Shopping'),
        ('services', 'Services'),
        ('other',    'Other'),
    ]
    business_name  = models.CharField(max_length=150)
    title          = models.CharField(max_length=200)
    discount_text  = models.CharField(max_length=60, help_text='e.g. 20% OFF, Buy 1 Get 1, Free Delivery')
    category       = models.CharField(max_length=50, default='other')
    image          = models.ImageField(upload_to='offers/', blank=True, null=True)
    description    = models.TextField(blank=True)
    valid_until    = models.DateField(null=True, blank=True)
    valid_days     = models.CharField(max_length=50, blank=True, help_text='Comma-separated days e.g. Mon,Tue for recurring weekly offers')
    contact_phone  = models.CharField(max_length=15, blank=True)
    link_url       = models.URLField(blank=True)
    is_flash       = models.BooleanField(default=False, help_text='Show in Flash Deals with countdown')
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business_name} – {self.discount_text}"
