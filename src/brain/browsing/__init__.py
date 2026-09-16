"""Browsing: an agent with hands, and the four refusals that make that survivable.

A browser driving a client's accounting system is not a retrieval tool with a different
transport. It is a principal that can act, holding a session, reading a document somebody
else wrote, on a system where a mistake is a filing rather than a wrong sentence. Four of
M19's seven groups are refusals rather than features and each names the failure it prevents,
so this package is organised around them rather than around a runner.

**The planner cannot read the page.** Not "is told not to": cannot. Everything derived from a
page lives in `observation`, `planning` cannot reach that module, the planner's parameters are
walked through every field they touch, and no function in the package takes page content and
returns a plan. `shape` decides all of that by parsing the source, because the failure this
guards against is not the code as written but the reasonable-looking function somebody adds
after the first run fails and the page had the answer on it.

**The policy cannot change mid-run.** `enforcer.Policy` is compiled once from the sealed
envelope, is frozen, and has no field a reload could hang off. The party who would reach
whatever a policy was re-read from is the container whose browser is executing somebody
else's code.

**The credential never reaches the model.** A placeholder travels through the plan, the
envelope, the policy and the action; `credentials.resolve` is the only thing that produces a
value, it does so inside `brain.ops.secrets.borrow`, and it refuses unless the action's origin
is exactly the one the binding names. The custody argument is not restated here: it was
settled for connectors and this package is a caller of it.

**The rubric is written before the trajectory exists.** `grading.build_rubric` takes a goal
and a declaration and there is no parameter a run could arrive through, so the criteria are
about what was asked for rather than about what happened. The agent's own claim of success is
carried, compared and never scored.

**Nothing here counts anything twice.** Browser sessions are one of the seven globally
budgeted resources and `brain.ops.admission` owns that arithmetic, so `sessions.may_start`
builds a request and calls `decide`. The stop button belongs to `brain.ops.halt` and this is
the first thing in the repository to consult its `SIGNAL_RUNNING` effect, because a browser
run is the case that lasts long enough for stopping it to mean something.

**The runner is specified and has never run.** `sandbox` builds the Engine bodies for one run: a
gVisor container with nothing writable but memory, on a network of its own whose only other member
is a mitmproxy container holding the run's origins (`egress_addon`). `launcher` is the one service
holding the Docker socket, creating and removing those and relaying `wire`, the line protocol, to
`runner`, the process inside the container that owns the DevTools session. `recording` keeps the
transcript for the recordings bucket's window, and `verification` judges a run on its actions,
then on masked pictures, then on its system of record. There is no Docker, gVisor or browser on the
machine this was written on, so every decision is tested and none of the plumbing has run;
`ops/browser/REHEARSAL.md` is the rehearsal for a server that can.
"""
