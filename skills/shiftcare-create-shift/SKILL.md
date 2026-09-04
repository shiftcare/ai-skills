---
name: shiftcare-create-shift
description: Create a shift in ShiftCare from a plain-language request — one-off or recurring, staffed or vacant. Resolves client and staff names to IDs, discovers the account's own shift types and locations, pins the time to an explicit UTC offset, reads the whole booking back for explicit confirmation, then writes once and verifies. Use for "book a shift for Mary tomorrow 9 to 5 with Sarah", "create a recurring Monday morning shift", "schedule a sleepover this Friday", "add a shift, I'll pick the carer later". Not for cancelling a shift, changing the time of an existing shift, or swapping the carer on one — those are separate workflows this skill will not attempt. Writes data; never without confirmation.
license: Apache-2.0
metadata:
  author: shiftcare
  version: "1.0.0"
---

# Create a ShiftCare shift

Booking a shift is the most common write a coordinator makes, and the one with the most
ways to be quietly wrong. `create_shift` takes over twenty optional fields, the useful
values for most of them live in four different listing tools, and the two fields that
matter most — the start and end time — accept a value that looks right and means something
else. This skill exists to close those gaps, not to save typing.

**This skill changes data.** Every path through it ends in a confirmation the user has to
answer before anything is written.

## The three things that make this hard

1. **A datetime without an offset is a silent one-hour bug.** `start_at` and `end_at`
   accept `2026-05-10T09:00:00`, and interpret it in the account's time zone — which the
   tool's own documentation calls "rarely what you want". Nothing errors. The shift is just
   at the wrong time, and a carer arrives an hour late to someone who needed them.
   **Always send an explicit offset.**
2. **Shift types are account vocabulary, and the name is not the value.** On a real account
   the type whose `type_string` is `standard` is displayed as *Personal Care*. The user says
   the display name; the tool wants the `type_string`. Never invent one, and never assume a
   type exists because the word is common.
3. **Assigning staff can reach their phone.** `published` and `notify` decide whether a real
   person gets a real notification. They have server-side defaults, so an agent that never
   mentions them has still made the decision. Say what will happen before you write.

## Step 0 — Preflight, and fail closed

Before any other ShiftCare tool call, call `check_skill_compatibility` with
`skill: shiftcare-create-shift` and the `metadata.version` from this file's frontmatter.

| Status | What to do |
| --- | --- |
| `up_to_date` | Continue. |
| `update_available` | Continue, and tell the user a newer version exists. |
| `update_required` | **Stop.** Tell the user to run `npx skills update shiftcare-create-shift`. |
| `unrecognized` | **Stop.** This is not a published ShiftCare skill. |
| `retired` | **Stop.** This skill has been withdrawn. |

If the call itself fails or the tool is not available, stop and say so. Do not fall back to
creating the shift anyway — the whole point of the check is the writes that come after it.

Then call `whoami` and read the account you will be writing to:

- `mcp_available` must be `true`.
- `mcp_writes_enabled` must be `true`. If it is `false`, stop: an Admin has to turn on
  **Allow Write Actions** under **Account → AI Settings**. Report that instead of trying.
- `role` must be `admin`. Any other role is read-only regardless of the account setting.
- If the user belongs to more than one account, ask which one before resolving any name.

Connection problems are not this skill's job. If ShiftCare tools are missing entirely, use
the `shiftcare-mcp` skill.

## Step 1 — Resolve every name to an ID

Use `list_clients` and `list_staff` with `filter_by_name`. Both are **partial** matches, so
"Sam" matches Samantha and Sammy.

- **Exactly one match** → use it, and keep the returned display name for the confirmation.
- **More than one match** → list them and ask. Never pick the first, the most recent, or the
  closest string. Two people named Mary is the normal case, not an edge case.
- **No match** → say so and stop. Do not widen the search to a shorter fragment and guess;
  the client may be inactive, on another team, or simply not exist.

Listings are permission-scoped. An empty result means "nothing this user can see", which is
not the same as "does not exist" — say it that way.

A shift may legitimately have no staff. If the user has not named a carer ("add a shift next
week, I'll pick the carer"), create it **vacant** by omitting `staff_ids`. Do not choose
someone. Note that recurring series cannot be vacant — see Step 4.

## Step 2 — Get the account's UTC offset

No MCP tool reports the account's time zone directly. `list_account_locations` returns names
and addresses but no zone, and on some accounts it is not enabled at all. Read the offset off
an existing shift instead:

1. Call `list_shifts` with `from_date` and `to_date` (both `YYYY-MM-DD`) spanning a few days
   **around the requested date**.
2. Read the offset from a returned `start_at`, for example `2026-09-04T09:00:00+10:00` → `+10:00`.

Take it from near the target date, not from today. Accounts in daylight-saving regions change
offset mid-year, and a shift booked across the changeover with today's offset is wrong by an
hour in exactly the way this step is meant to prevent.

If that range comes back empty, **ask the user for their time zone or offset.** Guessing from
the region is not good enough: a single account can have locations in Perth, Queensland,
Melbourne and Hobart, which are three different offsets.

Then build the datetimes from the user's wall-clock time plus that offset:
`"tomorrow 9am to 5pm"` with `+10:00` → `start_at: 2026-09-05T09:00:00+10:00`,
`end_at: 2026-09-05T17:00:00+10:00`.

**If `end_at` is earlier than `start_at` on the same date, stop and ask.** "9pm to 7am" is
either an overnight shift, in which case `end_at` belongs on the next day, or a typo. Never
decide which on the user's behalf.

## Step 3 — Learn the account's vocabulary

Call `list_shift_types`. Each row has a `name` (what the user says) and a `type_string` (what
the tool wants). Match the user's words against `name`, send `type_string`.

- No confident match → show the available names and ask. Never pass a `type_string` you did
  not read from this listing.
- The user named no type → omit `shift_type`; it defaults to `standard`. Say so in the
  confirmation, using the display name that account gives `standard`.

**Sleepover is two independent things.** Most accounts have a shift type named *Sleepover*,
and `create_shift` also has a separate `sleepover` boolean that changes pay treatment (often a
fixed rate instead of hourly). Setting the type does not set the flag. For "schedule a
sleepover", propose both and confirm them as two separate lines. `live_in` behaves the same
way for multi-day live-in shifts.

Only if the user asked for them:

- `list_account_locations` → `account_location_id`. If it returns *Feature not enabled*, that
  account does not expose locations; carry on without one.
- `list_facilities` → `facility_id`.
- `list_allowances` → `allowance_ids`.

`address` and `suburb_address` are free text stored on the shift. They do **not** look up or
override `account_location_id` or `facility_id`, and those three IDs are not interchangeable.

## Step 4 — Route one-off vs recurring

| Request | Tool |
| --- | --- |
| A single date | `create_shift` |
| "every Monday", "weekly", "every second Tuesday", "monthly on the 3rd" | `create_recurring_shift` |

`create_shift` cannot create a series and `create_recurring_shift` cannot create a one-off.
Pick before you confirm, and confirm the one you picked.

Recurring needs more from the user, and it will not proceed without it:

- `recurrence_unit` (`day` / `week` / `month`) and `recurrence_repeat_every` (1–365).
- `recurrence_week_days` when the unit is `week`, as `["Mon", "Wed"]`.
- `recurrence_day_of_month` when the unit is `month`.
- **`recurrence_end_date` is required.** There is no open-ended series. If the user did not
  give an end date, ask for one — do not invent a horizon.
- **`client_ids` and `staff_ids` are both required.** A recurring series cannot be created
  vacant. If the user has not chosen a carer, say that and offer a one-off shift instead.

`start_at` / `end_at` describe the **first** occurrence and still need an explicit offset.

## Step 5 — Check for clashes before you confirm

For each staff member you are about to assign, call `list_shifts` with `from_date` and
`to_date` covering the shift's date **and the day before**. `list_shifts` filters on
`start_at`, so a window matching the exact shift times misses an earlier-starting or overnight
shift that still overlaps.

Compare the returned `start_at`/`end_at` against the requested window yourself. Any overlap
goes into the confirmation as a named conflict, with the choice to proceed anyway or pick
someone else. Never create over a clash silently.

Leave and availability are not checked by this skill. If the user asks, read them with
`list_leaves` and `list_availability_schedules` before confirming.

## Step 6 — Confirm, in full, every time

Read back every resolved value. Not "shall I create the shift?" — the whole booking, so the
user can catch the resolution that went wrong. Nothing above this line has changed any data;
everything below it does.

```text
Ready to create this shift:

  Client:      Mary Chen (id 12345)
  Staff:       Sarah Okafor (id 67890)
  When:        Fri 5 Sep 2026, 9:00 am – 5:00 pm (+10:00)
  Shift type:  Personal Care (standard)
  Location:    Melbourne
  Sleepover:   no
  Published:   yes — visible to Sarah on her roster
  Notify:      yes — Sarah gets a notification

  Note: Sarah already has a shift 4:00 pm – 6:00 pm that day.

Create it?
```

Rules for this step:

- **Explicit confirmation only.** An earlier "book me a shift" is intent, not consent for the
  specific booking you just assembled. Wait for an answer to this message.
- **The user declines → create nothing.** No partial write, no "I'll create it unassigned
  instead", no retry with a tweak. Report that nothing was created and stop.
- **State `published` and `notify` in plain words**, as above. Both have server-side defaults
  (`published` is computed from the account's Publish Shifts setting and the shift type), so
  if you are leaving them to the default, say which way you expect it to resolve and that the
  account setting decides. If the user wants either one off, pass it explicitly as `false`.
- **For a recurring series**, confirm the pattern and the count you expect:
  "every Monday from 7 Sep to 21 Dec — about 16 shifts".
- **If anything is still unresolved, this message is not confirmation-ready.** Ask the
  question instead.

## Step 7 — Write once, then verify

Call the write tool exactly once.

**Never blindly retry a create.** These tools are not idempotent, and an unclear result is
much more likely to be a slow success than a failure. If the outcome is uncertain, read first
with `list_shifts` over that date, then decide.

Verify and report what actually exists:

- **One-off:** read the created shift back and report its stored `start_at`/`end_at`. Check the
  offset in the response matches the wall-clock time the user asked for. This is the check that
  catches a timezone mistake before the carer does.
- **Recurring:** the response carries a `program_id`. The first 20 shifts are created
  synchronously and any remainder follows asynchronously, so call `list_shifts` across the
  series range, filter by that `program_id`, and report the count. If it is short of expected,
  say the rest are still being generated rather than reporting a failure.

Report in plain language: what was created, when, for whom, with whom, and whether staff were
notified. Include the returned `url` if there is one.

## What this skill will not do

MCP does not expose these on shift creation. Do not smuggle them into the call — direct the
user to the ShiftCare web app:

- Price book, fund, and pay group selection. These fall back to V3 server-side defaults.
- Per-shift travel billing. It follows each client's own Invoice Travel setting.
- Additional charges such as transport or equipment billed to the client on the shift.

One consequence worth surfacing: **pricing uses each client's default service area, and a
client with no configured area produces an unpriced ($0) shift with no error.** If a shift
matters financially, tell the user to check its pricing in the app.

Out of scope for this skill entirely — say so and stop rather than improvising:

- **Cancelling a shift.** Use the `shiftcare-cancel-shift` skill. The two cancel tools differ
  in whether the client is billed *and* whether the carer is paid — a billing decision, not a
  cleanup step.
- **Changing an existing shift, including swapping the carer.** `update_shift`'s client and
  staff arrays **replace the assignment list wholesale** — sending one staff ID removes
  everyone else on the shift. Do not reach for it to "fix" a shift you just created.
- **Editing or deleting a recurring series.** MCP cannot. A wrong series has to be corrected
  in the app, which is the other reason Step 6 is not optional.

"Sarah called in sick tomorrow" is not this skill. It could mean cancel (the
`shiftcare-cancel-shift` skill), reassign, or create a replacement shift. Ask which, and only
continue here if the answer is "create".

## Errors

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| Write tools missing or refused | Allow Write Actions off, or user is not an Admin | An Admin enables it in AI Settings; stop until then |
| `Feature not enabled` | That endpoint is not enabled for the account | For `list_account_locations`, continue without a location. For the create tools, stop — the v3 shift create endpoint has to be enabled for the account |
| `Missing required arguments: from_date, to_date` | `list_shifts` always needs both, as `YYYY-MM-DD` | Supply a whole-day range |
| Shift created at the wrong hour | Offset omitted, or taken from the wrong side of a DST change | Read the offset from a shift near the target date (Step 2), and check the stored time in Step 7 |
| Shift type rejected | A `type_string` that is not configured on this account | Re-read `list_shift_types` and ask the user to choose a listed name |
| Recurring create rejected | Missing `recurrence_end_date`, `client_ids`, or `staff_ids` | Ask for the missing piece; none of them have a safe default |
