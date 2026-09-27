Smart Marketing Agents
======================

Apply the migration with the deployment environment's Python and settings:

    python manage.py migrate

1. Super admin dashboard → Manage Smart Marketing Agents. Create an agent with
   username, pincode, phone number and password.
2. The registered business owner opens Employer Dashboard → Smart Marketing
   Agent access, enters the agent username and grants access. The same page
   allows immediate revocation.
3. The agent signs in through the existing login page with username or phone
   and password. Their dashboard lists only shops that granted access.
4. Clicking a shop asks for that shop owner's registered personal/business phone
   and account password. The agent can then use offers, gift vouchers, videos,
   coupon history and (for shop accounts) coupon redemption.

Shop access expires after one hour, or immediately upon revocation, owner
password change or account deactivation. Opening another shop requires its
credentials. The authenticated session remains the agent's session; only an
explicit list of marketing views uses the selected owner for ownership checks.
Shop passwords are verified and are never stored in the agent session.

Pincode is agent profile information; authorization comes from the owner's grant.
Existing voucher business approval and publishing requirements still apply.
Coupon issuance remains the existing salesman's responsibility.

Validation:

    .venv\Scripts\python.exe manage.py test jobs.test_marketing --settings=jobportal.test_settings
