---
name: staff-compliance-check
description: Sweep staff credentials and certifications in ShiftCare and report what has expired, is expiring, is missing, or is unverified — for one staff member or a whole account. Optionally checks against an advisory NDIS or Australian aged-care worker checklist. Use when the user asks about compliance, expiring certifications, police checks, worker screening, audit readiness, or staff documents.
license: Apache-2.0
metadata:
  author: shiftcare
  version: "1.0.0"
---

# Check staff compliance

Read a ShiftCare account's staff credentials and report the gaps. Two things this skill does, and the difference matters:

1. **Facts from the account.** What each staff member holds, what has expired, what expires soon, what is unverified, and what the account's own mandatory qualifications require. This is exact.
2. **Advisory framework checklists.** General NDIS or Australian aged-care worker requirement lists, matched against the account's own qualification names. These are guidance, not a compliance determination.

**Never state or imply that the account, or any staff member, *is* compliant.** Report what the records show and what a framework checklist suggests reviewing. Compliance is a determination the provider and its regulator make, not one this skill can make.

This skill is read-only. It never creates, updates, or deletes anything.

## Preflight — stop if this fails

Run before any other tool call. If any step fails, stop and tell the user what is missing. Do not substitute another tool, and do not guess at data you could not read.

1. Call `whoami`. Find the account the user means. Read `mcp_available`. If it is `false`, report `mcp_unavailable_reason` and stop.
2. Confirm these tools are available: `list_staff`, `list_staff_qualifications`, `list_qualifications`, `list_qualification_categories`. Any one missing means this account cannot be swept — say so and stop.
3. `list_staff_files` is needed only for a single-staff review. If it is absent, continue without document evidence and say the report omits it.

A partial sweep reported as a full one is worse than no sweep. If pagination breaks, a call fails, or you had to skip staff, name the staff you skipped in the output.

## Step 1 — ask two questions first

Ask both before reading anything. Never infer either one.

**Scope.** One staff member, or the whole account?

**Framework.** Offer exactly these:

| Choice | What it adds |
| --- | --- |
| Expiry check (default) | Nothing external. Checks the account's own configured qualifications for expiry, verification, and the account's own mandatory requirements. Fully exact. |
| NDIS worker check | Adds the advisory NDIS checklist in `references/ndis-worker-requirements.md`. Australia. Covers Supported Independent Living, which is an NDIS support. |
| Aged-care worker check | Adds the advisory checklist in `references/aged-care-worker-requirements.md`. Australia, home care and community aged care — Support at Home, Home Care Packages, and the Commonwealth Home Support Programme. |

An account running both SIL and home care needs both checks, and each staff member reported against the framework matching the work they do. Offer that rather than forcing one choice. The two frameworks also overlap on screening: a current NDIS Worker Screening Check can stand in for an aged-care police certificate, so do not report the same worker as missing both.

Do not offer a framework check based on the account's region, name, or client mix. The user chooses. If the user asks "are we NDIS compliant?", still ask them to confirm the NDIS check is what they want, then answer with the caveats in the reference file rather than a verdict.

**Expiry window.** Default 90 days. State the number in the output every time. Accept an override between 7 and 365 days ("check with a 30-day window"). The account's own configured window may differ from 90 days and is not readable through the MCP server, so never claim the number you used is the account's setting.

## Step 2 — load the account's catalog

Two calls, once per sweep, whatever the scope:

- `list_qualifications` — the whole catalog in one call. Each entry carries `id`, `name`, `category_id`, and three flags that drive the report:
  - `require_for_all_carers: true` — the account's **own** mandatory list. A staff member with no record for one of these has a real, exact gap. This works with no framework selected.
  - `require_document: true` — a record with no `document_id` is not audit-ready, whatever its expiry says.
  - `require_expiry: true` — a record with no `expires_at` is incomplete.
- `list_qualification_categories` with `include_metadata=true` and `per_page=50` — category names for grouping the output.

`list_staff_qualifications` returns `qualification_id` but no name. Build the id-to-name map from the catalog and use names in every line of output. Never show a bare qualification ID to the user.

## Step 3 — sweep

**Single staff member.** Resolve the person with `list_staff` (`filter_by_name`), confirm you have the right person by name before proceeding, then call `list_staff_qualifications` with their `staff_id`. Also call `list_staff_files` with their `user_id` for document evidence.

**Whole account.** `list_staff` caps at 20 per page and has no active-only filter.

1. Call `list_staff` with `per_page=20`, page 1. Read `_metadata.total_count` and `total_pages`.
2. **Cost guard.** Each staff member costs one further call — `list_staff_qualifications` takes a single `staff_id` and has no account-wide form. Before sweeping more than about 25 staff, tell the user the number of calls it will take and offer to narrow the scope by name or role first. Wait for their answer. A 300-staff account is roughly 315 calls and a large amount of token spend.
3. Page through every page. Keep staff whose `onboarding_status` is `active`; there is no server-side filter for this. Say how many you excluded as inactive.
4. Per staff member, call `list_staff_qualifications`.

Do not sweep `list_staff_files` account-wide. Every document row carries a long signed file URL, so an account-wide document listing costs far more tokens than it returns in value, and rows with `user_id: null` are account-level documents that belong to no staff member. Never echo a file URL into the output; they are temporary and unreadable to the user.

## Step 4 — work out each status

Per qualification record, in this order. The first match wins.

1. **Requires attachment** — the qualification has `require_document: true` and the record has no `document_id`. An expiry date on a record with no document attached does not mean anything, so this takes precedence over the dates.
2. **Expired** — `expires_at` date is before today.
3. **Expiring soon** — `expires_at` is today or later and within the window.
4. **Unverified** — `verified_at` is null.
5. **Valid** — everything else. A record with no `expires_at` is valid but flag it separately if the qualification has `require_expiry: true`.

**One staff member can hold several records for the same qualification.** Collapse them to the best status, in this order: valid, no expiry, expiring soon, requires attachment, unverified, expired. A renewal supersedes the certificate it replaced, so one valid record makes that qualification valid even when an expired record for it still exists.

**Missing** is a separate bucket, computed against a requirement list rather than a record:

- Always: every qualification with `require_for_all_carers: true` that the staff member has no record for.
- Framework mode: every checklist requirement with no matching qualification in the account's catalog, or with a matching qualification the staff member holds no record for.

Compare dates as calendar dates in the account's time zone. `expires_at` and `verified_at` come back as UTC timestamps; converting a UTC timestamp against a local date without conversion moves credentials in and out of the expired bucket at the day boundary.

## Step 5 — matching a framework checklist to the account

The product has no built-in industry checklists — qualification categories and names are free-form per account. So the checklist lives in this skill and has to be matched to whatever the account happens to call things.

1. Read the reference file for the chosen framework. Each requirement lists match terms.
2. For each requirement, find the account qualifications whose name or category contains one of those terms, case-insensitively.
3. **Show the user the mapping once, before reporting.** List each requirement with the account qualification you matched it to, and every requirement you could not match. Ask them to correct it. Reuse the corrected mapping for the rest of the conversation, and do not re-ask.
4. An unmatched requirement is not automatically a gap. It may be tracked outside ShiftCare. Report it as "not tracked in this account" and let the user decide, rather than as a failure.

**Role scoping.** Framework requirements split into ones every worker holds and ones that apply only to staff delivering direct client support. `list_staff` returns `role` and sometimes `job_title`. Use `job_title` when it is set, otherwise `role`. Do not report an office administrator as missing First Aid. Say in the output which staff you treated as frontline and which as office, so a wrong call is visible and correctable.

**Conditional requirements.** Some requirements apply only when a trigger is true — transporting participants, supporting anyone under 18, assisting with medication. ShiftCare does not track those triggers. Report each conditional requirement as a check the user makes: "Applies only if you transport participants — confirm this applies to your service." Never present a conditional requirement as an unmet obligation.

## Step 6 — report

Worst first. Lead with the counts, then the detail.

```text
Staff compliance — expiry check, 90-day window
28 active staff (3 inactive excluded)

Expired               4
Expiring within 90d   7
Requires attachment   2
Missing (mandatory)   5
Unverified           11

Expired
  Jordan Ellis    First Aid Certificate       expired 12 Aug 2026
  Sam Whitfield   Police Check                expired 3 Sep 2026
...
```

Rules for the output:

- Names, not IDs. Qualification names, not qualification IDs.
- Every date as a calendar date the user recognises, plus how many days for anything expiring.
- State the window you used, and that it may not match the account's own configured window.
- State the framework and its caveat when one was chosen, quoting the reference file's caveat rather than paraphrasing it.
- Name every staff member you skipped, excluded, or could not read.
- No compliance verdict. No score. No "you're audit-ready".
- Offer the detail per staff member on request instead of dumping every record for a large account.

## Fixing what the report finds

This skill does not write. When the user wants to record a renewal, verify a credential, or upload a document, tell them where it lives in ShiftCare — the staff member's profile, under their qualifications — and stop there. Do not call a write tool from this skill even when the account allows writes and the user asks. See the [ShiftCare help centre](https://help.shiftcare.com) for the current steps.

## What this skill cannot see

Say so plainly when it matters, rather than reporting a gap that is not one:

- The account's own expiring-soon threshold. Not readable here.
- Whether a document actually says what its qualification record claims. Only that a document is attached.
- Worker screening records held outside the qualifications list.
- Any credential the account has not configured as a qualification. If a provider tracks police checks in a spreadsheet, this skill cannot see them and must not report them as missing without saying that is why.
