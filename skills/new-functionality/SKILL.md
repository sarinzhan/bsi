---
name: new-functionality
description: Use when a developer asks for a new feature or a change in behaviour ("add…", "customers should be able to…", "create an app that…").
---

# New functionality

Goal: turn a plain request into working, tested, deployed code with one
readable decision record. Follow the steps in order. Do not skip step 2.

## 1. Understand the request

Write down for yourself, in one sentence each:
- **Who** uses it (customer, shop staff, finance, another service)
- **What** they can do after the change that they cannot do now
- **Done when** — how a person would check it works

If one of the three is unclear and you cannot pick a safe default, ask.
Ask at most 3 questions, all at once, each with options when possible.
Never ask about things you can find in the files.

Good question: "Can a paid order be cancelled, or only NEW ones? (only NEW / also PAID with refund)"
Bad question: "Which database should I use?" — you decide that yourself.

## 2. Find where it belongs

Read `platform/system.yaml` and the newest ADRs, then decide:

| Situation | Do |
|---|---|
| An existing project owns this data or behaviour | Change that project |
| It needs data owned by another project | Call its API or use its events. Never read its database |
| Nothing in the system covers it | Create a new project from a template |
| It does not belong to this system at all | Stop and say which system fits better |

Prefer changing one project. Touch several only when the data really lives
in several. Creating a new project is a bigger decision: give the reason in
the ADR.

Call `link_project` for every project you will touch.

## 3. Plan and record the decision

Write `platform/docs/adr/NNNN-<short-title>.md` (next free number):

    # ADR-NNNN: <title the developer would understand>
    Kind: feature | change | infrastructure | fix
    Projects: <names>
    Requested in chat: <chat id>

    ## Context
    <the request in 2–3 sentences, in the developer's words>

    ## Decision
    <what you build: use cases, endpoints, events, tables, new resources>

    ## Why
    <why this way>

    ## Rejected
    <at least one real alternative and why not>

Then call `record_decision` and `report_plan`. Then start immediately —
do not wait for approval.

## 4. Build

- Contracts first: new or changed API or event goes to `platform/contracts/`
  before the code. Changes must be backward compatible (only add fields).
- Follow the code skill of the project (`spring-service` or `react-tool`).
- Every rule from the request gets a test. Name tests after the rule:
  `cancel_is_rejected_when_order_is_paid`.
- Database changes: a new Flyway migration, never edit an old one.
  Old and new code run together during deploy, so do not drop or rename
  columns in the same change.
- Infrastructure only if needed (new database, new topic, new service):
  follow `readable-infra` and `deploy-compose`. Add the ADR number as a
  comment on every service you add.

## 5. Check before you hand over

All must be true:
- [ ] `mvn verify` / `npm run build` green, including ArchUnit
- [ ] each "Done when" from step 1 is covered by a test
- [ ] `docker compose config` has no warnings (if infra changed)
- [ ] no secrets, no `latest` tags, no shell scripts in the change
- [ ] the ADR matches what you actually built (update it if you changed course)

Then the platform validates and deploys. Wait for the health check.

## 6. Tell the developer

3–6 lines, plain words:
- what now works and where to try it (URL or endpoint)
- what you decided and the ADR number
- anything you did NOT do and why (e.g. "paid orders are not cancellable yet")

## Do not

- invent requirements the developer did not ask for
- refactor unrelated code "while you are there"
- change another project's database or internal code
- create a new project when an existing one owns the data
- continue after 3 failed attempts — stop and explain
