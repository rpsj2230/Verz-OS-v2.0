# Version and updates

Which release this install is on, whether anything newer has been recorded, and how old that answer is. Nothing here asks anywhere outside this network.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `updates` |
| Title | Version and updates |
| Group | `install` |
| Tool | `console.updates` |
| Needs | `read:release` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `yes` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

Which release this install is on, whether anything newer has been recorded, and how old that answer is (`version_view.panel`). Nothing here asks anywhere outside this network.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.updates` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:release` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is offered it, and sees it narrowed to their own scope.

The same for everybody who opens it. It shares `read:release` with This install, because both are statements about which release is running.

## When it is empty or refuses

No release is named when there is no release marker and no pinned image, when the image is unpinned or pinned to `latest`, or when the marker and the pin disagree; each missing input is shown as unknown. Today no compose file gives the application container either the install directory or the image variable, so in practice the screen cannot read the marker or the pin. Nothing records a newer release yet either.

## When it shows an alarm

Each standing says what to do. `BEHIND`: read the release notes, back up if they say the database changes, and run the update script. `STALE`: what was recorded is older than `TELLING_GOES_OFF_AFTER_DAYS` days, so check and record the newest release. `AHEAD`: record the release actually running. `DIFFERS`: the two tags cannot be ordered, so compare by hand. `NOBODY_HAS_SAID`: check the published list and record it. `UNKNOWN_RUNNING`: fix the version statement first. Only `CURRENT` is settled.
