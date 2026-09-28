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
