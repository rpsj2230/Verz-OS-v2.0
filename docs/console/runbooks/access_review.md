# Access review

The recertification round: each department's admin confirms or removes what their people hold. The screen an auditor asks for and the one nobody builds until then.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `access_review` |
| Title | Access review |
| Group | `govern` |
| Tool | `console.access_review` |
| Needs | `approve:grant` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

The recertification round: every grant you may decide on, each kept or removed (`govern.recertifiable`, `certify`, `apply_round`). Removal deletes that exact capability; nothing is ever added to take access away.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.access_review` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `approve:grant` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

A grant appears only when it sits inside your `approve:grant` reach and you could have granted that capability in that scope yourself (`govern.may_certify`).

## When it is empty or refuses

A grant you may not decide on is absent, with no count. Deciding on your own grant is refused with `GovernError`; that check covers grants to a person and not grants to a team. Expired grants can appear in a round, and removing them is correct.

## When it shows an alarm

Every row is a decision waiting. When unsure, remove: it is the safe direction, and the person can ask for the grant again. If you are refused on your own grant, another administrator decides it.
