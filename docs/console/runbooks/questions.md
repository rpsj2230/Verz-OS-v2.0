# Questions and gaps

What people asked and what the system could not answer. The gaps are the roadmap.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `questions` |
| Title | Questions and gaps |
| Group | `report` |
| Tool | `console.questions` |
| Needs | `read:question` |
| Console plane | `read:console.existence` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What people asked, without the answers, and the gaps: areas nothing is connected to, most asked about first (`Gap`). The gaps are the roadmap.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.questions` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:question` and `read:console.existence`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Without `read:question` in scope you see only your own questions.

## When it is empty or refuses

Seeing only your own questions looks the same as there being no others. A gap counts only questions that failed because nothing was connected; nothing found, not entitled and refused are never counted, so a missing gap is not evidence people were answered. A gap carries no question text.

## When it shows an alarm

A gap asked about often is a source worth connecting for that area. Take it to whoever owns that system.
