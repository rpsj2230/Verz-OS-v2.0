# People and grants

Everybody the system knows, what each of them may reach, and where that came from. The page the owner asked for so nobody has to open Keycloak.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `people` |
| Title | People and grants |
| Group | `govern` |
| Tool | `console.people` |
| Needs | `read:grant` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, auditor` |
| Can be opened today | `no` |

## What it is for

Everybody the grants name, a person or a team, and the capabilities each holds (`govern.people`, `PersonRow`), so nobody has to open the identity provider to answer who may do what.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.people` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:grant` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Rows are the grants inside your `read:grant` scope. The capability names on each row are shown only if you may also open the Capabilities screen (`govern.may_name_capabilities`).

## When it is empty or refuses

An expired grant is left out rather than flagged. A grant outside your scope is absent. An empty capability list means either you may not open the Capabilities screen or the person holds nothing, deliberately without saying which. A team is listed as the team, not expanded into its members. Nothing raises.

## When it shows an alarm

Nothing on this screen is computed as an alarm. A grant left behind by somebody's move between departments looks like any other row: remove it through an access review round. A grant somebody made to themselves is raised on the Activity screen.
