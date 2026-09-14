# Queue and automations

What is waiting, what is scheduled, what failed and what is being retried.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `queue` |
| Title | Queue and automations |
| Group | `operate` |
| Tool | `console.queue` |
| Needs | `read:queue` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

What is waiting and what went wrong: jobs in `JobState.QUEUED` summarised by task, with how many are retrying and the oldest still waiting (`QueueSummary`); the automations you may see, with their run history; and dead letters, the jobs that gave up.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.queue` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:queue` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

The summary's basis comes from `operate.queue_basis` and automations from `agent_automations.may_see`. Dead letters need `read:job.dead_letter` as well, so holding `read:queue` alone never shows one.

## When it is empty or refuses

An empty summary (no tasks, nothing retrying, no oldest time) is the same whether the queue is empty or nothing in it is visible to you. An automation you may not see has a history with no runs and no next run, which reads the same as one that is paused and has never run. `agent_automations.failure_pause` produces nothing until an automation has failed `FAILURES_BEFORE_PAUSE` times in a row.

## When it shows an alarm

An old oldest-waiting time is a stuck queue: check the worker is running, then the stop screen. A paused automation carries a notice to its owner saying it paused after a run of failures and that nothing it does is happening until somebody resumes it; resuming needs an approver who is not the principal it runs as. For a dead letter, `ATTEMPTS_EXHAUSTED` means look at the task, `TIMED_OUT_EVERY_ATTEMPT` means look at what it waits on or its deadline, and `RE_DRIVEN_TOO_OFTEN` means look at the host or the size of the job. A dead letter older than `DEAD_LETTER_ACTIONABLE_DAYS` is past acting on and is counted apart. The halt a failure pause declares is on an axis nothing enforces yet, which `automation_gaps` reports, so a paused automation is stopped by its schedule rather than by that halt.
