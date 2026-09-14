# Incidents

What is currently degraded, what it blocks, and what has been done about it. Distinct from connector health, which is one component at a time.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `incidents` |
| Title | Incidents |
| Group | `operate` |
| Tool | `console.incidents` |
| Needs | `read:incident` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, connector, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What is degraded and what it stops working (`Incident`: the subject, its state, since when, and what it blocks). What it blocks is read off the degraded connector's own manifest: the tools that source provides.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.incidents` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:incident` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Only incidents on connectors you already reach, from `operate.incidents`, with the blocked tools filtered to what you reach.

## When it is empty or refuses

An incident on a source you do not reach is absent rather than shown with its details hidden. Nothing raises. Only connector incidents appear, because no dependency graph exists between components, and the registry's promise of what has been done about an incident has no field behind it yet.

## When it shows an alarm

Every row is an alarm. A state of down or degraded means the listed tools are not answering; tell the departments that use them, then work the source from the connectors screen. Unconfigured is a setup task rather than an outage.
