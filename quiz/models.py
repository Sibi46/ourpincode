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
