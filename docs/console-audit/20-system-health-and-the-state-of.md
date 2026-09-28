### System health and the state of every service

- **Screens:** `/`, `/models`, `/runs`
- **Tables:** `ops.halt`
- **Installation values:** none
- **Measured here:** 2 routes, 0 called by no screen; 0 write routes, 0 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/overview` | `/` |
| `GET /api/v1/console/overview/figures` | `/` |

- **Gap.** The install cannot be stopped or resumed from the console: 0136 stores a halt and its resume, GET /api/v1/console/overview reads the halts in force, and no route or Stop control writes one yet. Open leaf `M27.12.4`.
