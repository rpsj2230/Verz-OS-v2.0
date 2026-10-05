# Stop

The stop button, and everything currently stopped. Stopping needs no approval; resuming needs a stated reason. See brain.ops.halt.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `halt` |
| Title | Stop |
| Group | `operate` |
| Tool | `console.halt` |
| Needs | `admin:halt` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent, connector` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

The stop button, and everything currently stopped (`operate.stopped_for`): each halt with its scope, target, who declared it, when, why and what it does. Stopping needs no approval. Resuming needs a stated reason. A halt never expires on its own.

The page is at `/stop`, under Operations, and every console page's header carries a Stop control for a reader who may stop something: one press stops everything, or for a department administrator their own department, with nothing to confirm and nothing to type. The table's last row is about agent tools, and no console tool named `console.halt` is registered, as none is for any screen.

## Who may see it

Opening it needs `admin:halt` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

A halt on everything is shown to everybody it stops, whatever they hold, because hiding it would leave somebody looking at a screen saying nothing is stopped while nothing runs. A narrower halt is shown only to a holder of `admin:halt` whose scope matches it.

## When it is empty or refuses

An empty list has two meanings: nothing you may see is stopped, or the halt store could not be read. Always check `stop_is_unknown`: when the state is unknown every request is refused, on the rule that if we cannot tell whether we are halted, we are. `HaltError` refuses a halt with no target where one is needed, a reason shorter than `MINIMUM_REASON`, or no effects.

## When it shows an alarm

An unknown state is treated as stopped: restore access to the halt store before anything else. A halt on everything means nothing runs. `halt_gaps` reports two mistakes worth knowing: a halt on a department, an agent or a person refuses no request anywhere today, so stop a connector or everything instead; and a halt without `SIGNAL_RUNNING` leaves jobs that were already running still writing. The person refused is never shown the reason.
