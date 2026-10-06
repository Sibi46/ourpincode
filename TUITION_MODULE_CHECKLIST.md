# Tuition & Learning Module - implementation checklist

## Current design status
Phase 5 local audit complete. All 22 original requirements remain preserved. **21 locally verified; requirement 22 remains production-verification gated.** Checked items do not authorize release. No push, deployment, production data changes or reverse migrations.

Release-readiness continuation: **PASS** synthetic MySQL/media recovery (262 tables, 1,474 rows, one private image; checksums, balance and restored access verified) and one new scheduler command/reminder/retry test. **BLOCKED** production storage/proxy controls, deployed scheduler/alerts, operational encrypted backup/restore, effective HTTPS/HSTS/configuration and staging/physical-device acceptance. No newly failing executed assertions; W004 remains unresolved pending actual configuration evidence. Requirement 22's original nine acceptance criteria now have individual evidence in tuition/PHASE5_AUDIT.md. Operator commands: tuition/SERVER_VERIFICATION.md; recovery procedure: tuition/RECOVERY_RUNBOOK.md; prepared smoke matrix: tuition/STAGING_SMOKE_TESTS.md. No unchanged broad suite rerun and no production access.

Final evidence: **460 SQLite tests run: 453 passed, 7 MySQL-only skips**. On isolated MySQL 8.4.11, **120 run: 119 passed, 1 optional UI-export skip**, including all seven concurrent tests; subsequent targeted readiness run: 6 passed, 1 optional export skip. Real MP4/WebM validation passed with ffprobe 9.0.2. Django checks passed; no migration drift. Synthetic production-default check reports HSTS warning W004. Full evidence, all-22 mapping, changed files and blockers: [Phase 5 audit](tuition/PHASE5_AUDIT.md). Release steps: [deployment checklist](tuition/DEPLOYMENT_CHECKLIST.md).

## Findings and reuse
- Django project: jobportal; apps include jobs, community, campus, portal, coupons, vouchers, quiz, health and newsdesk. Phase 1 found no tuition app; Phase 3 adds the separate tuition app.
- Authentication: jobs.User, PhoneOrEmailBackend, FamilyAccountBackend and existing register/login routes. Add tuition roles through related profiles and memberships, not replacement authentication or exclusive user types.
- Existing family records: community.FamilySetup/FamilyMember. Family membership alone must not authorize access to student records; use verified learner/guardian links and explicit consent.
- Database: configured MySQL; isolated test settings use SQLite. Validate constraints and transactional concurrency against MySQL as well as local tests.
- Reuse jobs.UserNotification for in-app delivery and existing admin activity conventions; add tuition event/outbox and detailed audit records as needed.
- Reuse templates/base.html, site branding, existing navigation and UI components. Add tuition entry in Explore and main super-admin tools; preserve current employer dashboard.
- LoginRequiredMiddleware, AssignedAdminMiddleware and MarketingMiddleware require narrowly scoped integration. Public discovery/profile access must not make private tuition views public. Admin permission switches and geographic restrictions remain enforced.
- Existing PIN model has State/District hierarchy but no geographic coordinates. Accept valid six-digit PINs without requiring pre-registration. Distance requires explicit coordinates or reliable geocoding, not subtraction of PIN codes. Plan coordinate input/map location and documented geographic distance; retain service-area PIN filtering when coordinates are absent.
- Public /media/ is unsuitable for private student photos/certificates. Plan private storage and authorized file-serving routes, separate from consent-approved public media.
- Existing campus/school/portal events are separate domains; reuse patterns without mixing their ownership and permissions with tuition enrolments.

## Phases and proposed implementation boundaries
1. Inspection and persistent checklist: complete.
2. Design: complete; model/relationship inventory, tenant and guardian permissions, routes, state transitions, constraints and additive migration plan documented. Design approved; core Phase 3 and Phase 4 implementation now exists.
3. Implement profiles/discovery, lessons/batches, invitations/applications, enrolment, both dashboards, sessions/timetable, join access, attendance and fee/payment ledger.
4. Implement events/competitions/festivals, assignments/progress, points/levels, achievements/consent/showcase, gallery, announcements/messages, notification delivery and admin moderation/reports.
5. Verify positive and negative permissions, cross-teacher isolation, guardian links, consent withdrawal, private media, race-safe capacity/enrolment/payment/points, recurrence exceptions, public filters, both dashboards and existing authentication/admin regressions. Run Django checks and migration checks; never mark completion merely because code exists.

Proposed app layout: tuition/models/, forms/, services/, permissions.py, validators.py, views/, urls.py, admin.py, migrations/, tests/; templates/tuition/ and static/tuition/. Prefer existing dependencies.
Proposed routes: /tuition/ discovery; /tuition/teachers/<slug>/ public profile; /tuition/apply/; /tuition/teacher/; /tuition/learn/; /tuition/classes/<id>/join/; protected media; super-admin tuition management. Exact route/permission mapping belongs to Phase 2.

## Requirement checklist - all mandatory

- [x] 1. Teacher/Academy Registration: Profiles, photos/logos, descriptions, qualifications, experience, subjects, age groups, online/offline/hybrid modes, address, PIN code, service area, contact details, timings, optional public fees, media, achievements, events and unique public profile URLs.
  - Planned implementation: TeacherProfile, subjects/service areas, public slug, media and profile editing.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: core teacher/academy profiles, free six-digit PINs, approved photos/logos, gallery/showcase/event navigation and achievements. Media requires separate moderation. Video runtime validation is documented below; profiles and image galleries work without it.

- [x] 2. Lesson Management: Multiple lessons per teacher, descriptions, age groups, skill levels, mode, location, fees, duration, capacity, weekdays, timings, start and end dates.
  - Planned implementation: Lesson and availability records.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested in Phase 3: multiple lessons, age/level/mode/location/fee/duration/capacity/date fields, recurring weekday/time rules, date and overlap checks. No unrelated lesson refactor.

- [x] 3. Group/Batch Management: Create/edit batches, assign/remove/transfer students, change timings, manage capacity, cancel and reschedule classes.
  - Planned implementation: Batch, membership history, transfer service and session exceptions.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: batch CRUD, assign/remove/transfer with capacity checks, recurrence and individual cancellation/reschedule. Admin reactivation preserves transferred rosters. Phase 5 isolated MySQL last-slot contention passes; actual production-version rehearsal remains under item 22.

- [x] 4. Student Registration: Teacher invitations and public Apply to Learn applications; accept, reject or request more information; convert accepted applications to enrolments.
  - Planned implementation: Invitation, Application, decision history and idempotent enrolment conversion.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: expiring single-use invitations, applications, same-browser enquiry claim after login, accept/reject/request-info/reply and idempotent enrolment. No automatic guardian linking or phone-based identity lookup.

- [x] 5. Student Information: Name, optional photo, age/DOB, guardian, address, PIN code, contact details, interests, lessons, level, batch, joining date, fees, payments, attendance, progress, points and achievements. Enforce strict permissions.
  - Planned implementation: Learner, verified guardian access and teacher-scoped enrolment records.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: private identity/contact/photo and verified guardian access plus enrolment-scoped attendance, fees, progress, computed points/levels and achievements. Main admin alone can verify adult identity; changes invalidate identity verification.

- [x] 6. Teacher Dashboard: Student totals, active batches, today's classes, pending fees, upcoming events, students, lessons, groups, timetable, attendance, fees, events, competitions, points/levels, achievements, gallery, enquiries, messages/notifications and public profile.
  - Planned implementation: Teacher dashboard and complete section navigation.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: core dashboard totals/navigation, upcoming events and Activities workspace with events/competitions/festivals, points/levels, achievements, media, announcements and existing-message contexts. Teacher data remains tenant-scoped.

- [x] 7. Student/Parent Dashboard: One account supporting multiple teachers and lessons; schedules, meeting links, attendance, fees, payment history, progress, points, levels, events, competitions, achievements and announcements.
  - Planned implementation: Learner/guardian dashboard across multiple teachers and lessons.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: one authorized account across learners/teachers, core schedule/attendance/fee history and Activities with points, levels, invitations, assignments, achievements, consent management and announcements.

- [x] 8. Timetable: Recurring and individual classes, daily/upcoming views, cancellation, rescheduling and automatic display in relevant student dashboards.
  - Planned implementation: Recurrence rules and dated sessions; cancellation/reschedule history.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: recurring 90-day horizon, individual classes, today/upcoming view, cancellation/reschedule/history and student rosters. Explicit POST refresh/command; no generation on GET. Server scheduler provisioning is pending release.

- [x] 9. Online/Offline/Hybrid Classes: Physical location/address, online meeting links, start times and authorized Join Class access.
  - Planned implementation: Session location/mode, protected join endpoint and meeting URL validation.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: offline/online/hybrid locations, approved HTTPS meeting hosts and private authorized join window. Invalid/cancelled/revoked/unrelated access denied. Real provider/device checks remain operational validation.

- [x] 10. Attendance: Present, Absent, Late and Excused; teachers mark attendance; students/parents view attendance history.
  - Planned implementation: Unique session/student attendance and editable audit history.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: unique roster attendance, present/absent/late/excused, teacher-only correction, student history and idempotent point awards/reversals.

- [x] 11. Fee Management: Student/lesson-specific fees, billing period, due dates, paid amount, balance, payment date/method and Paid, Partially Paid, Pending and Overdue statuses. Keep payment history. Online gateway integration can be a later integration, but the data model must support it.
  - Planned implementation: Invoice/fee agreement and immutable payment ledger; derived status and gateway references.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: agreements/invoices, paid/balance/status, manual payments/reversals, references/idempotency and notifications. Future gateway metadata retained. Phase 5 isolated MySQL payment idempotency, overpayment and reversal races pass. Actual production-version rehearsal remains a release gate.

- [x] 12. Events: Annual days, performances, workshops, examinations, exhibitions, sports days and educational trips, including schedules, venues, participants, registrations, media and results.
  - Planned implementation: Typed events, registrations, participant permissions, media and results.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented locally: nine event types, windows/capacity, adult-confirmed registrations, invitations/acceptance/withdrawal, programmes, image galleries and structured results. Workflow/tenant/constraint/point tests pass. Phase 5: real MP4/H.264 and WebM/VP8 validation passes with ffprobe 9.0.2; corrupt, audio-only and disguised-container files rejected. MySQL registration-capacity race passes. Production runtime/storage checks remain under item 22.

- [x] 13. Competitions: Create competitions, register participants and record winners, runners-up, participation and special awards.
  - Planned implementation: Competition rules, participation and structured award results.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: competition event, unique learner participation, winner/runner-up/participation/special results, repeat-save deduplication, consent-gated public results and compensating point reversals on rejection/withdrawal.

- [x] 14. Points & Levels: Configurable points for attendance, completed assignments, performances, competitions and achievements. Support customizable levels from Beginner to Champion.
  - Planned implementation: Configurable point rules, deduplicated ledger, assignments/completion and custom levels.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: configurable five-source rules, versions, append-only source/reversal ledger, future-only values, assignments/submissions/teacher completion and custom threshold levels. Default Beginner-to-Champion set; duplicate rule/level validation and cross-tenant guards.

- [x] 15. Achievements: Certificates, level completion, attendance awards, performances, competition results, photographs and videos.
  - Planned implementation: Achievement/certificate records with private media and review.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented locally: teacher/student achievements, completion/attendance/performance/competition kinds, authorized printable certificates (browser PDF export), private/reviewed photographs and video upload path. Certificate access/consent/point history tested. Phase 5 real ffprobe MP4/WebM tests pass; authorization/consent guards pass on SQLite and MySQL. Arbitrary uploaded PDFs are not supported; certificates support browser PDF export. Production runtime checks remain under item 22.

- [x] 16. Annual Festivals: Create festivals, invite students, publish programme schedules, awards, results, photos and videos.
  - Planned implementation: Festival, invitations, programme entries, awards/results and galleries.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented locally: festival event, student invitation/verified registration, bounded programme schedules and participants, awards/results and image/video gallery paths. Programme bounds/tenant/consent revision tests pass. Phase 5 real ffprobe MP4/WebM tests pass; festival/programme/consent tests pass on SQLite and MySQL. Production runtime checks remain under item 22.

- [x] 17. Student Showcase: Display approved achievements on public teacher profiles only with appropriate parent/guardian consent where required.
  - Planned implementation: Per-achievement consent, approval and revocation-aware public queries.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: per-revision consent by reviewed guardian or verified adult self, explicit media/public-name choice, expiry/replacement/revocation, all-subject group checks and admin moderation. Public views and both file routes recheck current authority. Teacher consent, stale revision and legacy-route bypasses denied; adult transition requires fresh consent.

- [x] 18. Find a Teacher: Search/filter by PIN code, lesson, subject, teacher/academy, age group, online/offline mode, distance/service area, day and available timings.
  - Planned implementation: Indexed discovery filters, service areas and coordinate-based distance.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested in Phase 3: PIN/service area/name/type/subject/age/mode/day/time/capacity filtering, approved visibility, pagination and coordinate-based Haversine distance. No invented PIN distance or compulsory registered PIN.

- [x] 19. Apply to Learn: Collect name, age, mobile, email, PIN code, lesson interest, preferred days/timings, learning mode and message. Teachers manage enquiries from their dashboard.
  - Planned implementation: Public application form, validation, spam protection and teacher enquiry workflow.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: public application fields, CSRF/honeypot/rate bucket, teacher enquiry workflow, safe session claim and authorized learner attachment/replies/decisions.

- [x] 20. Notifications: In-app notifications for classes, cancellations, rescheduling, fees, payments, events, competitions, achievements, new enquiries and announcements. Structure the system to support future email, WhatsApp, SMS and push integrations.
  - Planned implementation: Domain event/outbox, in-app delivery, announcements and authorized messaging; future channel adapters.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: existing UserNotification through deduplicated outbox, core and activity triggers, scheduled announcements/event/fee reminders and recipient-only reads. Adult-context messaging reuses Conversation/Message; revoked/minor/legacy access guarded. Future external-channel adapters remain explicitly deferred; server scheduler not installed.

- [x] 21. OURPINCODE Admin: Manage teachers, students, categories, complaints, reports, content moderation and overall platform activity.
  - Planned implementation: Super-admin moderation, categories, students, complaints, reports and activity; scoped access explicit.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented and locally tested: main/state-capability teacher/content moderation, enrolment status and main-only adult identity review, categories/cycle validation, existing Complaint resolution, scoped reports and activity with pagination. Existing generic admin/chat/complaint routes exclude tuition contexts. Unmapped PINs remain main-admin-only.

- [ ] 22. Security and Data Integrity: Role-based access, private student information, child-safety protections, upload validation, duplicate-enrolment prevention, secure meeting links, payment consistency, audit trails and protection against unauthorized access.
  - Planned implementation: Central authorization, upload validation, private files, transactions, constraints and audit trail.
  - Design: complete; see Phase 2 design section 6, matching requirement ID, for models, URLs, permissions and build phase.
  - Implementation and verification: Implemented locally and negative-tested: server permissions, guardian verification and revision-bound consent, private storage/routes, validated raster/probed-video path, typed FK/check/unique constraints, locked services, audited history and legacy-context guards. Phase 5: fresh MySQL migrations and seven contention tests pass; real video probing and 24 offline browser layouts pass. RELEASE GATES REMAIN: actual server-version rehearsal, private storage/nginx isolation, scheduler, physical devices/provider checks, production configuration/log review, backup restoration and reviewed orphan-media retention. No automatic deletion command or compliance claim.

## Safety and dependencies
- Phase 3 and Phase 4 approved and implemented locally. Await separate explicit approval for production rollout. No deployment, destructive commands or production migrations without explicit approval for this module.
- Existing unrelated .env.example and portal/network_forms.py edits and untracked previews must remain untouched.
- Online payment gateway integration is explicitly allowed later; invoice/payment schema and manual payment functionality remain mandatory now.
- Future email/WhatsApp/SMS/push transports are extension points; all required in-app notifications must work now.
- Production server connectivity failed in the preceding incident; local planning/development can proceed, but production validation/deployment requires restored access and explicit approval.
- Phase 2 must specify private storage provisioning, geographic coordinates, consent verification/revocation and scheduled session generation. Do not silently omit these dependencies.

## Verification log
Phase 1: read-only inspection of relevant settings, routes, auth, models, middleware, base/home/dashboard templates, admin scoping, notification patterns and test configuration. No functionality tests claimed. Only this documentation file created.

Phase 2: completed design-only mapping of all 22 items; no model/migration code created, tests run or production actions performed. Next: wait for user approval of Phase 3.


## Phase 3 verification and remaining gates
- 92 tests passed: 52 tuition plus 40 existing assigned-admin, marketing, business registration and GA4 regressions. The expected mocked audit-failure log in the existing admin regression test is not a test failure.
- `manage.py check --settings=jobportal.test_settings`: no issues. `makemigrations --check --dry-run`: no changes. Core migrations applied forward in the isolated test database; no production migration or schema reversal.
- First 30-test run: 29 passed, temporary-file test hit Windows sandbox access denial. Authorized isolated rerun passed all 30; expanded final suite passed 92.
- MySQL validation blocked: no local mysql/mysqld binary; Docker executable exists but Linux engine socket is unavailable. No production DB used as a substitute.
- Private image storage/nginx separation and scheduler need operational provisioning/testing before release. No PDF/video or public student media enabled. Orphan upload retention/cleanup remains documented, with no deletion command added.
- Actual browser/device visual review is not claimed. Django template/form rendering is covered by tests.
- Schema design implemented as three new-app migrations: identity/media/outbox; learning/application/enrolment; scheduling/attendance/finance. This dependency ordering differs from the preliminary draft numbering but does not modify existing tables.
- GET remains read-only; recurring horizon extended on creation, explicit POST refresh or idempotent `tuition_schedule` command, rather than side effects on dashboard GET.
- Tuition-context messaging and legacy chat guards are deferred together to approved Phase 4, keeping existing chat unchanged and avoiding an unsafe partial integration.
- Implementation/runbook: `tuition/README.md`. Existing `.env.example` and `portal/network_forms.py` changes remain untouched. No push/deploy performed.


## Phase 4 verification and remaining gates
- Reused one typed event/participant/result domain across events, competitions and festivals; existing user/auth/UI/notifications/messages/complaints/audit remain the integration foundations.
- New test file: tuition/test_activities.py. Covers service and HTTP workflows, unrelated users/tenants, verified adult authority, group consent/revision/replacement/revocation, point corrections, private files, legacy chat/admin bypasses, scoped moderation, pagination and DB constraints.
- Checks: Django check passed; makemigrations --check --dry-run found no changes. Six tuition migrations applied forward during isolated test DB creation. No production DB, deletion or schema reversal used.
- Historical Phase 3 log above remains historical. Images and consent-gated galleries are now implemented; real video runtime testing remains blocked (ffprobe absent). Mocked codec-probe tests do not replace real-video checks.
- Initial Phase 4 run identified an outdated route name in a test, a generic Child string colliding with shared-page JavaScript, an assigned-admin fixture needing the new tuition section, and a missing shared GA4 include on the new certificate. Corrected without dropping assertions or existing regressions. An intermediate run overlapped a moderation-version test edit; the stable 142-test run then passed.
- Still not deployed or production-ready. Deferred optional integrations: payment gateway and email/WhatsApp/SMS/push. Mandatory release validation remains explicit, with 12/15/16/22 left unchecked rather than overstating verification.
- File inventory, workflow/runbook, configuration and migration rollout/rollback cautions: tuition/README.md.

Final Phase 4 verification (2026-10-04): **145/145 passed**, including the generic admin conversation selector, video-versus-image rendering and teacher student-points follow-ups. System check: 0 issues. Migration drift: no changes. Integration diff whitespace check passed. Expected CSRF-denial and mocked audit-failure logs are successful negative-test coverage, not failures. Checklist: 18 locally verified items; 12, 15, 16 and 22 retain explicit video/release verification gates.

## Phase 5 verification
- Historical Phase 3/4 blockers above are retained as history; current evidence supersedes their missing local MySQL/ffprobe/browser environment statements.
- Initial broad regression runs identified stale fixtures, a persisted news-file handle leak, a WebM container mismatch and MySQL test-response cleanup failures; corrected and rerun. Also added fresh-enrolment authorization and inactive-owner scheduler regressions.
- Final SQLite suite: 460 run, 453 passed, 7 MySQL-only skips. MySQL suite: 120 run, 119 passed, 1 optional export skip; follow-up readiness checks: 6 passed, 1 optional export skip. No remaining failing executed assertions.
- UI: eight synthetic pages at three viewport widths, no detected overflow/JS errors; representative mobile screenshots visually reviewed. External requests blocked; physical device/browser workflows still pending.
- Django checks: zero issues. Migration drift: none. Production-default audit: W004 HSTS warning; actual server settings unavailable. No blanket claim that every legacy feature is regression-covered.
- See tuition/PHASE5_AUDIT.md for evidence per requirement and tuition/DEPLOYMENT_CHECKLIST.md for safe forward rollout and data-preserving rollback. Deployment requires separate explicit approval after release blockers are resolved or reviewed.
