# Usage and tokens

Questions asked, tokens in and out, by person, by department, by model and by agent. What was consumed, as against what it is allowed to consume.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `usage` |
| Title | Usage and tokens |
| Group | `report` |
| Tool | `console.usage` |
| Needs | `read:usage` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

Questions asked and tokens in and out, by person, department, model and agent (`usage_view.breakdowns`), with whether machine traffic is included. What was consumed, as against what may be consumed, which is the budget screen.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.usage` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:usage` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Rows are narrowed by your `read:usage` scope on department. The breakdown by agent also needs `read:agent`, and without it that breakdown is left out.

## When it is empty or refuses

Holding nothing gives an empty report rather than a refusal. A missing agent breakdown means no `read:agent`. Machine traffic is excluded unless it says otherwise, your own runs included. `UsageViewError` means a recorded row was malformed or the totals did not add up, which is a recording defect.

## When it shows an alarm

No alarm. Always read whether machine traffic is included before comparing two reports.
