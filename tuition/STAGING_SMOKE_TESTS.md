# Staging and real-device sign-off

All execution is **BLOCKED** until an isolated staging URL and approved synthetic accounts/devices are available. This is a prepared plan, not evidence of passing tests. Do not execute mutation scenarios on production. Use no real minors, guardians, phone numbers, payments or messages. Disable external delivery, gateway charges and analytics collection in staging.

Record build/config revision, DB version, UTC time, tester, device/OS/browser version, viewport, PASS/FAIL/BLOCKED and redacted screenshot/evidence per row. Exercise Android Chrome and iPhone Safari on physical devices, desktop Chrome/Firefox, portrait/landscape, keyboard-only navigation, zoom, slow connection and interrupted upload. Offline Chromium screenshots already passed; do not substitute them for this sign-off.

Accounts: teacher A/B, guardian A/B, learner A/B, unverified guardian, verified adult learner, main admin, scoped tuition admin for two states, and unrelated normal/marketing account. Use two synthetic PINs, including an unmapped valid PIN.

| Scenario | Expected acceptance |
|---|---|
| Auth/session and role isolation | Login/logout work; anonymous private routes denied; teacher B/guardian B cannot see A; revoked/inactive/scoped users denied according to role; no sensitive data in errors |
| Discovery/profiles | Pending profile invisible; approval publishes; free six-digit PIN and service-area filters work; distance requires real coordinates; mode/age/day/time filters match fixtures; public fees follow opt-in |
| Applications/batches | Apply/request-info/reply/accept; invalid learner assignment rejected; repeated acceptance creates one enrolment; transfers update future roster; two concurrent last-slot attempts admit only one |
| Dashboards/timetable | Correct teacher and multi-learner totals; individual/recurring classes appear; reschedule/cancel persist; permitted join works in time window; cancelled/unrelated access fails |
| Attendance/fees | Owner-only marks; correction preserves audit/point compensation; partial/full fee balances and reversal match ledger; repeated payment key does not duplicate; no real charge |
| Activities | Event/competition/festival registration window/capacity, invitations, results and programme bounds; awards/levels/assignment completion do not double-credit |
| Private files | Both download routes and raw proxy/CDN paths tested with known synthetic file; unauthorized/revoked receive no bytes; authorized response hash/no-store verified |
| Consent/showcase | Teacher cannot consent; verified guardian/all group subjects required; edit/expiry/revoke/adult transition immediately closes publication, including previously cached URLs |
| Media/certificates | Representative Android/iPhone MP4 and WebM validate and play; malformed/oversized/disguised files denied; interrupted upload fails safely; certificate print/PDF usable and private |
| Messages/notifications | Adult-only authorized thread; legacy inbox/admin cannot expose tuition context; read/send/poll denied after withdrawal; upcoming event, fee and due announcement delivered once; no private text in shared notification |
| Moderation | Correct state/section scope, unmapped PIN main-only, global identity main-only; category/content/complaint/report/audit filters match mutations |
| Scheduled operations | Observe real timer trigger; approved future announcement due; retries recover; repeat execution no duplicates; deliberate staging failure alerts operator |
| Recovery | Restore paired DB/media into a separate environment; row/hash/balance/permission checks; record agreed-volume RPO/RTO |

Legacy OURPINCODE smoke matrix (all synthetic, isolated staging):

| Existing feature | Required checks |
|---|---|
| Home/navigation | Desktop/mobile Explore and links, promotion layout, header/footer; no new JS errors |
| Business/employer | Registration with unmapped valid PIN; profile/dashboard/options; marketing agent shop access and tenant restrictions |
| Main/scoped admins | Login, state assignment, section toggles, create/restrict delegated admin; existing hierarchy unchanged |
| Jobs/campus | List/search/apply; own application only; employer applicant access correctly scoped |
| Offers/coupons/vouchers | Create/view/redeem with synthetic balances; shop ownership/expiry/duplicate redemption denied |
| Community/network/flicks/gallery | Membership and private/public visibility; post/upload/comment flows; no tuition private media in shared galleries |
| Newsdesk | Create/edit/publish with PIN; private draft/photo/video permission and public front page |
| Quiz/health | PIN-restricted quiz answering; health auth/rate-limit paths using mocks, no real medical data/provider requests |
| Messaging/notifications | Existing non-tuition messages remain usable; unrelated users blocked; notification links/read state correct |
| Plans/wallet/billing | Sandbox or mocked transactions only; ledger unchanged by failed/replayed requests |

Existing automated suites cover portions of these features; no claim of exhaustive acceptance until every row/device is signed off. Return a defect list with reproducible synthetic steps, never screenshots of real personal information.
