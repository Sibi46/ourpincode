# Prioritized server verification — execution pending

No commands in this plan were executed against a server. No new server evidence exists; all five operational gates and Requirement 22 remain **BLOCKED**. Existing local test results stand. Execute priorities 1–5 in order; collect read-only evidence first, then stage-only exercises after confirming isolation. Do not deploy tuition merely to test it.

## Provider discovery from local evidence

Repository inspection confirms the following **code or documentation**, not installed production services. Environment files/credential values were not printed, settings were inspected statically without starting Django, and no production connection was made. Generated audit files are not deployment evidence. A protected temporary directory could not be enumerated; absence findings below apply to inspected source/deployment documentation, not the entire server.

| Component | Confirmed local finding and location | Still unresolved |
|---|---|---|
| Hosting provider | User previously identified DigitalOcean. No checked-in DigitalOcean resource/IaC configuration was found in inspected files. | Exact project/Droplet identity, region, attached volumes, managed services and current resource configuration. Historical user identification is not dashboard verification. |
| Media/storage | `jobportal/settings.py:245–254` defines environment-overridable static/media/private roots under a sibling application-data directory. `tuition/storage.py:13` constructs FileSystemStorage and rejects overlap with checkout/public roots. `newsdesk/uploads.py:12` uses FileSystemStorage, defaulting to a sibling `newsdesk-private` directory. No object-storage/CDN backend found in inspected settings/dependencies. | Effective production paths, mounts/ACLs, external overrides, bucket/CDN or web-server aliases. With documented checkout `/var/www/ourpincode`, the unoverridden default data directory would be `/var/www/ourpincode-data`; this is a derived default, NOT a verified server path. |
| Reverse proxy/deployment service | `SEO_DEPLOYMENT.md` names `/etc/nginx/sites-available/ourpincode`, `/var/www/ourpincode`, OS user `ourpincode`, and systemd unit `ourpincode`. It describes HTTP redirects plus existing TLS/WebSocket/static/upload proxy behavior. | Current enabled Nginx site, actual service user/unit, upstream listener, cloud proxy/LB and live TLS termination. No checked-in unit or Nginx site file was found. |
| Application server | `jobportal/settings.py:292` documents Daphne logging to the `ourpincode` systemd journal. `jobportal/asgi.py` wires Django HTTP and authenticated/origin-validated Channels WebSockets. `requirements.txt` includes both Daphne and Gunicorn. | Actual unit executable/worker topology. A dependency or comment is not proof of which server is running. |
| Redis/cache/background work | `jobportal/settings.py:403–407` defines REDIS_URL (loopback default) and RedisChannelLayer. `settings.py:283` configures FileBasedCache, not Redis for Django cache. Dependencies include channels-redis. `tuition/management/commands/tuition_schedule.py`, `community/management/commands/send_birthday_notifications.py` and `jobs/management/commands/expire_jobs.py` exist. | Redis service/endpoint and installed cron/timers. Channels Redis is not evidence of Celery, a task queue or installed scheduler. No Celery config/dependency, worker unit or schedule definition was found in inspected source. |
| Database | `jobportal/settings.py:195` selects Django's MySQL backend using DB_NAME/USER/PASSWORD/HOST/PORT environment inputs. | Local MySQL vs managed service, version, engine configuration, TLS and backup ownership. No DB credentials/endpoints queried or printed. |
| Backups | Historical untracked `.test-tmp/deploy_newsdesk.py:32–42` describes a timestamped server-local mysqldump under `/var/backups`; its credential-bearing contents were not printed or executed. New `tuition/audit_recovery.py` is explicitly a synthetic local rehearsal. | No evidence these historical commands ran; no confirmed recurring DB/media backup, encryption, off-host destination or restoration. No encryption/off-host command was found in that helper. Neither helper establishes a production backup system. |
| HTTPS/security | `jobportal/settings.py:104–114` sets trusted X-Forwarded-Proto, default HTTPS redirect/secure cookies/nosniff/DENY; HSTS default zero. `SEO_DEPLOYMENT.md` documents Nginx TLS handling. | Certificate issuer/renewal mechanism, real headers/HSTS values, proxy header overwrite and any upstream LB/CDN. Certbot/Let's Encrypt is NOT confirmed. |

### Service-specific read-only commands now supported by evidence

**R — operator runs on server; not executed here. No restart/reload/enable, DB query or file-content download.**

```bash
set -o pipefail
sudo systemctl show ourpincode --property=LoadState,ActiveState,SubState,User,Group,WorkingDirectory,FragmentPath,MainPID,EnvironmentFiles
tuition_pid=$(systemctl show ourpincode --property=MainPID --value)
case "$tuition_pid" in ''|0|*[!0-9]*) echo 'BLOCKED: no valid active MainPID';; *) ps -p "$tuition_pid" -o pid=,comm=;; esac
sudo systemctl show nginx --property=LoadState,ActiveState,SubState,FragmentPath
sudo nginx -t
sudo stat -c '%a %U %G %F' /etc/nginx/sites-available/ourpincode
sudo readlink -f /etc/nginx/sites-enabled/ourpincode
sudo nginx -T 2>&1 | grep -E 'configuration file|^[[:space:]]*(server_name|listen|location|root|alias|autoindex|internal|ssl_certificate[[:space:]]|ssl_protocols|proxy_cache|proxy_no_cache|proxy_cache_bypass|proxy_ignore_headers|proxy_set_header X-Forwarded-Proto|add_header (Strict-Transport-Security|X-Content-Type-Options|X-Frame-Options|Referrer-Policy))'
```

Expected: documented site is included/enabled, syntax valid, service metadata consistent with deployment docs. A nonexistent sites-enabled name may mean another include/name, not absence of Nginx; inspect reported includes. Process name may be only `python`, so it cannot prove Daphne/Gunicorn: operator must review actual ExecStart privately and report only executable/worker type, never full arguments/environment. Filtered Nginx output omits certificate-key contents and most headers, but still review locally before sharing.

**R — identify mounts without listing or reading media** (use only actual configured path confirmed privately):

```bash
read -r -p 'Verified TUITION_PRIVATE_ROOT absolute path: ' tuition_private
case "$tuition_private" in /*) ;; *) exit 1;; esac
sudo findmnt --target "$tuition_private" --output TARGET,SOURCE,FSTYPE
sudo stat -c '%a %U %G %F' -- "$tuition_private"
sudo namei -l -- "$tuition_private"
```

Expected mount/ownership ties the storage root to the correct Droplet disk/volume and backup scope. No mount options are printed (they can contain credentials). Reuse priority 1 ACL/CDN checks; filesystem source code does not rule out an upstream CDN.

**R — discovery only; unit names below are candidates, not confirmed installations:**

```bash
systemctl list-unit-files --type=service --no-pager | grep -Ei 'ourpincode|nginx|redis|mysql|mariadb|celery|rq|supervisor|backup|restic|borg'
systemctl list-timers --all --no-pager
sudo grep -Rl -- 'tuition_schedule\|send_birthday_notifications\|expire_jobs' /etc/cron.d /etc/crontab /var/spool/cron/crontabs
```

Expected inventory identifies actual unit/schedule names; grep no-match is not proof of no external orchestration. For a discovered unit, use `systemctl show ACTUAL_UNIT --property=LoadState,ActiveState,SubState,User,FragmentPath,Result,ExecMainStatus,OnFailure`. Do not execute management commands, Redis key/queue queries, SQL or logs. An externally managed Redis/MySQL endpoint will not necessarily have a local unit.

**R — certificate metadata only, if Nginx configuration identifies a local public certificate file:**

```bash
read -r -p 'Verified ssl_certificate path (NOT ssl_certificate_key): ' tuition_certificate
case "$tuition_certificate" in /*) ;; *) exit 1;; esac
sudo openssl x509 -in "$tuition_certificate" -noout -issuer -subject -dates
systemctl list-timers --all --no-pager | grep -Ei 'certbot|acme|certificate'
```

Expected issuer/SAN verification via the existing hostname TLS probe, validity and identified renewal ownership. Do not assume Certbot from the issuer; issuance and renewal tools may differ. These commands do not renew a certificate. If TLS ends at a load balancer/CDN, inspect its dashboard metadata instead.

### Exactly what to check in the hosting dashboard

Use the **existing DigitalOcean account identified by the user**, in view-only mode. No new tokens, resources, snapshots, restores, toggles or downloads. If the actual host differs, stop and identify it. Return sanitized metadata only:

1. **Project / Droplet:** correct OURPINCODE resource ID/name, region, status, attached volume identifiers/mount ownership, connected load balancers and cloud firewall. Confirm which disk contains DB, public media and private tuition/news files; the app's file paths alone cannot establish backup coverage.
2. **Spaces / CDN:** whether any Space is actually used by OURPINCODE; bucket/region and origin/CDN/custom-host relationship, public-listing/object-access policy and cache settings. If none is used, record an operator-confirmed “no OURPINCODE Spaces/CDN resource,” not “none exists” based on Django dependencies. Do not list/download objects or keys. [Spaces CDN reference](https://docs.digitalocean.com/products/spaces/reference/api/cdn-endpoints/).
3. **Networking / domains / load balancers:** DNS A/AAAA/CNAME target, authoritative DNS provider, linked LB and forwarding rules, TLS termination vs pass-through, certificate expiry/renewal ownership, origin firewall restriction. DigitalOcean load balancers can terminate TLS; this does not establish that this site uses one. [Provider capabilities](https://docs.digitalocean.com/products/networking/load-balancers/details/features/). If DNS/proxy is elsewhere, provide that provider name and sanitized proxy/cache/TLS settings there; Cloudflare is currently unconfirmed.
4. **Droplet backups/snapshots and attached-volume protection:** enabled/disabled status, most recent successful recovery point, schedule/retention, exact disks/resources covered and restore-policy owner. Obtain provider documentation/configuration for encryption and recovery access; do not treat the label “backup” as application-consistent DB+media evidence. No restore or snapshot creation now. [DigitalOcean backup documentation](https://docs.digitalocean.com/products/backups/).
5. **Managed Databases:** whether OURPINCODE uses a managed MySQL/Redis resource; service type/version/region, trusted-source restrictions, encryption/TLS policy and backup/retention status where applicable. No credentials, connection strings, console queries or data downloads. If self-hosted, record that and use OS-service metadata instead.
6. **Alerts / external scheduler / backup vendor:** identify the configured schedule/monitoring service, backup agent/vendor, encryption/key-custody system, off-host destination type/region, latest success/failure status, alert policy and tested delivery receipt (recipient details redacted). Droplet health monitoring alone does not prove tuition job or backup failure alerts. If an App Platform worker/job or external cron product is used, report its actual resource name/schedule/environment association. No such service is locally confirmed.
7. **Staging:** existing resource/domain, separate DB/storage and disabled real integrations, build revision and device-test owner. Do not create or deploy staging under this request.

Dashboard metadata may resolve provider identity, but cannot replace the remaining permission, representative restore, alert/retry and physical-device acceptance evidence. Until supplied, provider-dependent commands and gates remain **BLOCKED**. All commands added in this discovery section are read-only; earlier **S** snippets remain state-changing staging-only proposals, not part of this inspection.

## Command classifications and evidence rules

- **R — server access, read-only:** service/configuration/filesystem metadata; sudo may be required. Ordinary system audit logging can occur. No production records or file contents.
- **H — network headers/handshake:** no SSH required; requests can write access logs and affect cache counters. No authenticated production requests or production file bodies.
- **S — changes isolated staging state:** creates synthetic records/files, sends staging notifications or writes recovery artifacts. Commands are preparation only; verify target/environment and obtain authorization for the specific staging environment before execution. Never substitute production paths/settings.
- **M — manual review/sign-off:** screenshots/settings from approved staging or sanitized operator configuration evidence. Missing tool, permission, target, provider or evidence is BLOCKED, not PASS. Nonzero commands must be investigated, not hidden by a successful pipeline filter.

Use Bash for the Linux snippets. Run `set -o pipefail` before pipelines and record exit status immediately. Do not use shell tracing (`set -x`), `env`, `printenv`, `systemctl show ... Environment`, full settings dumps or raw log exports. Review outputs locally and share only sanitized metadata. Record UTC time, exact build/config revision, environment, command exit status, reviewer and evidence reference. A proposed command is not evidence.

## 1 — Private media storage and proxy/CDN isolation

**R: server identity and path metadata**

```bash
set -o pipefail
date -u +%FT%TZ
sudo systemctl show ourpincode --property=LoadState,ActiveState,SubState,User,Group,WorkingDirectory,FragmentPath,EnvironmentFiles
sudo nginx -t
read -r -p 'Verified configured private-root absolute path: ' tuition_private
read -r -p 'Verified application OS user: ' tuition_user
test -n "$tuition_private" && test -n "$tuition_user" || exit 1
case "$tuition_private" in /*) ;; *) echo 'BLOCKED: absolute path required'; exit 1;; esac
sudo realpath -- "$tuition_private"
sudo namei -l -- "$tuition_private"
sudo stat -c '%a %U %G %F' -- "$tuition_private"
sudo getfacl -cp -- "$tuition_private"
sudo -u "$tuition_user" test -r "$tuition_private"; printf 'app read exit=%s\n' "$?"
sudo -u "$tuition_user" test -w "$tuition_private"; printf 'app write exit=%s\n' "$?"
sudo -u "$tuition_user" test -x "$tuition_private"; printf 'app traverse exit=%s\n' "$?"
sudo -u nobody test -x "$tuition_private"; printf 'unrelated traverse exit=%s\n' "$?"
```

Expected: valid service identity, directory outside checkout/public media/static, app exits 0, unrelated traversal denied (exit 1 from `test`, with no sudo/tool error), restrictive mode/ACL. Check all parent directories and any symlink resolution; do not infer security from a numeric mode alone. Privately review file-level permissions on an already approved synthetic file, not real student files. Use the filtered Nginx command in [SERVER_VERIFICATION.md section 1](SERVER_VERIFICATION.md#1-private-storage-and-unauthorized-access); inspect all relevant inherited locations/aliases/cache rules, not just the named private directory.

**M:** obtain CDN provider and sanitized route/cache policy evidence. Confirm no public object bucket/alias/symlink/internal redirect exposes this root; private responses bypass caches and public-cache overrides do not ignore `Cache-Control`. Provider API commands cannot be supplied accurately until the provider/resource identity is known: **BLOCKED**, do not guess cloud IDs or expose tokens.

**H/S, staging only:** use an existing approved synthetic image and known UUID/storage key. Staging fixture setup, login and consent revocation change state. From a signed-in staging browser, request both `/tuition/files/<uuid>/` and `/tuition/gallery/<uuid>/file/`, verify exact bytes/hash and `private, no-store`/`nosniff`. Repeat as anonymous, unrelated teacher/guardian and after guardian/publication revocation; warm the permitted path before revocation and test the identical URL again at edge and origin. Browser cookies stay local, never copied into command history or reports.

For anonymous header probes of each **known staging fixture** path:

```bash
read -r -p 'Approved staging origin, https://host (not production): ' tuition_stage
case "$tuition_stage" in https://ourpincode.com*|https://www.ourpincode.com*) exit 1;; https://*) ;; *) exit 1;; esac
read -r -p 'Synthetic fixture UUID: ' tuition_fixture
for tuition_path in "/tuition/files/$tuition_fixture/" "/tuition/gallery/$tuition_fixture/file/"; do
  curl --head --silent --show-error --max-time 20 "$tuition_stage$tuition_path" |
    grep -Ei '^(HTTP/|location:|cache-control:|x-content-type-options:|age:|x-cache:|cf-cache-status:)'
  printf 'probe exit=%s\n' "$?"
done
```

These string checks do not establish environment isolation; verify DNS, database, storage, credentials and CDN independently. HEAD alone is not a bytes-denial test. Raw-key GET checks under every configured alias must use synthetic staging content and verify no fixture bytes. A nonexistent UUID/404 or login page with status 200 is not PASS.

**PASS:** effective ACL/path/proxy/CDN evidence plus both-route authorized/denied/revoked byte/cache matrix pass on a matching configuration; production controls have independent operator evidence. **FAIL:** any unauthorized fixture bytes, stale cache disclosure, public alias, broad permissions or wrong tenant access. **BLOCKED:** missing server/CDN configuration or approved fixture, no deployment, or no permitted production evidence. Do not create a production canary under this request.

## 2 — Installed scheduler, retries and failure alerts

**R: actual unit metadata; replace names only with discovered units**

```bash
timedatectl show --property=Timezone,NTPSynchronized
systemctl list-timers --all --no-pager
sudo systemctl show tuition-schedule.timer --property=LoadState,ActiveState,LastTriggerUSec,NextElapseUSecRealtime
sudo systemctl show tuition-schedule.service --property=LoadState,Type,User,Group,WorkingDirectory,EnvironmentFiles,Result,ExecMainStatus,ExecMainStartTimestamp,ExecMainExitTimestamp,OnFailure
sudo grep -Rl -- 'tuition_schedule' /etc/cron.d /etc/crontab /var/spool/cron/crontabs
```

Expected: installed timer active with next/last trigger; last run `Result=success`, `ExecMainStatus=0`; correct app environment and clock. A successful oneshot service normally returns inactive/dead between triggers—this alone is not failure. Cron is acceptable with equivalent run-history/overlap/alert evidence; grep exit 1 is no match, exit 2 is an inspection error. Inspect cron/unit execution command locally without sharing secrets. `OnFailure=` empty does not prove alerts absent if external monitoring exists, and nonempty does not prove delivery.

**S: only inside an already provisioned, verified synthetic staging checkout and venv with its staging environment loaded:**

```bash
python manage.py tuition_schedule
printf 'first exit=%s\n' "$?"
python manage.py tuition_schedule
printf 'second exit=%s\n' "$?"
```

Expected `Generated N sessions.` then no additional duplicates for unchanged fixtures (normally second `Generated 0 sessions.`). Record row/inbox counts using synthetic staging UI and approved aggregate checks. Observe an actual timer trigger delivering a due approved announcement, next-day event and due fee once; check delivery latency against the agreed target. Proposed five-minute cadence is not installed or approved by this plan.

**S, existing disposable LOCAL MySQL test environment only:**

```text
.venv\Scripts\python.exe manage.py test tuition.test_readiness.ReadinessTests.test_scheduler_command_due_notifications_and_retry --settings=tuition.audit_mysql_settings --noinput --keepdb
```

This was already PASS; do not rerun unchanged. It injects a failure in test code, checks pending retry and deduplication; it does **not** test installed alert infrastructure. Real alert acceptance requires the monitoring owner's approved staging fault-injection/synthetic probe, observable failed job, received alert and successful recovery. Exact provider-specific injection is BLOCKED until that integration is identified; never stop production services, break DB credentials or send real notifications to simulate failure.

**PASS:** installed schedule, correct environment, no overlap/duplicates, agreed delivery latency and witnessed staging failure-alert/retry recovery. **FAIL:** wrong environment, missed/duplicate delivery, failure reported as success, or configured alert fails its agreed test. **BLOCKED:** absent config/history, no staging alert target or no approved test. Never run production `tuition_schedule` now—it writes records.

## 3 — Encrypted off-host backups and representative recovery

**R: metadata only, without opening real backup contents**

```bash
read -r -p 'Actual backup timer unit: ' tuition_backup_timer
read -r -p 'Actual backup service unit: ' tuition_backup_service
test -n "$tuition_backup_timer" && test -n "$tuition_backup_service" || exit 1
sudo systemctl show "$tuition_backup_timer" --property=LoadState,ActiveState,LastTriggerUSec,NextElapseUSecRealtime
sudo systemctl show "$tuition_backup_service" --property=LoadState,User,Result,ExecMainStatus,ExecMainStartTimestamp,ExecMainExitTimestamp,OnFailure
```

Expected recent successful snapshot job and next run; obtain sanitized provider metadata for off-host object ID, creation time, retention, encryption/key identifier, access policy and failure alerts. A file extension, successful job or same-host copy does not prove encryption/off-host recovery. No backup provider, key system, approved volume or recovery targets have been supplied. Exact provider metadata/download/decryption commands remain **BLOCKED** until those non-secret details are known; inventing them would risk reading production data or using incorrect keys.

**S: new local synthetic recovery only**, already PASS; retain existing result rather than rerun:

```text
.venv\Scripts\python.exe -m tuition.audit_recovery
```

Creates fresh synthetic MySQL databases/media and backup files on the dedicated loopback instance; no production credentials. Expected final JSON `status: PASS`, row/media manifest matches, recovered fee balance and guardian-denial checks. This small unencrypted local rehearsal is not the encrypted off-host gate.

**S/M: representative exercise, preparation only:** agree synthetic row counts, media count/bytes, concurrent write assumptions and RPO/RTO from sanitized capacity estimates. Use the actual approved backup/encryption/off-host path on isolated staging, retrieve into a **new empty** recovery DB/root, and follow [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md). Ensure external messaging/payments are disabled. No real customer data, production backup reads, overwrite, DROP, schema reversal or destructive cleanup. Use a key-recovery custodian independent of the backup writer. Verify media hashes, all relevant table counts/content digests, schema/FKs, balances, audit/consent and protected downloads; measure elapsed restore and snapshot age.

Exact checksum command for a known **synthetic** encrypted archive and its retrieved copy, on the recovery host:

```bash
read -r -p 'Synthetic encrypted source archive path: ' tuition_archive
read -r -p 'Retrieved synthetic encrypted copy path: ' tuition_retrieved
sha256sum -- "$tuition_archive" "$tuition_retrieved"
cmp --silent -- "$tuition_archive" "$tuition_retrieved"
printf 'encrypted-copy comparison exit=%s\n' "$?"
```

Expected matching digests and exit 0. This only proves byte equality, not encryption or decryption/recovery correctness. Do not point these commands at production backups under this request.

**PASS:** authenticated encrypted off-host snapshot, tested access restrictions/retention/key recovery, paired DB/media restore at representative volume, integrity/access tests and measured RPO/RTO within approved limits. **FAIL:** missing/corrupt objects, decryption failure, mismatched rows/files/balances/permissions, or missed agreed objectives. **BLOCKED:** unknown provider/key process, absent representative fixture/objectives, no authorized recovery environment/evidence. Tiny local timings do not establish production targets.

## 4 — HTTPS certificate, HSTS, reverse proxy and headers

**H: public TLS/headers only**

```bash
set -o pipefail
for tuition_host in ourpincode.com www.ourpincode.com; do
  curl --head --silent --show-error --max-time 20 "http://$tuition_host/" | grep -Ei '^(HTTP/|location:)'
  printf 'HTTP probe exit=%s\n' "$?"
  curl --head --silent --show-error --max-time 20 "https://$tuition_host/" | grep -Ei '^(HTTP/|location:|strict-transport-security:|x-content-type-options:|x-frame-options:|referrer-policy:|content-security-policy:)'
  printf 'HTTPS probe exit=%s\n' "$?"
  timeout 20 openssl s_client -connect "$tuition_host:443" -servername "$tuition_host" -verify_hostname "$tuition_host" -verify_return_error </dev/null 2>&1 | grep -E 'Verification:|Verify return code:|Protocol|Cipher|verify error'
  printf 'TLS probe exit=%s\n' "$?"
  timeout 20 openssl s_client -connect "$tuition_host:443" -servername "$tuition_host" </dev/null 2>/dev/null | openssl x509 -noout -dates -checkend 2592000
  printf '30-day certificate horizon exit=%s\n' "$?"
done
```

Expected HTTP 301/302/307/308 to intended HTTPS host, TLS hostname/chain verification successful, valid certificate and documented renewal plan; 30-day horizon exit 1 needs expiry/renewal investigation, not an automatic finding that current TLS is invalid. Follow legitimate canonical redirects manually and check destination too. Curl HEAD may differ from GET: compare actual browser GET headers on synthetic staging pages. Never use `-k` to turn a TLS failure into a pass.

**R:** `sudo nginx -t`, filtered Nginx configuration from SERVER_VERIFICATION.md, `sudo ss -lntp`; obtain sanitized firewall/cloud firewall and proxy chain settings. Expect origin application listener unreachable by untrusted clients; trusted proxy strips/overwrites X-Forwarded-Proto, appropriate redirect/Host handling, no redirect loop. Socket bindings alone do not establish firewall/CDN controls.

**S, verified staging environment only:**

```bash
python manage.py check --deploy
printf 'deployment check exit=%s\n' "$?"
```

Django initialization may run app startup hooks; do not run in an unknown environment. Expected no unresolved security warnings; exit 0 alone is insufficient because Django can emit warnings without nonzero exit. Privately record allowlisted effective security settings from SERVER_VERIFICATION.md, actual HTTPS/private-response headers and cookie flags through browser DevTools. Do not publish cookie values. Headers must reflect endpoint policy: nosniff, deliberate framing/referrer protections, private no-store; CSP absence alone is not a confirmed defect without an agreed policy.

HSTS W004 is currently known only for synthetic defaults. Require an explicit verified HTTPS/HSTS policy before passing; do not blindly change max-age, includeSubDomains or preload. See [Django HSTS guidance](https://docs.djangoproject.com/en/5.2/ref/middleware/#http-strict-transport-security) and [trusted proxy requirements](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header). No configuration change is authorized by a finding; propose a concrete fix for review separately.

**PASS:** verified certificate/renewal, canonical HTTPS, reviewed HSTS policy/effective headers, safe trusted proxy boundary, protected cookies/files and no unresolved check warnings. **FAIL:** invalid certificate, actual unprotected transport, forged proxy trust, private public-cache response, or confirmed policy violation. **BLOCKED:** no live effective values, inaccessible endpoint/inspection, unresolved W004 or unreviewed policy. HSTS is not marked fixed by changing an audit setting.

## 5 — Staging and physical-device sign-off

**H/M: identify the existing approved staging target; do not provision/deploy**

```bash
read -r -p 'Approved isolated staging origin https://host: ' tuition_stage
case "$tuition_stage" in https://ourpincode.com*|https://www.ourpincode.com*) exit 1;; https://*) ;; *) exit 1;; esac
curl --head --silent --show-error --max-time 20 "$tuition_stage/tuition/" | grep -Ei '^(HTTP/|location:|x-content-type-options:)'
printf 'staging reachability exit=%s\n' "$?"
```

Expected reachable intended build and route. Response 200 alone does not prove build, environment or database isolation. Operator records build revision, DB version, synthetic-only storage and disabled external integrations before any scenario. If tuition is absent, BLOCKED; do not deploy to satisfy the probe.

**S/M:** execute [STAGING_SMOKE_TESTS.md](STAGING_SMOKE_TESTS.md) with approved synthetic roles on physical Android Chrome/iPhone Safari and desktop Chrome/Firefox. Auth, applications, fees, consent, posts and notifications change staging state. Cover all tuition rows plus legacy home/business/marketing/admin/jobs/campus/offers/coupons/vouchers/community/network/flicks/news/quiz/health/messages/wallet flows. Keep real charges, real recipients, analytics and health/provider calls disabled or mocked. Include orientation/zoom/keyboard, real synthetic device video, interrupted upload, scheduling and paired recovery. No CLI can replace a physical-device sign-off.

Expected signed result per flow/device/version with sanitized screenshot and defect reference. Existing 24 offline layout checks and broad automated suite are reused, not described as physical-device tests.

**PASS:** every required matrix row/device signed off on the intended build, security negatives pass and no unresolved release-blocking defects. **FAIL:** reproduced incorrect workflow, disclosure or blocking device failure. **BLOCKED:** missing staging/devices/accounts, untested row, ambiguous build or unverified isolation.

## Final sign-off record

| Priority | Current operational status | Missing evidence |
|---|---|---|
| 1 | BLOCKED | Effective storage/ACL/proxy/CDN and authorized synthetic-fixture matrix |
| 2 | BLOCKED | Installed schedule/environment, observed trigger and real alert/retry |
| 3 | BLOCKED | Encryption/off-host provider/key evidence and representative timed restore |
| 4 | BLOCKED | Actual certificate/config/header/proxy/HSTS policy evidence |
| 5 | BLOCKED | Staging and physical-device results |

Requirement 22 stays **BLOCKED** until every applicable release gate, including its existing moderation/retention/runtime obligations, has verified evidence. Store only sanitized summaries in PHASE5_AUDIT.md and DEPLOYMENT_CHECKLIST.md; keep sensitive operator artifacts outside the repository. No deployment, push, production-data access or destructive action is included in this plan.
