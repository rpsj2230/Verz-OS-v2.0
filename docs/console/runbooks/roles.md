# Roles

The six roles, what each one is for, and who holds it. A role governs the platform and never implies a capability, which this screen has to make visible.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `roles` |
| Title | Roles |
| Group | `govern` |
| Tool | `console.roles` |
| Needs | `read:role` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, auditor` |
| Can be opened today | `no` |

## What it is for

The six roles, what each is for, whether it needs a scope, and who holds it (`govern.role_catalogue`, `govern.role_holders`). A role governs the platform and never implies a capability.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.roles` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:role` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

The catalogue is the same for everybody who opens the screen. Holders are narrowed to your scope.

## When it is empty or refuses

A role grant that is no longer active, a deputy appointment past its end for example, is absent rather than greyed out. A holder outside your scope is absent. Nothing raises.

## When it shows an alarm

Nothing here is computed as an alarm. A super administrator who holds no grants sees no data anywhere, and that is the design rather than a fault: give them the grants they need. A deputy appointment ends by itself.
