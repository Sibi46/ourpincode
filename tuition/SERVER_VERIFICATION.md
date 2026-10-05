# Operator evidence commands — no deployment

Status: **BLOCKED** until an authorized operator supplies reviewed evidence. Run metadata-only commands on the server; do not send credentials, environment dumps, private filenames, student records or raw logs. No command below installs, restarts or migrates anything. If tuition is not deployed/provisioned, record that fact; do not enable it to complete this audit.

Prioritized execution and explicit PASS/FAIL/BLOCKED criteria are in [SERVER_VERIFICATION_PLAN.md](SERVER_VERIFICATION_PLAN.md). Its state-changing examples are **staging-only, preparation only**; they were not executed. The metadata commands in this document remain read-only apart from ordinary audit/access logging.

## 1. Private storage and unauthorized access

On the Linux host:

```bash
sudo systemctl show ourpincode --property=ActiveState,SubState,User,Group,WorkingDirectory,FragmentPath,EnvironmentFiles
sudo nginx -t
sudo nginx -T 2>&1 | grep -E 'configuration file|^[[:space:]]*(server_name|listen|location|root|alias|autoindex|internal|proxy_cache|proxy_no_cache|proxy_cache_bypass|proxy_ignore_headers|proxy_set_header X-Forwarded-Proto|add_header (Strict-Transport-Security|X-Content-Type-Options|X-Frame-Options|Referrer-Policy))'
read -r -p 'Configured absolute TUITION_PRIVATE_ROOT (path only): ' tuition_private
read -r -p 'Actual application service user: ' tuition_user
test -n "$tuition_private" && test -n "$tuition_user"
sudo realpath -- "$tuition_private"
sudo namei -l -- "$tuition_private"
sudo stat -c '%a %U %G %F' -- "$tuition_private"
sudo getfacl -cp -- "$tuition_private"
sudo -u "$tuition_user" test -r "$tuition_private" && echo 'app directory readable'
sudo -u "$tuition_user" test -w "$tuition_private" && echo 'app directory writable'
sudo -u nobody test -r "$tuition_private" && echo 'FAIL: unrelated user can read directory' || echo 'unrelated user denied (check command errors too)'
```

Expected: service active/running with a deliberate non-root identity; Nginx config valid; resolved private root exists outside checkout, public media/static and web roots. Restricted owner/group access (typically directory 0700 or carefully scoped 0750), no broad ACL, no public alias/root/symlink path reaching it. App has required read/write/traverse access; unrelated accounts do not. If Nginx and Django share an account, filesystem access alone cannot prove safety: review every matching location, alias, internal redirect and CDN mapping. Do not chmod anything during evidence collection. A missing tool/error is BLOCKED, not a denial PASS.

Review actual file modes and symlink targets locally using an approved **synthetic fixture only**; never enumerate real student media for this audit. Record effective `TUITION_PRIVATE_ROOT`, `MEDIA_ROOT`, `STATIC_ROOT`, checkout and service identity from the service's actual configuration without sharing its environment file. Directory metadata alone does not prove all file modes or CDN policies.

Staging unauthorized-download matrix (synthetic fixture with known stored bytes): anonymous, unrelated teacher, unrelated guardian, revoked guardian -> 403/404 or login redirect with no file bytes; current guardian -> 200 and correct bytes; both `/tuition/files/<uuid>/` and `/tuition/gallery/<uuid>/file/`. Verify `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`; revoked consent must block public showcase downloads after a prior permitted fetch. Raw storage-key URLs under `/media/`, `/static/` and any actual configured aliases must never return the fixture bytes. Verify CDN/cache-hit and origin paths. A random nonexistent URL returning 404 is **not evidence** that an existing private file is protected.

Production file-access testing is **BLOCKED** by the no-production-data restriction and absence of an approved existing synthetic fixture. Do not create a production canary or request a real student file without separate authorization.

## 2. Scheduler metadata (do not run the production command)

```bash
date -u
timedatectl show --property=Timezone,NTPSynchronized
systemctl list-timers --all --no-pager
sudo systemctl show tuition-schedule.timer --property=LoadState,ActiveState,LastTriggerUSec,NextElapseUSecRealtime
sudo systemctl show tuition-schedule.service --property=LoadState,User,Group,WorkingDirectory,EnvironmentFiles,Result,ExecMainStatus,ExecMainStartTimestamp,ExecMainExitTimestamp
sudo grep -Rl -- 'tuition_schedule' /etc/cron.d /etc/crontab /var/spool/cron/crontabs 2>/dev/null
```

Expected: one deliberate timer/cron path, matching application user/working directory/environment, recent successful execution, future trigger, synchronized clock. If unit names differ, repeat `systemctl show` with the actual names. Privately inspect the reported unit/cron file to confirm it runs the correct venv's `manage.py tuition_schedule`; don't paste commands containing secrets. Missing units plus no cron evidence means NOT VERIFIED, not automatically a confirmed production defect. No scheduler unit currently exists in this repository.

Staging schedule target: agree a delivery-latency objective (proposed <=5 minutes plus runtime), prevent overlapping runs, define failure alerts, and check reminder day/time behavior. A once-daily schedule can delay scheduled announcements nearly a day; choose cadence explicitly. Staging operator should observe a future approved announcement become due, an event in the next 24 hours, a due fee, and a pending delivery retry. Run the command twice **on isolated staging only**; counts must not duplicate. Exercise a staging-only delivery failure, observe nonzero/error alert, recover and verify retry. Do not run `tuition_schedule` on production now: it writes sessions and notifications.

## 3. Backup/restore

Use [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md). Current synthetic rehearsal does not authorize production backup access. Production backup encryption, off-host retention, restoration permissions and measured recovery objectives remain BLOCKED until operator evidence is available. Never send dumps/media to this conversation.

## 4. HTTPS, headers and configuration

These optional operator commands fetch headers/TLS metadata only; they were not executed against production by the agent:

```bash
for tuition_host in ourpincode.com www.ourpincode.com; do
  curl --head --silent --show-error --max-time 20 "http://$tuition_host/" | grep -Ei '^(HTTP/|location:)'
  curl --head --silent --show-error --max-time 20 "https://$tuition_host/" | grep -Ei '^(HTTP/|location:|strict-transport-security:|x-content-type-options:|x-frame-options:|referrer-policy:|cache-control:|content-security-policy:)'
  openssl s_client -connect "$tuition_host:443" -servername "$tuition_host" -verify_hostname "$tuition_host" -verify_return_error </dev/null 2>&1 | grep -E 'Verification:|Verify return code:|Protocol|Cipher|verify error'
done
sudo ss -lntp
sudo journalctl --disk-usage
```

Expected: HTTP -> canonical HTTPS, valid certificate/hostname/chain, no redirect loop, `nosniff`, deliberate framing/referrer policy. Check protected responses separately in staging: public homepage caching is not evidence for private media caching. Application listener should not be publicly reachable in a way that permits forged trusted proxy headers. Review the real proxy configuration to ensure it overwrites/strips incoming X-Forwarded-Proto rather than trusting arbitrary client values. Record firewall/cloud firewall restrictions privately; listening sockets alone do not prove reachability.

Record these **non-secret effective values** from the actual service environment: DEBUG, ALLOWED_HOSTS, SECURE_SSL_REDIRECT, SECURE_PROXY_SSL_HEADER, SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE, CSRF_COOKIE_SECURE, SECURE_HSTS_SECONDS/INCLUDE_SUBDOMAINS/PRELOAD, and upload/worker limits. Do not run a generic settings/environment dump. A shell without the service environment cannot establish effective settings. Run Django `check --deploy` on matching isolated staging, not an unknown production command environment.

HSTS W004: confirmed only in synthetic production defaults (`SECURE_HSTS_SECONDS=0`). No live value/header evidence exists. Do not turn it on blindly; verify HTTPS on all affected hostnames and document the owner-approved rollout. Do not add includeSubDomains or preload without checking their entire scope. Django documents this operational requirement in its [SecurityMiddleware guidance](https://docs.djangoproject.com/en/5.2/ref/middleware/#http-strict-transport-security). Trusting a proxy header also requires control of that proxy's behavior: [Django settings](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header).

Review logs locally for redaction and retention; return only a PASS/FAIL summary and redacted error category, never raw student/guardian/payment logs. Verify alerts by a controlled staging failure. Record ffprobe version/path, executable ownership, patch responsibility and worker limits from staging metadata; no production uploads requested.

## Evidence to return

For each section provide UTC date, environment, command/check, PASS/FAIL/BLOCKED, sanitized output and reviewer. Include actual service/timer names and only non-secret paths/settings. No server changes are requested. Missing configuration, unprovisioned tuition or unavailable staging should remain explicit BLOCKED entries.
