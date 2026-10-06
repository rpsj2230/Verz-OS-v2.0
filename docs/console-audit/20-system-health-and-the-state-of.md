### System health and the state of every service

- **Screens:** `/`, `/models`, `/runs`
- **Tables:** `ops.halt`
- **Installation values:** none
- **Measured here:** 5 routes, 3 called by no screen; 0 write routes, 0 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/overview` | `/` |
| `GET /api/v1/console/overview/figures` | `/` |
| `GET /api/v1/halts` | **no screen** |
| `POST /api/v1/halts` | **no screen** |
| `POST /api/v1/halts/resume` | **no screen** |

- **Gap.** The install cannot be stopped or resumed from the console yet: GET, POST /api/v1/halts and POST /api/v1/halts/resume stop and resume through brain.ops.halt_store, and no Stop screen or header control calls them. Open leaf `M27.12.4`.
