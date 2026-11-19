"""Human moderation and protected media delivery for the general Flicks feed."""
import mimetypes,re
from pathlib import Path
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_safe
from .models import Flick,User,UserNotification,AdminActivity


def is_reviewer(user):
    return user.is_authenticated and user.is_active and user.admin_role == 'super_admin'


class FlickSubmissionForm(forms.ModelForm):
    category=forms.ChoiceField(choices=Flick.CAT_CHOICES,required=False)

    def clean_category(self):
        return self.cleaned_data.get('category') or 'general'

    class Meta:
        model=Flick
        fields=['title','caption','category','video','image']

    def clean_video(self):
        upload=self.cleaned_data.get('video')
        if upload:
            if upload.size>50*1024*1024:
                raise forms.ValidationError('Video must be no larger than 50 MB.')
            if Path(upload.name).suffix.lower() not in {'.mp4','.webm','.mov'}:
                raise forms.ValidationError('Upload an MP4, WebM or MOV video.')
        return upload

    def clean_image(self):
        upload=self.cleaned_data.get('image')
        if upload and upload.size>10*1024*1024:
            raise forms.ValidationError('Image must be no larger than 10 MB.')
        if upload and getattr(upload,'image',None) and upload.image.format not in {'JPEG','PNG','GIF','WEBP'}:
            raise forms.ValidationError('Upload a JPEG, PNG, GIF or WebP image.')
        return upload

    def clean(self):
        data=super().clean()
        if not data.get('caption','').strip() and not data.get('video') and not data.get('image'):
            raise forms.ValidationError('Add a caption, image, or video.')
        return data


def notify_submission(flick):
    admins=User.objects.filter(is_active=True,admin_role='super_admin')
    UserNotification.objects.bulk_create([UserNotification(user=admin,title='Flick awaiting review',
        message=f'{flick.title or "A new Flick"} needs content review.',link='/super-admin/flicks/') for admin in admins])


@transaction.atomic
def review_flick(actor, pk, status, reason='', reviewed=False):
    if not is_reviewer(actor):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if not reviewed:
        raise ValidationError('Confirm that you reviewed the media and caption before making a decision.')
    if status not in {'approved','rejected'}:
        raise ValidationError('Choose Approve or Reject.')
    reason=reason.strip()
    if status=='rejected' and not 5<=len(reason)<=2000:
        raise ValidationError('Provide a rejection reason between 5 and 2000 characters.')
    try:
        pk=int(pk)
    except (ValueError,TypeError):
        raise ValidationError('Choose a valid Flick.')
    flick=Flick.objects.select_for_update().get(pk=pk)
    if flick.moderation_status==status and (status!='rejected' or flick.rejection_reason==reason):
        return flick
    flick.moderation_status=status;flick.reviewed_by=actor;flick.reviewed_at=timezone.now()
    flick.rejection_reason=reason if status=='rejected' else ''
    flick.save(update_fields=['moderation_status','reviewed_by','reviewed_at','rejection_reason'])
    UserNotification.objects.create(user=flick.user,title='Flick '+status,notif_type='success' if status=='approved' else 'warning',
        message=('Your Flick is approved and is now published.' if status=='approved' else 'Your Flick was rejected: '+reason),link='/flicks/mine/')
    AdminActivity.objects.create(actor=actor,actor_name=actor.username,section='flicks',action='flick_'+status,
        target_id=str(flick.pk),target_name=(flick.title or 'Flick')[:250],details={'reason':reason if status=='rejected' else ''})
    return flick


@login_required
def my_flicks(request):
    from django.core.paginator import Paginator
    page=Paginator(Flick.objects.filter(user=request.user).order_by('-created_at'),20).get_page(request.GET.get('page'))
    return render(request,'my_flicks.html',{'submissions':page})


@require_safe
def flick_media(request,name):
    matches=Flick.objects.filter(Q(video=name)|Q(image=name)).select_related('user').order_by('pk')
    flick=matches.filter(moderation_status='approved',user__is_active=True).first()
    if not flick and request.user.is_authenticated and request.user.is_active:
        flick=matches.first() if is_reviewer(request.user) else matches.filter(user=request.user).first()
    if not flick:
        from django.http import Http404
        raise Http404

    field=flick.video if flick.video and flick.video.name==name else flick.image
    try:
        stream=field.storage.open(name,'rb');size=field.storage.size(name)
    except (OSError,ValueError):
        from django.http import Http404
        raise Http404
    suffix=Path(name).suffix.lower()
    content_type=({'.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime'}.get(suffix) if field==flick.video else
                  {'.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.gif':'image/gif','.webp':'image/webp'}.get(suffix)) or 'application/octet-stream'
    range_header=request.headers.get('Range','')
    if range_header:
        match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header)
        try:
            if not match or not any(match.groups()) or size==0:raise ValueError
            first,last=match.groups()
            start=int(first) if first else max(0,size-int(last))
            end=min(size-1,int(last)) if first and last else size-1
            if start>end or start>=size:raise ValueError
        except ValueError:
            stream.close();response=HttpResponse(status=416);response['Content-Range']=f'bytes */{size}';return response
        if request.method=='HEAD':
            stream.close();response=HttpResponse(status=206,content_type=content_type)
        else:
            def chunks():
                try:
                    stream.seek(start);remaining=end-start+1
                    while remaining:
                        chunk=stream.read(min(65536,remaining))
                        if not chunk:break
                        remaining-=len(chunk);yield chunk
                finally:stream.close()
            response=StreamingHttpResponse(chunks(),status=206,content_type=content_type)
        response['Content-Range']=f'bytes {start}-{end}/{size}';response['Content-Length']=end-start+1
    elif request.method=='HEAD':
        stream.close();response=HttpResponse(content_type=content_type);response['Content-Length']=size
    else:
        response=FileResponse(stream,content_type=content_type);response['Content-Length']=size
    response['Accept-Ranges']='bytes';response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    return response
