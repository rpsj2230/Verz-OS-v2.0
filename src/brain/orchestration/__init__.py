"""Orchestration: one question becoming several runs, and the reach that follows it down.

A run through an agent is a lens over the person who asked. When that run delegates, the
child is a lens over the parent, and the composition is the whole of what this package is
for: `E_run(caller, agent) = E(caller) intersect agent_ceiling` applied once per hop, in
order, so that a chain can only ever narrow. An agent that could restore reach at any hop
would be a laundering route, because installing an agent is not a grant and must not
become one by being called from another agent.

**Nothing here computes an intersection.** `brain.ops.automation.flow_reach` is the one
wrapper over the one `EntitlementSet.intersect`, and every hop in this package goes
through it. A second implementation would be a second place the platform's central rule
can be subtly wrong, and the wrong copy is the one running at depth two with nobody
watching.

**What does not belong here.** Anything that decides whether a single call is allowed.
That is `brain.gate`, and `brain.gate.leash` decides what a run may do with the reach this
package computes for it. Orchestration decides how many runs there are and what each one
is handed; the gate decides what each one may then do.
"""
