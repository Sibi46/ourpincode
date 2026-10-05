# Tuition module: Phase 2 design

Status: Phase 2 design retained below; Phase 3 core implementation now exists locally. See checklist and tuition/README.md for verified scope and release gates. Phase 4 was approved and is implemented locally; verification status and release gates are tracked in the checklist. No production schema changes made. Requirement IDs refer to TUITION_MODULE_CHECKLIST.md. All proposed names below belong to tuition unless explicitly qualified.

## 1. Boundaries and reuse

- Keep jobs.User, existing authentication, registration, CSRF and sessions. A user can teach, learn and act as guardian simultaneously; do not replace user_type or create tuition passwords.
- TeacherProfile is the tenant: either an individual teacher or academy, owned by an existing user. Support multiple profiles per owner. No implicit academy staff access; explicit future membership is required before delegation.
- Reuse jobs.UserNotification (inbox), jobs.AdminActivity (audit), jobs.Complaint (complaint lifecycle), jobs.Conversation/Message (adult messaging), jobs.PinCode/State/District (geography), base.html and existing UI patterns.
- Campus Student is institution/course-specific and requires a user account; FamilyMember includes relatives and pets. Neither is a tuition enrolment or a safe authorization boundary. Learner is necessary; it can link to FamilyMember with permission, without importing the entire family tree.
- Use one typed LearningEvent for events, competitions and festivals; one participant/result/media implementation. Do not duplicate existing wallet or online checkout: tuition fees are invoices owed to a teacher, not platform-wallet balances.
- Only narrowly scoped integration edits in later phases: settings/app registration, root URLs/public route allowlist, Explore/menu, main/scoped admin tuition entry and messaging/complaint authorization hooks. No unrelated refactor.

## 2. Model and relationship inventory

Conventions: BigAutoField internal keys; UUID identifiers for private routes and random public slugs; created_at/updated_at; explicit statuses; Decimal monetary amounts (INR initially); timezone-aware datetimes; tenant FKs indexed. Financial/enrolment/history parents use PROTECT and archival, not cascade deletion. SET_NULL for optional historical actors and family/geography references. CASCADE only expendable joins/drafts with explicit deletion service. No generic foreign keys for authorization-critical relationships.

### Identity and discovery (Phase 3)

| Model | Fields and relationships | Constraints/lifecycle |
|---|---|---|
| Subject | name, unique slug, active, optional parent Subject | Admin-managed tuition taxonomy, distinct from job industries/community categories |
| TeacherProfile | owner FK User PROTECT; individual/academy; name, unique slug, description, qualifications, experience years, Subjects M2M, min/max age, supported modes, address/contact, six-digit PIN text, optional FK PinCode, location lat/lon, coordinate source/accuracy, public fee toggle, status | draft -> pending -> approved/rejected; approved -> suspended; only approved published profiles discoverable; nonnegative experience; valid ages/coordinates |
| ServiceArea | teacher FK, PIN text, optional mapped PinCode; optional centre/radius on teacher | unique teacher/PIN; unknown valid PIN accepted; scope never inferred from a claimed state |
| Availability | teacher FK; weekday, local start/end time, timezone | start < end; overnight availability split into two rows |
| Learner | name, optional DOB or age with as-of date, contact/address/PIN, interests M2M Subject, private photo FK MediaAsset; optional verified User O2O (adult self-link or guardian-approved minor link); optional FamilyMember O2O SET_NULL; created_by | Missing/uncertain age treated as requiring guardian consent for publication; family link alone gives no permission |
| GuardianLink | learner FK, adult User FK, relationship, state pending/verified/revoked/disputed, verification method/reviewer/time | unique learner/user; explicit verified authority needed; revocation immediate |
| Invitation | teacher, optional learner/lesson, intended recipient, token hash, expiry, consumed_at, purpose (enrol/guardian) | Single use, expiring; never expose raw token in logs; acceptance verifies recipient control, not just matching phone text |
| Application | teacher, optional lesson, learner (nullable until claim), applicant User nullable, requested student name/age, guardian/contact mobile/email, PIN, preferred days/times/mode, message, state, response | pending -> needs_info/accepted/rejected/withdrawn; verified applicant may view/respond; anonymous submissions get opaque receipt only, no record lookup by phone |
| Lesson | teacher, subjects, name/description, age range, skill level, mode, location, fee/default billing period, fee visibility, duration, capacity, date range, weekday/time availability | teacher cannot reference another tenant's objects; end >= start; capacity/duration positive |
| Batch | lesson, name, capacity, status, location/mode overrides | same teacher inferred through lesson; active/cancelled/archived |
| Enrolment | learner, lesson, accepted application nullable O2O, start/end dates, status, level/progress summary | unique learner/lesson for lifetime; reactivation adds history rather than duplicate row; join date valid |
| BatchMembership | enrolment O2O, current batch nullable | stable current slot avoids MySQL partial-unique constraints; history of assignment/removal/transfer stored in AdminActivity |
| ProgressEntry | enrolment, teacher actor, date, assessment/level/comments | teacher sees only own lesson; guardian sees own learner; shared Learner contains no cross-teacher progress |

Teachers may create private provisional learners through invitations. They cannot discover/link arbitrary existing learners by phone or name; a verified adult authorizes attaching an existing learner. Teacher edits of personal details are restricted to provisional records; after claim, learner/guardian controls shared identity and teacher keeps enrolment-specific notes.

### Scheduling and finance (Phase 3)

| Model | Fields and relationships | Constraints/lifecycle |
|---|---|---|
| ScheduleRule | batch, weekday, local start time, duration, timezone, valid date range, version, active | Weekly recurrence; unique rule/version/day; validate DST ambiguous/nonexistent times; edited versions affect future sessions only |
| ClassSession | batch, rule nullable, original occurrence timestamp, start/end, physical location, mode, private meeting URL, status, revision, cancellation reason | unique rule/original occurrence; individual sessions have null rule; reschedule same row to retain attendance; end > start |
| SessionParticipant | session, enrolment, eligibility state | unique pair; explicit roster snapshot; transfers update future rosters, not past attendance; no other tenant/lesson |
| Attendance | SessionParticipant O2O, present/absent/late/excused, marked_by/time, note | no automatic absent before teacher marking; correction audited and points adjusted |
| FeeAgreement | enrolment, effective date range, agreed fee, billing cadence, currency | Preserve agreed student-specific fee independently of lesson changes; no overlapping effective ranges via locked validation |
| Invoice | agreement, billing period start/end, due date, amount, currency, state void/open, idempotency key | unique agreement/period; due amount nonnegative; immutable amount after payment, correction by audited adjustment |
| Payment | invoice, amount, paid_at, method, manual/gateway source, pending/confirmed/failed/reversed state, external provider/ref nullable, unique idempotency key, recorded_by, reverses Payment nullable O2O | Positive amount; append reversal not destructive edit; sum confirmed less reversals is amount paid; lock invoice for payment/reversal; no overpayment or duplicate processing |

Invoice display: Paid when balance=0; Overdue when balance>0 and due date passed; otherwise Partially Paid if paid>0, else Pending. Show amount paid separately even if Overdue. Gateway identifiers and lifecycle exist now; actual gateway integration deferred only as expressly allowed.

Session generation: idempotent management command creates next 90 days from rules; invoke after schedule changes and via planned daily server scheduler. Dashboard can trigger bounded, idempotent missing-horizon generation so lack of scheduler does not hide classes. Notifications use outbox deduplication. Rule edits preview affected future sessions, skip cancelled/overridden occurrences and retain originals. Overlapping classes for the same teacher/batch blocked; authorized reschedule updates roster notifications. Cancellation never deletes attendance/history.

### Activities, progress and media (Phase 4)

| Model | Fields and relationships | Constraints/lifecycle |
|---|---|---|
| LearningEvent | teacher, type annual_day/performance/workshop/examination/exhibition/sports_day/trip/competition/festival, title/description, schedule, venue, mode, registration window, capacity, visibility, status | one implementation across types; separate programme entries for multi-day festivals |
| EventParticipation | event, learner, relevant enrolment, invited/registered/accepted/withdrawn, consent flags | unique event/learner; only own learner registration; minors need guardian confirmation for trips/media |
| ProgrammeItem | event, starts/ends, title, venue, description, participants M2M EventParticipation | times within event range; public participant names subject to consent |
| EventResult | participation, award kind winner/runner_up/participation/special, placement, title, notes | unique participation/award key; editable with audit and point adjustment |
| Assignment / Submission | assignment belongs to lesson/batch; title, due_at, instructions; submission belongs to enrolment, completion/review, feedback | unique assignment/enrolment; completion accepted by authorized teacher; media private |
| PointRule | teacher, source type attendance/assignment/performance/competition/achievement, value, rule version, active | one current rule per teacher/source; edits affect future awards, not historical ledger |
| PointEntry | enrolment, rule/version snapshot, delta, reason, typed source FK, source revision, optional reverses entry | unique source/rule/revision action; exactly one source; immutable ledger, compensating reversal prevents duplicate awards |
| LevelDefinition | teacher, name, threshold, order | unique teacher/name and teacher/threshold; default Beginner-to-Champion set at profile creation, customizable; level derived from ledger, override audited |
| Achievement | teacher, enrolment nullable for teacher's own achievements, type/title/date/description, result/level nullable, private/public-requested/moderated status | no public student data until all consent checks pass |
| MediaAsset | uploader, teacher, UUID storage key, file kind, verified MIME, byte size, checksum, moderation state; nullable profile/learner/achievement/event/submission parent FKs | exactly one parent; private by default; no direct public storage path; ownership/tenant checked at upload and download |
| MediaSubject | asset, learner | unique asset/learner; group photos require each recognizable child's clearance; moderation rejects unverified subjects |
| PublicationConsent | learner, authority (verified guardian or verified adult learner), achievement/asset/programme/result scope, permitted public name/media, policy version, granted/revoked/expiry timestamps | explicit opt-in per publication; no broad teacher consent; current permission rechecked on every public render/file access |
| Announcement | teacher, lesson/batch/event audience selectors, title/body, publish time | audience filtered via current enrolment/participation, no broadcast to unrelated accounts |

## 3. Notification, messaging, complaints and audit reuse

- NotificationEvent: teacher, type, minimal payload/target reference, unique source/revision key, created_at. NotificationDelivery: event, recipient User, channel, pending/sent/failed state, attempts/next retry, O2O jobs.UserNotification nullable; unique event/recipient/channel. Event + business mutation commit atomically; delivery creates existing inbox record transactionally and retries through command. Core class/fee/application notifications start in Phase 3; remaining event types in Phase 4. No private details or meeting URLs in notification bodies. Future channel adapters use this outbox, not new inboxes.
- TuitionConversation is a context O2O to existing Conversation, tied to teacher and verified adult learner/guardian. Reuse Message text and read status. Disable file attachments for tuition conversations; private file sharing uses MediaAsset routes. Do not start teacher-to-minor private messaging. Both tuition and existing chat read/send/poll handlers must invoke a context-aware permission hook; otherwise revoked guardians could bypass tuition checks. Lock teacher/recipient when creating context because existing nullable job uniqueness is insufficient. Existing non-tuition conversations unchanged.
- TuitionComplaint context O2O to jobs.Complaint; teacher and optional enrolment/media/event target (one target). Existing complaint status/resolution reused; tuition complaints require context permission checks wherever listed/viewed. Reporting aggregates use existing tables and protected queries, not duplicate report models.
- Reuse AdminActivity for all tuition transitions with section='tuition', actor snapshot, action, target UUID and allowlisted changes; no meeting links, tokens, DOB or contact values in JSON. Mutation and audit must commit together. Financial/consent records retain their own history. Main admin sees all; scoped admin tuition audit filtered by verified geography. No separate duplicate audit model.

## 4. Authorization and privacy

Roles are relationships, not user_type assumptions. Every handler/service/file route checks active User and live role status, then tenant and object scope. UUIDs are not access control. Hidden form fields never supply trusted teacher/learner ownership. Mutations POST + CSRF; GET/HEAD read-only.

| Actor | Allowed | Never implicitly allowed |
|---|---|---|
| Visitor | approved public profiles/search/consented showcase; submit application; public event information | student lists, private files, meeting links, application status by phone |
| Teacher owner | own profiles, lessons, roster/enrolment-specific records, fees, schedules, activities | other teachers' records, global learner search, approving guardian identity or granting publication consent |
| Adult learner | own identity and enrolments across teachers, own payments/history, register for permitted events, consent | payment confirmation, attendance marking, other learners |
| Verified guardian | linked learner dashboard/data, applications, event consent and permitted showcase consent | unrelated relatives, sibling inference, another guardian's credentials |
| Minor account | explicitly linked own learning read access only; guarded teacher contact through adult | self-granting public consent, managing guardian links, unrestricted private messaging |
| Main super-admin | moderation, verification, categories, complaints/reports and audited necessary student access | unaudited impersonation or public release without consent |
| Scoped admin | explicitly enabled tuition section AND verified state match | unresolved PIN geography, another state or global student/family data |
| Marketing agent | none by default | access inherited from shop grants |

Guardian verification: an existing authenticated adult requests a link; verify contact control through existing verified-account/OTP facilities only after auditing their guarantees. Matching a number or FamilyMember row is not proof. Initial authority requires manual main-admin review of relationship attestation and minimal supporting evidence through private storage; avoid routine identity-document collection. Store reviewer/reason and notify existing verified guardians for additions/disputes. Pending/disputed links have no access. Invitation redemption alone cannot approve guardianship. Withdrawn/revoked links immediately lose dashboard, chat, media and notifications access. Adulthood transition does not silently transfer consent: verify learner account and obtain new self-consent; expired guardian publication consent must not remain public.

Public showcase requires teacher approved + content approved + valid publication consent for ALL learner subjects. Unknown age uses minor protections; under-18 threshold is conservative product policy, not a claim of legal compliance. Hide exact student address, phone, DOB and meeting links. Public profile uses consented display name (first name by default). Consent withdrawal removes listing and media access immediately; downloads already made cannot be recalled.

Private storage: TUITION_PRIVATE_ROOT outside MEDIA_ROOT/STATIC_ROOT and web server aliases. UUID filenames, extension + MIME/signature/decode checks, image pixel limits, size limits (images 10 MB, PDF 20 MB, video 100 MB initial), reject HTML/SVG/executables, sanitize raster EXIF, quarantine until validated. Video validation requires trusted server-side probe, failing closed if unavailable. Serve through authorized Django streaming/internal nginx location with no-store, nosniff, restrictive content disposition and no public URL leakage. Public approved media also goes through a consent-checking route, not a copied permanent public file. Temporary/orphan cleanup command checks references and retention before removal; no destructive task now.

Join Class: authenticated session participant/current verified guardian or teacher only; session not cancelled, teacher active, enrolment eligible; allow 15 minutes before through 30 minutes after end. Validate HTTPS meeting URL against configurable approved conferencing hosts; no javascript/data/open redirect or server fetching external URLs. Never embed links in public HTML/API/notifications; no-store and no-referrer response. Reschedule/revocation changes authorization immediately.

## 5. Search and geography

PIN input: exactly six digits, stored verbatim with optional existing PinCode FK. Missing/unassigned PIN cannot block registration; mapped state used only if verified active State/District/PinCode hierarchy exists. Do not create fake districts or trust client-provided state for admin scope.

No duplicate PIN table. Teacher lat/lon provided through an explicit location picker/manual coordinates with range validation and accuracy/source metadata. A visitor supplies a location or coordinates with consent; do not retain visitor location by default. Use bounding-box candidate query followed by Haversine straight-line distance in km, not road/travel distance. Include boundary rounding tolerance; handle poles/dateline; paginate after distance ordering. Unknown coordinates excluded only from radius searches, with clear UI explanation. PIN-only search is exact PIN/service-area matching, never a fabricated km distance. PIN centroid geocoding may be added from a verified source, marked approximate; not required to support true coordinate radius search.

All discovery filters combine: subject/lesson/name/type, age compatibility, supported mode (hybrid matches both), weekday, overlapping available time interval, PIN/service area and optional radius. Use EXISTS to avoid duplicated results, approved lesson/profile visibility and actual capacity. Date availability excludes cancelled sessions/full batches. Index status/PIN, teacher/subject, lesson/mode, rule weekday/time and geo bounding fields; add further indexes after query-plan tests.

## 6. Routes and requirement mapping

Prefix /tuition/, namespace tuition. T=own teacher tenant; L=authorized learner/verified guardian; A=main admin or explicit verified geographic tuition scope; P=public approved content. Private mutations all POST. Forms use GET to display, POST to validate/save. URL identifiers are UUID except public slug; no phone identifiers.

| ID | Models / reused components | Routes (relative to /tuition/) | Permission | Build phase |
|---|---|---|---|---|
| 1 | TeacherProfile, Subject, ServiceArea, Availability, MediaAsset, Achievement | register/, teacher/profile/, teachers/<slug>/ | existing login for register; T edit; P published | 3 + 4 media/achievements |
| 2 | Lesson, Availability/ScheduleRule | teacher/lessons/, teacher/lessons/<id>/edit/ | T | 3 |
| 3 | Batch, BatchMembership, Enrolment, ClassSession | teacher/batches/, batches/<id>/members/, enrolments/<id>/transfer/, classes/<id>/cancel-or-reschedule/ | T + locked capacity | 3 |
| 4 | Invitation, Application, Enrolment, GuardianLink | teacher/invitations/, invitations/<token>/accept/, applications/<id>/decision/ | T issue/decide; verified recipient accept | 3 |
| 5 | Learner, GuardianLink, Enrolment, ProgressEntry, ledgers | teacher/students/<id>/, learn/students/<id>/, guardian-links/ | T own enrolments only; L shared identity | 3 + 4 progression |
| 6 | Aggregates of all tenant models | teacher/, teacher/<section>/ | T | 3 foundation; 4 complete |
| 7 | Learner links and scoped enrolments | learn/, learn/students/<id>/<section>/ | L | 3 foundation; 4 complete |
| 8 | ScheduleRule, ClassSession, SessionParticipant | timetable/, teacher/schedules/, classes/<id>/ | T/L | 3 |
| 9 | ClassSession | classes/<id>/join/ | T/L participant + join window | 3 |
| 10 | Attendance, SessionParticipant | classes/<id>/attendance/, learn/attendance/ | T mark; L read | 3 |
| 11 | FeeAgreement, Invoice, Payment | teacher/fees/, invoices/<id>/, invoices/<id>/payments/, payments/<id>/reverse/ | T record/reverse; L read own | 3 |
| 12 | LearningEvent, EventParticipation, ProgrammeItem, EventResult, MediaAsset | events/<id>/, events/<id>/register/, teacher/events/ | T manage; L register; P public sanitized | 4 |
| 13 | competition-type event, participation/result | teacher/competitions/, events/<id>/results/ | T write; L/P filtered read | 4 |
| 14 | PointRule, PointEntry, LevelDefinition, Assignment, Submission | teacher/points/, teacher/levels/, assignments/<id>/submit/, submissions/<id>/review/ | T rules/review; L own submit/read | 4 |
| 15 | Achievement, MediaAsset | teacher/achievements/, achievements/<id>/ | T issue; L own; P consent-only | 4 |
| 16 | festival-type event, programme/participation/result/media | teacher/festivals/, events/<id>/programme/, events/<id>/invite/ | T manage; L own invitation; P sanitized | 4 |
| 17 | PublicationConsent, MediaSubject, Achievement | achievements/<id>/consent/, media/<id>/consent/, teachers/<slug>/showcase/ | verified adult authority grant/revoke; T cannot grant; P approved | 4 |
| 18 | Profile, Subject, Lesson, ServiceArea, schedule/capacity | root search GET | P, approved records only | 3 |
| 19 | Application | teachers/<slug>/apply/, applications/<id>/, applications/<id>/respond/ | P submit; verified applicant read/respond; T review | 3 |
| 20 | NotificationEvent/Delivery, UserNotification, Announcement, TuitionConversation + Message | notifications/, notifications/<id>/read/, teacher/announcements/, messages/<id>/ | recipient only; T scoped audience; verified adult chat | 3 core triggers; 4 complete |
| 21 | existing Complaint/AdminActivity, TuitionComplaint, Subject and moderation statuses | admin/, admin/teachers/, admin/students/, admin/subjects/, admin/complaints/, admin/content/, admin/reports/, admin/activity/ | A; students resolved via permitted enrolments, no global family access | 4 |
| 22 | all constraints + central permissions, MediaAsset, audit | files/<id>/, public-media/<id>/ and all above | fresh object authorization on every route | 3/4; full regression 5 |

Exact public allowlist: search, published teacher profiles/showcase, sanitized published event detail, apply form, token acceptance landing and consent-checked public media. Authentication required inside invitation acceptance and all private views. Scoped admin middleware allows only named tuition admin routes after checking section/geography; do not broadly allow tuition namespace. Deny tenant/profile suspension bypasses even to valid old sessions.

## 7. Integrity services and verification acceptance

- Service transactions lock tenant then lesson/batches (sorted PK), learner/enrolment, invoice as appropriate. All entrypoints including admin use same services. Unique constraints are final defence; no SQLite-only conditional unique constraints. Cross-table same-tenant, roster membership, capacity and effective-date overlaps require locked validation; tests on MySQL cover concurrent races.
- Application acceptance locks application/learner/lesson, checks guardian authority and capacity, creates or reactivates exactly one enrolment and links application; repeated POST idempotent. Transfer is atomic, target capacity checked before removing prior membership; cancelled/historical attendance preserved.
- Points source and rule version stored; attendance edits/results corrections reverse prior award once; no recursive achievement-to-points-to-level award loop.
- Payment corrections append reversal; pending gateway payment contributes zero; duplicated references/webhooks cannot credit twice. Balance and dashboard pending fee totals derived from same ledger logic.
- Test each ID with create/edit/view flow and unauthorized path. Include other teacher, unrelated parent, revoked guardian, inactive user, suspended teacher, wrong-state admin, guessed UUID, private file/public-media consent withdrawal, application replay, recurrence overrides, timezone cases, fee and points races, duplicate enrolment, search filter combinations and mobile/keyboard UI.
- No tests executed or functionality verified in this design phase. Future Phase 5 runs focused tuition tests, existing auth/family/admin/chat/business regressions, Django checks, migration drift checks and disposable MySQL migration/concurrency tests.

## 8. Safe migration and rollout design

Proposed new-app migrations only; exact dependency leaf names determined once at implementation from migration graph, not guessed now.

1. 0001_identity: Subject, TeacherProfile, ServiceArea, Availability, Learner, GuardianLink, Invitation, Application; core MediaAsset with profile/learner parent fields and learner photo link added after MediaAsset creation. swappable dependency AUTH_USER_MODEL; jobs geography and community FamilyMember dependencies. No user conversion/backfill.
2. 0002_learning: Lesson, Batch, Enrolment, BatchMembership, ProgressEntry; add Application lesson/enrolment links in dependency order. Include constraints/indexes only on new tables.
3. 0003_schedule_finance: ScheduleRule, ClassSession, SessionParticipant, Attendance, FeeAgreement, Invoice, Payment; NotificationEvent/Delivery with dependencies on existing UserNotification, ready for core notifications.
4. 0004_activities: events, participants/programme/results, assignments/submissions, point rules/ledger/levels, achievements.
5. 0005_media_consent: add nullable activity/submission parent FKs to core MediaAsset; replace exactly-one-parent constraint to include these; create MediaSubject/PublicationConsent. Reverse returns to core constraint only after explicit export/removal of later activity media; operational rollback keeps data.
6. 0006_integrations: TuitionConversation and TuitionComplaint FKs to existing tables; extend outbox event choices for remaining activities. No existing auth/message/inbox table mutation. Their authorization integration is code, not data rewrite.

Phase 3 includes private uploads and core in-app notifications through 0001/0003. Activity media and consent-based publication remain disabled until 0004/0005 and their authorization code are present.

No production migrations now. Future commands: inspect showmigrations/plan and sqlmigrate; generate/check in migrations; migrate empty and representative disposable MySQL copy; reverse/apply there; run makemigrations --check --dry-run and tests. MySQL DDL is not generally transactional: each migration small, review failed-apply recovery and backups before rollout. No table drops/renames or destructive data conversions in existing apps.

Avoid seed RunPython for editable business records. Default point rules/levels created idempotently when teacher profile created; subjects managed through admin. If a data migration becomes necessary, it must use historical apps, explicit reversible function and only rows it owns.

New CreateModel migrations are schema-reversible, but reversing them after live use destroys tuition data. Operational rollback is disable tuition routes/navigation and roll back code while RETAINING tables/data; schema rollback only with explicit approval and verified backup/export. PROTECT references mean later user deletion workflows must archive/anonymize tuition records deliberately; do not unexpectedly cascade invoices or children.

Deploy only after explicit approval: database/media backups and restore check, provision nonpublic storage, approved meeting-host configuration, scheduler, video probe availability, then additive migrations, static collection, service reload and smoke checks. Production connectivity must be restored first; prior outage is not presumed fixed. No new package/provider requirement silently introduced; geocoding provider, paid messaging transports and gateway are not required for core release.

## 9. Decisions awaiting implementation verification

Guardian attestation review and minor privacy rules require product validation; no legal compliance assertion. Server private-storage isolation and video probing must be validated before upload activation. Distance is truthful straight-line distance only when coordinates exist. Existing chat and complaint endpoints require bounded context guards to prevent legacy-route bypass. SQLite tests cannot prove MySQL locking behaviour. Each risk is a verification gate, not permission to omit the feature.


## Phase 3 implementation notes
Core files now exist under tuition/, templates/tuition/ and static/tuition/. Three additive migrations group identity/private images/outbox, learning, and scheduling/finance. Model identifiers and route names are defined in tuition/models.py and tuition/urls.py. Daily recurrence uses a command plus explicit owner POST refresh; dashboard GET never mutates. Image-only private upload is enabled; extended media/consent remain Phase 4. Anonymous enquiry claiming uses the original browser session after login, never mobile-number identity matching. No tuition messaging entry is enabled until Phase 4 includes legacy route authorization hooks. MySQL and production storage validation are release gates; SQLite test success does not prove MySQL locking behaviour.


## Phase 4 implementation notes
The approved typed-event, existing-message/complaint context, revision-bound consent and append-only points architecture is implemented. Exact endpoints are in tuition/urls.py. Certificates use protected printable HTML (browser PDF export), not uploaded PDFs. Video probing fails closed without ffprobe. Moderation and consent submissions reject stale content versions. The three planned Phase 4 migration groups are retained (0004 activities, 0005 media/consent, 0006 integrations). See tuition/README.md and the checklist for verification and operational gates; no production rollout occurred.
