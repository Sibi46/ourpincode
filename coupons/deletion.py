"""Review and remove coupon records without erasing customer reward history."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from jobs.models import AdminActivity
from .models import Salesman, Coupon


def can_delete_records(user):
    return bool(user.is_authenticated and user.is_active and
                (user.is_superuser or user.admin_role == 'super_admin'))


def review_state(obj):
    if isinstance(obj, Salesman):
        return {'kind':'salesman','pk':obj.pk,'active':obj.is_active,
                'shops':obj.shops.count(),'batches':obj.batches.count(),
                'coupons':Coupon.objects.filter(batch__salesman=obj).count()}
    return {'kind':'coupon','pk':obj.pk,'status':obj.status,
            'activated_by':obj.activated_by_id,'points':obj.points_awarded,
            'activated_at':str(obj.activated_at)}


@login_required
@require_http_methods(['GET','POST'])
def delete_record(request, pk, kind):
    if not can_delete_records(request.user):
        return HttpResponseForbidden('Only Super Admin can delete these records.')
    model=Salesman if kind=='salesman' else Coupon
    return_name='opc_admin_salesmen' if kind=='salesman' else 'opc_admin_coupons'
    error=''
    status=200
    with transaction.atomic():
        queryset=model.objects.select_for_update() if request.method=='POST' else model.objects
        obj=get_object_or_404(queryset,pk=pk,deleted_at__isnull=True)
        state=review_state(obj)
        if request.method=='POST':
            try:
                reviewed=signing.loads(request.POST.get('review_token',''),
                                       salt='coupon-delete',max_age=900)
            except signing.BadSignature:
                reviewed=None
            if reviewed != {'actor':request.user.pk,'state':state}:
                error='The record changed or this review expired. Review the details again before deleting.'
                status=409
            elif request.POST.get('confirmation','').strip()!='DELETE':
                error='Type DELETE to confirm.'
                status=400
            else:
                obj.deleted_at=timezone.now()
                fields=['deleted_at']
                if kind=='salesman':
                    obj.is_active=False
                    fields.append('is_active')
                elif obj.status=='available':
                    obj.status='cancelled'
                    fields.append('status')
                obj.save(update_fields=fields)
                AdminActivity.objects.create(actor=request.user,actor_name=request.user.username,
                    section='coupons',action='delete_'+kind,target_id=str(obj.pk),
                    target_name=str(obj)[:250],details={**state,'history_preserved':True})
                messages.success(request,('Salesman deleted. Salesman portal access is disabled.'
                    if kind=='salesman' else 'Coupon deleted. It cannot be activated again.'))
                return redirect(return_name)
        token=signing.dumps({'actor':request.user.pk,'state':state},salt='coupon-delete')
    return render(request,'coupons/admin/delete_record.html',{
        'record':obj,'kind':kind,'state':state,'review_token':token,
        'return_name':return_name,'error':error},status=status)
