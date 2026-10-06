# Tuition release checklist — not deployment authorization

Complete the unresolved evidence in PHASE5_AUDIT.md and obtain explicit approval before any production action.

Operator execution order and acceptance criteria: [prioritized server-verification plan](SERVER_VERIFICATION_PLAN.md). Read-only commands and state-changing staging-only exercises are labeled separately. Plan preparation is complete; execution evidence is still unavailable, so all existing operational blockers and Requirement 22 remain unchanged.

## Current gate status (continuation)

| Gate | Status | Evidence / blocker |
|---|---|---|
| Production private storage and file denial | **BLOCKED** | Local restored-file authorization PASS; need real service-user/ACL/proxy/CDN and approved synthetic-fixture evidence. [Commands](SERVER_VERIFICATION.md#1-private-storage-and-unauthorized-access). |
| Scheduler | **BLOCKED** configuration; **PASS** local behavior | Actual command repeated safely; due announcement/event/fee/retry test 1/1 PASS on isolated MySQL. Need installed timer/cron, cadence, no overlap, failure alert and environment evidence. [Commands](SERVER_VERIFICATION.md#2-scheduler-metadata-do-not-run-the-production-command). |
| Backup/restore | **PASS** synthetic; **BLOCKED** operational | 262 tables/1,474 rows/one image match after new-target recovery; restored permission and INR 60 balance checks PASS. Encrypted/off-host/representative-volume recovery remains unverified. [Procedure](RECOVERY_RUNBOOK.md). |
| HTTPS/configuration/headers | **BLOCKED** | W004 persists in synthetic defaults; no live evidence to justify a settings change. [Commands](SERVER_VERIFICATION.md#4-https-headers-and-configuration). |
| Real-device/staging acceptance | **BLOCKED** execution; **PASS** test preparation | [Smoke matrix](STAGING_SMOKE_TESTS.md); no staging/device sign-off yet. |
| Requirement 22 | **BLOCKED** release gate | Local criterion evidence PASS, detailed matrix in PHASE5_AUDIT.md; operational checks above outstanding. |

No newly failing executed assertion. BLOCKED is not PASS. Prior automated suites were reused without redundant reruns. Do not run the production scheduler, backups, mutations or create production canaries under the present authorization.

## Before approval

- [ ] Review a focused release diff; exclude secrets, unrelated edits, synthetic media, test DBs and downloaded audit tools. Record immutable release and rollback revisions.
- [ ] Rehearse forward migrations and regression/concurrency tests on staging matching production MySQL, Python and runtime configuration. Inspect `migrate --plan` and migration SQL; confirm jobs/community dependencies. All six tuition migrations are additive; audit fixes need no new migration.
- [ ] Confirm a recent encrypted database backup plus private-file backup, restore both to an isolated environment, check counts/checksums and representative protected downloads. Record restore duration, owner and recovery objectives. A database-only backup is insufficient.
- [ ] Confirm private-storage ownership, proxy/CDN exclusion, authenticated no-store responses and revoked-consent denial from outside the server. Test raw-path guesses and both file routes.
- [ ] Install supported ffprobe on staging/production only after approval; configure TUITION_FFPROBE, upload limits and worker resource/time limits. Test representative MP4/WebM recordings and supported playback devices.
- [ ] Verify secure cookies, HTTPS/proxy trust and HSTS decision with real deployment settings. Review log permissions, redaction/retention and alerts.
- [ ] Configure/verify scheduler, timezone and retry monitoring; run tuition_schedule twice in staging and confirm deduplicated sessions/notifications.
- [ ] Complete physical-device/browser, conferencing and legacy feature acceptance; document any accepted coverage gaps. Review guardian verification, moderation, retention and orphan-media procedures.
- [ ] Obtain explicit user approval of the concrete release and remaining accepted risks.

## Approved rollout procedure

1. Take and verify protected backups; record current release/config/schema state. Coordinate a maintenance window if required by staging timings.
2. Apply only reviewed forward migrations with the intended environment. MySQL DDL is not fully transactional: if a migration fails, stop and inspect schema/history; do not blindly fake, reverse or repeatedly retry it.
3. Release code and static files together, verify service health and logs, then enable tuition entry points and scheduler. Verify private access before publishing any student media.
4. Smoke-test discovery, teacher/student/guardian permissions, enrolment, attendance, fee balance/reversal, events, consent revocation, notifications, moderation and legacy chat isolation using approved test accounts.
5. Monitor errors, slow queries, upload resources, scheduler failures and audit records; record rollout outcome.

## Rollback without deleting tuition data

- Disable tuition entry points/mutations and pause its scheduled command if needed. Preserve tables, private files, financial/audit history and backups.
- **Retain tuition-aware legacy chat, complaint and generic-admin guards.** Reverting to a pre-tuition build that lacks these exclusions could expose existing tuition conversations/complaints. A safe rollback build must keep the guards and any model definitions they query.
- Restore a known compatible application/config revision only after staging rehearsal. Verify both private routes and legacy exclusions after rollback.
- Do not reverse migrations, delete tables/files or overwrite production from a backup automatically. Data restoration is a separate explicitly authorized recovery operation with a reconciliation plan for changes since backup.

No production rollout, backup or rollback rehearsal was executed during Phase 5. A synthetic localhost MySQL/database-media recovery rehearsal passed; this does not verify production backup operations.
