from django.db import models
from django.conf import settings
from django.db import transaction
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Salesman(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='salesman_profile')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_salesmen')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def total_shops(self):
        return self.shops.count()

    def total_coupons_given(self):
        return self.batches.aggregate(t=models.Sum('quantity'))['t'] or 0


class Shop(models.Model):
    business = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='coupon_shops')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['salesman', 'business'],
                                                name='unique_salesman_business_shop')]

    salesman = models.ForeignKey(Salesman, on_delete=models.CASCADE, related_name='shops')
    name = models.CharField(max_length=200)
    pincode = models.CharField(max_length=10)
    address = models.TextField()
    phone = models.CharField(max_length=15)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def total_coupons(self):
        return self.batches.aggregate(t=models.Sum('quantity'))['t'] or 0


class CouponCounter(models.Model):
    """Global sequence for coupon numbers — only one row."""
    last_number = models.PositiveIntegerField(default=0)

    @classmethod
    def next_range(cls, quantity):
        """Atomically claim a range and return (start, end)."""
        with transaction.atomic():
            obj, _ = cls.objects.select_for_update().get_or_create(pk=1)
            start = obj.last_number + 1
            end = obj.last_number + quantity
            obj.last_number = end
            obj.save(update_fields=['last_number'])
        return start, end


class CouponBatch(models.Model):
    """A batch of coupons given by a salesman to a shop."""
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='batches')
    salesman = models.ForeignKey(Salesman, on_delete=models.CASCADE, related_name='batches')
    quantity = models.PositiveIntegerField()
    start_number = models.PositiveIntegerField()
    end_number = models.PositiveIntegerField()
    distributed_date = models.DateField(null=True, blank=True, help_text='Date coupons were physically distributed')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'OPC-{self.start_number:06d} → OPC-{self.end_number:06d}'

    def start_code(self):
        return f'OPC-{self.start_number:06d}'

    def end_code(self):
        return f'OPC-{self.end_number:06d}'


class Coupon(models.Model):
    STATUS_AVAILABLE = 'available'
    STATUS_ACTIVATED = 'activated'
    STATUS_EXPIRED = 'expired'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_AVAILABLE, 'Available'),
        (STATUS_ACTIVATED, 'Activated'),
        (STATUS_EXPIRED, 'Expired'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    code = models.CharField(max_length=20, unique=True)  # OPC-000001
    number = models.PositiveIntegerField(unique=True)
    batch = models.ForeignKey(CouponBatch, on_delete=models.CASCADE, related_name='coupons')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    activated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='activated_coupons')
    activated_at = models.DateTimeField(null=True, blank=True)
    points_awarded = models.PositiveIntegerField(null=True, blank=True)
    is_surprise_gift = models.BooleanField(default=False)
    surprise_gift_name = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.code

    @property
    def shop(self):
        return self.batch.shop

    @property
    def salesman(self):
        return self.batch.salesman


class SpinWheelSlot(models.Model):
    label = models.CharField(max_length=100)
    points = models.PositiveIntegerField(default=0)
    is_surprise = models.BooleanField(default=False)
    surprise_gift_name = models.CharField(max_length=200, blank=True)
    probability = models.DecimalField(max_digits=5, decimal_places=2)
    color = models.CharField(max_length=20, default='#6366f1')
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f'{self.label} ({self.probability}%)'


class Reward(models.Model):
    redemption_shop = models.ForeignKey(
        'jobs.ShopProfile', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='opc_rewards',
        help_text='Only this shop account may verify and fulfil this reward.',
    )
    name = models.CharField(max_length=200)
    business_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    points_required = models.PositiveIntegerField()
    quantity_limit = models.PositiveIntegerField(null=True, blank=True)
    quantity_redeemed = models.PositiveIntegerField(default=0)
    expiry = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} — {self.business_name}'

    def is_available(self):
        if self.expiry and self.expiry < timezone.localdate():
            return False
        if not self.is_active:
            return False
        if self.quantity_limit and self.quantity_redeemed >= self.quantity_limit:
            return False
        return True


class PointsWallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='opc_wallet')
    balance = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user} — {self.balance} pts'

    @classmethod
    def get_or_create_for(cls, user):
        wallet, _ = cls.objects.get_or_create(user=user)
        return wallet

    def credit(self, amount, description, coupon=None):
        with transaction.atomic():
            wallet = PointsWallet.objects.select_for_update().get(pk=self.pk)
            wallet.balance += amount
            wallet.save(update_fields=['balance', 'updated_at'])
            tx = PointsTransaction.objects.create(
                wallet=wallet, type='credit', amount=amount,
                balance_after=wallet.balance, description=description,
                coupon=coupon,
            )
            self.balance = wallet.balance
            return tx

    def debit(self, amount, description, redemption=None):
        with transaction.atomic():
            wallet = PointsWallet.objects.select_for_update().get(pk=self.pk)
            if wallet.balance < amount:
                raise ValueError('Insufficient balance')
            wallet.balance -= amount
            wallet.save(update_fields=['balance', 'updated_at'])
            tx = PointsTransaction.objects.create(
                wallet=wallet, type='debit', amount=amount,
                balance_after=wallet.balance, description=description,
                redemption=redemption,
            )
            self.balance = wallet.balance
            return tx


class PointsTransaction(models.Model):
    TYPE_CHOICES = [('credit', 'Credit'), ('debit', 'Debit')]
    wallet = models.ForeignKey(PointsWallet, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.PositiveIntegerField()
    balance_after = models.PositiveIntegerField()
    description = models.CharField(max_length=500)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='transactions')
    redemption = models.ForeignKey('Redemption', null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='transactions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.type} {self.amount} → {self.wallet.user}'


class RedemptionCounter(models.Model):
    """Global sequence for redemption codes — only one row."""
    last_number = models.PositiveIntegerField(default=0)

    @classmethod
    def next_number(cls):
        with transaction.atomic():
            obj, _ = cls.objects.select_for_update().get_or_create(pk=1)
            obj.last_number += 1
            obj.save(update_fields=['last_number'])
            return obj.last_number


class Redemption(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_REDEEMED = 'redeemed'
    STATUS_EXPIRED = 'expired'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_REDEEMED, 'Redeemed'),
        (STATUS_EXPIRED, 'Expired'),
    ]

    code = models.CharField(max_length=25, unique=True)  # OPC-RED-000001
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='opc_redemptions')
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE, related_name='redemptions')
    points_used = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    verified_by_shop = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.code
