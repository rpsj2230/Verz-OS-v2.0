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
| M12.3.2 | install and CI | Edit saved 0.0.1 (digest 206fc727, "Edited from 71f38809") as a new version waiting for review while 0.0.0 stayed listed and readable; the pin half (no agent's pin moves) is tests/unit/test_skill_versions route and database tests, green on main |
| M12.4.6 | install and CI | Approving my own import of 0.0.1 succeeded and Govern > Audit, searched for self_approved, lists "skill acceptance-test-weekly-note, change self_approved, digest 206fc727"; the other half (an import by someone else needs a different reviewer) is the skill review route tests, green on main |
| M38.4.1.2 | CI | tests/invariants/test_cassettes.py::test_every_connector_that_exists_is_tested_against_the_recordings, run by "Lint, types, invariants", green on main at d426e3d3 (run 36427359504); every shipped connector has its own cassette and replays through its own code |
