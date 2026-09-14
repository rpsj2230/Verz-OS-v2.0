# Rate limits

The ceilings on requests and what is currently being throttled by them.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `limits` |
| Title | Rate limits |
| Group | `install` |
| Tool | `console.limits` |
| Needs | `read:rate_limit` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent, period` |
| Offered to a department admin | `no` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

Who is being throttled right now, by which limit, and how long they must wait (`installation.throttled_now`, `ThrottleRow`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.limits` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:rate_limit` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is not offered it in their menu, for the reason recorded against it in the screen registry, and anybody holding the capability still reaches it by its address.

Rows are narrowed by your `read:rate_limit` scope on a limit's scope and subject. A rate limit's subject is a person, a channel, an agent, a connector or a widget origin, and never a department, so a department-scoped grant matches no row at all.

## When it is empty or refuses

An empty list means nobody is over a limit, or you hold no grant, or your grant is department-scoped and so matches nothing. That last case is why a department admin is not offered this screen: the list would be a directory of who is busy across the whole company. It will be offered once a limit carries its subject's department.

## When it shows an alarm

Every row is somebody refused for the number of seconds shown, the longest wait across every limit they are over. Repeated refusals back off further, up to `MAX_BACKOFF_SECONDS`, and refused requests do not extend the window. If one subject is always here, the ceiling is wrong for them or something is looping.
