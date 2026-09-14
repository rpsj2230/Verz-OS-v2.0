# Access friction

Where people are repeatedly hitting a boundary, by shape and never by name. Either somebody is under-granted or somebody is probing, and both look like this.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `access_friction` |
| Title | Access friction |
| Group | `govern` |
| Tool | `console.access_friction` |
| Needs | `read:denial_pattern` |
| Console plane | `read:console.existence` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, auditor` |
| Can be opened today | `no` |

## What it is for

Where people keep hitting a boundary, by the shape of it and never by the capability or the record (`FrictionRow`). Either somebody is under-granted or somebody is probing, and both look like this.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.access_friction` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:denial_pattern` and `read:console.existence`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Your own denials are never shown to you, and each pattern is shown only inside your reach.

## When it is empty or refuses

Ordinary denials are not listed at all, so an empty screen means nothing has crossed a threshold rather than nobody was refused.

## When it shows an alarm

`ACCESS_NEEDED` means somebody looks like they are missing a grant: find which on the Activity screen and decide. `ENUMERATION` means somebody is reaching across many different things: every attempt was already refused, so understand it before granting anything. The thresholds are `DENIALS_WORTH_NOTICING` and `ENUMERATION_DISTINCT_TARGETS`.
