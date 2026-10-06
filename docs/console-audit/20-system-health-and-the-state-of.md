### System health and the state of every service

- **Screens:** `/`, `/models`, `/runs`, `/stop`
- **Tables:** `ops.halt`
- **Installation values:** none
- **Measured here:** 5 routes, 2 called by no screen; 2 write routes, 2 with all three proofs; 0 gaps.

| Route | Called by |
| --- | --- |
| `GET /api/v1/console/overview` | `/` |
| `GET /api/v1/console/overview/figures` | `/` |
| `GET /api/v1/halts` | `/stop` |
| `POST /api/v1/halts` | **no screen** |
| `POST /api/v1/halts/resume` | **no screen** |

No gap recorded.

**Every write to this area, followed to the system.**

| Write | Called by | Row | Audit entry | Behaviour |
| --- | --- | --- | --- | --- |
| `POST /api/v1/halts` | **no screen** | `test_on_a_real_database_a_stop_needs_no_words_and_a_resume_does` in `tests/unit/test_halt_store.py` (database, in CI) | `test_on_a_real_database_a_stop_needs_no_words_and_a_resume_does` in `tests/unit/test_halt_store.py` (database, in CI) | `test_a_question_asked_while_everything_is_stopped_is_turned_away_in_the_halt_s_words` in `tests/unit/test_halt_store.py` (database, in CI) |
| `POST /api/v1/halts/resume` | **no screen** | `test_on_a_real_database_a_stop_needs_no_words_and_a_resume_does` in `tests/unit/test_halt_store.py` (database, in CI) | `test_on_a_real_database_a_stop_needs_no_words_and_a_resume_does` in `tests/unit/test_halt_store.py` (database, in CI) | `test_a_resume_from_the_screen_needs_words_and_says_whose_stop_it_lifts` in `tests/unit/test_halt_store.py` (database, in CI) |
