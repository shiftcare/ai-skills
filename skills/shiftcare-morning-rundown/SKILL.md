---
name: shiftcare-morning-rundown
description: Sweep yesterday's and today's ShiftCare shifts and report what needs a coordinator's attention, grouped by urgency — missed clock-ins, vacant shifts, double-booked staff, short breaks, expiring staff compliance, and rate gaps that will block invoicing. Every finding names the shift, client, staff and a concrete next step. Use when the user asks "what needs my attention today", "morning rundown", "any problems with yesterday's shifts", "did anyone miss a clock-in", or "anything blocking invoicing". Read-only. Not for checking whether an account is set up correctly — that is onboarding-check.
license: Apache-2.0
metadata:
  author: shiftcare
  version: "1.0.0"
---

# ShiftCare morning rundown

The daily sweep a rostering coordinator does across several screens before the day starts:
what went wrong yesterday, what is unstaffed today, and what will block this week's invoice
run. This skill answers it in one pass and **never calls a write tool**.

## Use this, or use onboarding-check

| The user is asking | Skill |
| --- | --- |
| "What needs my attention today?" — an operating account, this morning's problems | **this one** |
| "Is my account set up properly?" — a new account, configuration gaps | `onboarding-check` |

If the account turns out to have almost no real data, say so and offer `onboarding-check`
instead of reporting an empty rundown as "all clear".

## Before any tool call

1. **Compatibility preflight.** Call `check_skill_compatibility` with skill
   `shiftcare-morning-rundown` and skill_version `1.0.0`, before every other tool.
   - `up_to_date` — continue.
   - `update_available` — continue, and tell the user a newer version exists.
   - `update_required` — **stop.** Tell the user to run `npx skills update shiftcare-morning-rundown`.
   - `retired` — **stop.** The skill has been withdrawn.
   - `unrecognized` — the server's registry has no entry for this skill yet, which is
     expected while the skill is new. Continue, and say once that the version could not be
     verified. Do not treat it as an error the user has to fix.
   - The tool missing entirely, or erroring — say the version could not be checked, and
     continue.
2. **Connection.** If ShiftCare tools are missing, use the `shiftcare-mcp` skill first.
3. **Account and time zone.** Call `whoami`. Note the `account_id` and the signed-in
   person. If they belong to more than one account, ask which one. Everything below is
   read-only, so no confirmation is needed before reading.
4. **Fix the window before you call anything.** "Yesterday" and "today" are calendar days
   in the **account's** time zone, not yours and not UTC. Shift `start_at` values come back
   with an explicit offset — read the offset off the first shift, or off any timesheet
   item's `account_location_time_zone`, and use it for every date comparison. A shift that
   ran 22:00–06:00 belongs to the day it started.

Tell the user the sweep is read-only and costs roughly twenty to forty tool calls
depending on how many staff and shifts are in the window.

## What the tools do and do not give you

Four of these are the reason a naive sweep reports the wrong thing. Read them before
planning calls.

**`list_shifts` does not return staff.** There is no `staff` array and no `staff_ids` on a
shift. A shift you fetched looks identical whether three carers are on it or none. So you
can never conclude "vacant" from a `list_shifts` row — see the coverage sweep below for
the way around it. `is_approved` is also not coverage: it means at least one assigned
worker was verified, and `status: "unapproved"` explicitly *includes* shifts with nobody on
them.

**`list_shift_events` in bulk mode loses the shift.** Passing `shift_ids` as an array
returns one flat `events` array with no per-event shift reference — only the requested ids
echoed back in `_metadata`. You cannot tell which shift an event belongs to. **Use bulk
mode only to answer "did anything at all happen across these shifts", never to attribute an
event.** When you need to attribute one, pass a single `shift_id`, one call per shift, and
only for shifts you have already flagged.

**Timesheet clock fields are gated by an account feature flag, not by a request parameter.**
There is no argument you can pass to turn them on. When a timesheet comes back carrying
only `staff_id`, `date`, `client_ids` and `items`, the flag is off for the account — that
is **not** evidence nobody clocked in. This is the single worst failure mode of this skill:
reporting "everyone clocked in fine" when the account simply does not expose clock times.
See "Clock-ins" below for what to say instead.

**`list_allowances` is the account's allowance catalogue, not what was claimed.** It lists
the allowance types the account has defined — a meal allowance, a sleepover allowance —
with their codes and values. It says nothing about any shift. Mileage actually claimed
lives on the shift's `km` and on the `Travel Kms` / `Transport Kms` line items under each
client on the shift.

Two smaller ones:

- A shift's `shift_type` field is a structural value such as `standard`. The account's own
  named type — Personal Care, Respite Care — appears as `shift_type_name` on a timesheet
  item, not on the shift.
- `list_staff_files` returns account-level documents with `user_id: null`. Those cannot be
  attributed to a person, so report them as an account document expiring, not as a staff
  member's compliance gap.

## The sweep

Run these in order. Steps 1–4 are the core and always run. Steps 5–7 are additive; skip one
and say so rather than guessing at its findings.

### 1. The shift spine

`list_shifts` from yesterday to today, `per_page` 20, `include_clients` true. Page until
`_metadata.next_page_link` is null, but **stop at 5 pages (100 shifts) and tell the user the
window was truncated** rather than burning the context on a large roster.

Keep per shift: `id`, `start_at`, `end_at`, `break_time`, `km`, `published`, `pending`,
`is_approved`, `cancelled_at`, `address`, `url`, and each client's name and `line_items`.

**Drop every shift with a non-null `cancelled_at` before any other check.** A cancelled
shift is not vacant, not a missed clock-in, and not a break breach. Cancellation is not
deletion, so they do come back in the list.

### 2. Coverage — the staffed set

This is how you get around `list_shifts` not returning staff, in a bounded number of calls
rather than one call per shift.

1. `list_staff`, `per_page` 20, paging until done. Keep `id` and `name`.
2. `list_shifts` over the same window with `staff_id` set to an **array of every staff id**.
   The filter is an OR, so one call returns every shift in the window that has at least one
   of those staff on it. Batch the ids **50 at a time** so the request stays inside URL
   length limits, and page each batch.
3. **Vacant = the step 1 shift ids minus the union of the step 2 ids.**

Cost is one call per 50 staff plus paging, instead of one call per shift.

Two limits to state rather than hide. A **group shift** can need several carers and this
method only proves *one* is assigned, so a partly-filled group shift will not be flagged —
say "at least one carer assigned" rather than "covered". And if the staff list itself was
truncated, the vacant set is unreliable; report coverage as **cannot check** instead of
listing wrong shifts.

To attribute a specific vacant shift before reporting it, `list_shift_staffs` takes one
`shift_id` per call and returns the assigned staff. Use it to confirm the handful you are
about to report, not to scan the roster.

### 3. Per-staff intervals

`list_timesheets` over the window, `include_staff` true, `per_page` 20, paged. A timesheet
row exists for **every rostered staff assignment whether or not anyone turned up**, so the
count means nothing on its own — but the rows are the cheapest per-staff view of the window
there is. Each carries `staff_id`, `date`, `client_ids`, and `items[]` with `start_at`,
`finish_at`, `break_minutes`, `amount`, `pricebook_id`, `pricebook_name`, `shift_type_name`
and `account_location_time_zone`. When the account's clocking flag is on, the row also
carries `clockin_at` and `clockout_at`.

This one sweep feeds the overlap, hours, break and rate checks below.

### 4. Clock-ins — and the trap

**First decide whether the account exposes clock times at all.** Look across every timesheet
row in the window: if not one of them has a `clockin_at` or `clockout_at` field present, the
feature is off for the account.

- **Flag off** → report the clock-in check as **"Cannot verify clock-ins on this account"**,
  explain that clocking data is not exposed to the API here, and point at the roster screen.
  Never render this as "no missed clock-ins" or fold it into an all-clear.
- **Flag on** → a shift that has already **finished** and whose timesheet has no
  `clockout_at` is a no clock-out. One that started more than a short grace period ago with
  no `clockin_at` is a missed clock-in. Never flag a shift that has not started yet, and
  never flag today's in-progress shifts for a missing clock-*out*.

The fallback when the flag is off is `list_shift_events` with a single `shift_id`, looking
for events named `start` and `finish` (`offline_clock_in` and `offline_clock_out` count
too). It is one call per shift, so use it only for a few shifts the user asks about — not
across the window. Most events on a shift are `create`, `update`, `approved`,
`shift_published` and `shift_extended`, none of which are attendance.

### 5. Overlaps, hours and breaks — approximate, and say so

All three come from the step 3 intervals, computed client-side.

- **Overlap.** Group the timesheet items by `staff_id` and compare intervals. Any two that
  intersect are a double-booking. Convert to a single offset first; items can come from
  locations in different time zones.
- **Rolling hours.** Sum each staff member's item durations across the window. Flag anyone
  well past a normal day. There is no award engine here, so report the number and let the
  coordinator judge it.
- **Breaks.** Compare `break_minutes` against the item's duration. A long unbroken shift
  with a zero break is worth surfacing.

**State the limitation in the report, once:** these three are derived from rostered times
on the client side and are not the award-rule evaluation the product's own compliance
screens run. They find the obvious cases. They are not a compliance sign-off, and a clean
result here does not mean the roster is award-compliant.

### 6. Expiring compliance

Two sources, and the cheaper one first.

- `list_staff_files`, paged, is one account-wide listing with `category`, `expires_at` and
  `no_expiration`. Flag anything expiring inside the next 30 days or already expired. Rows
  with `user_id: null` are account documents — report them as such, not against a person.
- `list_staff_qualifications` needs a `staff_id` and handles **one staff member per call**.
  Do not run it across the whole team. **Run it only for staff rostered in the window**,
  which is the set you already have from step 2, and cap it at 20 calls — beyond that, say
  you checked the first 20 and offer to continue.

It returns `qualification_id` and `expires_at`, **not the qualification's name**. To name
one, `list_qualifications` gives the account's library — but that is several pages, so only
fetch it when you actually have an expiry to report, and then look up just the ids you need.

### 7. Invoicing blockers

Two independent signals for the current week:

- **Rate gaps, from the step 3 timesheet items.** An item with a null `pricebook_id`, or an
  `amount` of zero on an item that clearly represents worked hours, will not price. These
  are the rows that silently drop out of an invoice run.
- **`list_invoiceable_items`** for the week, dates in the account time zone. Omit
  `client_id` to sweep every client, and page with the `next_cursor` it returns. Use
  `estimated_total` as the figure to quote. This tool is **not published on every regional
  server** — if it is absent, report invoicing from the rate gaps alone and say the totals
  could not be read.

`get_client_fund_balance` is worth one call per client only when a specific client's
invoicing is already in question. Do not sweep it.

## Reporting

Three buckets, in this order. **Every row names the shift, the client, the staff member and
one concrete next step** — an action in the imperative, not a restatement of the problem.
Put the shift's `url` on the row where you have it, so the coordinator can click through.

| Bucket | What belongs in it |
| --- | --- |
| **Needs action now** | Vacant shift starting today. Staff double-booked today. A client with nobody assigned right now. |
| **Today** | Yesterday's missed clock-in or missing clock-out. Short or missing break. Over-hours. A qualification that has already expired on someone rostered today. |
| **This week** | Rate and pricebook gaps blocking the invoice run. Compliance expiring in the next 30 days. Uninvoiced billable work. |

Lead with a one-line summary — how many shifts were swept, over what dates, and how many
findings. Then the buckets. Then a short **Could not check** list naming every check that
was skipped, truncated, or gated off, with the reason.

**That last section is not optional.** A rundown that quietly omits the clock-in check reads
as "clock-ins are fine". If a check could not run, its absence must be visible.

Shape of the tone, with invented data:

> **14 shifts across Thu 3 and Fri 4 April. 4 things need you.**
>
> **Needs action now**
> - **Vacant — today 14:00–18:00**, A. Example (Personal Care, 12 Example St). Nobody
>   assigned. → Assign a carer, or post it to the Job Board.
> - **Double-booked — today 09:00–12:00 and 11:00–15:00**, J. Sample is on both. → Move one
>   shift or reassign it.
>
> **This week**
> - **No price book — Thu 3 April, 3h for B. Example.** The line will not price and drops
>   out of the invoice run. → Set a price book on the client's service agreement.
>
> **Could not check**
> - **Clock-ins.** This account does not expose clock times to the API, so I cannot tell
>   who clocked on. Check the roster screen.

### Hold the line on these

- **Never invent a finding to fill a bucket.** A clean sweep reports clean, in one line,
  with the Could not check list underneath. Silence in a bucket is a result.
- **A tool error or a "not found" is Cannot check, never a clean result.** Some listings are
  enabled per account.
- **Results are permission-scoped.** An empty list means "nothing visible to this caller",
  which is not the same as "nothing exists" — worth saying plainly if the user is not an
  Admin.
- **Do not list every shift back.** Report the findings and the counts. The user asked what
  needs attention, not for the roster.
- **This skill reads. It does not fix.** If the user asks you to assign the vacant shift or
  correct a timesheet, that is a write: check `whoami` for `mcp_writes_enabled` and an
  `admin` role first, confirm the exact change, and follow `shiftcare-basics` for the tool
  and its confirmation rules.
