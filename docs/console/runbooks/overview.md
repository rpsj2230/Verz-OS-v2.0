# Company overview

What the system did today, counted honestly: nothing here is a figure derived from rows the reader may not see.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `overview` |
| Title | Company overview |
| Group | `operate` |
| Tool | `console.overview` |
| Needs | `read:overview` |
| Console plane | `read:console.existence` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

The landing screen: one figure for each Operate and Report panel in `brain.console.operate.PANELS`, each marked with the basis it was counted on, everyone or your own. It holds no rows of its own; each figure belongs to the screen it came from.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.overview` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:overview` and `read:console.existence`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Each figure is decided separately by `operate.tile`. It is counted at everybody's scale only when you could open the screen it came from and count those rows yourself. Otherwise a per-person panel (runs, queue, usage, questions) counts only your own rows, and a panel about the whole install (connectors, models, knowledge coverage, incidents, stop, budget, quality) is not shown at all.

## When it is empty or refuses

A missing figure means either that panel is withheld on your basis or there is no such panel, and the screen deliberately does not say which: `operate.overview` drops a withheld figure with no placeholder. A figure on your own basis counts only your rows, so never compare it with one somebody else reads on the everyone basis. `OperateError` is a wiring defect rather than a state: two figures for one screen, a panel keyed to the landing screen, a row with no `principal_id`, or a negative count. Report it to whoever maintains the install.

## When it shows an alarm

This screen has no alarm of its own. A figure that looks wrong is investigated on the screen it came from, after checking which basis it was counted on. Findings from `operate.operate_gaps` are a defect in the product, not an operational alarm.
