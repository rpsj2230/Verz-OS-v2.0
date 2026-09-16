# Version and updates

Which release this install is on, whether a newer one has been published, and how old that answer is. Nothing here asks anywhere outside this network unless the install switches the check on.

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
| Offered to a department admin | `no` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

Which release this install is on, whether a newer one has been published, and how old that answer is (`version_view.panel`). The release is read from the image reference the application was started with, and the commit from the image itself. Whether anything newer exists is asked of the published list of releases only when `BRAIN_RELEASE_CHECK` is true, in the background, when somebody opens the screen.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.updates` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:release` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is not offered it in their menu, because its subject is the installation rather than any department's work, and anybody holding the capability still reaches it by its address.

The same for everybody who opens it. It shares `read:release` with This install, because both are statements about which release is running.

## When it is empty or refuses

No release is named when the application was handed no image reference, which is a deployment whose compose file predates the line, or when the reference ends in `latest` or in no tag; the commit is shown instead, labelled as a commit. The release marker is never read here and is shown as unknown on purpose. With the check switched off the screen says so; switched on, the first opening after a start says no look has finished yet, because the page never waits for the list.

## When it shows an alarm

Each standing says what to do. `BEHIND`: read the notes of the release named, back up if they say the database changes, and run the update script. `STALE`: the last answer is older than `TELLING_GOES_OFF_AFTER_DAYS` days, so open the screen again to start a fresh look. `AHEAD`: a copy of the release list is behind the install, so refresh the copy. `DIFFERS`: the two tags cannot be ordered, so compare by hand. `SWITCHED_OFF`: check the published list by hand or switch the check on. `NOT_LOOKED_YET`: open the screen again in a minute. `CHECK_FAILED`: check the server can reach the list. `UNKNOWN_RUNNING`: pin a release with the update script. Only `CURRENT` is settled.
