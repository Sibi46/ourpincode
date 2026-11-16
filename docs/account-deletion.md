Super Admin permanent account deletion
======================================

Open Super Admin > Users > Delete everything beside the selected account.
Review the account name, phone, ID, record counts and uploaded-file count.
Type DELETE, tick the acknowledgement and submit the final deletion.

The preview follows owned account records and their dependent records, including
protected tuition profiles, media, lessons, applications, payments, quiz answers
and other linked modules. It never follows forward relations into other users'
accounts. Other user accounts, shared learner identities, site prize definitions,
monthly draw configurations and admin audit history are retained. Their links to
the deleted account are cleared or reassigned where needed. Uploaded files still
referenced by surviving records are retained.

Only active Super Admin accounts can perform this action. Super Admin and Django
superuser accounts cannot be removed here. GET only previews. POST requires CSRF,
explicit acknowledgement and a signed preview tied to the actor, target and exact
record/file set, valid for 15 minutes. Changed record sets must be reviewed again.

Database deletion and shared-record updates run in one transaction. Foreign-key
constraints remain enabled. Dependency cycles or unexpected records cancel the
operation. An audit entry records the actor, target and counts; an audit failure
also rolls deletion back. Repeating a completed POST reports that the account has
already been deleted.

Files are queued in jobs.AccountFileDeletion and cleaned only after commit.
Private tuition files, public uploads and private news/identity uploads use their
configured storage. Cleanup checks for surviving references before unlinking a
file. A storage outage leaves a retryable task. Super Admin > Users shows Retry
file cleanup when tasks remain. Operators can also run:

    python manage.py cleanup_account_files --limit 100

Tests: jobs.test_account_delete_all and jobs.test_user_deletion.
