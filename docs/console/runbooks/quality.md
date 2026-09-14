# Quality and canaries

How the golden corpus scored, what the permission canaries found, and what regressed since the last release.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `quality` |
| Title | Quality and canaries |
| Group | `report` |
| Tool | `console.quality` |
| Needs | `read:evaluation` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person, period` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

What the permission canaries found (`operate.findings_in_reach`): each finding's kind, who asked, which question, and which field. The registry also names golden corpus scores and regressions since the last release; nothing behind this screen covers those yet.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.quality` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:evaluation` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

A finding is shown only when you reach its exact field, because a finding names a field and a list of findings is otherwise a list of the schema.

## When it is empty or refuses

None found and none you may see look the same. The landing screen's quality figure is withheld unless you could open this screen.

## When it shows an alarm

`LEAKED` means a value reached somebody without the grant: treat it as a security incident, stop the source or everything from the stop screen, and read the Activity screen. `REFUSAL_DISTINGUISHABLE` means a refusal could be told apart from an absence. `UNLOCKED` and `PROJECTION_TOO_WIDE` mean a column was shown that should not have been. `PROJECTION_TOO_NARROW` withholds a column from somebody entitled to it; it is not a leak, and the fix is the classification. Canaries run every `CANARY_INTERVAL_SECONDS` and on every deployment.
