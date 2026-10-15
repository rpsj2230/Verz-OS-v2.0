The website widget's answer written by the model from the public passages, under a daily cap (needs item 139, decided B on 2026-10-13). Leaves M10.7.6, M10.7.7, M10.7.8 (new), register row DEC-139B.

- Off by default: the `widget_model_answers` feature ships switched off. Off, the widget answers with the published passages as before and no model is called.
- On: the model is handed the visitor's question and the public passages and nothing else (no tool, no memory), and the passages stay beside its sentence. A question nothing was found for never reaches the model.
- The cap is a new knob on the Rate limits screen (`widget_daily_spend`, minor units a day). Each answer's cost is written to the spend ledger under the widget's own name and department, and the day's total (midnight UTC) is one sum over those rows. Over the cap, unpriced, no model, or no answer: the visitor gets the passages. A counter in a table of its own was rejected as a second place a cost is written, so no migration.
- Install check `acceptance_checks_widget_answers` (order 1510), shown failing four ways; the model is a stand-in answering in the process, so a real provider's wording stays unproved.

Reused: widget_routes and public_searcher, ModelCalls, Meter, pricing.cost_of, spend_store.record, the tuning knobs and the Rate limits screen, the feature switches, the coauthor route's call pattern.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
