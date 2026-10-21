### Version, build and deployment information

- **Screens:** `/updates`, `/install`
- **Tables:** `ops.deployment_record`
- **Installation values:** `INSTALL_UPDATE_MODE`
- **Measured here:** 4 routes, 3 called by no screen; 0 write routes, 0 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/handover` | **no screen** |
| `GET /api/v1/install/updates` | `/updates` |
| `PUT /api/v1/handover/owners` | **no screen** |
| `PUT /api/v1/handover/review` | **no screen** |

- **Gap.** No page draws the handover pack: the service level statement, the subprocessors, the named owners and the booked review are served and nothing links to them. Recorded: brain.handover_routes serves them to the install authority (M30.5.4, M30.6.6, M37.4.2.4, M37.4.3.3, M37.4.3.5) and the console has not been given a Handover page.
