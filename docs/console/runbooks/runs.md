# Live runs

What is executing right now, with its lane, its agent and how long it has been going. Configuration and not content: the question, not the answer.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `runs` |
| Title | Live runs |
| Group | `operate` |
| Tool | `console.runs` |
| Needs | `read:run` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent, connector` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What is executing right now: every job in `JobState.RUNNING` or `JobState.CANCELLING`, as a `RunRow` with its job id, task, the person it runs for, its state, its attempts and since when. It shows the work and never its arguments, because an argument names a record you may hold nothing over.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.runs` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:run` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Rows are decided by `operate.may_watch`: your own jobs always, and somebody else's when your `read:run` scope matches the job's task, traffic class, state and principal.

## When it is empty or refuses

An empty list means nothing is running that you may watch, and it is deliberately the same as the jobs you cannot see never having been queued. Nothing on this screen raises. The registry says the screen shows each run's lane and agent and can be narrowed by agent and connector; `RunRow` carries none of those fields yet, so those filters narrow nothing today.

## When it shows an alarm

`CANCELLING` means a cancel was asked for and the worker has not acknowledged it. A cancellation is a request rather than an undo, and it ends as aborted, succeeded or failed, so wait for that rather than cancelling again. A run whose start is long past is long-running; nothing sets a threshold, so compare with what that task normally takes and look at the queue screen for retries.
