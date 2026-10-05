# Phase 5 audit — 4 October 2026

Release request, 5 October 2026: user authorized GitHub push and deployment. The reviewed source is prepared for the existing `Sibi46/ourpincode` feature branch. Django checks and migration drift checks passed again; earlier test evidence is reused. Actual deployment remains pending verified server access and the unresolved release gates below. User authorization does not constitute technical verification; Requirement 22 remains BLOCKED. Environment files, unrelated edits and local audit/preview artifacts are excluded from this release commit.

Decision: local verification substantially completed; **production approval withheld**. No push, deployment, production access/data changes or reverse migrations. Checked checklist items mean local implementation evidence, not approval to release.

Planning update: [SERVER_VERIFICATION_PLAN.md](SERVER_VERIFICATION_PLAN.md) now provides priorities 1–5, command classifications, expected results and explicit PASS/FAIL/BLOCKED criteria. This is documentation evidence only: no additional server checks or tests were executed, no operational status changed, and Requirement 22 remains BLOCKED. Provider-specific CDN, backup and alert commands await actual non-secret service identities.

Local provider-discovery update: inspected project settings/dependencies/storage classes, ASGI entry point, SEO deployment documentation and a statically inspected historical news deployment helper (no execution or credential output). Confirmed filesystem-storage code; documented Nginx site and `ourpincode` systemd/user/checkout; Daphne logging comment with both Daphne/Gunicorn dependencies; Redis Channels and separate file-based Django cache; MySQL environment configuration. Historical helper describes a local mysqldump, not verified encryption/off-host backup. Installed services, effective paths, CDN, scheduler, backup vendor and TLS issuer/termination remain unverified. Full file locations, read-only commands and exact DigitalOcean dashboard questions are in the plan's provider-discovery section. No release gate changed; Requirement 22 remains BLOCKED.

## Release-readiness continuation (4 October 2026)

This section supersedes earlier statements that no synthetic backup/restore rehearsal had been completed. Earlier suite results remain valid; unchanged broad suites were not rerun. No production service, file, data, settings or endpoint was accessed during this continuation. No runtime code/configuration was changed; new work is the recovery harness, one focused scheduler test and operator runbooks.

| Ordered gate | Status | Evidence / exact remaining action |
|---|---|---|
| 1. Production private storage and unauthorized files | **BLOCKED** production; **PASS** local application/restore checks | Existing permission suite reused; restored synthetic file denied anonymous/unrelated/revoked users on both routes, permitted guardian bytes/hash/no-store verified. Production ownership/ACL/alias/CDN and known synthetic file evidence unavailable. Run SERVER_VERIFICATION.md section 1; random 404 alone is insufficient. |
| 2. Scheduler configuration and notifications | **BLOCKED** deployment configuration; **PASS** command behavior | Recovery harness ran actual command twice without duplicate sessions/notifications. New `ReadinessTests.test_scheduler_command_due_notifications_and_retry`: 1/1 passed on MySQL (0.587s); future-approved announcement becomes due, event/fee reminders delivered once, failed pending retry remains pending and later sends once, repeated command deduplicates. Real timer cadence, environment, overlap control, clock and alert evidence missing. |
| 3. Database/media recovery procedure | **PASS** synthetic rehearsal; **BLOCKED** operational backup gate | MySQL 8.4.11: 262 tables, 1,474 rows and one private image restored into a new database/root; all row-count/content digests and file SHA-256 match. INR 60 remaining invoice balance preserved. Backup 2.307s; restore plus verification 9.677s on tiny synthetic data, not production RTO. Encryption/off-host retention/key recovery/representative-volume restore remain unverified. |
| 4. Server/HTTPS/HSTS/headers | **BLOCKED** live verification | Existing synthetic default audit retains W004 (HSTS=0). Investigated against Django proxy/HSTS guidance; absence of live settings/HTTPS evidence does not justify blindly changing it. No newly confirmed runtime issue; no server configuration fix applied. Exact read-only metadata/header commands in SERVER_VERIFICATION.md section 4. |
| 5. Real-device and staging smoke tests | **PASS** preparation; **BLOCKED** execution | STAGING_SMOKE_TESTS.md covers tuition and legacy flows, role fixtures, physical Android/iOS, desktop browsers, accessibility/zoom, media and fault/recovery checks. Staging URL, approved accounts, real devices and sign-off unavailable. Prior 24 offline layout checks are not physical-device evidence. |
| 6. Requirement 22 | **PASS** listed application acceptance checks locally; **BLOCKED** release sign-off | Criterion-by-criterion evidence below; no operational blocker has been silently waived. Requirement remains unchecked. |

**FAIL:** no failing assertion in the newly executed checks. Unverified environments remain BLOCKED; W004 remains an unresolved warning, not a claimed production vulnerability or a passed HSTS gate.

Recovery evidence: ignored `.audit-tools/recovery-3cab4546f5ce/evidence.json`, matching `database.sql` and `media.zip`; source `tuition_recovery_src_3cab4546f5ce`, restored `tuition_recovery_dst_3cab4546f5ce`. All artifacts are synthetic and retained. No DROP, reverse migration or overwrite occurred. Restore comparisons were taken before deliberate synthetic login/revocation checks mutated the restored fixture. `tuition/audit_recovery.py` reproduces this in unique new databases. Local archives are unencrypted and not suitable for real data.

### Requirement 22 actual acceptance criteria

| Original criterion | Local status and evidence | Production limitation |
|---|---|---|
| Role-based access | **PASS** core/activity tests for owner/other teacher, main/scoped admin and state/section filters; current enrolment reload readiness tests | Matching staging roles/session/proxy smoke sign-off **BLOCKED** |
| Private student information | **PASS** private learner fields/certificates/fees and both download routes; fresh recovery verifies guardian-only file bytes/no-store | File modes, ACL, aliases, CDN/cache isolation **BLOCKED** |
| Child-safety protections | **PASS** verified guardian/adult authorization, revision/all-subject consent, expiry/revocation/adult transition and no minor private teacher thread | Human identity/guardian review, subject moderation and retention procedure sign-off **BLOCKED** |
| Upload validation | **PASS** raster validation, real MP4/WebM and corrupt/audio/disguised rejection | Production ffprobe maintenance/resource limits and actual device recordings **BLOCKED** |
| Duplicate-enrolment prevention | **PASS** lifetime learner/lesson unique constraint, idempotent acceptance, MySQL constraints and capacity races | Production-version schema rehearsal **BLOCKED** |
| Secure meeting links | **PASS** HTTPS host validation, current authorized participant, time window, cancelled/revoked denial and links absent from public page | Physical conferencing-provider/device smoke **BLOCKED** |
| Payment consistency | **PASS** Decimal ledger, balance/status/reversal/idempotency, audit rollback and three payment races; recovery preserves balance/data | Representative recovery and production-version test **BLOCKED**; gateway explicitly deferred |
| Audit trails | **PASS** transactional AdminActivity services and rollback-on-audit-failure tests; backup includes restored database records | Log access/redaction/retention, monitoring and operator review **BLOCKED** |
| Unauthorized access protection | **PASS** cross-tenant/guardian/legacy chat/admin exclusions, CSRF tests and restored revoked-file denial | Live TLS/proxy trust, security headers, staging and raw-path/cache tests **BLOCKED** |

New/updated continuation files: `audit_recovery.py`, `test_readiness.py`, `SERVER_VERIFICATION.md`, `RECOVERY_RUNBOOK.md`, `STAGING_SMOKE_TESTS.md`, this report, DEPLOYMENT_CHECKLIST.md and the root requirement checklist. Deployment remains unauthorized until explicit approval after every gate is verified.

Continuation cleanup: the temporary localhost MySQL service was shut down gracefully; synthetic databases/media/backups retained. Python compilation and tracked diff whitespace checks passed. No dependency, schema or runtime configuration changes were needed.

## Evidence and limits

- SQLite regression suite: **460 run, 453 passed, seven MySQL-only skips**; those seven passed separately on MySQL. Explicit app labels include jobs, community, campus, portal, coupons, vouchers, quiz, health, newsdesk, jobportal and tuition. Root-level live-data inspection scripts were deliberately excluded. Existing automated coverage is not proof of every legacy feature or external integration.
- MySQL Community 8.4.11, disposable loopback-only instance on port 13317: 120 tests run, 119 passed, one optional UI-export skip. All seven real concurrent tests passed: duplicate payment key, overpayment prevention, duplicate reversal, batch capacity, event capacity, point deduplication and guardian revocation/publication. Six additional readiness checks passed in a subsequent targeted run (one optional export skipped).
- All six tuition migrations applied forward on fresh isolated SQLite/MySQL databases. Django check passed; migration drift check found no changes. No new migration required by audit fixes.
- Real FFmpeg/ffprobe 9.0.2: generated MP4/H.264 and WebM/VP8 accepted; corrupt MP4, audio-only MP4 and renamed Matroska rejected. Tests use synthetic one-second clips. This is not exhaustive codec/device coverage or a malware-proof sandbox.
- Offline Chromium: eight synthetic Django-rendered pages at 320, 390 and 1280px; 24 checks, no horizontal overflow, visible hidden inputs or JavaScript page errors. Teacher/mobile and event-form/mobile screenshots reviewed. External requests blocked. This is not a physical-device, Safari, keyboard/accessibility or end-to-end browser mutation audit.
- Production-default check with synthetic secrets and dotenv disabled: one warning, `security.W004` (HSTS defaults to zero). HTTPS redirect/secure cookie defaults inspected. Live environment, TLS/proxy trust, storage aliases, log rotation, backups and scheduled service configuration were not accessed or verified.

Local logs/screenshots/tools are in ignored `.audit-tools/`; they contain synthetic fixtures, are not release assets, and must not be uploaded. The test MySQL database is retained, not dropped. No production credentials were used.

Final follow-up: corrected templates rendered successfully in an additional MySQL test; all 24 offline browser checks passed again. The temporary MySQL instance was shut down gracefully after testing, with its synthetic files retained. Python compilation and tracked diff whitespace checks passed.

## Confirmed findings and fixes

1. Renamed Matroska passed the former WebM magic-byte test. Added bounded EBML DocType parsing and container-specific codec allowlists; real-file regression passes.
2. Cached enrolment objects could outlive withdrawal in event registration/message authorization. Reload current enrolment (locked for registration); regression tests reject stale objects.
3. Scheduled generation could fail for a disabled teacher account. Skip inactive owners; regression test verifies zero generated sessions.
4. Existing news photo validation left persisted file handles open on Windows. Restore the input's original open/closed state, including repeated validation; video validation uses the same ownership discipline. Existing news upload/publish regression exercises this fix.
5. Explicit streaming-response `close()` in tests triggered request-finished database cleanup inside MySQL test transactions, producing cascading connection errors. Consume streaming content through Django's test-client wrapper instead. MySQL suite then passed; no database constraint was removed.
6. Existing settings tests lacked synthetic secret configuration; two role assertions contradicted documented legacy main/state access; an Event history assertion contradicted its previously requested removal. Corrected fixtures/expectations and added a scoped-admin denial assertion. No production legacy authorization was widened.
7. Visual review found question-mark separators in tuition templates. Replaced them with HTML middots.

Initial failed runs remain in local logs. Do not describe them as passing; results above refer to reruns after fixes.

## All 22 requirements: implementation and evidence

`core` = tuition/tests.py; `activity` = tuition/test_activities.py; `readiness` = tuition/test_readiness.py; `race` = tuition/test_mysql_concurrency.py. Exact models/URLs/permission mapping remains in the approved design, section 6, and tuition/urls.py.

| ID | Actual implementation reviewed | Evidence / remaining limit |
|---|---|---|
| 1 | TeacherProfile, subjects/service areas, public slug; register/profile views | core registration cannot self-approve, free-PIN discovery, fee privacy; activity approved galleries and image/video rendering |
| 2 | Lesson, lesson forms and owner services | core form routes, age/date/capacity and cross-teacher tests |
| 3 | Batch, BatchMembership, transfer/history | core transfer/roster tests; race last-slot serialization; activity reactivation preserves roster |
| 4 | Invitation, Application, Enrolment | core token expiry/single use, claim ownership, acceptance/request-info/rejection and duplicate constraint |
| 5 | Learner, GuardianLink, enrolment-scoped records | core private photo/identity/fees; activity main-only identity review; readiness private-root and self-verification denial |
| 6 | Teacher dashboard and activities hub | core/activity rendering, tenant authorization, teacher student points; responsive snapshot |
| 7 | Learner dashboard and activities hub | authorized multi-enrolment query, consent and fee/history tests; responsive snapshot |
| 8 | ScheduleRule, ClassSession, SessionParticipant | core recurrence/cancellation/reschedule/idempotency; readiness inactive owner; real scheduler provisioning pending |
| 9 | Session mode/location, protected join endpoint | core join windows, allowed HTTPS hosts, cancelled/revoked access; real conferencing devices pending |
| 10 | Attendance and correction history | core owner-only marks/cancelled session; activity point compensation |
| 11 | FeeAgreement, Invoice, immutable Payment | core balances/status/idempotency/reversal/audit rollback; MySQL duplicate/overpayment/reversal races pass; gateway explicitly deferred |
| 12 | LearningEvent and participation/media/results | activity nine types, window/capacity/invitations/HTTP workflows; race capacity; real MP4/WebM tests pass locally |
| 13 | Competition event, EventParticipation/EventResult | activity awards, uniqueness, consent and withdrawal compensation |
| 14 | PointRule, PointEntry, Level, Assignment/Submission | activity five sources, future-only rule changes and corrections; race award deduplication |
| 15 | Achievement, protected printable certificate/media | activity certificate/consent/revision/private routes; real video validation; browser PDF export supported, arbitrary uploaded PDFs not supported |
| 16 | Festival event and ProgrammeItem | activity bounds, participants/invitations, revision consent and results; real video path passes |
| 17 | Revision-bound consent, all-subject moderation and showcase | activity guardian/adult transition, expiry/replacement/revocation, two download routes; race revocation remains private; human subject/identity review required |
| 18 | Discovery filters, exact PIN/service areas, Haversine coordinates | core PIN, distance, invalid coordinates, day/time overlap; no inferred distance from PIN alone; real coordinate quality remains operational |
| 19 | Public application and teacher decision services | core CSRF, safe session claim, no arbitrary learner attachment, request-info/replies |
| 20 | Existing UserNotification, outbox, announcements and adult Message contexts | core/activity delivery deduplication/reminders/recipient-only reads/legacy bypass denial; server scheduler pending; external channels deferred |
| 21 | Scoped tuition moderation plus existing Complaint/AdminActivity | activity teacher/content/student/category/complaint/report scope, pagination and generic-admin isolation |
| 22 | Central permissions, private storage, constraints/locks, audited financial services | local negative tests and MySQL races pass; production storage/proxy/runtime/backup/retention controls remain **blocked** |

## Unverified / release blockers

- Production MySQL version, SQL mode/collation and existing migration history may differ from local MySQL 8.4.11. Rehearse against a protected staging copy on the actual server version. Local two-worker contention tests are not load testing.
- Provision a private directory outside checkout/media/static, service-user-only access, and encrypted backups. Verify Nginx/CDN never exposes it by raw path and never publicly caches authorized responses. Application tests alone cannot establish proxy isolation.
- Provision maintained ffprobe and OS resource controls. Validate representative user recordings/browser playback; monitor upload memory/CPU and request timeouts. Original video metadata is retained; moderator/privacy review must account for it.
- Configure scheduled `tuition_schedule`, retry/error monitoring and trusted server time. Test repeated execution and failure alerting in staging.
- Verify TLS/proxy headers and review HSTS deliberately after HTTPS coverage is confirmed. Do not blindly enable HSTS from a local warning.
- Review production logs for student/guardian details, secret redaction, access restrictions and retention; confirm incident ownership. Audit logging is transactional, but production log operations were not tested.
- Establish guardian/adult identity review procedures, moderation of every identifiable subject, retention and orphan-file handling. No automatic face detection, recall of downloaded media or automatic deletion is claimed.
- Protected backup/restore rehearsal and measured rollback duration are outstanding. Physical/mobile-browser/conferencing/payment-provider checks and comprehensive legacy feature acceptance remain outstanding.

## Changed files in Phase 5

- Runtime fixes: tuition/activity_storage.py, tuition/activities.py, tuition/messaging.py, tuition/services.py, newsdesk/uploads.py; templates/tuition/page.html and activities.html.
- Tests/fixtures: tuition/test_readiness.py, tuition/test_mysql_concurrency.py, tuition/tests.py, tuition/test_activities.py; newsdesk/tests.py, jobs/tests.py, jobs/test_corrections.py.
- Local audit tools/settings: tuition/audit_mysql_settings.py, tuition/audit_production_settings.py, tuition/audit_ui.cjs; .gitignore excludes artifacts.
- Documentation: TUITION_MODULE_CHECKLIST.md, tuition/README.md, this report and DEPLOYMENT_CHECKLIST.md.

Earlier Phase 3/4 changes remain uncommitted. Preexisting .env.example, portal/network_forms.py and unrelated preview files were not part of this audit and must not be swept into a release.

## Reproduction

Run from project root with synthetic settings. Configure `TUITION_FFPROBE` and `TUITION_AUDIT_FFMPEG` to local executable paths to avoid explicitly skipped real-video tests.

```text
python manage.py test jobs community campus portal coupons vouchers quiz health newsdesk jobportal tuition --settings=jobportal.test_settings --noinput
python manage.py test tuition --settings=tuition.audit_mysql_settings --noinput --keepdb
python manage.py check --settings=jobportal.test_settings
python manage.py makemigrations --check --dry-run --settings=jobportal.test_settings
python manage.py check --deploy --settings=tuition.audit_production_settings
```

The MySQL settings are **local audit only**, hard-wired to the isolated loopback port and synthetic database. Never select either audit settings module for a deployment service. `--keepdb` avoids dropping the audit database; test fixtures still reset synthetic rows. Browser export requires `TUITION_AUDIT_UI=1`; run `node tuition/audit_ui.cjs` with a local Playwright module configured in `TUITION_PLAYWRIGHT_MODULE`. No package dependency was added.
