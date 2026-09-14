# Agents

Every agent, its ceiling, its leash state, and the history of every promotion and demotion. An agent is a lens and its ceiling is the only thing that narrows it.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `agents` |
| Title | Agents |
| Group | `govern` |
| Tool | `console.agents` |
| Needs | `read:agent` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, agent` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin, department_admin` |
| Can be opened today | `no` |

## What it is for

Every agent: its ceiling, its leash for each entity and operation, and the history of every promotion and demotion with the evidence or the circuit break behind it.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.agents` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:agent` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

Agents you may see are listed. The ceiling's detail needs `read:capability` as well and is shown locked without it; the run preview needs `read:grant`; an approver's name needs the People screen.

## When it is empty or refuses

An agent you may not see is absent. A blank approver means a demotion or that you may not open People, deliberately without saying which. The run preview returns the same nothing for every kind of refusal.

## When it shows an alarm

A circuit break means the agent fell back to shadow, and the row shows the measure against its threshold: find out what changed before promoting it again. Promotion needs `MINIMUM_CLEAN_RUNS` clean runs and `MINIMUM_AGREEMENT_RATE` agreement, and an action that cannot be undone, sending or moving money, needs a second approver.
