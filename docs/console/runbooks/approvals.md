# Approvals

What is waiting on a human: an action above its rung, a grant, a promotion.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `approvals` |
| Title | Approvals |
| Group | `govern` |
| Tool | `console.approvals` |
| Needs | `approve:action` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, approver` |
| Can be opened today | `no` |

## What it is for

What is waiting on a person, in three sections: an action above an agent's rung, a grant, and a promotion (`govern_surfaces.approval_sections`). Each card shows what is proposed, who it runs as, when it was raised and when it lapses.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.approvals` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `approve:action` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Opening the screen needs `approve:action`, and each section then uses its own authority: an action needs the tool's capability in a scope matching the action's record; a grant needs you to be able to grant it without outliving your own access; a promotion needs you not to be its proposer.

## When it is empty or refuses

A section with nothing in it is left out. A card out of your reach, one already decided and one that has lapsed all look the same. The route that lists approvals exists and answers identically for a card out of reach and one that does not exist, but no decision can be sent and nothing stores a suspension yet, so the list cannot be served today.

## When it shows an alarm

Anything waiting. Items about to lapse are listed by `expiring_within`, and a lapsed item drops off without notice, so decide before then. A high rate of take-overs means agents are set up wrongly, not that people are slow.
