# Capacity

Database connections, memory ceilings and pool sizes against what is deployed. brain.ops.connections holds the arithmetic; this shows it.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `connections` |
| Title | Capacity |
| Group | `install` |
| Tool | `console.connections` |
| Needs | `read:connection_budget` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `no` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

Database connections and memory against what is deployed: for each database, how many connections it admits, how many the declared clients demand and what is left (`ConnectionCapacity`), and the memory the profile declares beside what the compose files reserve (`MemoryCapacity`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.connections` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:connection_budget` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is not offered it in their menu, because its subject is the installation rather than any department's work, and anybody holding the capability still reaches it by its address.

The same for everybody who opens it.

## When it is empty or refuses

Without compose files the deployed memory is not measured, which is different from agreeing. The `lite` profile declares no components and so declares no memory. Only declared clients are counted, so a client nobody declared is invisible here. Pool sizes per client, which the registry names, are not shown, and every figure is declared arithmetic rather than a live count.

## When it shows an alarm

Headroom below zero means the declared clients demand more connections than the database admits. Headroom of exactly zero means a backup, a migration or a diagnosis has nowhere to connect: raise the database's ceiling or lower a client's pool. A memory breach names the largest component; a service with no memory budget is listed as unbudgeted.
