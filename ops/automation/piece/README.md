# The Company Brain piece for Activepieces

One action, **Call a tool**, which posts one tool name and one argument bag to
`POST /api/v1/automation/tool-call` with the automation's own credential as a bearer. What the
request contains is `contract.json`, and `tests/unit/test_automation_piece_package.py` holds that
file equal to the route the application mounts.

## What is in this directory

| Path | What it is |
| --- | --- |
| `contract.json` | The one request, stated once. |
| `lib/call.ts` | Builds that request. No dependency, so Node runs its tests directly. |
| `lib/index.ts` | The piece: authentication, the action and its inputs, around `call.ts`. |
| `scripts/build.mjs` | Compiles `lib/` into `dist/` and stages the package the canvas installs. |
| `test/call.test.ts` | The request builder, held to `contract.json`. |
| `test/load.test.ts` | The built package, loaded the way the canvas engine loads a piece. |
| `package.json`, `package-lock.json` | Exact versions, and the lock that `npm ci` installs. |

`node_modules/` and `dist/` are never committed and never carried in a release.

## Why these versions

**`@activepieces/pieces-framework` 0.7.42.** The canvas runs `activepieces/activepieces:0.39.5`
(`docker-compose.automation.yml`). The Activepieces source at tag `0.39.5` declares
`packages/pieces/community/framework/package.json` as version 0.7.42. The registry agrees:
0.7.42 was published on 2024-12-05, the image was pushed on 2025-01-20, and 0.7.43 did not
appear until 2025-02-14. So 0.7.42 is both the framework that release was built with and the
newest one that existed when it shipped. A newer framework can describe properties and
metadata the 0.39.5 server does not know. The unit test reads the image tag from the compose
file and fails if the tag changes without the framework being re-pinned.

**Node 18 types (`@types/node` 18.19.130).** The image is built `FROM node:18.20.5`, so the
compiler refuses any Node API the sandbox does not have. 18.19.130 is the newest 18.x type
release.

**TypeScript 5.8.3**, the version the console already pins.

**Two things the registry says about 0.7.42 that were recorded, not fixed.**

- `npm audit` reports `nanoid` 3.3.6 (one high and two moderate advisories, via the framework
  and `@activepieces/shared` 0.10.132). The fixed framework releases are 0.7.43 and later,
  which postdate the image. This piece never calls `nanoid`.
- Neither `@activepieces` package declares a licence in its registry metadata.
  `python -m brain.ops.sweeps dependencies` reads the Python environment only, so it does not
  check any npm package, this one included.

## Building it

You need Node 22.18 or later on the machine that builds it. The tests use Node's own type
stripping. The piece itself runs on the canvas's Node 18.

From `ops/automation/piece`:

1. `npm ci --ignore-scripts`
2. `npm run build`
3. `npm test` (eleven tests, all of which should pass)
4. `npm run package`

The last step writes `dist/piece-brain-tool-call-0.1.0.tgz`. **Its dependencies are bundled
inside it.** The canvas reaches the internet only through the egress proxy, and the npm
registry is not on the allowlist, so a piece that had to download its framework at install
could not be installed there.

## Loading it into the canvas

Activepieces documents a private piece as a tarball uploaded from **Platform Admin, Pieces**, and
marks that as an enterprise feature. The canvas here runs the Community Edition.

In Community Edition 0.39.5 the server still offers the same upload to a signed-in user, as
`POST /api/v1/pieces`, and accepts an archive at platform scope. The screen hides the option,
so the steps below use the API directly. They were read from the 0.39.5 source and have not yet
been run against a live canvas.

1. **Copy the tarball** from step 4 above onto a machine that can open the canvas's address.
   That address is the `AUTOMATION_PUBLIC_URL` value in the install's environment file.

2. **Sign in to the canvas and keep the token.** Use the email and password of the canvas
   account you created when the canvas was first opened. In PowerShell:

   ```
   $canvas = "<AUTOMATION_PUBLIC_URL>"
   $body = @{ email = "<your canvas email>"; password = "<your canvas password>" } | ConvertTo-Json
   $token = (Invoke-RestMethod -Method Post -Uri "$canvas/api/v1/authentication/sign-in" -ContentType "application/json" -Body $body).token
   ```

3. **Upload the piece.** The name and the version must be the `name` and `version` in
   `package.json`, which are `piece-brain-tool-call` and `0.1.0`. `curl.exe` is used here
   because PowerShell 5.1 cannot send a multipart form:

   ```
   curl.exe -X POST "$canvas/api/v1/pieces" -H "authorization: Bearer $token" -F packageType=ARCHIVE -F scope=PLATFORM -F pieceName=piece-brain-tool-call -F pieceVersion=0.1.0 -F "pieceArchive=@piece-brain-tool-call-0.1.0.tgz"
   ```

   A successful upload answers with the piece's metadata, including `"displayName":"Company
   Brain"`. An error that mentions the engine means the canvas could not load the package. Send
   the whole response back rather than retrying.

4. **Check it in a flow.** Open any flow in the canvas and add a step. Search for
   **Company Brain** and choose **Call a tool**.

5. **Create the connection it asks for.**
   - **Application address on the tool network**: `http://app:8000`. `app` is the application's
     service name in `docker-compose.yml`, and 8000 is the port its image listens on. This is
     the private `tool-api` network, never the public hostname.
   - **Automation credential**: the `bap.` credential issued when this automation was
     registered, shown once. A person's own sign-in token is refused before anything is sent.

6. **To ship a change**, raise `version` in `package.json` and repeat from the build. A second
   upload under the same name and version is not a replacement.

## What this does not yet prove

- That the canvas's own package manager installs the bundled tarball offline. `npm` does,
  measured with an empty cache and `--offline`. The image installs pieces with `pnpm` 9.15,
  and that has not been run.
- That a call succeeds end to end. On a deployed process nothing yet issues an automation
  credential or constructs the gate wiring the route needs, so today the route refuses every
  credential.
