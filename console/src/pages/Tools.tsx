/**
 * Tools: every tool this install offers, what it needs and does, and the switch that stops one.
 *
 * One card per tool, in the API's order. The effect is drawn in the product's three words, the
 * owner's sensitive effect as his own sentence, and the stops this reader may see beneath. The
 * switches offered are the ones the API says this reader may throw: the install's when their grant
 * is over everything, and each department their grant names. Stopping takes an optional note and
 * starting again a reason, `brain.ops.halt`'s asymmetry, and both are confirmed.
 *
 * **Nothing here decides who may switch.** The route asks for `admin:tool` at the place the switch
 * names and refuses everybody else, so a button drawn by mistake is a button the API refuses.
 *
 * **A write is followed by a fresh request**, keyed on a counter, for `Sessions.tsx`' reason: the
 * page shows what the database holds, not what it sent.
 *
 * Task ids: M12.1.1, M12.1.3, M12.1.4, M12.3.8, M12.4.3
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Chip } from "../ui/Chip";
import { FailureNotice } from "../ui/FailureNotice";
import { when } from "./sessionsQuery";
import {
  A_SWITCH_ONLY_NARROWS,
  EFFECT_SENTENCES,
  EFFECT_WORDS,
  EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  KEEP_IT,
  NO_LONGER_OFFERED,
  NO_TOOLS,
  NOTE_LABEL,
  OFF_FOR_THE_INSTALL,
  ON,
  READING_TOOLS,
  REASON_LABEL,
  RUNG_WORDS,
  SENSITIVE_EFFECT_SENTENCES,
  THE_ASKER_IS_NEVER_TOLD,
  TOOLS_API_PATH,
  TOOLS_CRUMB,
  TOOLS_LABEL,
  TOOLS_LEDE,
  UNREADABLE_ANSWER,
  choiceConsequence,
  choiceLabel,
  choiceQuestion,
  choicesFor,
  readChanged,
  readTools,
  stopSentence,
  switchBody,
  switchPath,
  switchedSentence,
  type SwitchChoice,
  type ToolRow,
  type ToolsBody,
} from "./toolsQuery";

function status(row: ToolRow): string[] {
  const words: string[] = [];
  if (row.off_for_install !== null && row.off_for_install !== undefined) {
    words.push(OFF_FOR_THE_INSTALL);
  }
  for (const stop of row.stopped_for) {
    words.push(`Stopped for ${stop.department ?? ""}`);
  }
  return words.length === 0 ? [ON] : words;
}

function ToolCard({
  row,
  body,
  busy,
  onChoose,
}: {
  readonly row: ToolRow;
  readonly body: ToolsBody;
  readonly busy: boolean;
  readonly onChoose: (choice: SwitchChoice) => void;
}) {
  const id = `tool-${row.name.replace(/[^a-z0-9]/g, "-")}`;
  const effect = EFFECT_WORDS[row.effect] ?? row.effect;
  const sensitive =
    row.sensitive_effect === null || row.sensitive_effect === undefined
      ? null
      : (SENSITIVE_EFFECT_SENTENCES[row.sensitive_effect] ?? row.sensitive_effect);
  const stops = [
    ...(row.off_for_install === null || row.off_for_install === undefined ? [] : [row.off_for_install]),
    ...row.stopped_for,
  ];
  return (
    <section className="card" aria-labelledby={id}>
      <h2 id={id}>
        <code>{row.name}</code> <Chip label={effect} />{" "}
        {status(row).map((word) => (
          <Chip key={word} label={word} />
        ))}
      </h2>
      <p>{row.description}</p>
      <dl className="fields">
        <div className="fields__row">
          <dt>Needs</dt>
          <dd>
            <code>{row.capability}</code>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Effect</dt>
          <dd>
            {EFFECT_SENTENCES[row.effect] ?? row.effect}
            {sensitive === null ? null : ` ${sensitive}`}
          </dd>
        </div>
        <div className="fields__row">
          <dt>Result</dt>
          <dd>{row.result_contract === "opaque" ? "Opaque: returned whole to those allowed it" : "Typed: redacted field by field"}</dd>
        </div>
        <div className="fields__row">
          <dt>Leash at most</dt>
          <dd>{RUNG_WORDS[row.leash_at_most] ?? row.leash_at_most}</dd>
        </div>
        <div className="fields__row">
          <dt>Runs as</dt>
          <dd>{row.identity_mode === "service" ? "A shared service credential" : "The person asking"}</dd>
        </div>
      </dl>
      {row.registered ? null : <p className="note">{NO_LONGER_OFFERED}</p>}
      {stops.map((stop) => (
        <p className="note" key={`${stop.department ?? ""}-${stop.switched_off_at}`}>
          {stopSentence(stop, when)}
        </p>
      ))}
      <div className="form-actions">
        {choicesFor(row, body).map((choice) => (
          <button
            key={`${choice.department ?? ""}`}
            type="button"
            className="button"
            disabled={busy || !row.registered}
            aria-label={`${choiceLabel(choice)}: ${row.name}`}
            onClick={() => {
              onChoose(choice);
            }}
          >
            {choiceLabel(choice)}
          </button>
        ))}
      </div>
    </section>
  );
}

function ToolList({ onSwitched }: { readonly onSwitched: (sentence: string) => void }) {
  const answer = useResource<unknown>(TOOLS_API_PATH);
  const [confirming, setConfirming] = useState<SwitchChoice | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const flip = useCallback(
    (choice: SwitchChoice, typed: string) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(switchPath(choice.tool), {
          method: "POST",
          body: switchBody(choice, typed),
        });
        setBusy(false);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setConfirming(null);
        setReason("");
        setFailure(null);
        onSwitched(switchedSentence(choice, readChanged(result.data) ?? true));
      })();
    },
    [onSwitched],
  );

  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_TOOLS}
      </p>
    );
  }
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  const body = readTools(answer.data);
  if (body === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }

  const facts = [
    body.a_switch_only_narrows === false ? null : A_SWITCH_ONLY_NARROWS,
    body.the_asker_is_never_told === false ? null : THE_ASKER_IS_NEVER_TOLD,
    body.every_change_is_in_the_audit_trail === false ? null : EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  ].filter((one): one is string => one !== null);
  const needed = body.reason_to_switch_on ?? 12;

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {confirming === null ? null : (
        <ConfirmAction
          question={choiceQuestion(confirming)}
          consequence={choiceConsequence(confirming)}
          details={
            <label className="control-label">
              {confirming.on ? `${REASON_LABEL} (at least ${needed} characters)` : NOTE_LABEL}{" "}
              <textarea
                className="form-control"
                name="reason"
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                }}
              />
            </label>
          }
          confirmLabel={choiceLabel(confirming)}
          cancelLabel={KEEP_IT}
          busy={busy}
          onConfirm={() => {
            flip(confirming, reason);
          }}
          onCancel={() => {
            setConfirming(null);
            setReason("");
          }}
        />
      )}
      {body.tools.length === 0 ? <p className="note">{NO_TOOLS}</p> : null}
      {body.tools.map((row) => (
        <ToolCard
          key={row.name}
          row={row}
          body={body}
          busy={busy}
          onChoose={(choice) => {
            setFailure(null);
            setReason("");
            setConfirming(choice);
          }}
        />
      ))}
      {facts.length === 0 ? null : (
        <section className="card" aria-labelledby="tools-facts">
          <h2 id="tools-facts">What a switch does</h2>
          {facts.map((one) => (
            <p key={one}>{one}</p>
          ))}
        </section>
      )}
    </>
  );
}

export function Tools() {
  // A counter rather than a boolean, so two switches in a row remount twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [switched, setSwitched] = useState<string | null>(null);
  const onSwitched = useCallback((sentence: string) => {
    setSwitched(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{TOOLS_CRUMB}</p>
      <h1>{TOOLS_LABEL}</h1>
      <p className="lede">{TOOLS_LEDE}</p>
      {switched === null ? null : (
        <p className="note" role="status">
          {switched}
        </p>
      )}
      <ToolList key={generation} onSwitched={onSwitched} />
    </article>
  );
}
