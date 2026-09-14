# Activity

Everything that happened: every question, every grant, every export, every halt. Filterable by department and by person like everything else.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `audit` |
| Title | Activity |
| Group | `govern` |
| Tool | `console.audit` |
| Needs | `read:audit` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent, connector, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, auditor` |
| Can be opened today | `no` |

## What it is for

Everything that happened, oldest first, a page at a time: every question, grant, export and halt (`AuditPage`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.audit` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:audit` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

You see entries about yourself, and entries of a kind your `read:audit.<kind>` grant matches on the ledger's own fields. A department-scoped audit grant matches nothing, because the ledger's fields carry no department; department heads read their department's activity through `scoped_authority.department_activity` instead.

## When it is empty or refuses

Holding plain `read:audit` shows only your own entries, which reads like a broken page and is reported by `audit_grant_gaps`. A department you do not head shows an empty page, the same as a department with no activity. A page is between 1 and `MAX_PAGE_SIZE` entries.

## When it shows an alarm

A grant somebody made to themselves raises a notice to a steward who is not them, and if no other standing super administrator exists that is refused: appoint a second. A late membership sync behind a head's grants is marked overdue.
