/**
 * Features: which genuinely new features this install has switched on, and the switch.
 *
 * One card per feature, in the order `brain.ops.features` declares them. Switching is confirmed,
 * and the confirmation's consequence is the product's own sentence for that direction: what the
 * feature lets somebody do when it goes on, and what stays true when it goes off. A success says
 * which feature is now on or off; a failure is the API's sentence with its reference.
 *
 * **Nothing here decides who may switch.** The route asks for `admin:feature` over everything and
 * refuses everybody else before it reads anything, so a reader who may not switch never sees this
 * page's list at all, only the API's refusal.
 *
 * **A write is followed by a fresh request**, keyed on a counter, for `Sessions.tsx`' reason: the
 * page shows what the database holds, not what it sent.
 *
 * Task ids: none
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Chip } from "../ui/Chip";
import { FailureNotice } from "../ui/FailureNotice";
import {
  CANNOT_SWITCH_HEADING,
  COMPONENTS_ARE_CHOSEN_BY_THE_PROFILE,
  FEATURES_API_PATH,
  FEATURES_CRUMB,
  FEATURES_LABEL,
  FEATURES_LEDE,
  KEEP_IT,
  NEVER_CHANGED,
  NO_FEATURES,
  OFF,
  ON,
  EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  PLUGINS_HAVE_NO_LOADER,
  READING_FEATURES,
  readFeature,
  readFeatures,
  SWITCH_OFF,
  SWITCH_ON,
  switchConsequence,
  switchedSentence,
  switchPath,
  switchQuestion,
  UNREADABLE_ANSWER,
  type FeatureRow,
} from "./featuresQuery";
import { when } from "./sessionsQuery";

function FeatureList({ onSwitched }: { readonly onSwitched: (sentence: string) => void }) {
  const answer = useResource<unknown>(FEATURES_API_PATH);
  const [confirming, setConfirming] = useState<FeatureRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const flip = useCallback(
    (row: FeatureRow) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(switchPath(row.name), {
          method: "POST",
          body: { on: !row.on },
        });
        setBusy(false);
        setConfirming(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        const switched = readFeature(result.data);
        onSwitched(switched === null ? switchedSentence({ ...row, on: !row.on }) : switchedSentence(switched));
      })();
    },
    [onSwitched],
  );

  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_FEATURES}
      </p>
    );
  }
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  const body = readFeatures(answer.data);
  if (body === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }

  const cannot = [
    body.components_are_chosen_by_the_profile === false ? null : COMPONENTS_ARE_CHOSEN_BY_THE_PROFILE,
    body.plugins_have_no_loader === false ? null : PLUGINS_HAVE_NO_LOADER,
    body.every_change_is_in_the_audit_trail === false ? null : EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  ].filter((one): one is string => one !== null);

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {confirming === null ? null : (
        <ConfirmAction
          question={switchQuestion(confirming)}
          consequence={switchConsequence(confirming)}
          confirmLabel={confirming.on ? SWITCH_OFF : SWITCH_ON}
          cancelLabel={KEEP_IT}
          busy={busy}
          onConfirm={() => {
            flip(confirming);
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        />
      )}
      {body.features.length === 0 ? <p className="note">{NO_FEATURES}</p> : null}
      {body.features.map((row) => (
        <section className="card" key={row.name} aria-labelledby={`feature-${row.name}`}>
          <h2 id={`feature-${row.name}`}>
            {row.title} <Chip label={row.on ? ON : OFF} />
          </h2>
          <p>{row.what}</p>
          <p className="note">{row.while_off}</p>
          <p className="note">
            Read by{" "}
            {row.read_by.map((reader, index) => (
              <span key={reader}>
                {index === 0 ? "" : ", "}
                <code>{reader}</code>
              </span>
            ))}
          </p>
          <p className="note">
            {row.changed_by === null || row.changed_by === undefined
              ? NEVER_CHANGED
              : `Last switched ${row.on ? "on" : "off"} by ${row.changed_by} at ${when(row.changed_at ?? "")}.`}
          </p>
          <div className="form-actions">
            <button
              type="button"
              className="button"
              disabled={busy}
              aria-label={`${row.on ? SWITCH_OFF : SWITCH_ON}: ${row.title}`}
              onClick={() => {
                setFailure(null);
                setConfirming(row);
              }}
            >
              {row.on ? SWITCH_OFF : SWITCH_ON}
            </button>
          </div>
        </section>
      ))}
      {cannot.length === 0 ? null : (
        <section className="card" aria-labelledby="features-cannot">
          <h2 id="features-cannot">{CANNOT_SWITCH_HEADING}</h2>
          {cannot.map((one) => (
            <p key={one}>{one}</p>
          ))}
        </section>
      )}
    </>
  );
}

export function Features() {
  // A counter rather than a boolean, so two switches in a row remount twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [switched, setSwitched] = useState<string | null>(null);
  const onSwitched = useCallback((sentence: string) => {
    setSwitched(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{FEATURES_CRUMB}</p>
      <h1>{FEATURES_LABEL}</h1>
      <p className="lede">{FEATURES_LEDE}</p>
      {switched === null ? null : (
        <p className="note" role="status">
          {switched}
        </p>
      )}
      <FeatureList key={generation} onSwitched={onSwitched} />
    </article>
  );
}
