### Logs and errors

- **Screens:** `/errors`, `/logs`
- **Tables:** `obs.application_log`
- **Installation values:** none
- **Measured here:** 2 routes, 0 called by no screen; 0 write routes, 0 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/errors` | `/errors` |
| `GET /api/v1/logs` | `/logs` |

- **Gap.** The background worker's own output and every debug line are not kept, and information lines are a sample. Recorded: The Logs screen says worker_output_is_not_kept, debug_is_not_kept and info_is_a_sample: the worker prints to its container rather than logging through structlog, and brain.ops.log_capture keeps warnings and above and bounds the rest.
