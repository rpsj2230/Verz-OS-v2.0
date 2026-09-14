# Models and providers

Which model answers which lane, which provider is degraded, and what fell back.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `models` |
| Title | Models and providers |
| Group | `operate` |
| Tool | `console.models` |
| Needs | `read:model_route` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

Every rung of every model chain in order, from `brain.console.model_matrix.matrix`: the tier, its position, the model, deployment and provider, the breaker state and why it opened, how many live requests it has seen and failed, and its last probe.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.models` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:model_route` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

All or nothing. The matrix is not narrowed by department, and without `read:model_route` it comes back empty rather than refused.

## When it is empty or refuses

Empty means you do not hold `read:model_route`. A deployment nothing has recorded health for shows as `CLOSED`, which means nothing has failed against it, not that its state is unknown. `ModelMatrixError` means whatever recorded the health figures recorded something impossible, such as more failures than requests.

## When it shows an alarm

A non-empty `exhausted_tiers` is the one thing here worth an alert: every rung of that tier is open and its lane has nowhere to fall back to. Check the providers named, then the matrix configuration. One `OPEN` rung on its own is the chain doing its job. The reasons are `CONSECUTIVE_LIVE_FAILURES`, `LIVE_FAIL_RATIO` and `PROBE_FAILURES_WHILE_IDLE`, the last meaning the outage began before anybody asked anything. `OPEN` with no reason means the evidence for it has aged out.
