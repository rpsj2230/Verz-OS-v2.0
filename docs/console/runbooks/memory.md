# Memory

What the system remembers about a person or a department, and every change to it.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `memory` |
| Title | Memory |
| Group | `govern` |
| Tool | `console.memory` |
| Needs | `read:memory` |
| Console plane | `read:console.content` |
| Narrowed by | `department, person, agent` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What the system remembers about one person or department, curated and extracted, and every revision to it (`govern_estate.subject_memory`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.memory` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:memory` and `read:console.content`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

It shows remembered content, so it needs the content plane, and each memory is shown only if you may recall it.

## When it is empty or refuses

A memory you may not recall is absent with no note. A revision whose earlier version you may not read shows no difference. Asking with no subject is refused.

## When it shows an alarm

A revision marked superseded or demoted is a correction worth reading. Extracted memories fade; curated ones stay until contradicted.
