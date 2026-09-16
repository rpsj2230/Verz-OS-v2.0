# This install

What is actually running: the release, the migration level, the profile and the features it turns on. The first question of every support conversation.

<!-- checked: what the registry says about this screen -->

| Fact | Value |
| --- | --- |
| Key | `install` |
| Title | This install |
| Group | `install` |
| Tool | `console.install` |
| Needs | `read:release` |
| Console plane | `read:console.configuration` |
| Narrowed by | `department, person` |
| Offered to a department admin | `no` |
| Designed for | `super_admin` |
| Can be opened today | `no` |

## What it is for

What is actually running: the profile, the release and when it was built, the migration level, the declared branding, locale, model and storage settings, and which features the profile turns on (`installation.install_facts`). The first question of every support conversation.

**This screen cannot be opened yet.** The registry declares it and no console tool named `console.install` is registered, so there is no page to go to. Everything below describes what the module behind it decides, which is what the screen will show once the tool exists.

## Who may see it

Opening it needs `read:release` and `read:console.configuration`, both, and a role on its own confers neither. A department admin is not offered it in their menu, because its subject is the installation rather than any department's work, and anybody holding the capability still reaches it by its address.

The facts are the same for everybody who opens it. Identity settings are deliberately never shown.

## When it is empty or refuses

The release is unknown when the image carries no release manifest, which is normal outside a built image. The migration level is the level the code expects, not the level the database is on, unless the pending migrations were read, and it is unknown when the migration history branches. Each fact says which of measured, declared or unknown it is. On a database where every migration is still pending the level reads as no migration applied, with how many are waiting.

## When it shows an alarm

Migrations pending, or a revision that is not the code's head, means the database is behind the code: run the migrations before anything else. The screen shows the revision and not the head beside it, so compare with `installation.level_of`. Findings from `installation_gaps` are defects in the screen itself.
