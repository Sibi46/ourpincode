# Coupon categories and Lucky Draw

Apply migrations with `python manage.py migrate`. Existing OPC codes and the
salesman → business assignment flow are preserved. New assignments select S, G,
P or C and produce codes such as `opcg000001` (Silver: `opcs`, Gold: `opcg`,
Points: `opcp`, Complimentary: `opcc`, followed by a six-digit number, without a hyphen).
Customers select the category and enter only the number; shorter numbers are
zero-padded in the preview. Category and number are checked together on the server.
Previously printed category-first codes such as `Gopc000001` remain valid and
retain their original display in batch history. The older full-code entry is
available under "Have an older printed coupon?" for legacy `OPC-` coupons.
Numbers remain globally unique,
as before; categories do not allow reassignment of an existing number range.
Legacy batches retain a blank category (Standard) and their original codes.
The stored `activated` status remains the used status for compatibility with reports.

Configure category-specific rewards in Coupon Admin → Spin Wheel. Blank-category
slots are the existing defaults; a category's active slots replace those defaults
when configured. With no configured slots, the existing 10-point fallback remains.

Coupon Admin → Monthly Lucky Draws configures prizes, lists entries and winners,
and records awarded/claimed prizes. Entries are created automatically for the
local month only when the spin transaction successfully awards the reward.
Past activations are not retroactively entered. Each coupon can enter only once.

Schedule `python manage.py select_monthly_draws` daily using the deployment's
scheduler (cron or Windows Task Scheduler), with the same environment and working
directory as Django. It selects winners for completed months, including missed
runs, and never replaces an existing winner. Months without a prize or eligible
entries are reported and skipped. Each eligible coupon has equal probability.
Month boundaries use Django's configured Asia/Kolkata timezone.

The repository has no existing scheduler; deployment must register this command
for automatic month-end selection (on the first run after the month closes).
