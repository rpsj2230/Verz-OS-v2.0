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

**What is not here, and it is most of M19's first group.** There is no gVisor, no container
runtime, no Playwright, no Chromium and no mitmproxy, and no dependency on any of them: `uv
.lock` names none. So the ephemeral container, the per-run network namespace, the tmpfs
writable layer, the CDP worker and the proxy sidecar are not delivered and are not declared
either, because a protocol nothing implements makes a register complete and worse. What is
here is the decision such a runtime would ask for, in a form that can be tested without one.
Every module ends its docstring by saying which of its own leaves it does not close.
"""
