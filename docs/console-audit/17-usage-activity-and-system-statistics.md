### Usage, activity and system statistics

- **Screens:** `/usage`, `/adoption`, `/spend`, `/questions`, `/quality`, `/service-levels`, `/me`, `/company/estate`, `/company/activity`, `/company/consumption`
- **Tables:** `ops.question_asked`, `ops.question_gap`, `ops.report_refresh`, `ops.spend_actual`, `obs.request_telemetry`
- **Installation values:** none
- **Measured here:** 10 routes, 0 called by no screen; 0 write routes, 0 with all three proofs; 0 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/company/activity` | `/company/activity` |
| `GET /api/v1/company/consumption` | `/company/consumption` |
| `GET /api/v1/company/estate` | `/company/estate` |
| `GET /api/v1/me/workspace` | `/me` |
| `GET /api/v1/report/adoption` | `/adoption` |
| `GET /api/v1/report/quality` | `/quality` |
| `GET /api/v1/report/questions` | `/department`, `/questions` |
| `GET /api/v1/report/service-levels` | `/service-levels` |
| `GET /api/v1/report/spend` | `/spend` |
| `GET /api/v1/report/usage` | `/adoption`, `/department`, `/usage` |

No gap recorded.
