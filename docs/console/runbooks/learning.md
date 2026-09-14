# Learning review

What the system has inferred and would like to keep. Tiers separated, and tier one undoable, because a wrong inference kept quietly becomes a fact.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `learning` |
| Title | Learning review |
| Group | `govern` |
| Tool | `console.learning` |
| Needs | `read:learning` |
| Console plane | `read:console.content` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What the system has inferred and would like to keep, in three tiers: corrections that can be undone, inferences with their evidence and whether they are ready to promote, and changes routed to a department's queue. Learning can be frozen and thawed here.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.learning` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:learning` and `read:console.content`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

It shows inferred content, so it needs the content plane. The third tier is shown only when you may see every department.

## When it is empty or refuses

A missing third tier on a narrower basis does not mean nothing is there. With no occurrences an inference is never ready to promote.

## When it shows an alarm

A frozen state means nothing is being learnt. Rows ready to promote are waiting for a person. Thawing needs a stated reason.
