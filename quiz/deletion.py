"""Super Admin removal with preserved PincodeDay scores and issued daily sets."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404,redirect,render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from jobs.models import AdminActivity
from .models import PincodeDay,DayQuestion,DayAnswer


def can_delete_quiz(user):
    return user.is_authenticated and user.is_active and user.admin_role=='super_admin'


@login_required
@require_http_methods(['GET','POST'])
def remove(request,pk,question_pk=None):
    if not can_delete_quiz(request.user):
        return HttpResponseForbidden('Only Super Admin can delete quizzes and questions.')
    error='';status=200
    with transaction.atomic():
        events=PincodeDay.objects.select_for_update() if request.method=='POST' else PincodeDay.objects
        event=get_object_or_404(events,pk=pk,deleted_at__isnull=True)
        kind='question' if question_pk is not None else 'event'
        obj=event
        if question_pk is not None:
            questions=DayQuestion.objects.select_for_update() if request.method=='POST' else DayQuestion.objects
            obj=get_object_or_404(questions,pk=question_pk,event=event,deleted_at__isnull=True)
        fingerprint={'event':event.pk,'kind':kind,'pk':obj.pk,'published':event.published,
            'finalized_at':str(event.finalized_at),'title':event.title}
        if kind=='question':
            fingerprint.update(text=obj.text,options=[obj.option_a,obj.option_b,obj.option_c,obj.option_d],correct=obj.correct_answer)
        else:
            fingerprint['questions']=list(event.questions.filter(deleted_at__isnull=True).values_list('pk',flat=True).order_by('pk'))
        expected={'actor':request.user.pk,'state':fingerprint}
        if request.method=='POST':
            try:
                reviewed=signing.loads(request.POST.get('review_token',''),salt='quiz-delete',max_age=900)
            except signing.BadSignature:
                reviewed=None
            if reviewed!=expected:
                error='This review expired or the quiz changed. Review the details again before deleting.'
                status=409
            elif request.POST.get('confirmation','').strip()!='DELETE':
                error='Type DELETE to confirm.'
                status=400
            else:
                obj.deleted_at=timezone.now()
                fields=['deleted_at']
                if kind=='event':
                    obj.published=False
                    fields.append('published')
                obj.save(update_fields=fields)
                AdminActivity.objects.create(actor=request.user,actor_name=request.user.username,
                    section='quiz',action='delete_quiz_'+kind,target_id=str(obj.pk),
                    target_name=(obj.text if kind=='question' else event.title)[:250],
                    details={**fingerprint,'history_preserved':True})
                messages.success(request,('Quiz event deleted and closed. Scores and winner history are preserved.'
                    if kind=='event' else 'Question deleted from future daily sets. Existing issued sets and scores are preserved.'))
                return redirect('day_admin' if kind=='event' else reverse('day_admin_event',args=[event.pk])+'#question-pool')
        answers=DayAnswer.objects.filter(participant__event=event)
        if kind=='question':
            answers=answers.filter(question=obj)
        summary={'issued':answers.count(),'answered':answers.filter(answered_at__isnull=False).count(),
            'points':answers.aggregate(total=Sum('points',default=0))['total'],
            'questions':event.questions.filter(deleted_at__isnull=True).count(),
            'participants':event.participants.count(),'gifts':event.gifts.count()}
        token=signing.dumps(expected,salt='quiz-delete')
    return render(request,'quiz/day_delete.html',{'event':event,'record':obj,'kind':kind,
        'summary':summary,'review_token':token,'error':error},status=status)
