# Sessions

Who is signed in, from when, and the control to end one. A revoked grant does not end a session that is already open, which is why this is separate from people.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `sessions` |
| Title | Sessions |
| Group | `govern` |
| Tool | `console.sessions` |
| Needs | `read:session` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

Who is signed in, since when, and the control to end a session (`govern.open_sessions`, `govern.end_one`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.sessions` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:session` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Listing needs `read:session`. Ending one also needs `approve:grant` in a scope covering the session (`SESSION_CONTROL`).

## When it is empty or refuses

A session that is no longer live is absent rather than shown as expired, and one outside your scope is absent. Ending a session returns nothing alike for a session out of reach, one you may see and not end, and one that is not there.

## When it shows an alarm

Revoking a grant does not close a session that is already open: the person keeps what they reached until the session idles out or reaches its absolute limit. After a revocation that matters, end their session here. For somebody leaving, the leaver path does both.
