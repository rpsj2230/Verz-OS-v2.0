### Import and export

- **Screens:** `/import-export`
- **Tables:** `ops.data_export`
- **Installation values:** none
- **Measured here:** 2 routes, 0 called by no screen; 1 write routes, 1 with all three proofs; 1 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/data-transfer` | `/import-export` |
| `POST /api/v1/data-transfer/exports` | `/import-export` |

- **Gap.** Nothing can be imported, and the audit trail is the only export. Open leaf `M27.8.16`.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/data-transfer/exports` | `/import-export` | `test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it` in `tests/unit/test_data_export_store.py` (database, in CI) | `test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it` in `tests/unit/test_data_export_store.py` (database, in CI) | `test_the_listing_offers_the_export_to_a_reader_who_may_take_it_and_shows_only_their_own` in `tests/unit/test_data_transfer_routes.py` |
