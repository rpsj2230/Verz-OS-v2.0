# Connector health

Every source this install reads, whether it is answering, and when it last did.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `connectors` |
| Title | Connector health |
| Group | `operate` |
| Tool | `console.connectors` |
| Needs | `read:connector` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, connector` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin, connector_admin` |
| Can be opened today | `no` |

## What it is for

Every source this install reads that you may be shown, with its lifecycle (`ConnectorState`), its health (`HealthState`) and when it was last checked (`ConnectorRow`). No credential, host or endpoint appears on it.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.connectors` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:connector` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

The list is `operate.reachable_connectors`: only the connectors you already reach, through `screens.offerable`.

## When it is empty or refuses

A source you do not reach and a source that was never installed are both simply absent. A blank health with no check time means nothing has checked the source yet; it does not mean healthy. The landing screen's connector figure is withheld unless you could open this screen.

## When it shows an alarm

`DOWN` is an incident: open the incidents screen to see which tools it blocks. `DEGRADED` is still usable. `UNCONFIGURED` is a task for whoever installed the source, not an incident. `QUARANTINED` means the source stopped matching what it was pinned to at connect, and enabling it does not clear that: find out what changed at the source first. `DISABLED` is deliberate and `REGISTERED` serves nothing yet. A check time that has stopped moving may mean the prober itself has stopped.
