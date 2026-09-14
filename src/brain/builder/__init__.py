"""The builder: where somebody assembles a thing that later runs against real data.

Everywhere else in this repository a person asks a question and the gate decides what they
may be told. Here a person builds the asker. That inverts the risk, and the inversion is the
only reason this package exists as its own thing rather than as another console module.

**What somebody builds must not reach further than they can.** `E_run(caller, agent) =
E(caller) intersect agent_ceiling` holds at run time whoever runs the agent, so a published
agent can never hand its own caller more than that caller already had. What it can do is
carry a ceiling wider than its *author's* reach, and then be run by somebody else. The author
never sees the extra reach, because their own runs are intersected down to what they hold, so
the widening is invisible from the only seat they occupy. That is what the publish gate is
for, and it is why the publish gate rather than the form is the load-bearing part.

**What does not belong here.** Any computation of a reach. `EntitlementSet.intersect` is the
one implementation of the invariant and this package calls it nowhere: a builder that worked
out its own reach would be a copy of the central rule owned by the layer with the least
reason to be trusted with it. Every function here is handed a reach and filters at it, and
`brain.console.workspace.intersections_in` is run over both modules by their own diagnostics
so that the absence is checked rather than remembered.

**And no rendering.** Nothing in this package draws a form, a canvas or a screen, exactly as
nothing behind `brain.console.screens` does. What is built here is the domain layer: the
sectioning of the manifest and the form schema cut from it, the revisions a manifest is saved
as before it is whole and the version publishing makes of one, the grammar a procedure may be
drawn in and the bounded drawing and SKILL.md that come from it, whose reach a rehearsal runs
at, and what a publish gate may refuse and how it must word the refusal. The rendering is the
console's (`ManifestForm.tsx`, `ProcedureCanvas.tsx`, `TraceGraph.tsx`), and no route joins the
two halves yet.
"""
