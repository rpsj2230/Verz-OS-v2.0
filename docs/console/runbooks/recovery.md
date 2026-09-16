# Backup and recovery

The last backup, the last verified restore, the measured recovery time, and the control to run a drill.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `recovery` |
| Title | Backup and recovery |
| Group | `install` |
| Tool | `console.recovery` |
| Needs | `read:backup` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `no` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

The last backup of the database, the object store and the configuration, how far back each newest copy reaches, the last verified restore, the latest attempt, whether a drill is due, and one verdict on whether this install is recoverable (`recovery_view.panel`).

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.recovery` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:backup` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is not offered it in their menu, because its subject is the installation rather than any department's work, and anybody holding the capability still reaches it by its address.

The same for everybody who opens it.

## When it is empty or refuses

Nothing on it is ever blank: a coverage with no schedule or no copy shows as unknown, and with no verified restore that fact is unknown and a drill is due. A backup record that cannot be read is listed by where it is and why, rather than stopping the screen. A copy that claims to restore to a moment after now is refused outright, because it means two clocks disagree. The control to run a drill that the registry names is not built.

## When it shows an alarm

The verdict is checked in order and each has an action. `RECORDS_UNREADABLE`: look at the files named. `NOTHING_COPIED`: get that coverage copying. `VERIFICATION_FAILED`: the latest rehearsal did not verify; fix it and rehearse again. `NEVER_VERIFIED`: rehearse a restore into a scratch database. `BACKUP_AGED`: the newest copy or the schedule is older than the recovery point promised; look for a timer that is off or a destination refusing writes. `DRILL_OVERDUE`: rehearse again. `SLOWER_THAN_PROMISED`: the measured recovery took longer than promised; speed it up or change the promise. Only `RECOVERABLE` is settled.
