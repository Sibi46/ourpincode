from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator

User = settings.AUTH_USER_MODEL

CORRECT_CHOICES = [('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')]


class Quiz(models.Model):
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=200)
    pincode = models.CharField(
        max_length=6, default='',
        validators=[RegexValidator(r'^[1-9][0-9]{5}$', 'Enter a valid six-digit pincode.')],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Quizzes'

    def __str__(self):
        return self.title

    def question_count(self):
        return self.questions.count()


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField(default=0)
    question_text = models.TextField()
    question_image = models.ImageField(upload_to='quiz/questions/', null=True, blank=True)
    option_a_text = models.CharField(max_length=300)
    option_a_image = models.ImageField(upload_to='quiz/options/', null=True, blank=True)
    option_b_text = models.CharField(max_length=300)
    option_b_image = models.ImageField(upload_to='quiz/options/', null=True, blank=True)
    option_c_text = models.CharField(max_length=300)
    option_c_image = models.ImageField(upload_to='quiz/options/', null=True, blank=True)
    option_d_text = models.CharField(max_length=300)
    option_d_image = models.ImageField(upload_to='quiz/options/', null=True, blank=True)
    correct_answer = models.CharField(max_length=1, choices=CORRECT_CHOICES)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f'Q{self.order}: {self.question_text[:60]}'

    def correct_text(self):
        return getattr(self, f'option_{self.correct_answer.lower()}_text', '')


class UserQuizAnswer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_answers')
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='user_answers')
    answer = models.CharField(max_length=1, blank=True)  # blank = skipped
    is_correct = models.BooleanField(null=True, blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'question')]


class PromotionAdmin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)


class PincodeDay(models.Model):
    title = models.CharField(max_length=200, default='PincodeDay')
    description = models.TextField(blank=True)
    agenda = models.TextField(blank=True)
    venue = models.CharField(max_length=300, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    quiz_opens_on = models.DateField()
    quiz_closes_on = models.DateField()
    published = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-starts_at']

    def __str__(self):
        return self.title


class DayQuestion(models.Model):
    event = models.ForeignKey(PincodeDay, on_delete=models.CASCADE, related_name='questions')
    text = models.CharField(max_length=500)
    option_a = models.CharField(max_length=300)
    option_b = models.CharField(max_length=300)
    option_c = models.CharField(max_length=300)
    option_d = models.CharField(max_length=300)
    correct_answer = models.CharField(max_length=1, choices=CORRECT_CHOICES)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'text'], name='day_unique_question_text')]


class DayParticipant(models.Model):
    event = models.ForeignKey(PincodeDay, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    points = models.PositiveIntegerField(default=0)
    registered_at = models.DateTimeField(auto_now_add=True)
    attending = models.BooleanField(default=False)
    present = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'user'], name='day_unique_participant')]


class DayAnswer(models.Model):
    participant = models.ForeignKey(DayParticipant, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(DayQuestion, on_delete=models.PROTECT)
    day = models.DateField()
    slot = models.PositiveSmallIntegerField()
    answer = models.CharField(max_length=1, choices=CORRECT_CHOICES, blank=True)
    points = models.PositiveSmallIntegerField(default=0)
    answered_at = models.DateTimeField(null=True, blank=True)

    @property
    def selected_text(self):
        return getattr(self.question, 'option_' + self.answer.lower(), '') if self.answer else ''

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['participant', 'question'], name='day_never_repeat'),
            models.UniqueConstraint(fields=['participant', 'day', 'slot'], name='day_unique_slot'),
            models.CheckConstraint(condition=models.Q(slot__gte=1, slot__lte=3), name='day_three_slots'),
        ]


class DayGift(models.Model):
    event = models.ForeignKey(PincodeDay, on_delete=models.CASCADE, related_name='gifts')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    rank = models.PositiveIntegerField(help_text='Leaderboard position that wins this gift (1 = highest score).')
    minimum_points = models.PositiveIntegerField(default=0)
    winner = models.ForeignKey(DayParticipant, null=True, blank=True, on_delete=models.PROTECT)
    delivered = models.BooleanField(default=False)

    class Meta:
        ordering = ['rank', 'pk']
        constraints = [models.UniqueConstraint(fields=['event', 'rank'], name='day_one_gift_per_rank')]
