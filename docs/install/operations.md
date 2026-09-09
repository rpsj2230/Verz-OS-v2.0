# Backup, monitoring, logging and health checks

**Read this section first, before the rest of the page.** Thirteen mechanisms in this system
are meant to run on a schedule. Eleven of them have no caller of any kind: the code is written,
it is tested, and nothing anywhere invokes it. That includes the one that takes a backup, the
one that measures how long you have gone without a copy, and the one that proves a copy can be
restored. A twelfth has a caller and no schedule, which is one link of a chain rather than the
chain, and the table below says so per mechanism rather than in a count.

So this page is in two halves. What answers today, which is the health checks and the audit
ledger. And what is written down and switched off, which is nearly everything else.

You are not being handed a monitored system. You are being handed a system with the monitoring
built and not wired, and told which pieces those are, by name, in a table the code checks.

## Health checks, which do work

Two endpoints, and the difference between them is the whole of what a health check is for.

`/health/live` says the process is running. It says nothing about whether the system can answer
anything.

`/health/ready` says every dependency is reachable. It returns 503 when one is not, and it
carries a per-dependency breakdown so a failure names what is unreachable rather than reporting
a colour. Both endpoints report the commit the running image was built from, so "what is
actually live" is answerable without guessing.

**Point your deployment tool and your uptime monitor at `/health/ready`, not at
`/health/live`.** A container that is up but cannot reach its database still answers questions,
from whatever it can still reach, which is how a system starts giving wrong answers while
appearing healthy. Liveness is the check that lets that happen.

Every container in this deployment declares its own health check, and one-shot helpers declare
none because a one-shot is ready when it has exited. `brain.deployment.installer.health_report`
prints, per profile, which services have one and what "ready" means for each component that
does not.

## What "ready" means, per component

Every component in this system is required to carry a sentence saying what ready means for it,
in words, before it can be declared at all. That is not decoration: a component whose readiness
nobody wrote down gets whatever check the person wiring it up invents, which is almost always a
TCP connect, and a TCP connect proves a socket is listening. That is liveness wearing
readiness' clothes.

Some of them are worth knowing before you build a dashboard:

- The inference server is ready when **every** model it serves answers a probe of its own. One
  loaded out of three refuses two thirds of what it is asked while presenting a listening
  socket.
- The identity provider is ready when its own health endpoint answers, which is true only once
  the realm has been imported.
- The object store is ready when its gateway lists a known bucket, not when its port opens.
- A worker is ready when its queue driver has fetched at least once and the database is
  reachable.

## Logging

**The audit ledger is not optional and is not a log.** It records who read what, it is
append-only, it is hash-chained, and its retention never expires. Every profile writes to it,
including the smallest.

**Traces are optional and only `full` has anywhere to put them.** A trace is the step-by-step
record an operator reads to explain how one answer was assembled. It is a diagnostic aid rather
than an obligation, and the trace ledger is four containers and about two gigabytes.

This distinction catches people out during an incident on a `lite` install, so it is worth
stating in advance: **`lite` is not "logging off"**. What `lite` gives up is the trace, not the
record of who saw what.

**Do not set a trace destination on a profile that runs no trace ledger.** Startup refuses it,
deliberately, and the reason is worth knowing because the failure it prevents is silent in both
directions: a refused span is retried and dropped inside the client library, and an accepted one
means your traces are sitting on a host chosen by whoever last copied an environment file. The
same rule and a heavier version of it apply to `BRAIN_INFERENCE_URL`: a trace host receives
metadata about a request, and that address receives the text of the document itself.

## Backups, and the honest position

The schedule is written down and nothing runs it.

| What is covered | How | How often |
| --- | --- | --- |
| The database | continuous write-ahead archiving | every 60 seconds |
| The database | incremental | daily |
| The database | full | weekly |
| The object store | content-addressed snapshot | hourly |
| Configuration | snapshot | hourly |

The intervals are argued rather than round numbers. A write-ahead segment is archived every
minute whether or not it is full, so a quiet database does not accumulate an hour of exposure
waiting for a segment to fill. A daily incremental bounds how many segments a restore has to
replay, which is the difference between a recovery time in minutes and one in hours. A weekly
full bounds the incremental chain, and a chain with no full at the bottom is a set of copies
that restores nothing. Configuration is hourly because it changes rarely and matters entirely:
an install restored with last month's realm and policies is a different install.

**The worst gap on that schedule is one hour**, which is what the object store and the
configuration snapshots set.

### What the recovery figures mean, and what you should sign

Each profile carries a recovery point (how much work you can lose) and a recovery time (how
long you are down).

| Profile | Recovery point | Recovery time |
| --- | --- | --- |
| `lite` | 24 hours | 8 hours |
| `standard` | 4 hours | 4 hours |
| `full` | 1 hour | 2 hours |

**A recovery time nobody has measured is a guess in a contract.** This system will refuse to
render a service level statement that promises a recovery point the schedule cannot deliver,
one that no drill has ever measured, or one that the last drill exceeded. All three are
promises somebody signs and only the first is visible to anybody reading the schedule.

No drill has ever run here. So none of those figures has been verified against a real restore,
and the statement generator refuses accordingly. Do not sign one until it does not.

### A backup nobody has restored is a file

This is the sharpest thing on the page. The vocabulary in this system distinguishes a backup
that exists from a backup that has been restored, and only the second one counts, because the
first is a file whose contents nobody has ever read back.

There is a deliberate rule in the code that nothing under `src/brain` may be named "restore"
except the one function that answers "when was a restore last verified". A console field
labelled "last verified restore" beside a backup timestamp is the field somebody checks before
deciding not to worry, and the rule exists so that the day somebody builds a restore is the day
that screen gets written.

## Eleven of the thirteen mechanisms are started by nothing

Named individually, because "monitoring is not wired" is a sentence somebody skims. The last
column is the registry's own word for what starts each one, and this table is checked against
that registry in both directions: a mechanism this install carries and the table does not name
fails a test, and so does a row whose last column disagrees with the code.

That check exists because this section was wrong. It read "the twelve mechanisms nothing runs"
on the morning of 2026-09-09 and eleven was already true, because one had acquired a caller and
the heading, the table and the count were three hand-kept copies of a fact the code holds.

<!-- checked: every scheduled mechanism and whether anything starts it -->

| Mechanism | What it would guard | Started by |
| --- | --- | --- |
| `retention_sweep` | that nothing is kept past the window its data class was given | `nothing` |
| `canary_run` | that the gate still refuses today what it refused yesterday | `nothing` |
| `restore_drill` | that the copies being taken can actually be restored | `nothing` |
| `backup_exposure` | that a stretch of work with no copy anywhere is noticed while it is still short | `nothing` |
| `denial_digest` | that a colleague who keeps being told there is nothing there is noticed by somebody who can fix it | `nothing` |
| `directory_sync` | that the roster follows employment: joiners, movers and leavers | `nothing` |
| `knowledge_reverification` | that an answer drawn from something somebody once approved is not still being given long afterwards | `nothing` |
| `resolution_calibration` | that the weights deciding whether two records are the same person stay fitted to the data | `nothing` |
| `queue_redrive` | that a job whose worker died underneath it is reclaimed rather than left | `nothing` |
| `side_effect_resume` | that a side effect issued by a process which then died is read back from the source before anything is retried | `nothing` |
| `audit_anchor` | that entries removed from the end of the audit ledger are detectable rather than silent | `on_a_route` |
| `model_health_probes` | that a provider which has stopped answering is found by asking it rather than by a person's question failing | `nothing` |
| `spend_correction` | that the cost estimator every budget decision is taken against stays anchored to what actually ran | `in_process` |

Three words appear in that last column and they are not degrees of the same thing. `nothing`
means no call site of any kind. `in_process` means another module calls it and says nothing
about whether *that* module is ever reached, which for `spend_correction` today means a console
screen nobody opens on a schedule. `on_a_route` is the only one that runs: an external timer
calls an HTTP route, and it is what makes it detectable if entries are ever removed from the
end of the audit ledger.

**A safety mechanism with no caller is worse than no safety mechanism**, because the console
says the estate is protected. That is why they are listed here by name rather than summarised,
and why the registry that tracks them is checked in both directions: a mechanism that gets
wired without being recorded fails a test, and so does one that was wired and stops being.

## What to do about it

Two questions belong to whoever owns this install, and neither has a default answer.

**Where do scheduled jobs run?** There are three shapes: a small scheduler inside the
application container, external timers calling HTTP routes (which is how the one working
mechanism runs today), or timers on the server itself. The trade-off is between something that
follows the deploy and something an operator can see and disable without a release.

**Which mechanisms do you switch on first?** The backup one, then the drill that proves it,
before anything else on the list.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The backup schedule and its intervals | `test_recovery.py`, against the schedule |
| The recovery figures per profile | `test_reliability.py` |
| That a service level statement is refused when the arithmetic does not support it | `test_launch.py` |
| The thirteen mechanisms, and which have a caller | `test_controls.py`, read out of the source in both directions |
| That every component declares what ready means | `test_wiring.py` |
| **Everything about what you should do next** | **nobody. Prose, kept true by hand.** |

## Task ids

M42.2.8 is not claimed. The leaf asks for backup, monitoring, logging and health-check
configuration. Two of the four are configured and documented above: the health checks answer and
every container declares one, and the logging split between the audit ledger and the optional
trace ledger is real in every profile. The other two are not configuration at all today. The
backup schedule is a set of constants that nothing runs, no drill has ever verified a restore,
and almost every mechanism in the table above is the monitoring. A client following this page
ends with health checks and no backups.
