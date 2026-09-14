# Budget and spend

What each department and person may spend, what they have spent, and what happens when they reach it. A limit rather than a report, which is why it is not usage.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `budget` |
| Title | Budget and spend |
| Group | `report` |
| Tool | `console.budget` |
| Needs | `read:budget` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What each department and person may spend, what they have spent, and what happens when they reach it: the ladder `LADDER` of a cheaper tier, no fan-out, queueing, and refusal. Also every stop currently in force.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.budget` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:budget` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

The ceilings need `read:budget` in a matching scope. The spend figures beside them come from `spend_view` and need `read:usage`. Everybody is told about their own allowance.

## When it is empty or refuses

A ceiling outside your reach is absent. A refusal carries no amount, on purpose. Cost per answer is refused when too few rows are visible to make a distribution, and that refusal is the same for an empty ledger and for nothing visible to you.

## When it shows an alarm

A stop in `budget_stops` means a department is stopped for money, not for permission: tell them so, then raise the allowance or leave it deliberately. Pace ahead means spending faster than the period allows. A cost review not yet long enough is not yet to be trusted.
