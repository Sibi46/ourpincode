# Tuition module - Phases 3–5

Local implementation only. No production migration, deployment, reverse migration or user-data deletion has been performed. Phase 5 local audit: 453 SQLite tests passed (7 MySQL-only skips); 119 MySQL tests passed (1 optional export skip), plus 6 targeted readiness checks. See PHASE5_AUDIT.md and DEPLOYMENT_CHECKLIST.md for full evidence and unresolved production gates. All 22 requirements remain in TUITION_MODULE_CHECKLIST.md.

## Entry points

- `/tuition/`: public approved teacher/academy discovery; linked from homepage Explore.
- `/tuition/register/`: existing signed-in user creates a pending teaching profile.
- `/tuition/learn/`: teaching profiles, authorized learners, enquiries and existing in-app inbox.
- `/tuition/review/`: main super-admin verification of teachers/guardians and initial subject creation. Main-admin guardian verification records evidence and supports pagination. Full moderation is at `/tuition/admin/`.
- `/tuition/timetable/`: own teaching and authorized learner classes.

Create subjects in Verification, register a teacher, and approve the profile. The owner creates lessons and batches, then recurring or individual classes. Adult learners create their own profile; parents submit a child/guardian request. Main admin verifies guardian authority before access. Applying with an authorized learner allows the teacher to accept and enrol. The teacher assigns a batch, marks attendance after the class starts, creates fee agreements/invoices, and records manual payments or reversals. Learners/verified guardians see their own history across teachers.

Anonymous applicants retain an opaque receipt in their browser session. Sign in on the same browser, claim the enquiry in My learning, and attach an authorized learner. There is no lookup by phone and no automatic account/guardian linking. Invitation links are manually shared by teachers, single-use and expire in seven days; accepting only opens the application flow, never grants guardian authority or enrolment.

## Files and configuration

- `models.py`: domain records, database constraints, meeting-link validator and derived balances.
- `permissions.py`: tenant/learner/guardian access boundaries.
- `services.py`: locked enrolment, transfer, schedule, attendance, fee/payment, audit and notification operations.
- `forms.py`, `views.py`, `urls.py`: explicit scoped forms and endpoints; existing authentication/base UI reused.
- `storage.py`: validated/re-encoded image upload with private storage and authorized streaming.
- `migrations/0001_initial.py`, `0002_learning.py`, `0003_schedule_finance.py`: additive new-app schema; no existing table rewriting.
- `tests.py`: core workflows, permission negatives, constraints and idempotency.

`TUITION_PRIVATE_ROOT` may be set in the environment; default is the sibling application-data directory's `tuition-private` subdirectory. It must remain outside checkout, MEDIA_ROOT, STATIC_ROOT and nginx/public aliases. Never expose it through a web-server alias. Images are JPG/PNG/WebP only, <=10 MB and <=20 megapixels, re-encoded without original metadata. Student images always require current learner/guardian or active enrolment teacher access. Teacher logo upload puts the entire profile back into pending review. Logo publication requires separate content review confirming that no student subjects are missing. Student publication uses the Phase 4 consent workflow below. Arbitrary PDF uploads are rejected; certificates are authorized printable HTML with browser Save as PDF.

`TUITION_MEETING_HOSTS` currently allows HTTPS Google Meet, Zoom and Microsoft Teams hosts. Join URLs require an eligible session participant/current guardian or owner, active approved teacher, scheduled class, and the 15-minute-before to 30-minute-after window. Actual URLs are absent from learner/public page HTML and in-app notifications.

## Recurrence and notifications

Creating a schedule materializes the next 90 days transactionally. Stop a schedule to cancel future occurrences, then add a new schedule; individual reschedules preserve the session identity and attendance history. Owners can POST Refresh upcoming classes. GET requests never generate data. Future operations must schedule this idempotent command daily:

```text
python manage.py tuition_schedule
```

It generates the next horizon and retries pending in-app delivery through existing UserNotification. No scheduler has been installed. NotificationEvent/Delivery allow future channels but only in-app is implemented. It also delivers approved scheduled announcements and event/fee reminders. Tuition messaging reuses existing Conversation/Message with an enrolment/adult context and protects legacy chat/read/send/poll paths. Other conversations continue through existing routes.

## Verification and release gates

```text
.venv\Scripts\python.exe manage.py test tuition jobs.test_assigned_admin jobs.test_marketing jobs.test_business_registration jobportal.test_ga4 --settings=jobportal.test_settings --noinput
.venv\Scripts\python.exe manage.py check --settings=jobportal.test_settings
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=jobportal.test_settings
```

These use the isolated in-memory SQLite test database; private-file tests use temporary directories. Production schema/data are untouched. Phase 5 applied migrations and passed seven contention tests using a fresh portable MySQL 8.4.11 instance. Production-version/staging rehearsal remains a release gate. Do not mistake SQLite transaction tests for MySQL concurrency verification.

Private storage/nginx isolation, scheduler provisioning, physical-device/browser interaction and live provider join links need pre-release validation. Offline Chromium layout checks passed at 320/390/1280px; these do not replace end-to-end device checks. A failed database transaction after writing an image can leave an unreferenced private file; it remains inaccessible by HTTP. A reviewed orphan-cleanup/retention workflow is still required; no cleanup/deletion command is introduced here.

Schema rollback after use would lose tuition data. Disable module navigation/routes while retaining tables AND tuition-aware legacy chat/complaint/admin guards; reverting those guards could expose tuition records. See DEPLOYMENT_CHECKLIST.md. No migration reversals were run. Deploy only with separate explicit authorization and backups.

## Phase 4 workflows

- Teacher dashboard -> Activities: create any of nine event types, including competitions and annual festivals. Set a registration window/capacity; an admin approves public content. Invite enrolled students; invitation alone does not authorize participation. A verified guardian or verified adult learner registers. Teachers accept/withdraw registrations and record winner, runner-up, participation or special awards. Programme entries must fit within event dates and use that event's registered participants.
- Lessons -> Assignments: scope to lesson or batch. Authorized students/guardians submit text and private attachments; the teacher reviews completion/returns work. Resubmission and corrections reverse points without deleting history.
- Activities -> Points and levels: configurable source values and thresholds; default Beginner through Champion. Attendance, assignments, performance/competition results and achievements generate deduplicated entries. Rules affect future awards; corrections use original values and compensating entries. Source student/result identity cannot be reassigned after issue.
- Activities -> Achievements: certificates, completion, attendance, performances and competition records. Print/save certificate as PDF is private to the owner and authorized learner/guardian. Optional photo/video attachments are private until all publication gates pass.
- Student/parent Activities: events, invitations, assignments, achievements, points/levels, announcements and consent history across authorized learners/teachers. Review the exact content, choose an optional public display name, explicitly allow media, and set expiry (maximum one year). An edit invalidates prior version consent; replacement consent supersedes old grants. Revocation immediately stops future public renders/downloads, but cannot recall previously downloaded copies.
- Public teacher profile -> Showcase: only approved, explicitly requested content with current consent from every identifiable learner. Guardians must have a reviewed, verified link; adult self-consent requires verified identity/DOB. Teachers cannot grant consent for students. Unknown ages are treated as minors. Guardian revocation, expiry, teacher suspension and adult transition close publication. Group media additionally needs moderator confirmation of all subjects.
- Learning messages: existing text messages, notifications, pagination and POST mark-read. Only the teacher and a currently verified adult participant can access the context. No teacher-to-minor private thread and no generic chat attachments. Legacy chat and Django-admin lists exclude tuition contexts.
- `/tuition/admin/`: main admin manages all tuition teachers, enrolments, adult identity checks, categories, content, complaints, reports and audited activity. State admins require the explicitly enabled `tuition` section and an active mapped State/District/PIN; unknown PINs are main-admin-only. Scoped admins cannot verify global adult identity or guardian authority. Reports and pagination use the same scope as mutations. Existing Complaint lifecycle and AdminActivity are reused.

## Video validation and release gates

MP4/WebM uploads are implemented (100 MB, up to two hours, restricted streams/codecs/dimensions). Phase 5 installed portable FFmpeg/ffprobe 9.0.2 locally and passed real MP4/H.264 and WebM/VP8 fixtures plus rejection tests for corrupt, audio-only and disguised Matroska files. WebM requires a parsed EBML WebM DocType. Configure TUITION_FFPROBE or a maintained ffprobe on PATH in the approved release environment. Validation permits only local-file protocol, has a 20-second timeout and fails closed when unavailable. No Python dependency added. Real user recordings/device playback, OS resource containment and production binary maintenance remain operational checks. Original video metadata is retained; human privacy review remains necessary.

All media stays in `TUITION_PRIVATE_ROOT`, outside public storage and checkout. Approved public media still passes live consent checks on every file request. Moderators must review content for identifying text and all recognizable subjects; automatic face identification/redaction is not implemented or claimed. Private attachments and learner photos never become public through a public flag.

Pending release validation: production-version staging rehearsal; private storage/nginx isolation; production ffprobe/resource configuration; scheduler provisioning; physical-device/conferencing checks; log review; backup restoration; reviewed retention/orphan cleanup. No production deployment is authorized by local test success. Gateway and email/WhatsApp/SMS/push adapters remain explicitly deferred extension points.

## Phase 4 files and migrations

New: `activities.py`, `activity_forms.py`, `activity_views.py`, `activity_storage.py`, `messaging.py`, `moderation.py`, `test_activities.py`; `templates/tuition/activities.html` and `certificate.html`.
Updated: tuition models, permissions, services, core views/storage, URLs and `tuition_schedule`; shared tuition page. Narrow integration: settings/public route allowlist, assigned-admin tuition capability/menu, jobs message/complaint query guards and Django-admin exclusions, main super-admin entry, assigned-admin regression fixture. No unrelated features refactored.

Phase 4 migrations add only tuition schema:

1. `0004_achievement_announcement_assignment_and_more`: events/programmes/results, assignments, points/levels, achievements and announcements.
2. `0005_media_consent`: nullable media parents, extended exactly-one-parent constraint, declared media subjects, versioned consent and adult identity flag defaulting false. Existing records remain private/pending; no automatic consent backfill.
3. `0006_integrations`: contexts linked to existing Conversation and Complaint; no replacement message/complaint tables and no existing jobs table rewrite.

Migrations were applied forward only in isolated SQLite tests. No reverse migration was run. Rollback after real use means disabling routes/navigation while retaining tables; schema reversal can lose tuition data and requires separate approval, backup/export and MySQL rehearsal. Reverting only Phase 4 schema is unsafe once activity media exist under the extended parent constraint.

Final verification on 2026-10-04: **145/145 tests passed**, Django checks reported 0 issues, migration drift reported no changes, and integration diff whitespace checks passed. This is isolated SQLite evidence, not production/MySQL/video-codec validation. Checklist items 12, 15, 16 and 22 remain explicitly verification-gated.


### Group leave / absence dates

Group creation now accepts multiple start times for each selected weekday, rather than calendar-date or shared-time inputs. New groups inherit the teacher's age range and schedule weekly from the next occurrence for 365 days (disclosed on the form); existing groups are unchanged. Each new slot reserves 60 minutes for calendar availability and clash checks. In-person groups require an address, online groups require an approved meeting URL, and hybrid groups require both. Standard 90-day generation and the existing scheduler still apply. No schema migration is required.

Teachers now start with **Create group** from My Learning or their teacher dashboard. One transaction creates the internal lesson, batch, typed/selected subjects and recurring rules (India timezone), and generates the existing scheduling horizon. Existing groups/data remain intact; no schema migration or fixed group-count limit is introduced. Teacher approval and ownership are required. Scheduling conflicts roll back the whole group.

**Add students** accepts an authorized learner's application and assigns the enrolment atomically, or assigns an existing active enrolment for that group's underlying lesson. Existing age, guardian, capacity and notification checks remain in place. New students use the group application link or teacher invitation; there is no unrestricted lookup of private learners. Group fees are advertised amounts; per-student agreements/invoices remain separate. Existing scheduler configuration is still required to extend recurring classes beyond the generated horizon.

Teachers open a batch and select **Record leave / absence dates**, then choose an active enrolled student, inclusive dates, status and reason. Approved owners only can submit. `excused` means leave (including future scheduled classes); `absent` requires the class to have started. Existing attendance cannot be overwritten through the date-range form; corrections use the individual class attendance form. Membership and enrolment end dates are unchanged.

This reuses Attendance and SessionParticipant, including audit and points handling; no migration is needed. Only already-generated scheduled classes are covered, not future timetable additions. Create the timetable before recording leave. An invalid range is rolled back as a whole. This is teacher-recorded leave, not a parent leave-request approval workflow.

### Phase 4 changed-file inventory

- Added: `tuition/activities.py`, `activity_forms.py`, `activity_views.py`, `activity_storage.py`, `messaging.py`, `moderation.py`, `test_activities.py`; migrations `0004_achievement_announcement_assignment_and_more.py`, `0005_media_consent.py`, `0006_integrations.py`.
- Updated tuition core: `models.py`, `permissions.py`, `services.py`, `views.py`, `storage.py`, `urls.py`, `management/commands/tuition_schedule.py`.
- Templates: new `templates/tuition/activities.html`, `templates/tuition/certificate.html`; updated `templates/tuition/page.html`, `templates/assigned_admin/section.html`, `templates/super_admin_dashboard.html`.
- Integration: `jobportal/settings.py`, `jobportal/middleware.py`, `jobs/admin.py`, `jobs/assigned_admin.py`, `jobs/views.py`, `jobs/test_assigned_admin.py`.
- Documentation: `TUITION_MODULE_DESIGN.md`, `TUITION_MODULE_CHECKLIST.md`, `tuition/README.md`, `tuition/PHASE4_HANDOFF.md`.
- Earlier Phase 3 app registration/root URL/home Explore and core migrations remain in the uncommitted workspace. Pre-existing unrelated `.env.example`, `portal/network_forms.py` and preview artifacts were left untouched. No Git push or deployment performed.

Create Group allows multiple start-time-only slots per weekday (+/remove controls). Each reserves 60 minutes for calendar/clash checks; repeated or conflicting times are rejected. Advertised fee is optional and blank saves zero; fee agreements remain separate. No migration required.

Timetable defaults to group cards with weekday/start-time slots from active, unexpired rules. Access is limited to the group's teacher or an authorized learner's active enrolment/membership. The existing monthly calendar remains available via View calendar (?month=YYYY-MM).


### Profile and academy management
Teacher/academy registration accepts moderated profile and banner images through existing private media storage. Public profiles include active weekly class-day counts, approved teacher videos, and opted-in academy staff (phone numbers remain owner-only). Staff are managed by the academy owner, not separate login accounts. Changing a staff profile to private also removes publication permission on its photo.

Subject inputs support +/remove; selected weekdays show five optional start-time inputs (at least one is required server-side; up to 24). Student guardian failures are field-specific, with adult self-registration hiding guardian-only inputs; verified access is still required.

Delete requires an owner-authorized confirmation POST. Groups with related sessions, membership, rules or history cannot be deleted. Teacher profiles with business/history records cannot be deleted; only unused configuration (service areas, availability, points/levels) is cleared with an otherwise unused profile. Staff deletion keeps uploaded media records intact. Existing group edit and private media/video validation services are reused.

Migration 0007 adds nullable image references and the academy staff table/M2M only. It must be applied before running this version; no data migration, new dependency, storage change or production action was performed. Take the normal verified backup before deployment. Video uploads continue to require ffprobe and existing moderation/consent checks.

Academy registration now requires opening weekdays and opening/closing times, saved as existing Availability rows. Existing hours are edited through Teaching hours, so profile edits do not overwrite them. Branches are independently reviewed academy profiles owned by the same account, linked through nullable parent_academy (migration 0008). Public branch lists only show approved profiles.

Student deletion requires a confirmation POST by the student account or the original creator with a pending/verified guardian request. Other guardians or any linked education/media records prevent deletion. Only an unused student's authorization metadata is removed alongside the profile. Apply to learn keeps its authorized-only selector and explains empty/pending states, with Add student and request-status links.


### Permanent teacher-profile deletion
The teacher Delete profile page now previews scoped counts and requires exact profile name, the owner's current account password, and explicit acknowledgement. The dedicated transaction deletes that profile's Tuition records (including enrolments, financial records, activity history and media); student accounts, guardian links, other profiles and branch profiles remain. Branches become standalone profiles. Shared messaging/complaint records, inbox notifications and audit history remain. Payment-record deletion does not refund external payments. Group/student/staff deletion retains its existing unused-record protections.

Migration 0009 adds a durable private-file cleanup queue. Files are removed only after the database transaction commits. Failed cleanup remains queued, logs a task ID, and is retried by tuition_schedule; verify that scheduler is running before relying on automatic retries. Cross-profile media references and unexpected protected relationships abort the entire transaction. A deletion audit record remains. No production data was deleted during implementation.

Media uploads label Subjects as students visible in the media (not teaching subjects), explain an empty enrolment list, and convert storage/OS configuration failures into a form error while logging the traceback. Production upload failures still require server-log evidence to identify and correct the underlying configuration.

Teacher gallery uploads now default to public opt-in and auto-approve media after the owner confirms all recognizable students are identified (including a no-students declaration). Approved teacher status, active account, private-file delivery, video validation and guardian/student publication consent checks remain in effect. Existing pending teacher assets can be published by their owner through Manage uploads; admin-rejected assets cannot be republished this way. Previously identified students cannot be removed to bypass consent. Changing the student list increments the media revision and requires renewed consent. Event/achievement/submission moderation is unchanged.

The supplied production traceback identified upload PermissionError creating /var/www/ourpincode-data. The operator reported uploads succeeded after creating the service-owned private directory; this does not verify unrelated production release gates.

Registration now uses typed subjects only and preserves the existing public-fee preference without displaying that control. Owners can publish brand/profile/banner images after confirming no recognizable students; existing student-linked or rejected media cannot use this shortcut. Photo-only changes retain teacher approval, while teaching-detail changes still return to review. Group pages show first weekday/time/date without the recurrence end date or repeated session/enrolment lists; recurrence data is unchanged. Apply to learn accepts typed student-name/contact enquiries without a learner selector or Add student link; identity linking remains a later authorized step.
