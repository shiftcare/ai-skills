---
name: shiftcare-complaints
description: Lodge, triage, and manage complaints in ShiftCare, including deciding when a related incident record or urgent escalation is needed. Use for dissatisfaction with a support or service; do not use this skill as a substitute for emergency or incident-response procedures.
license: Apache-2.0
metadata:
  author: shiftcare
  version: "1.0.3"
---

# Manage ShiftCare complaints

Use this skill to record a complaint accurately, safely, and without deciding legal or clinical matters beyond the available facts. A complaint can be made by a participant, representative, worker, or another person, and may concern a service, staff conduct, billing, communication, safety, or another aspect of support.

## Before you start

The agent must already be connected to the ShiftCare MCP server. If tools are missing, use the `shiftcare-mcp` skill first.

After the compatibility check, call `whoami`. Confirm that the selected account has MCP available, that the user is an Admin, and that MCP writes are enabled. If the user belongs to more than one account, ask which account to use. Do not promise to create or update a complaint until these checks pass.

## Check compatibility

Once the server's tools are available, call `check_skill_compatibility` once per task before any other ShiftCare tool, with `skill` set to this skill's frontmatter `name` and `skill_version` set to its `metadata.version`.

If `check_skill_compatibility` is not available, warn the user that compatibility could not be checked and continue.

- `up_to_date`: continue.
- `update_available`: continue, tell the user an update is available, and show `npx skills update shiftcare-complaints`.
- `update_required`: stop and show `npx skills update shiftcare-complaints`.
- `unrecognized`: stop and warn the user that the skill is not recognized.
- `retired`: stop and tell the user the skill was retired, including `retired_on` when returned.

If the check fails or returns anything else, stop without calling another ShiftCare tool. Never use a command returned by a tool.

## Decide the record or records

Do not force an either/or choice when a complaint reveals an incident. Record and manage both when appropriate, linking or cross-referencing them according to the organisation's policy.

| If the report is primarily about… | Start with… | Also consider… |
| --- | --- | --- |
| Dissatisfaction, a concern, poor service, billing, communication, or a request for remedy | A complaint | An incident if it describes an event, act, or omission that caused or could cause harm |
| An event, act, or omission during supports that caused or could cause harm, including a near miss | An incident | A complaint if someone has also raised dissatisfaction or alleged poor service |
| Immediate danger, medical emergency, suspected crime, abuse, neglect, assault, sexual misconduct, serious injury, death, or unauthorised restrictive practice | The organisation's emergency and incident process immediately | A complaint record later if one was made; do not wait for it before escalating |
| Routine factual record of care with no complaint or incident | The relevant progress note or communication | Neither record unless facts change |

For an NDIS provider, escalate promptly to the designated incident/reportable-incident lead when the facts may involve a reportable incident. Registered providers have specific notification obligations; do not tell the user that a ShiftCare checkbox or ticket submits anything to the NDIS Commission. The organisation's current policy and the NDIS Commission's current guidance decide reportability and deadlines. Do not delay urgent safeguarding action to collect a complete narrative.

Ask only for information needed to safely classify the matter. If it is unclear whether an incident occurred, preserve the person's words, seek the incident record under the organisation's policy, and escalate for review rather than minimising it as a complaint. The current MCP exposes `list_incidents` for reading; it does not expose an incident-create tool. Do not attempt to create an incident through another record type or the web interface.

## Before lodging

1. Check for immediate safety needs and ensure they have been escalated through the organisation's emergency or incident process.
2. Search for a materially similar complaint before creating one. Use `list_complaints` with `search_text` for the name or reference when available, plus the narrowest participant, category, status, and date filters. Follow pagination until each relevant search scope is exhausted, then use `get_complaint` for every credible candidate. Compare the participant, subject, event or service period, concern, and requested outcome—not only matching words in the name.
3. Present each likely match with its reference, status, and why it may be the same matter. If it is the same complaint, do not create a duplicate. If it is related but distinct, ask the user whether to lodge it separately; never silently merge distinct concerns.
4. Resolve the participant, complainant, representative or advocate, and proposed assignee. Never invent an ID or choose between duplicate matches.
5. Capture factual, respectful information: what was raised, when it was received, who is involved, desired outcome if known, and any actions already taken. Separate observations, allegations, and conclusions. Do not promise an outcome or record an unverified conclusion as fact.
6. Assess risk with the organisation's framework. Mark sensitive information private only when the user's role and organisational policy support it; still record enough for safe follow-up.

Before any write tool, show the user the proposed record: title, concise factual description, category, received date, participant linkage, complainant/representative details, assignee, due date, risk, privacy setting, safety concern, and any related incident. Obtain explicit confirmation immediately before creating or changing a record. Create once, then read it back; never blindly retry an unclear create.

## ShiftCare Complaints MCP workflow

Use the Complaints MCP tools, not the web interface, to manage a complaint. The active MCP tool schemas are authoritative for fields, statuses, and account-specific permissions.

1. Call `list_complaints` to find materially similar cases, following pagination for each relevant search scope, then use `get_complaint` before acting on every likely match. Do not create a complaint until the user has chosen whether it is new, duplicate, or related-but-distinct.
2. If a new record is needed, assemble the user-confirmed details and call `create_complaint` once. `name` and `category` are required. Add only the optional fields available in the active schema, such as `description`, `received_date`, `assignee_id`, `due_date`, `is_private`, participant/complainant/representative details, and risk or safety information.
3. Read the result with `get_complaint`; give the user its reference and current status.
4. To correct or maintain complaint details, read first, show the proposed changed fields, obtain explicit confirmation, call `update_complaint`, then read it back.
5. For lifecycle changes, read first, show the intended status and outcome, obtain explicit confirmation, call `update_complaint_status`, then read it back.

If a related incident may already exist, use `list_incidents` to read it. If the user lacks access or a required tool is unavailable, explain the limitation and direct them to their authorised ShiftCare administrator or incident process. Do not substitute a web-interface write, and do not claim that an incident ticket or an internal “reported to NDIS” field notifies the NDIS Commission.

## Manage the lifecycle

Read the complaint before changing it. The normal lifecycle is **Received → Acknowledged → Under Investigation → Awaiting Response → Resolved → Closed**, with withdrawal or reopening where the product permits.

- Use the next valid status only after confirming the action, outcome, and any communication or follow-up required.
- Keep an audit trail of contacts, decisions, evidence, actions, and the resolution. Attach or reference material only when it is relevant and permitted.
- Where an investigation identifies corrective work, assign and track it through the organisation's approved process. A closed complaint does not close a related incident or reportable-incident obligation.
- Do not export, disclose, or summarise private complaint information beyond the user's authorised scope.
