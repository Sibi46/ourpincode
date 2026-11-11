PincodeDay promotion
===================

Homepage Quiz links to `/quiz/pincodeday/`. Users sign in and go directly to
their daily questions and points. If no quiz is active, they see a short
availability message and their saved score. Event details, gifts, leaderboard
and management are restricted to super admins and appointed promotion admins.

Setup
-----

1. Open Super Admin > PincodeDay & Promotion Admins
   (`/quiz/promotion-admin/`). Grant promotion access using an existing active
   account's exact username. Revoking the grant removes this access immediately.
2. Open the December 20, 2026 draft created by migration 0004. Set the venue,
   description, agenda, event times and quiz dates. Times use Asia/Kolkata.
   The draft initially uses 10 AM–6 PM with scoring through December 19;
   these times are editable defaults, not a published schedule.
3. Add the four-option questions and correct answers. Publishing requires at
   least three questions. To support N daily plays per participant, add at least
   3 × N distinct questions. Questions remain immutable, and existing questions
   are never recycled when the pool is exhausted.
4. Configure gifts by leaderboard rank and minimum qualifying points. Gift
   rules may be edited or removed before results are finalized.
5. Publish the event. The homepage Quiz button opens the active daily quiz.
   Users receive the same three allocated questions when
   returning that day; the following day starts at midnight India time.
6. Promotion admins review attendance and mark or undo check-in in the
   participant list, independently of quiz scoring.
7. On or after the event starts, after the final quiz date has passed, finalize
   the leaderboard and gift winners. This action permanently locks event
   configuration, scoring and gift assignments. Mark each awarded gift delivered
   after handing it to the winner.

Scoring and winner rules
------------------------

Correct answers earn 5 points; wrong answers earn 1 point. The daily maximum is
15. Repeat submissions cannot award additional points. Scores belong to this
event and do not change referral wallets. Users cannot submit another user's
allocated question or answer an allocation from a previous day.

Rank uses descending points. Equal scores use earlier event participation
registration, then lower user ID. Participants with zero points are excluded.
For each gift, only the specified rank is considered. If that participant does
not meet the minimum score, or the rank does not exist, there is no eligible
winner for that gift. Scores are not exchanged or deducted.

Database constraints enforce one participant per event/account, one allocation
per question/account, and slots 1–3 only. Event and participant row locks
serialize daily allocations, scoring retries and winner finalization on MySQL.
Public leaderboards show first names and event participant IDs, not usernames,
phone numbers or email addresses.

Validation
----------

`python manage.py test quiz.test_pincodeday --settings=jobportal.test_settings`

Coverage includes scoring, duplicate submissions, daily caps and pool exhaustion,
authorization and revocation, CSRF, nonrepeat allocation, date validation,
attendance, ties, gift thresholds, finalization locks and delivery tracking.
