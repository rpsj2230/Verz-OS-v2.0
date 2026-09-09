# Updating, and going back

**This procedure has never been executed.** Nothing on this page has been run against a
server, no update has ever been performed on an install of this product, and no rollback has
ever been performed either. It is written from what the deployment declares, which is enough to
be worth reading before you try it and is not the same thing as a rehearsed procedure.

The precedent for shipping it this way is in this repository: `console/scripts/check-boundaries.mjs`
carried "this script has never been run" in its own header for weeks, and that was the right way
to ship it. Read this page the same way.

## What an update is

One published image, deployed by tag. Your server pulls it and recreates the containers. Nothing
is compiled on your machine, so the artefact you run is the same artefact every other install
runs with that tag on it, which is the whole point of the arrangement: a fix reaches everybody
through one image rather than reaching each install separately.

So an update is: change the image tag, pull, recreate, wait for readiness, check the commit.

## What a rollback is, and the thing that does not roll back

Images are tagged by the commit they were built from, so going back is re-pinning the previous
tag and redeploying. Nothing needs rebuilding and the tag you want still exists.

**The database does not go back with it.** The application applies its own migrations at
startup, so the moment the new image came up it may have changed the schema, and re-pinning the
old image puts old code in front of a newer database. Every migration in this product carries a
reverse, so undoing one is possible; running one has never been done here, and the reverse of a
migration that changed both a schema and the data in it is not the reverse of the migration.

That last point is checked rather than left to a reviewer: a migration that changes a schema and
data together is refused before it can merge, precisely because the schema part reverses cleanly
and the data part usually cannot, so combining them makes the whole thing one-way.

**So the two directions are not symmetrical.** An update is a tag change. A rollback is a tag
change plus a decision about the database, and the decision needs somebody who has read what
changed.

## The procedure, as it would be run

### Before

1. **Take a backup and know that you can restore it.** Nothing in this install takes one
   automatically today; see [operations.md](operations.md). A rollback plan that begins with a
   copy nobody has ever restored is a plan with one step missing.
2. **Read the release notes for whether it changes the database.** They do not say so today.
   The release record this product publishes carries the commit, the build time and the list of
   work it contains, and it has no field anywhere saying whether a migration is in it. Until it
   does, the only way to know is to compare the migration directory between the two tags.
3. **Write down the tag you are on.** `/health/ready` reports the commit the running image was
   built from. That is where to read it, and it is the same place you will check afterwards.

### The update

4. Set the image variable to the new tag. Note that one image in this deployment is selected by
   two different variables, so setting one and not the other leaves some containers on the old
   tag while every version figure the system reports is true of only part of it.
5. Pull before recreating, so that an unreachable registry fails while the old containers are
   still serving.
6. Recreate. Migrations run inside the application's startup, under a lock, before readiness
   passes.
7. Wait for `/health/ready` to answer 200. On a release carrying migrations this takes longer
   than usual, and readiness failing during that window is the system working as designed.
8. Check the commit on `/health/ready` is the one you deployed. If it says `unknown`, something
   in your deployment tool is overriding it; see [troubleshooting.md](troubleshooting.md).

### Going back

9. Re-pin the previous tag, both variables, and recreate.
10. **Then decide about the database.** If the release you are backing out of carried no
    migration, you are done. If it did, the new schema is still there and the old code is now
    running against it. Whether that is safe depends on what the migration did, and nothing in
    this system answers that question for you today.

## What would make this rehearsed

Four things, and none of them exists yet.

**An update script and a rollback script.** One that pins a release tag and one that re-pins the
previous one. The install plan is written and tested as a plan; there is no equivalent for
either of these.

**Release notes that say whether the database changes.** In plain English, with how urgent the
release is. The release record has no field for either.

**A running version indicator in the console**, showing what is running and whether a newer
release exists, because nothing else reminds anybody to update.

**A drill.** The procedure above run start to finish on a throwaway server, including the
rollback, including the database decision, by somebody following only this page. That is what
"rehearsed" means and it is the only thing that would turn the paragraphs above into a
procedure.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| That no service is built on a client's machine, and none is deployed untagged | `test_deployment_installer.py` |
| That an install which pins nothing is not pinned, and that one image is selected by two variables | the same test, which reports both as findings rather than hiding them |
| That a migration mixing schema and data changes cannot merge | `test_migration_policy.py` |
| That every migration carries a reverse | the migration files themselves |
| **The procedure on this page** | **nobody. It has never been run.** |

## Task ids

M42.2.10 is not claimed. The leaf asks for an update procedure and a rollback procedure
"rehearsed rather than written", and this is written. There is no server here to rehearse it
against, and four of the pieces it would need are listed above as not existing.
