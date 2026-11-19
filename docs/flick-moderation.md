# Flick content approval

General Flicks follow **Submit → Pending review → Approve or Reject**. Content-agreement declarations and paid promotion do not grant publication. Only active Super Admins can review at `/super-admin/flicks/`; promotional admins and ordinary staff cannot approve general Flicks.

Owners submit at `/flicks/post/` and follow pending, approved or rejected submissions at `/flicks/mine/`. Rejections include a reason. Reviewers preview the complete caption and uploaded media, confirm they reviewed the content guidelines, and approve or provide a rejection reason. Approving publishes the Flick; rejecting an approved Flick removes it from public feeds. Decisions record reviewer, time and an audit entry and notify the owner in the application. New submissions notify active Super Admins. Repeating an unchanged decision does not duplicate notifications.

Migration `0064_flick_moderation` puts existing Flicks into pending review; it does not invent prior approvals. Public feeds, business-profile Flick lists and public interactions only use approved content from active owners. This policy concerns `jobs.Flick`; community and tuition media retain their separate moderation rules.

## Media deployment requirements

Set `FLICKS_PRIVATE_ROOT` to a writable directory outside `MEDIA_ROOT`, e.g. `/var/lib/ourpincode/flicks-private`, owned by the application service user. New uploads go there. Field URLs point to `/flicks/media/<name>`; pending/rejected media can only be viewed by the owner or an active Super Admin. Approved media is public through this endpoint. Byte-range requests support video playback and seeking; responses disable caching.

Legacy files remain readable through the protected endpoint from their existing storage. **Block direct legacy media URLs in nginx before reopening the application after migration**:

```nginx
location ^~ /media/flicks/ { return 404; }
```

Apply the equivalent restriction to every external media host/CDN if one is introduced. Do not publish the private directory through nginx aliases. Existing third-party copies cannot be recalled by this change.

Take a database/code/environment/nginx backup, stop the service, update code, run migrations and Django checks, collect static files, validate/reload nginx and start the service. Verify direct `/media/flicks/` paths return 404 and protected routes enforce status and identity. Rollback requires restoring the matching database and code; do not remove moderation fields while the new application is running.

## Validation

`jobs.test_flick_moderation` covers forged publication status, consent bypass attempts, approval/rejection, audit and notification idempotence, staff restrictions, CSRF, promotion separation, private media authorization, legacy/shared names, inactive owners, byte ranges and invalid uploads. Related form, business-profile, delegated marketing and assigned-admin tests exercise integrations. Human reviewers must assess actual content; this feature does not claim automatic content classification.
