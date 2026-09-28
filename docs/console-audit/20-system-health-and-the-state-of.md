### System health and the state of every service

- **Screens:** `/models`, `/runs`
- **Tables:** `ops.halt`
- **Installation values:** none
- **Measured here:** 1 routes, 1 called by no screen; 0 write routes, 0 with all three proofs; 2 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/overview` | **no screen** |

- **Gap.** The install cannot be stopped or resumed from the console: 0136 stores a halt and its resume, GET /api/v1/console/overview reads the halts in force, and no route or Stop control writes one yet. Open leaf `M27.12.4`.
- **Gap.** The state of each service the install runs on is not shown. Recorded: /health/ready answers the orchestrator outside /api/v1, and GET /api/v1/console/overview serves the same parts beside Needs you with no screen reading it yet. Each rung's circuit breaker is shown, on the Models and health screen from GET /api/v1/models/providers, replayed from the attempts the executor recorded.
