# Proof recorded on 2026-09-28

A proof commit must change a file or a rebase merge drops it (see 2026-09-21), so the evidence for
each claim is kept here. Install evidence was read on the owner's install, read-only, at migration
head 0115 (commit c57a512); CI evidence names the test files the unit and invariant jobs run, which
passed on main at c57a512 and locally against PostgreSQL 18 with pgvector (263 passed).

| Task | Where proved | Evidence |
| --- | --- | --- |
| M10.1.1 | CI | tests/unit/test_channel_pipeline.py and test_channels.py: every adapter in brain.channels exposes normalise, send and capabilities, and a channel added as one file is registered with no list edited |
| M10.1.5 | CI | tests/unit/test_channel_pipeline.py, test_channels.py, test_channel_correction.py, test_cards.py: the one send path refuses a body that drops its label as cannot_carry |
| M7.3.1 | CI | tests/unit/test_knowledge_chunking.py and tests/invariants/test_knowledge_invariants.py: chunks respect the size bounds and overlap |
| M7.2.2 | CI | tests/unit/test_knowledge_chunking.py and test_text_path.py: a table survives chunking as whole rows, Word tables as pipe rows |
| M7.3.2 | install and CI | know.chunk on the install carries document_id, ordinal, page, span_start and span_end (position), department and visibility (scope) and owner_id; tests/unit/test_knowledge_chunking.py fills them |
| M7.4.1 | install | know.item on the install has owner_id, visibility and department (scope), verified_by, verified_at, review_by and state; the content is know.chunk.body |
| M7.4.2 | install | know.item on the install carries ck_item_visibility: company, department or personal, and nothing else |
| M3.2.2 | install and CI | gate.channel_event on the install has pk_channel_event PRIMARY KEY (channel, external_id); tests/unit/test_channel_pipeline.py shows a redelivered event claimed once and answered once |

## Checked in the console on the owner's install, signed in as the owner (2026-09-28, 20:01 SGT)

| Task | Where proved | Evidence |
| --- | --- | --- |
| M3.4.2 | install | A question asked on Ask ("Install check (Claude, 28 Sep): what can you help me with?") left its obs.request_telemetry row with risk_score 0, routed_lane answer, lane_basis default and selection_stage default, written when the request was decided; read back read-only |
| M12.4.12 | install | On Skills, pasting a SKILL.md whose description opened "Formats a weekly status note" was refused on screen: "does not open by saying when the skill is used; begin it with 'Use when'" (reference 12c8e59b), and nothing was added |
| M12.2.1 | install | The same form parsed and accepted a SKILL.md with name and a "Use when" description (acceptance-test-weekly-note 0.0.0, digest 71f38809), after refusing the malformed one above |
| M12.2.5 | install | The accepted skill was listed "waiting for review" with Approve, Reject and Edit, and the page said it "cannot be assigned to an agent until it is approved" |
| M12.4.13 | install | Adding it with categories "test, reporting" put the chips "reporting" and "test" on the Skills screen's library filter, beside "Every category" |
| M12.2.6 | install | After an edit the review pane showed "What changed since 0.0.0": version 0.0.0 to 0.0.1 and the body line "three bullet points" replaced by "four bullet points", compared with digest 71f38809 |
| M12.3.2 | install and CI | Edit saved 0.0.1 (digest 206fc727, "Edited from 71f38809") as a new version waiting for review while 0.0.0 stayed listed and readable; the pin half is tests/unit/test_skill_routes.py::test_an_edit_waits_for_review_as_a_new_version_while_the_agent_keeps_its_pin, green on main |
| M12.4.6 | install and CI | Approving my own import of 0.0.1 succeeded and Govern > Audit, searched for self_approved, lists "skill acceptance-test-weekly-note, change self_approved, digest 206fc727"; the other half is tests/unit/test_skill_routes.py::test_the_reviewer_approves_and_a_reader_who_only_adds_is_refused_the_decision and tests/unit/test_skill_store.py::test_a_self_decision_must_say_so_and_only_an_approved_skill_is_assigned_in_the_tables, green on main |
| M38.4.1.2 | CI | tests/invariants/test_cassettes.py::test_every_connector_that_exists_is_tested_against_the_recordings, run by "Lint, types, invariants", green on main at d426e3d3 (run 36427359504); every shipped connector has its own cassette and replays through its own code |
| M10.2.1, M10.3.3, M10.4.5, M10.6.3 | install | The install's own acceptance check a_webhook_channel_receives_once_and_stops_both_ways passed at commit 604e41d (ran 2026-09-28T15:36:34Z, /api/acceptance.json): a bad signature refused before the body was read, a signed message claimed once and its redelivery never, an unbound sender prompted, a reply's reach re-checked at send time, and switched off it neither received nor sent |
| M7.1.1, M7.2.5, M7.4.3, M7.6.3, M7.7.1 | install | documents_are_answered_in_their_department_only passed at 604e41d (15:36:35Z): Markdown, PDF and Word uploaded into acceptance_a with no worker were found by a member there with department, level and owner on each passage; a reader in acceptance_b got what a search for nothing gets; no upload was placed wider than its uploader may add; a damaged PDF and an unread type were refused by name |
| M23.2.1 | install | unusual_volume_is_found_per_person passed at 604e41d (15:36:36Z): twenty asks against a usual one a day scored unusual on the Limits screen from the install's request ledger; usual asking and machine traffic not flagged; a reader whose grant does not reach the person shown nobody |
| M23.2.2 | install | repeated_refusals_raise_a_denial_notice passed at 604e41d (15:36:36Z): repeated refusals written to the ledger were read back as a pattern by the hourly digest and routed to a company-wide holder naming a shape, never the thing; two refusals raised nothing |
| M1.8.3 | install | a_head_reads_their_own_peoples_audit_entries_only passed at 604e41d: the head of acceptance_a, given audit reads by the staff sync's own rewrite, read only the entries of people placed there; a joiner the next night, not a leaver; a member read nothing |
| M23.1.1, M23.1.2, M23.1.3, M23.1.5 | install | asking_past_a_window_is_refused_with_a_retry_hint passed when the acceptance suite was run by hand inside the app container at 604e41d (`python -m brain.ops.acceptance_run`: "6 passed, 0 failed, 0 not run"): in the install's own cache a person, a channel and an agent each asked past a window of two a minute were refused with a retry hint, and refused asks were not counted. The worker's own run reported it not run because the worker is given no cache address |
| M10.2.2, M10.2.6 | install | The worker's acceptance run at commit ed5a1c1 (2026-09-28T20:17:30Z, /api/acceptance.json) passed a_lark_group_message_is_answered_only_when_it_names_the_bot: a signed Lark event through the install's events path answered a group message only when it named the bot, and a direct message always |
| M10.4.1, M10.4.2, M10.2.5, M10.4.3, M10.4.4 | install | The same run passed a_lark_group_hears_its_floor_and_the_asker_reads_the_rest_alone, with CH2's binding reader live: the group got the answer at the floor of everyone present, the asker's fuller answer went by the channel's ephemeral send to them alone, where nothing could be said the ladder ended at a link to Ask, and the room was read again before sending (the vendor send recorded, not delivered) |
| M12.2.4 | install | The same run passed a_pasted_or_uploaded_skill_waits_undecided_and_unread: a zip holding one SKILL.md was accepted undecided and a zip with a `../` path was refused |
