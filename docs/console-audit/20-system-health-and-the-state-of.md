### System health and the state of every service

- **Screens:** `/models`, `/runs`
- **Tables:** `ops.halt`
- **Installation values:** none
- **Measured here:** 0 routes, 0 called by no screen; 0 write routes, 0 with all three proofs; 2 gaps.

- **Gap.** The install cannot be stopped or resumed from the console: 0136 stores a halt and its resume, and no store, route or Stop control reads or writes the table yet. Open leaf `M27.12.4`.
- **Gap.** The state of each service the install runs on is not shown. Recorded: /health/ready answers the orchestrator outside /api/v1 with no screen reading it. Each rung's circuit breaker is shown, on the Models and health screen from GET /api/v1/models/providers, replayed from the attempts the executor recorded.
