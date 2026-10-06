# Database + media recovery procedure

Scope: synthetic rehearsal now; real backup operations require separate authorization. No production backup was accessed. Do not reuse the empty-password localhost audit settings on a server.

## Reproducible safe rehearsal

`python -m tuition.audit_recovery` requires the existing disposable MySQL audit instance bound to 127.0.0.1:13317 and the downloaded portable MySQL executables under `.audit-tools/mysql/mysql-8.4.11-winx64/bin`. It ignores project DB credentials, asserts the dedicated port/bind address, creates two uniquely named databases, applies forward migrations to the new source and inserts synthetic fixtures only.

It records a partial fee payment, private learner image and scheduled learning fixture; runs the actual scheduler twice; backs up using mysqldump and a media archive; restores into the second new database and a new private directory; compares every table's row count/content digest and every file's SHA-256; checks the restored invoice balance and both private download routes for anonymous, unrelated, permitted and revoked guardians. No source database is dropped or overwritten. Artifacts are retained under ignored `.audit-tools/recovery-<id>/`; synthetic private roots are retained in the OS temporary directory. Test artifacts are unencrypted and must not contain real data or be published.

## Procedure for a later approved staging/production backup

1. Record immutable code revision, MySQL version/collation/SQL mode, migration history, UTC snapshot time, app configuration version and all relevant media roots. Store secrets separately in a restricted encrypted recovery vault. Define backup owner, retention and RPO/RTO before release.
2. Quiesce application/background writers and media publication for the approved snapshot window, or use a proven coordinated snapshot design. A transaction-consistent SQL dump alone does not synchronize files written outside the DB transaction. Do not run DDL during a dump. Check every required table uses a transaction-capable engine; adapt strategy if not.
3. Use restricted backup credentials and a protected option/login-path file, never a password in CLI arguments. Capture a complete schema/data snapshot and the matching private and required public media. Include routines/events/triggers if the actual schema needs them; preserve their definitions/definer permissions in the tested recovery plan.
4. The synthetic harness uses `mysqldump --single-transaction --quick --set-gtid-purged=OFF --no-tablespaces --skip-add-drop-table --skip-add-locks --skip-disable-keys <source>` and restores only to a new empty database. These flags were tested locally on MySQL 8.4.11; GTID/replication/privilege choices require review on the actual server. [MySQL documents the transactional-dump and concurrent-DDL limitations](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html).
5. Encrypt database/media archives before off-host transfer using the organization's approved tool/key custody. Record checksums and a manifest pairing DB/media snapshot IDs. Verify upload/retention/restore-reader permissions and alert on backup failure. Encryption/key recovery and off-host transport are not tested by the synthetic harness.
6. Restore into an isolated network/environment with new empty DB/storage, outbound messages/payments disabled, scheduler initially off and synthetic test accounts only. Never overwrite the source. Reject archive traversal/symlinks; restore restrictive ownership/modes rather than trusting archive permissions.
7. Compare schema/migrations, every relevant row count and sampled/full checksums, media existence/hash, foreign keys, invoice/payment balances, audit records and consent relationships. Verify authorized and unauthorized downloads, current consent/revocation and both legacy/private routes. Re-enable only the staging scheduler and test deduplication.
8. Measure backup time, restore/verification time and restored snapshot age; compare to agreed RPO/RTO on representative volume. Record operator sign-off and where encrypted artifacts/key recovery evidence are stored. Tiny synthetic timings are not a production capacity estimate.

## Rollback boundary

Prefer disabling tuition entry points and scheduler while retaining data and tuition-aware legacy chat/complaint/admin guards. Do not reverse migrations or restore an old backup over live data automatically. Any recovery that discards changes since snapshot requires explicit separate authorization and reconciliation of payments, notifications, consent and file changes.
