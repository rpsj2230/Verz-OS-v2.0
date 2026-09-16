# Cutting a release

Everything a client receives comes from one tag: an archive, its notes, and the image the
archive pins. This page is how the tag is made and how the two artefacts are proved to exist
afterwards, from a machine that has never seen this repository.

**Nothing has been tagged yet.** Until a tag is pushed, both workflows below have never run,
and a workflow that has never run is a claim rather than a fact. Read the blockers at the
bottom first: two of them are settings on the account rather than anything in this repository,
and both make an install fail at a step that leaves a client's server half prepared.

## What a tag produces

Pushing a tag matching `v*` runs **Release**, and nothing else. It does not run CI and it does
not run Deploy: CI triggers on a push to `main` and on a pull request, and Deploy triggers on
CI completing on `main`, so a tag ref matches neither.

The workflow has two jobs and the second waits for the first.

| Job | What it produces | Where it lands |
| --- | --- | --- |
| `image` | The release tag put onto the image digest the deploy pipeline already built for the commit the tag names, after that digest's signature is verified | `ghcr.io/rpsj2230/verz-brain-v2.0:<tag>`, as a second name on an existing digest |
| `archive` | `brain-<tag>.tar.gz`, the rendered notes, and the installer script as a second asset | A GitHub release named `<tag>` |

The archive carries what `brain.deployment.release.INCLUDED` names and nothing else: the
compose files every profile composes, the tunnel overlays, `.env.example`, the five `ops/`
directories a service or an operator reads, `ops/install` and `ops/update`, `migrations`,
`alembic.ini` and `docs/install`. It carries no `.git`, no `.github`, no `src`, no `console`
and no tests. The workflow spells none of those paths: it asks the module for the list and
diffs what went into the tar against what it asked for.

Three refusals run before the tar and any one of them fails the release rather than producing
one to withdraw later: a path the install reads that the archive would not carry, a path the
archive would carry that a refusal names, and a value belonging to one company in a file the
archive carries.

## Before you tag

1. **The commit is on `main` and both CI and Deploy are green for it.** The `image` job puts
   the release tag onto the image Deploy published for that commit. No image at that commit
   means CI never passed for it, and the job fails rather than building one, which is the CI
   gate reaching the client install instead of stopping at production.
2. **The tag message carries an `Urgency:` line.** One of `security`, `recommended`,
   `routine`. There is no default: a release with no urgency fails the build, which is the
   only moment anybody can still say what it is.
3. **Everything else in the message is one line per thing that changed**, in plain English. A
   line naming a module path, a `src/` or `tests/` path, or a task id is refused as a commit
   subject rather than a release note.
4. **Push the commit first and wait.** Pushing the commit and the tag together starts the
   release while Deploy is still building, and the `image` job then looks for an image that is
   minutes away from existing.

## The tag

Run from a clean checkout of the commit being released, with nothing uncommitted.

```sh
git fetch --all --tags
git checkout main
git pull --ff-only
git log --oneline -1                 # this is the commit the release names

git tag -a v0.1.0 -m "Urgency: routine
First published release: the archive, the image and the installer.
Console screens for skills and connectors.
"

git tag -v v0.1.0 || git tag -l --format='%(contents)' v0.1.0
git push origin v0.1.0
```

`-a` is not optional. A lightweight tag has no message, so the notes step reads an empty
string, finds no `Urgency:` line, and the release fails after the archive has been built.

## What to watch

```sh
gh run list --workflow Release --limit 1
gh run watch "$(gh run list --workflow Release --limit 1 --json databaseId -q '.[0].databaseId')"
```

In order, the run should say: the image name asked of the module, a digest found for the
commit, a signature verified against this repository, the release tag created, the tag read
back and matching the verified digest, then the gaps check, the file list, the tar, the diff
of asked against inside, the notes, and the publish.

A failure in `image` publishes nothing at all. A failure in `archive` leaves the image tag in
place, which is harmless: an image tag with no release beside it is unreachable by the
installer, since the installer is what the release carries.

## Proving both exist, from a machine that has never seen this repository

This is the whole of the leaf. Neither artefact is known to exist because a workflow went
green; it is known to exist because it was fetched back.

```sh
# The release and its assets
gh release view v0.1.0
gh release download v0.1.0 --pattern 'brain-*.tar.gz' --dir ./check
gh release download v0.1.0 --pattern 'install.sh' --dir ./check
tar -tzf ./check/brain-v0.1.0.tar.gz | sed 's,^brain-v0.1.0/,,' | sort | head -40
tar -tzf ./check/brain-v0.1.0.tar.gz | grep -cE '(^|/)(src|tests|console)/' # must print 0

# The image the archive pins
docker buildx imagetools inspect ghcr.io/rpsj2230/verz-brain-v2.0:v0.1.0
cosign verify ghcr.io/rpsj2230/verz-brain-v2.0:v0.1.0 \
  --certificate-identity-regexp '^https://github.com/rpsj2230/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
docker pull ghcr.io/rpsj2230/verz-brain-v2.0:v0.1.0
```

Then the fetch a client actually makes, which uses no credential at all. Run it signed out,
because run signed in it proves nothing about anybody else:

```sh
docker logout ghcr.io
curl -fsSL -o /dev/null -w '%{http_code}\n' \
  "$(gh release view v0.1.0 --json assets -q '.assets[]|select(.name|endswith(".tar.gz")).url')"
docker pull ghcr.io/rpsj2230/verz-brain-v2.0:v0.1.0
```

Both of those fail today. See the blockers below.

## Rolling back a bad release

Three things can be wrong and they undo in a different order.

**Nobody has installed it yet.** Withdraw the whole tag.

```sh
gh release delete v0.1.0 --yes --cleanup-tag
git push origin :refs/tags/v0.1.0       # if the tag survived
git tag -d v0.1.0
```

The image tag stays until it is moved or the package version is deleted. Move it onto the
previous good digest rather than leaving it pointing at a withdrawn release:

```sh
prev=$(docker buildx imagetools inspect ghcr.io/rpsj2230/verz-brain-v2.0:v0.0.9 \
         --format '{{.Manifest.Digest}}')
docker buildx imagetools create --tag ghcr.io/rpsj2230/verz-brain-v2.0:v0.1.0 \
  "ghcr.io/rpsj2230/verz-brain-v2.0@$prev"
```

**Somebody has installed it.** Do not withdraw the tag. An install that cannot re-fetch the
release it is on has no way back to it, and the rollback script on their server fetches by
tag. Publish the next release instead, and tell them to run `ops/update/rollback.sh`, which
re-pins the previous release out of `/opt/brain/PREVIOUS_RELEASE` and refuses when the
database is already past the release it would go back to.

**The tag names the wrong commit.** Withdraw it as above and tag again under a new version.
Moving a tag is not a rollback: a server that already pulled `v0.1.0` keeps the image it has,
and the two installs then report the same version and run different code.

## What still blocks a real install

Both are account settings and neither is fixable in this repository.

1. **The GHCR package is private, because the repository is private.** `ops/DEPLOY.md` says so
   in the Coolify step, which needs a `read:packages` token for the same reason. The
   installer's tenth step is a bare `docker compose pull` with no login, deliberately: nothing
   in this product asks a client for a credential on somebody else's registry. So either the
   package is made public, or every client is handed a token, which is a value this product has
   no place to keep. Make the package public: **Packages, the package, Package settings, Change
   visibility**.
2. **The release asset is behind the same wall.** The installer fetches
   `$BRAIN_RELEASE_URL` with a bare `curl`, and a release asset of a private repository answers
   404 without a token. `BRAIN_RELEASE_URL` is a variable rather than a constant exactly so the
   archive can be served from anywhere, so the other answer is to mirror the published archive
   somewhere readable and give the client that address. Whichever is chosen, it is a decision
   about publication rather than a change to the installer.

A third is smaller and worth knowing. The notes step passes the added migration files through
`xargs`, which splits into more than one invocation if the list is ever long enough to exceed
the command line limit, and the notes would then be two rendered documents concatenated. No
release is near that today.
