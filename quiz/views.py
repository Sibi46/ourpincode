import json
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q

from .models import Quiz, QuizQuestion, UserQuizAnswer


def _is_employer(user):
    return user.is_authenticated and hasattr(user, 'is_employer') and user.is_employer()


# ── Employer views ────────────────────────────────────────────────────────────

@login_required
def employer_quiz_list(request):
    if not _is_employer(request.user):
        return redirect('home')
    quizzes = Quiz.objects.filter(created_by=request.user).prefetch_related('questions')
    return render(request, 'quiz/employer/quiz_list.html', {'quizzes': quizzes})


@login_required
def employer_quiz_create(request):
    if not _is_employer(request.user):
        return redirect('home')
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if not title:
            messages.error(request, 'Quiz title is required.')
            return redirect('quiz_create')
        pincode = request.POST.get('pincode', '').strip()
        if not re.fullmatch(r'[1-9][0-9]{5}', pincode):
            messages.error(request, 'Enter a valid six-digit pincode.')
            return render(request, 'quiz/employer/quiz_create.html', {
                'title': title, 'pincode': pincode,
            }, status=400)
        quiz = Quiz.objects.create(created_by=request.user, title=title, pincode=pincode)
        messages.success(request, f'Quiz "{title}" created. Now add questions.')
        return redirect('quiz_manage', pk=quiz.pk)
    return render(request, 'quiz/employer/quiz_create.html')


@login_required
def employer_quiz_manage(request, pk):
    if not _is_employer(request.user):
        return redirect('home')
    quiz = get_object_or_404(Quiz, pk=pk, created_by=request.user)
    questions = quiz.questions.all()

    from django.db.models import Count, Q
    questions = list(questions)

    # Attach per-question stats directly to question objects
    for q in questions:
        agg = UserQuizAnswer.objects.filter(question=q).aggregate(
            total=Count('id'),
            correct=Count('id', filter=Q(is_correct=True)),
            wrong=Count('id', filter=Q(is_correct=False)),
            skipped=Count('id', filter=Q(answer='')),
        )
        q.stat_total = agg['total']
        q.stat_correct = agg['correct']
        q.stat_wrong = agg['wrong']
        q.stat_skipped = agg['skipped']

    # Overall quiz stats
    all_answers = UserQuizAnswer.objects.filter(question__quiz=quiz)
    overall = all_answers.aggregate(
        total=Count('id'),
        correct=Count('id', filter=Q(is_correct=True)),
        wrong=Count('id', filter=Q(is_correct=False)),
        skipped=Count('id', filter=Q(answer='')),
        users=Count('user', distinct=True),
    )

    return render(request, 'quiz/employer/quiz_manage.html', {
        'quiz': quiz,
        'questions': questions,
        'can_add': len(questions) < 20,
        'overall': overall,
    })


@login_required
def employer_quiz_toggle(request, pk):
    if not _is_employer(request.user):
        return redirect('home')
    quiz = get_object_or_404(Quiz, pk=pk, created_by=request.user)
    quiz.is_active = not quiz.is_active
    quiz.save(update_fields=['is_active'])
    return redirect('quiz_manage', pk=pk)


@login_required
def employer_question_add(request, quiz_pk):
    if not _is_employer(request.user):
        return redirect('home')
    quiz = get_object_or_404(Quiz, pk=quiz_pk, created_by=request.user)
    if quiz.questions.count() >= 20:
        messages.error(request, 'Maximum 20 questions per quiz.')
        return redirect('quiz_manage', pk=quiz_pk)

    if request.method == 'POST':
        q = QuizQuestion(
            quiz=quiz,
            order=quiz.questions.count() + 1,
            question_text=request.POST.get('question_text', '').strip(),
            option_a_text=request.POST.get('option_a_text', '').strip(),
            option_b_text=request.POST.get('option_b_text', '').strip(),
            option_c_text=request.POST.get('option_c_text', '').strip(),
            option_d_text=request.POST.get('option_d_text', '').strip(),
            correct_answer=request.POST.get('correct_answer', 'A'),
        )
        for field in ['question_image', 'option_a_image', 'option_b_image', 'option_c_image', 'option_d_image']:
            if field in request.FILES:
                setattr(q, field, request.FILES[field])
        q.save()
        messages.success(request, 'Question added.')
        return redirect('quiz_manage', pk=quiz_pk)
    return render(request, 'quiz/employer/question_form.html', {'quiz': quiz, 'action': 'Add'})


@login_required
def employer_question_edit(request, quiz_pk, q_pk):
    if not _is_employer(request.user):
        return redirect('home')
    quiz = get_object_or_404(Quiz, pk=quiz_pk, created_by=request.user)
    question = get_object_or_404(QuizQuestion, pk=q_pk, quiz=quiz)

    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            question.delete()
            messages.success(request, 'Question deleted.')
            return redirect('quiz_manage', pk=quiz_pk)
        question.question_text = request.POST.get('question_text', '').strip()
        question.option_a_text = request.POST.get('option_a_text', '').strip()
        question.option_b_text = request.POST.get('option_b_text', '').strip()
        question.option_c_text = request.POST.get('option_c_text', '').strip()
        question.option_d_text = request.POST.get('option_d_text', '').strip()
        question.correct_answer = request.POST.get('correct_answer', question.correct_answer)
        for field in ['question_image', 'option_a_image', 'option_b_image', 'option_c_image', 'option_d_image']:
            if field in request.FILES:
                setattr(question, field, request.FILES[field])
        question.save()
        messages.success(request, 'Question updated.')
        return redirect('quiz_manage', pk=quiz_pk)
    return render(request, 'quiz/employer/question_form.html', {
        'quiz': quiz, 'question': question, 'action': 'Edit'
    })


# ── User AJAX API ─────────────────────────────────────────────────────────────

@login_required
def quiz_next_question(request):
    """Return the next unseen question as JSON for the popup."""
    answered_ids = UserQuizAnswer.objects.filter(
        user=request.user
    ).values_list('question_id', flat=True)

    if not re.fullmatch(r'[1-9][0-9]{5}', request.user.pincode or ''):
        return JsonResponse({'done': True})

    question = QuizQuestion.objects.filter(
        quiz__is_active=True, quiz__pincode=request.user.pincode
    ).exclude(
        pk__in=answered_ids
    ).select_related('quiz').order_by('quiz__pk', 'order', 'pk').first()

    if not question:
        return JsonResponse({'done': True})

    def img_url(field):
        return field.url if field else None

    return JsonResponse({
        'done': False,
        'id': question.pk,
        'question': question.question_text,
        'question_image': img_url(question.question_image),
        'options': {
            'A': {'text': question.option_a_text, 'image': img_url(question.option_a_image)},
            'B': {'text': question.option_b_text, 'image': img_url(question.option_b_image)},
            'C': {'text': question.option_c_text, 'image': img_url(question.option_c_image)},
            'D': {'text': question.option_d_text, 'image': img_url(question.option_d_image)},
        },
    })


@login_required
@require_POST
def quiz_submit_answer(request):
    """Submit or skip a question answer."""
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Bad request'}, status=400)

    question_id = data.get('question_id')
    answer = data.get('answer', '').strip().upper()  # empty string = skip

    if not re.fullmatch(r'[1-9][0-9]{5}', request.user.pincode or ''):
        return JsonResponse({'error': 'A valid profile pincode is required.'}, status=403)
    question = get_object_or_404(
        QuizQuestion, pk=question_id, quiz__is_active=True,
        quiz__pincode=request.user.pincode,
    )

    # Idempotent — don't double-record
    if UserQuizAnswer.objects.filter(user=request.user, question=question).exists():
        return JsonResponse({'already_answered': True})

    is_correct = None
    if answer in ('A', 'B', 'C', 'D'):
        is_correct = (answer == question.correct_answer)

    UserQuizAnswer.objects.create(
        user=request.user,
        question=question,
        answer=answer,
        is_correct=is_correct,
    )

    return JsonResponse({
        'skipped': answer == '',
        'correct': is_correct,
        'correct_answer': question.correct_answer,
        'correct_text': question.correct_text(),
    })
