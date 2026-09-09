# Updating, and going back

**Neither of these procedures has ever been run against a server.** There are now two scripts,
they are generated from a plan this project tests, and no update and no rollback has been
performed on an install of this product. Read the page the same way you would read a runbook
somebody wrote carefully and never rehearsed, because that is what it is.

The precedent for shipping it this way is in this repository: `console/scripts/check-boundaries.mjs`
carried "this script has never been run" in its own header for weeks, and that was the right way
to ship it.

## What an update is

One published image, deployed by tag. Your server pulls it and recreates the containers. Nothing
is compiled on your machine, so the artefact you run is the same artefact every other install
runs with that tag on it, which is the whole point of the arrangement: a fix reaches everybody
through one image rather than reaching each install separately.

So an update is: pin the image tag, pull, recreate, wait for readiness, check the commit.

## The thing that was missing, and why this page changed

**Your install records which release it unpacked and never which image it runs, and until you
run the update script those are two different facts.**

The installer writes the tag you gave it into `/opt/brain/RELEASE`, and it writes nothing into
`/opt/brain/.env` that selects an image. Every container therefore falls back to the default in
the compose file, which ends in `:latest`. So a server whose `RELEASE` file says `v1.4.0` may be
running whatever `latest` pointed at on the afternoon it pulled, and every version figure it
reports is true of the marker rather than of the containers.

The update script closes that: it writes `APP_IMAGE` into your environment file, so from the
first update the marker and the running image are the same fact. Until then, treat `RELEASE` as
a record of what was downloaded and `/health/ready` as the record of what is running.

**The second gap was worse and it is the one the rollback needed.** `RELEASE` is the only
version fact an install holds, an update overwrites it, and nothing recorded what it overwrote.
So the update script copies `RELEASE` to `/opt/brain/PREVIOUS_RELEASE` **before** it writes the
new tag, and that copy is the only thing the rollback reads.

## What a rollback is, and the thing that does not roll back

Images are tagged by the release they were built for, so going back is re-pinning the previous
tag and redeploying. Nothing needs rebuilding and the tag you want still exists.

**The database does not go back with it.** The application applies its own migrations at
startup, under a lock, so the moment the new image came up it may have changed the schema.
Nothing in this product ever runs a migration backwards against your data. Re-pinning the old
image therefore puts older code in front of whatever the newer release left behind.

Whether that is safe was decided when the release was published, not when you roll back: the
release notes state it, in the paragraph that begins "Going back". That paragraph is not typed
by anybody. It is read out of the migrations the release carries.

**So the two directions are not symmetrical.** An update is a pin and a pull. A rollback is a
pin and a pull plus a question about the database, and the script asks the one form of that
question a server can answer for itself: whether your database has been migrated past anything
the older release knows about. If it has, the script stops and says so, because from there the
answer is the backup you took before the update, not a tag change.

## The two scripts

They arrive with the release, at `/opt/brain/ops/update/`, so the release you are on carries
the script that takes you off it. That is deliberate: the moment you need the rollback is the
moment you are least able to fetch anything.

| Script | You run | It needs |
| --- | --- | --- |
| `update.sh` | `sh /opt/brain/ops/update/update.sh <profile> <release tag>` | `BRAIN_RELEASE_URL` set to that release's archive |
| `rollback.sh` | `sh /opt/brain/ops/update/rollback.sh <profile>` | `BRAIN_RELEASE_URL` set to the archive of the release it names |

Both take the profile you installed, because nothing your install leaves on disk records which
one it was. Both are safe to run twice: every step that writes something says when it has
nothing left to do, and the count of steps and the reason for each is printed as they run.

**The rollback takes no tag, and that is the design.** It goes back to the release recorded in
`PREVIOUS_RELEASE` or it stops. What it could otherwise guess from is the tag it is already on
or whatever the release host offers today, and both are guesses about your server. It is run at
the worst moment of somebody's week, so it either goes to the release you were actually on or it
tells you which file is missing.

### What they refuse

**A tag of `latest`, in either direction.** Updating to `latest` is not moving to a release, it
is stopping being pinned: the next pull changes your running version with nobody having decided
anything, while the marker beside it goes on naming a tag.

**A directory that is not an install.** Both check for the release marker and the environment
file first. The second matters more than it looks: the step that writes the pin rewrites your
environment file, and against a directory with no environment file it would create one holding
the pin and nothing else, with every credential your install minted gone.

**A rollback with nothing recorded.** An install that has never been updated by `update.sh` has
no `PREVIOUS_RELEASE`, so there is no release to go back to and the script says so rather than
choosing one.

**A rollback onto a database that has moved past it.** The script asks your database which
migration revision it is on, and looks for that revision in the archive of the release you are
going back to. If it is not there, the older code would be running in front of a schema it has
never seen, and the script stops before anything is pulled or recreated.

## The procedure, as it would be run

### Before

1. **Take a backup and know that you can restore it.** Nothing in this install takes one
   automatically today; see [operations.md](operations.md). A rollback plan that begins with a
   copy nobody has ever restored is a plan with one step missing.
2. **Read the release notes.** They say what changed in plain English, how urgent it is, whether
   it changes your database, and what going back would mean. The database answer is derived from
   the migrations the release carries rather than typed by anybody, which is why it can be
   trusted in the direction that matters: a release cannot claim it changes nothing while
   carrying a migration.
3. **Write down the tag you are on.** `/health/ready` reports the commit the running image was
   built from, and `/opt/brain/RELEASE` reports the tag that was unpacked. Until your first
   update those can disagree; see above.

### The update

4. Set `BRAIN_RELEASE_URL` to the new release's archive.
5. Run `sh /opt/brain/ops/update/update.sh <profile> <tag>`. It refuses a tag of `latest`,
   records the release you are on, fetches and unpacks the new one, creates any settings file
   the new release added without touching one you have edited, writes `APP_IMAGE`, pulls before
   it recreates anything, recreates, and waits for `/health/ready`.
6. Check the commit on `/health/ready` is the one you deployed. If it says `unknown`, something
   in your deployment tool is overriding it; see [troubleshooting.md](troubleshooting.md).

On a release carrying migrations, step 5 takes longer than usual and readiness failing during
that window is the system working as designed.

### Going back

7. Run `sh /opt/brain/ops/update/rollback.sh <profile>`. It prints the release it is going back
   to and then asks for that release's archive in `BRAIN_RELEASE_URL`, because it cannot ask for
   it before it knows which release you are going to.
8. Set `BRAIN_RELEASE_URL` to that archive and run it again. It checks your database has not
   moved past that release, unpacks it, re-pins, pulls, recreates and waits for readiness.
9. It then removes `PREVIOUS_RELEASE`. **A rollback goes back one release**: a second run
   refuses rather than sending you back to the release you just left, and going back two
   releases is an update to a tag you name.

## What would make this rehearsed

Two things, and neither exists.

**A running version indicator in the console**, showing what is running and whether a newer
release exists, because nothing else reminds anybody to update.

**A drill.** Everything above run start to finish on a throwaway server, including the rollback,
including a database that has moved, by somebody following only this page. That is what
"rehearsed" means and it is the only thing that would turn these paragraphs into a procedure.

Two of the four things this section used to list have since been built. The release notes now
state whether a release changes the database and what going back would mean, and both are read
out of the release rather than typed into it. The update and rollback scripts now exist, are
generated from a plan with tests against it, and are carried in the archive. **Neither has been
run on a server**, which is why the list above still has a drill in it.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| That no service is built on a client's machine, and none is deployed untagged | `test_deployment_installer.py` |
| That one variable selects every container of an install, and that an install pinning nothing is not pinned | the same test, which reports both as findings rather than hiding them |
| That the update records the release it replaces before it writes the new one | `test_deployment_release.py`, which runs the step against a throwaway install directory |
| That a rollback with nothing recorded refuses, and that one with a record reads it | the same test, by running both scripts |
| That neither script will put an install on `latest` | the same test, in both directions |
| That the rollback refuses a database migrated past the release it goes back to | the same test, against a built archive and two revisions |
| That both scripts create a settings file a new release adds, and leave one you have edited | the same test, and the installer's own step, used rather than copied |
| That the scripts in the archive are the ones generated from the plan | the same test, which compares the files against the rendering |
| That a migration mixing schema and data changes cannot merge | `test_migration_policy.py` |
| That every migration carries a reverse | the migration files themselves |
| **The procedure on this page** | **nobody. It has never been run on a server.** |

## Task ids

M42.3.6 is claimed: the update script pins a release tag and the rollback script re-pins the
previous one, and both are generated from a plan with tests against every refusal.

M42.2.10 is not claimed. That leaf asks for an update procedure and a rollback procedure
"rehearsed rather than written", and this is written. There is no server here to rehearse it
against, and the two pieces it would still need are listed above as not existing.
