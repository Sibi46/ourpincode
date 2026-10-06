from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (User, CompanyProfile, ShopProfile, JobSeekerProfile,
                     Job, JobApplication, SavedJob, Interview,
                     Message, OfferLetter, Advertiser, AdPackage, Advertisement, AdPayment,
                     State, District, PinCode, AdminProfile, Industry, JobRole,
                     PaymentPlan, Discount, Complaint, SystemNotification,
                     SpinGift, UserSpin, LocalOffer)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ('username', 'user_type', 'phone', 'city', 'pincode', 'is_active', 'date_joined')
    list_filter   = ('user_type', 'is_active', 'city')
    search_fields = ('username', 'phone', 'email', 'city')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Extra Info', {'fields': ('user_type', 'phone', 'address', 'city', 'pincode')}),
    )


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display  = ('company_id', 'company_name', 'industry', 'website', 'company_size')
    search_fields = ('company_id', 'company_name', 'industry')


@admin.register(ShopProfile)
class ShopProfileAdmin(admin.ModelAdmin):
    list_display  = ('shop_name', 'shop_type', 'owner_name')
    search_fields = ('shop_name', 'owner_name')


@admin.register(JobSeekerProfile)
class JobSeekerProfileAdmin(admin.ModelAdmin):
    list_display  = ('seeker_id', 'user', 'job_category', 'primary_skill', 'experience')
    search_fields = ('seeker_id', 'user__username', 'primary_skill')
    list_filter   = ('job_category',)


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display  = ('job_id', 'title', 'collar_type', 'category', 'location', 'pincode', 'is_urgent', 'status', 'is_approved', 'created_at')
    list_filter   = ('collar_type', 'status', 'is_approved', 'is_urgent', 'job_type')
    search_fields = ('job_id', 'title', 'category', 'location', 'pincode')
    date_hierarchy = 'created_at'
    actions       = ['approve_jobs', 'reject_jobs']

    def approve_jobs(self, request, queryset):
        from .models import UserNotification
        count = 0
        for job in queryset:
            job.is_approved = True
            job.status = 'active'
            job.save()
            UserNotification.objects.create(
                user=job.posted_by,
                title=f'Job Approved! Choose Your Plan — {job.title}',
                message='Your job is approved! 🎉 Start with 1 Week FREE, or go straight to 12 Weeks for ₹499. Tap to choose.',
                notif_type='success',
                link=f'/jobs/{job.pk}/select-plan/',
            )
            count += 1
        self.message_user(request, f'{count} job(s) approved. Employers notified to select plan.')
    approve_jobs.short_description = 'Approve selected jobs'

    def reject_jobs(self, request, queryset):
        queryset.update(is_approved=False, status='closed')
        self.message_user(request, f'{queryset.count()} job(s) rejected.')
    reject_jobs.short_description = 'Reject selected jobs'


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display  = ('applicant', 'job', 'status', 'applied_at')
    list_filter   = ('status',)
    search_fields = ('applicant__username', 'job__title')



@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    list_display  = ('user', 'job', 'saved_at')
    search_fields = ('user__username', 'job__title')


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display  = ('application', 'date', 'time', 'mode', 'status')
    list_filter   = ('mode', 'status')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(conversation__tuition_context__isnull=True)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'conversation':
            kwargs['queryset'] = db_field.remote_field.model.objects.filter(tuition_context__isnull=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    list_display  = ('sender', 'receiver', 'job', 'sent_at', 'is_read')
    list_filter   = ('is_read',)
    search_fields = ('sender__username', 'receiver__username')


@admin.register(OfferLetter)
class OfferLetterAdmin(admin.ModelAdmin):
    list_display  = ('application', 'position', 'joining_date', 'issued_at')


# ---- Advertiser Module ----
@admin.register(Advertiser)
class AdvertiserAdmin(admin.ModelAdmin):
    list_display  = ('business_name', 'contact_person', 'phone', 'email', 'status', 'created_at')
    list_filter   = ('status',)
    search_fields = ('business_name', 'contact_person', 'phone', 'email')
    actions       = ['approve_advertisers', 'reject_advertisers']

    def approve_advertisers(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='approved', approved_at=timezone.now())
        self.message_user(request, f'{queryset.count()} advertisers approved.')
    approve_advertisers.short_description = 'Approve selected advertisers'

    def reject_advertisers(self, request, queryset):
        queryset.update(status='rejected')
        self.message_user(request, f'{queryset.count()} advertisers rejected.')
    reject_advertisers.short_description = 'Reject selected advertisers'


@admin.register(AdPackage)
class AdPackageAdmin(admin.ModelAdmin):
    list_display  = ('name', 'ad_type', 'duration_days', 'price', 'size_specs', 'is_active')
    list_filter   = ('ad_type', 'is_active')
    list_editable = ('price', 'is_active')
    search_fields = ('name',)


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display  = ('title', 'advertiser', 'package', 'status', 'views', 'clicks', 'start_date', 'end_date')
    list_filter   = ('status', 'package__ad_type')
    search_fields = ('title', 'advertiser__business_name')
    actions       = ['activate_ads', 'reject_ads']

    def activate_ads(self, request, queryset):
        from datetime import date, timedelta
        for ad in queryset:
            if ad.status == 'pending_review':
                ad.status     = 'active'
                ad.start_date = date.today()
                ad.end_date   = date.today() + timedelta(days=ad.package.duration_days)
                ad.save()
        self.message_user(request, 'Selected ads activated.')
    activate_ads.short_description = 'Activate selected ads'

    def reject_ads(self, request, queryset):
        queryset.update(status='rejected')
        self.message_user(request, 'Selected ads rejected.')
    reject_ads.short_description = 'Reject selected ads'


@admin.register(AdPayment)
class AdPaymentAdmin(admin.ModelAdmin):
    list_display  = ('advertisement', 'amount', 'gst_amount', 'total_amount', 'status', 'payment_method', 'paid_at')
    list_filter   = ('status', 'payment_method')
    search_fields = ('invoice_number', 'transaction_id', 'advertisement__title')


# ---- Admin Hierarchy Models ----
@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display  = ('name', 'code', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    list_editable = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display  = ('name', 'state', 'is_active', 'created_at')
    list_filter   = ('is_active', 'state')
    search_fields = ('name', 'state__name')


@admin.register(PinCode)
class PinCodeAdmin(admin.ModelAdmin):
    list_display  = ('code', 'area_name', 'district', 'is_active')
    list_filter   = ('is_active', 'district__state')
    search_fields = ('code', 'area_name')


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'role', 'state', 'district', 'is_active', 'created_at')
    list_filter   = ('role', 'is_active')
    search_fields = ('user__username', 'user__first_name')
    raw_id_fields = ('user', 'state', 'district', 'appointed_by')


@admin.register(Industry)
class IndustryAdmin(admin.ModelAdmin):
    list_display  = ('name', 'collar', 'icon', 'is_active', 'order')
    list_filter   = ('collar', 'is_active')
    list_editable = ('is_active', 'order')
    search_fields = ('name',)


@admin.register(JobRole)
class JobRoleAdmin(admin.ModelAdmin):
    list_display  = ('name', 'industry', 'is_active')
    list_filter   = ('is_active', 'industry')
    search_fields = ('name', 'industry__name')


@admin.register(PaymentPlan)
class PaymentPlanAdmin(admin.ModelAdmin):
    list_display  = ('name', 'plan_type', 'price', 'duration_days', 'job_posts', 'is_active', 'is_featured')
    list_filter   = ('plan_type', 'is_active', 'is_featured')
    list_editable = ('price', 'is_active', 'is_featured')


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display  = ('code', 'discount_type', 'value', 'used_count', 'max_uses', 'valid_until', 'is_active')
    list_filter   = ('discount_type', 'is_active')
    search_fields = ('code',)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(tuition_context__isnull=True)

    list_display  = ('subject', 'complaint_type', 'submitted_by', 'district', 'status', 'created_at')
    list_filter   = ('complaint_type', 'status')
    search_fields = ('subject', 'submitted_by__username')
    raw_id_fields = ('submitted_by', 'assigned_to', 'district')


@admin.register(SystemNotification)
class SystemNotificationAdmin(admin.ModelAdmin):
    list_display  = ('title', 'notif_type', 'target_role', 'is_active', 'created_at')
    list_filter   = ('notif_type', 'is_active', 'target_role')
    search_fields = ('title',)


@admin.register(SpinGift)
class SpinGiftAdmin(admin.ModelAdmin):
    list_display  = ('name', 'win_pct', 'code', 'is_active', 'created_at')
    list_editable = ('is_active', 'win_pct')


@admin.register(UserSpin)
class UserSpinAdmin(admin.ModelAdmin):
    list_display  = ('user', 'date', 'won', 'gift', 'code_shown', 'spun_at')
    list_filter   = ('won', 'date')
    search_fields = ('user__username',)


@admin.register(LocalOffer)
class LocalOfferAdmin(admin.ModelAdmin):
    list_display   = ('business_name', 'title', 'discount_text', 'category', 'is_flash', 'is_active', 'valid_until')
    list_filter    = ('category', 'is_flash', 'is_active')
    search_fields  = ('business_name', 'title')
    list_editable  = ('is_active', 'is_flash')
