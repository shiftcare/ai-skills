---
name: onboarding-check
description: Check whether a ShiftCare account is set up properly and report a setup scorecard with the next step for each gap. Covers clients, staff, pay groups, pay items, first shift, qualifications, shift types, locations, and teams. Use when the user is new to ShiftCare, asks "is my account set up", "what is left to set up", or wants an onboarding checklist. Read-only.
license: Apache-2.0
metadata:
  author: shiftcare
  version: "1.0.0"
---

# ShiftCare onboarding check

A read-only setup scorecard for a ShiftCare account. It follows the same order as the
[Quick Start Guide](https://help.shiftcare.com/en/articles/4293063-quick-start-guide):
staff and clients first, then pay, then the first shift. Every check uses a listing tool
and works for read-only users. This skill never calls a write tool.

## Before you start

1. The agent must already be connected to the ShiftCare MCP server. If tools are missing,
   use the `shiftcare-mcp` skill first.
2. Call `whoami` (or `list_accounts`). Note the `account_id` and the signed-in person's
   name. If the user belongs to more than one account, ask which one to check.
3. Tell the user this is read-only and takes roughly ten tool calls.

## How to check

Run each row below. You only need to learn one of three things per row: **nothing there**,
**only the defaults ShiftCare created at sign-up**, or **real data**. So request the
largest `per_page` the tool allows and stop paging as soon as you have found one real
record. Never list every record back to the user; count them and name at most three.

New accounts are created with a pay group called **Default Casual** holding four pay items
(**Weekdays - Mon Tue Wed Thu Fri**, **Saturday**, **Sunday**, **Public Holidays**) and a
price book called **Demo Price Book**. Anything else was added by a person.

| # | Setup item | Tool | Done when | Still default when |
| --- | --- | --- | --- | --- |
| 1 | Clients added | `list_clients` | At least one client | No clients, or every name looks like sample data (contains "Sample", "Demo", or "Test") |
| 2 | Staff added | `list_staff` | At least one staff member other than the signed-in person, ideally with a carer `role` | Only the signed-in person |
| 3 | Pay groups | `list_pay_groups` | Any pay group other than **Default Casual**, or the user confirms Default Casual is what they use | Exactly one group named **Default Casual** |
| 4 | Pay items | `list_pay_items` | Any pay item whose `name` is not one of the four seeded names, or any item on a second pay group | Only the four seeded names under Default Casual |
| 5 | First shift | `list_shifts` with `from_date` 90 days ago and `to_date` 90 days ahead, `per_page` 1 | Any shift returned | No shifts |
| 6 | Qualifications defined | `list_qualification_categories`, then `list_qualifications` | At least one qualification | None |
| 7 | Credentials recorded | `list_staff_qualifications` for up to three carers from step 2 | At least one credential on any checked carer | None recorded (skip if step 6 found nothing) |
| 8 | Shift types | `list_shift_types` | At least one shift type | None |
| 9 | Locations (optional) | `list_account_locations` | Any location | None; fine to leave empty |
| 10 | Teams (optional) | `list_teams` | Any team | None; fine to leave empty |

Sample data is not flagged by the API, so row 1 is a heuristic. If the client names look
invented, ask the user "Are these real clients, or sample data?" rather than deciding for
them.

If a tool returns an error or "not found", report that row as **Cannot check**, not as
**Not done**. Some listing tools are enabled per account.

### Not checkable through the API yet

Say so plainly instead of guessing:

- **Price books / client rates.** The only clue is `pricebook_name` on timesheet items,
  which is too weak to score. The Quick Start Guide covers price book setup.
- **Custom forms.**
- **Invoice settings.** See
  [Setting up and customising your invoice settings](https://help.shiftcare.com/en/articles/8491142-setting-up-and-customising-your-invoice-settings).

## Report

Present one table, in the order above, with a status per row: **Done**, **Still default**,
**Not done**, **Optional**, or **Cannot check**. Follow it with a short "Next steps" list
covering only the rows that are not Done, in Quick Start order, each with its help article:

| Setup item | Next step |
| --- | --- |
| Clients | [Adding and Managing Client Profiles](https://help.shiftcare.com/en/articles/13458486-adding-and-managing-client-profiles) |
| Staff | [Add a Carer or Office User to Your Account](https://help.shiftcare.com/en/articles/3022336-add-a-carer-or-office-user-to-your-account) |
| Pay groups and pay items | [Quick Start Guide](https://help.shiftcare.com/en/articles/4293063-quick-start-guide), Pay Groups section |
| First shift | [Create a Shift in the Scheduler/Roster](https://help.shiftcare.com/en/articles/3852009-create-a-shift-in-the-scheduler-roster) |
| Qualifications and shift types | [Customise categories for staff qualifications, client documents, and shift types](https://help.shiftcare.com/en/articles/4920353-customise-categories-or-types-for-staff-or-client-documents-or-shift-types-compliance-report) |
| Credentials on staff | [Managing Staff Documents](https://help.shiftcare.com/en/articles/3022454-managing-staff-documents) |
| Teams | [Teams](https://help.shiftcare.com/en/articles/3022481-teams) |

Example of the tone to use:

> **Clients: Still default.** Two clients, both named like sample data ("Sample Client
> One", "Sample Client Two"). Add your first real client: Adding and Managing Client
> Profiles.

## Offering to fix gaps

The user may ask you to create what is missing. Before agreeing, check `whoami`:
`mcp_writes_enabled` must be `true` and `role` must be `admin`, otherwise explain that an
Admin needs to enable **Allow Write Actions** and point at the help article for the item
instead.

When writes are allowed, treat each fix as a separate task: collect the details, read the
resolved values back to the user (for a shift: client, staff, date, start and end time
with time zone, shift type), and call the write tool only after the user has said yes.
Never batch several writes behind one confirmation.
