# Four things on the server that a release cannot do for you

For a server that deploys itself with the pull timer (`brain-autodeploy`) and has no checkout of
this repository on it. A release starts the optional services, applies its own vault changes and
records what it did, and it does all of that from inside the image. These four are the places where
something has to happen on the machine first, or where a release depends on what is installed on
it, and each is a few commands you run once.

None of them needs anything that belongs to a company, and none of them is run by a release. Run
them as root, at a quiet hour, and not while a deploy is running (`journalctl -u
brain-autodeploy.service -n 20` says whether one is).

In every command below, `IMAGE` is the image your install runs, the one `brain-autodeploy` pulls:

```
IMAGE=ghcr.io/rpsj2230/verz-brain-v2.0:latest
```

## 1. The deploy hook, and keeping it as new as the release

`/usr/local/bin/brain-deploy` is the script that deploys. A release that adds a step to it (the
vault's changes, the sign-in accounts client, the optional services) only takes effect on a server
whose installed hook has the step. Until 2026-10-13 nothing updated the hook after it was
installed, so a server drifted behind its releases without saying so: its deploys went on
succeeding, and what they did not do was start an optional service, apply a release's vault
policies or report which container runtimes the server has. That last one is why Install, Settings
refuses to save `sandbox` until a deploy has reported gVisor: only the optional services step
reports it, and a hook from before that step never runs it.

**What a release does now.** The image carries the hook (`/app/ops/deploy/brain-deploy`), and
`brain-autodeploy` copies it out of the image it is about to deploy, just before it runs it. The
copy is made only when the two differ, only when the image's file is non-empty, starts with a bash
shebang and passes `bash -n`, and it keeps the file it replaces as `brain-deploy.previous` beside
it. Any other outcome leaves the installed hook in place and says so in the journal as a line
beginning `hook:`. So a release that adds a step is deployed by the hook that has it.

**What it cannot do is refresh the script that does the refreshing.** A server whose
`brain-autodeploy` was installed before this existed has no refresh, so it needs the two scripts
copied once:

```
cid=$(docker create "$IMAGE")
sudo docker cp "$cid:/app/ops/deploy/brain-deploy" /usr/local/bin/brain-deploy
sudo docker cp "$cid:/app/ops/deploy/brain-autodeploy" /usr/local/bin/brain-autodeploy
docker rm "$cid"
sudo chmod 0755 /usr/local/bin/brain-deploy /usr/local/bin/brain-autodeploy
```

If the image you pulled is older than the release that added the two files, `docker cp` says
`Could not find the file`: wait for the next release to be pulled (`docker pull "$IMAGE"`), then
run the commands again.

**To see whether your hook is current:**

```
cid=$(docker create "$IMAGE")
docker cp "$cid:/app/ops/deploy/brain-deploy" - | tar -xO | diff - /usr/local/bin/brain-deploy \
  && echo current
docker rm "$cid"
```

**What changes the first time a stale hook is replaced.** Everything the releases since it was
installed added starts to happen, on the next deploy: the release's vault changes are applied (if
the server keeps a deploy token, see section 2), the accounts client step runs, the per-class
connection poolers start (they are not optional), and the optional services named in
`INSTALL_SERVICES` are started if the server has the memory for them. Read the deploy's journal
afterwards (`journalctl -u brain-autodeploy.service -n 80`): every one of those says what it did.

## 2. The vault opens itself: moving an install made before 2026-09-29

An install made before then has a vault that people unseal, and its releases' vault changes wait
for three of them. `switch-to-auto-unseal.sh` moves it in place onto the seal that opens itself, and
`ops/openbao/UNSEAL.md` (under "Moving an older install") is the account of what it does and what
it needs: three of the vault's unseal pieces in a file, and a `--rollback` that is good while the
dated copy it makes exists.

On a server with no checkout, the script and the vault's compose file it recreates the vault from
are in the image, in the one directory it has to run from:

```
cid=$(docker create "$IMAGE")
sudo rm -rf /root/openbao-release
sudo docker cp "$cid:/app/ops/openbao" /root/openbao-release
docker rm "$cid"
```

Then, with the file of pieces on the server for the length of the move and shredded afterwards
(`sudo shred -u <the file>`):

```
sudo bash /root/openbao-release/switch-to-auto-unseal.sh --pieces-file <the file holding the pieces>
```

It proves the pieces against the running vault before it changes anything, stops the vault for
under a minute, restarts the containers that reach it at the end, and prints what to keep. Choose a
quiet hour and no deploy in flight: the restarts are what a deploy would also be doing. When it has
finished, delete `/root/openbao-release`: it is a copy of one release's files, and the next release
carries its own.

The vault must have been brought up by docker compose under the service name `vault` with its data
on a named volume, and the script refuses with a sentence if it was not.

## 3. gVisor, for the script sandbox

The script sandbox runs code nobody here wrote, and runs it only under gVisor: a server whose
docker has no `runsc` runtime is refused at save and in the plan, and the sandbox is never started
on docker's own runtime instead. gVisor is installed on the server and registered with docker.

1. **Install `runsc` from gVisor's own repository for your distribution**, following its own
   documentation. A distribution's own package of it may be years behind, and is not what the
   sandbox was written against. `runsc --version` says what you have.
2. **Register it with docker**, keeping a copy of the daemon's file first (skip the copy if there is
   no such file yet):

   ```
   sudo cp -a /etc/docker/daemon.json /etc/docker/daemon.json.bak
   sudo runsc install
   sudo dockerd --validate --config-file=/etc/docker/daemon.json
   ```

3. **Reload docker. Do not restart it.**

   ```
   sudo systemctl reload docker
   docker info --format '{{json .Runtimes}}'
   ```

   The second command must now list `runsc`. A reload makes the daemon read its configuration again
   without stopping, and a new runtime is among what it picks up, so no container moves. A
   **restart** stops the daemon, and unless it runs with `live-restore` (`docker info --format
   '{{.LiveRestoreEnabled}}'` says) every container on the host stops with it: the application, the
   worker, the database and the vault, and whatever else shares the machine. If the reload does
   not list `runsc`, put the daemon's file back from the copy, reload again, and find out why
   before considering a restart at an hour nobody is using the system.

4. **Prove it runs a container**, with an image already on the host so nothing is pulled:

   ```
   docker run --rm --runtime=runsc --network none --entrypoint sh <an image on this host> \
     -c 'dmesg | head -3; echo $((20 + 22))'
   ```

   It must print lines that mention gVisor, and `42`.

5. **Let a deploy report it.** The next deploy's optional services step reads the runtimes docker
   offers and keeps them, and from then on Install, Settings accepts `sandbox` in
   `INSTALL_SERVICES`. This needs the deploy hook of section 1: a hook from before the step never
   reports anything.

To undo: put the daemon's file back from the copy, `sudo systemctl reload docker`, and remove the
package.

## 4. The object store and the automation canvas

Both are optional services named in `INSTALL_SERVICES` (`objectstore` and `automation`), started by
every release as their own compose project after it measures the server's memory, with their
secrets and settings files put in place by the release as
[coolify.md](coolify.md) describes. What a release cannot do is two things that are yours:

- **The application connects to the object store when it next starts.** A release hands the
  application's key for the store to the vault after the store is running, and the application
  reads it once, at start. So the first release after `objectstore` is named starts the store, and
  the one after it, or a restart of the application and the worker, is when uploads begin to go
  there. The application's log says `object store connected` when it does.
- **The canvas has no address until you give it one.** Its editor is reached through your proxy, on
  an address of its own that needs a DNS record and a route to the canvas's port 80. Until
  `AUTOMATION_PUBLIC_URL` in `/opt/brain/settings/overlays.env` holds that address, the canvas runs
  and answers its health check and its tool calls, and staff cannot open the editor. The canvas
  costs 896 MiB: the editor, its egress proxy and its own database.

The two overlays share the object store's container with the trace ledger when both are named, and
share the store's access file: the application's identity and the ledger's are both in it, and
neither release step replaces the other's.
