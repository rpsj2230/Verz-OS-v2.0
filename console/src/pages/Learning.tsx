/**
 * Learning: what the system has learnt across every department, with the tiers kept apart.
 *
 * SCREEN 8 of `docs/screens.html` is the design of record: Govern section, four figures, a
 * "What changed" listing, and two cards underneath, one explaining the four tiers and one saying
 * why tier one notifies rather than asks. This is that layout in that order. Two things differ
 * and both are argued in `learningQuery.ts`: the listing is one table per tier rather than one
 * table with a tier column, which is `THREE_TIERS_ARE_THREE_TABLES`, and the undo control is drawn
 * only on a row the API offers it on, which is `UNDO_IS_ASKED_OF_THE_SERVER_ROW_BY_ROW`.
 *
 * **The rule the whole page encodes is the design's**: learning that narrows, personalises or
 * re-ranks applies by itself, and learning that widens, publishes or changes behaviour waits for
 * a person. The four-tier card is drawn from `brain.memory.tiers.BLAST_RADIUS` as the API sends
 * it, so the change kinds listed under each tier are the ones that really need it.
 *
 * **Undo is a confirmed write; promote and decide are not drawn.** SCREEN 8 draws Undo beside every
 * tier-one row, Promote beside tier two and Decide beside tier three. Since 2026-09-17 an undo is
 * stored, audited and read by recall, so a tier-one row the API offers it on carries the button,
 * and pressing it opens a confirmation in the sentence the API serves for what it will write. A row
 * undone says so and offers nothing. Nothing records agreement or a decision, so Promote and Decide
 * are still sentences under their tiers rather than buttons refused every time they are pressed.
 *
 * **What a learning says is not on this screen.** A learning record carries no text, on purpose,
 * and the statement it produced is read on the Memory screen under the capability it was formed
 * with. Each row names the change kind and the memory it is about.
 *
 * Nothing here decides who may see anything. Tier three is null for a reader who may not be told
 * where gated changes were routed, and the page says so instead of drawing an empty table.
 *
 * Imported statically rather than split, which is `Roles.tsx`' rule.
 *
 * Task ids: M27.7.21
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Chip } from "../ui/Chip";
import {
  LEARNING_API_PATH,
  RECENT_DAYS,
  TIER_WORDS,
  UNDO_API_PATH,
  consideredSentence,
  learnedRecently,
  readLearningPage,
  readUndone,
  undoBody,
  type LearningPage,
  type TierOne,
} from "./learningQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** The design's own label for this screen. */
export const LEARNING_HEADING = "Learning";

/** Under the heading. SCREEN 8's own account of the rule the page encodes, kept in its words. */
export const LEARNING_LEDE =
  "Learning that narrows, personalises or re-ranks applies by itself; learning that widens, " +
  "publishes or changes behaviour waits for a person. Tier one is listed so it can be undone, not " +
  "so it can be approved. Only tier three blocks.";

/** What a figure the design draws and nothing measures says instead of a number. */
export const NOT_RECORDED = "Not recorded on this install.";

/** Under the figures: what they count, so a count is never read as the company's. */
export const FIGURES_ARE_OF_WHAT_YOU_CAN_SEE =
  "Every figure counts the learnings listed below, which are the ones you may see.";

/** What a learning row does not show, and where it is read instead. */
export const STATEMENTS_ARE_ELSEWHERE =
  "A learning record carries no text. What a learning says is read on the Memory screen, under " +
  "the capability it was formed with.";

/** The control beside a tier-one row the API offers it on, and the confirmation's verb. */
export const UNDO_LABEL = "Undo";

/** The confirmation's way out. */
export const KEEP_IT = "Keep it";

/** Under tier one: where the control is and is not, in words a person can act on. */
export const WHERE_UNDO_IS_OFFERED =
  "Undo is offered on a change that is still in effect, where you hold the authority to undo " +
  "learning in the department its memory was formed in, and you signed in with a second factor. " +
  "Undoing writes a correction and deletes nothing: the Memory screen shows what changed.";

/** The state of a tier-one row a correction has taken out of effect. */
export const UNDONE = "undone";

/** In place of the Promote button beside tier two. */
export const PROMOTE_NOT_OFFERED =
  "Promote is not offered. A rule is promoted once enough separate conversations agree, and " +
  "nothing on this install records that agreement.";

/** In place of the Decide button beside tier three. */
export const DECIDE_NOT_OFFERED =
  "Decide is not offered. A gated change is decided by a person on a screen that records the " +
  "decision, and this screen records none.";

/** Tier three withheld from this reader. Not the same sentence as an empty tier. */
export const TIER_THREE_WITHHELD =
  "Where gated changes were routed is shown to a reader who holds the Scopes and departments " +
  "screen for the whole company, because each one names the department that decides it.";

/** An empty tier. */
export const NOTHING_IN_TIER = "Nothing in this tier.";

/** The design's hint on the notify card, in its own words. */
export const NOTIFY_DO_NOT_ASK =
  "Tier one lands silently and appears in a weekly digest with one-click undo. Nobody approves " +
  "every preference change; they skim one message and reverse what looks wrong. Negative signals " +
  "are always tier one: forgetting something wrong can never need permission, or the system stays " +
  "wrong while it waits.";

/** The design's digest control, which is not on this screen. */
export const DIGEST_NOT_HERE = "The weekly digest is not sent from this screen.";

function Figure({
  label,
  value,
  sub,
}: {
  readonly label: string;
  readonly value: number;
  readonly sub: string;
}) {
  return (
    <div className="fields__row">
      <dt>{label}</dt>
      <dd>
        <span>{String(value)}</span>
        <p className="note">{sub}</p>
      </dd>
    </div>
  );
}

function Figures({ page }: { readonly page: LearningPage }) {
  return (
    <section className="card">
      <h2>At a glance</h2>
      <dl className="fields" aria-label="Learning at a glance">
        <Figure
          label={`Learned in the last ${String(RECENT_DAYS)} days`}
          value={learnedRecently(page)}
          sub="tiers one and two"
        />
        <Figure
          label="Applied automatically"
          value={page.tierOne.length}
          sub="tier one, each reversible"
        />
        <Figure
          label="In shadow"
          value={page.tierTwo.length}
          sub="tier two, proving out"
        />
        {page.tierThree === null ? (
          <div className="fields__row">
            <dt>Waiting on a human</dt>
            <dd>
              <p className="note">{TIER_THREE_WITHHELD}</p>
            </dd>
          </div>
        ) : (
          <Figure
            label="Waiting on a human"
            value={page.tierThree.length}
            sub="tier three"
            />
        )}
      </dl>
      <p className="note">{FIGURES_ARE_OF_WHAT_YOU_CAN_SEE}</p>
    </section>
  );
}

function TierOneTable({
  rows,
  busy,
  onUndo,
}: {
  readonly rows: readonly TierOne[];
  readonly busy: boolean;
  readonly onUndo: (row: TierOne) => void;
}) {
  return (
    <div className="grid__scroll">
      <table className="grid__table">
        <caption className="grid__caption">Tier one learnings you can see</caption>
        <thead>
          <tr>
            <th scope="col">What it learned</th>
            <th scope="col">Memory</th>
            <th scope="col">State</th>
            <th scope="col">Undo would write</th>
            <th scope="col">
              <span className="visually-hidden">Undo</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.memory_id}>
              <td>{row.change}</td>
              <td>
                <code>{row.memory_id}</code>
              </td>
              <td>{row.in_effect ? "applied" : UNDONE}</td>
              <td>{row.control_writes}</td>
              <td>
                {row.undo_offered ? (
                  <button
                    className="button"
                    type="button"
                    disabled={busy}
                    aria-label={`${UNDO_LABEL} ${row.memory_id}`}
                    onClick={() => {
                      onUndo(row);
                    }}
                  >
                    {UNDO_LABEL}
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LearningAnswerView({ onChanged }: { readonly onChanged: (sentence: string) => void }) {
  const answer = useResource<unknown>(LEARNING_API_PATH);
  const [undoing, setUndoing] = useState<TierOne | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const undo = useCallback(
    (row: TierOne) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(UNDO_API_PATH, {
          method: "POST",
          body: undoBody(row.memory_id),
        });
        setBusy(false);
        setUndoing(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onChanged(readUndone(result.data).told);
      })();
    },
    [onChanged],
  );

  if (answer.failure) {
    return (
      <FailureNotice failure={answer.failure} />
    );
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }

  const page = readLearningPage(answer.data);
  const consequence = undoing === null ? "" : (page.undoSays[undoing.control_writes] ?? "");

  return (
    <>
      {page.staleness === null ? null : <p className="note">{page.staleness}</p>}
      {failure === null ? null : <FailureNotice failure={failure} />}

      <Figures page={page} />

      <section className="card">
        <h2>What changed</h2>
        <p className="note">{STATEMENTS_ARE_ELSEWHERE}</p>

        <h3>Tier one: applied automatically</h3>
        {page.tierOne.length === 0 ? (
          <p className="note">{NOTHING_IN_TIER}</p>
        ) : (
          <TierOneTable
            rows={page.tierOne}
            busy={busy}
            onUndo={(row) => {
              setFailure(null);
              setUndoing(row);
            }}
          />
        )}
        {undoing === null || consequence === "" ? null : (
          <ConfirmAction
            question={`${UNDO_LABEL} the ${undoing.change} learning ${undoing.memory_id}?`}
            consequence={consequence}
            confirmLabel={UNDO_LABEL}
            cancelLabel={KEEP_IT}
            busy={busy}
            onConfirm={() => {
              undo(undoing);
            }}
            onCancel={() => {
              setUndoing(null);
            }}
          />
        )}
        <p className="note">{WHERE_UNDO_IS_OFFERED}</p>

        <h3>Tier two: in shadow</h3>
        {page.tierTwo.length === 0 ? (
          <p className="note">{NOTHING_IN_TIER}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">Tier two learnings you can see</caption>
              <thead>
                <tr>
                  <th scope="col">What it learned</th>
                  <th scope="col">Memory</th>
                  <th scope="col">Evidence</th>
                  <th scope="col">State</th>
                </tr>
              </thead>
              <tbody>
                {page.tierTwo.map((row) => (
                  <tr key={row.memory_id}>
                    <td>{row.change}</td>
                    <td>
                      <code>{row.memory_id}</code>
                    </td>
                    <td>{row.evidence.join(", ")}</td>
                    <td>{row.promote_ready ? "ready to promote" : "proving"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="note">{PROMOTE_NOT_OFFERED}</p>

        <h3>Tier three: waiting on a human</h3>
        {page.tierThree === null ? (
          <p className="note">{TIER_THREE_WITHHELD}</p>
        ) : page.tierThree.length === 0 ? (
          <p className="note">{NOTHING_IN_TIER}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">Gated changes and where they were routed</caption>
              <thead>
                <tr>
                  <th scope="col">Memory</th>
                  <th scope="col">Dept</th>
                  <th scope="col">State</th>
                </tr>
              </thead>
              <tbody>
                {page.tierThree.map((row) => (
                  <tr key={row.memory_id}>
                    <td>
                      <code>{row.memory_id}</code>
                    </td>
                    <td>{row.department}</td>
                    <td>waiting</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {page.tierThree === null ? null : <p className="note">{DECIDE_NOT_OFFERED}</p>}
        <p className="note">{consideredSentence(page.considered)}</p>
      </section>

      <section className="card">
        <h2>The four tiers</h2>
        <dl className="fields" aria-label="The four tiers">
          {page.tiers.map((rule) => (
            <div className="fields__row" key={rule.tier}>
              <dt>
                <Chip label={String(rule.tier)} /> {TIER_WORDS[rule.tier]?.what ?? ""}
              </dt>
              <dd>
                <span>{TIER_WORDS[rule.tier]?.how ?? ""}</span>
                <p className="note">{rule.changes.join(", ")}</p>
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="card">
        <h2>Notify, do not ask</h2>
        <p className="note">{NOTIFY_DO_NOT_ASK}</p>
        <dl className="fields" aria-label="Notify, do not ask">
          <div className="fields__row">
            <dt>Undone after the digest, last 90 days</dt>
            <dd>
              <p className="note">{NOT_RECORDED}</p>
            </dd>
          </div>
          <div className="fields__row">
            <dt>Median time a tier three change waits</dt>
            <dd>
              <p className="note">{NOT_RECORDED}</p>
            </dd>
          </div>
        </dl>
        <p className="note">{DIGEST_NOT_HERE}</p>
      </section>
    </>
  );
}

export function Learning() {
  // A counter rather than a boolean, so two undos in a row read the review twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [changed, setChanged] = useState<string | null>(null);
  const onChanged = useCallback((sentence: string) => {
    setChanged(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <h1>{LEARNING_HEADING}</h1>
      <p className="lede">{LEARNING_LEDE}</p>
      {changed === null ? null : (
        <p className="note" role="status">
          {changed}
        </p>
      )}
      <LearningAnswerView key={generation} onChanged={onChanged} />
    </article>
  );
}
