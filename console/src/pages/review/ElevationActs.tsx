/**
 * Asking for an elevation, and approving or denying one, each confirmed in the API's own words.
 *
 * **Anybody may ask, for themselves, and somebody else decides.** The ask form says what each field
 * takes before anything is sent (the capability's shape, the scope's short name, the hours); a blank
 * field is said beside it, and only a complete request is confirmed, with the API's sentence about
 * what an elevation is. An approval is a grant that lapses on its own, so nothing here ends one.
 *
 * **Nothing lists what an elevation could confer.** That would be the catalogue handed to somebody
 * holding nothing (`brain.console.elevation.A_LANDING_THAT_LISTS_WHAT_YOU_COULD_ELEVATE_TO_IS_THE_
 * CATALOGUE`); a requester types the capability they were told they need.
 *
 * **Nothing here decides who may decide.** A decision is offered where the API said the row is
 * decidable, and the route asks `may_approve` or `may_decide` again whatever was drawn.
 *
 * Task ids: M27.7.8, M1.2.5, M27.16.1
 */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Drawer, FailureState, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { CAPABILITY_HINT, capabilityProblem, Field, NativeSelect } from "../access/formParts";
import {
  ASK_BLANKS,
  askBlanks,
  askQuestion,
  ELEVATION_REQUESTS_API_PATH,
  elevationDecisionApiPath,
  elevationQuestion,
  reasonWords,
  type ElevationAsk,
  type ElevationDecisionWord,
  type ElevationRequestRow,
} from "../governPeopleQuery";
import { nameOf, whenWords } from "./parts";
import { ACT_LABELS } from "./reviewActions";
import { EXPLANATION_HINT, hoursHint, hoursWords, SCOPE_HINT } from "./reviewQuery";

/** What a success says, and the instant the database recorded. */
export function askedSentence(ask: ElevationAsk, at: string): string {
  return `Your request for ${ask.capability} was recorded at ${whenWords(at)}.`;
}

export function decidedSentence(row: ElevationRequestRow, decision: ElevationDecisionWord, at: string): string {
  return `${row.capability} for ${nameOf({}, row.principal_id, row.display_name)} was ${decision} at ${whenWords(at)}.`;
}

function stamp(payload: unknown, key: "requested_at" | "decided_at"): string {
  const at = typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>)[key] : undefined;
  return typeof at === "string" ? at : "";
}

/** The sentences the elevation route serves, which confirmations carry. */
export interface ElevationSentences {
  readonly what: string;
  readonly recorded: string;
}

type Pending = { readonly row: ElevationRequestRow; readonly decision: ElevationDecisionWord };

export function useElevationDecisions(sentences: ElevationSentences, onDone: () => void) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);

  const decide = useCallback((row: ElevationRequestRow, decision: ElevationDecisionWord) => {
    setFailure(null);
    setTold(null);
    setPending({ row, decision });
  }, []);

  const send = useCallback(
    (chosen: Pending) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(elevationDecisionApiPath(chosen.row.request_id), {
          method: "POST",
          body: { decision: chosen.decision },
        });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setTold(decidedSentence(chosen.row, chosen.decision, stamp(result.data, "decided_at")));
        onDone();
      })();
    },
    [onDone],
  );

  const drawn: ReactNode = (
    <>
      {failure === null ? null : <FailureState failure={failure} />}
      {told === null ? null : (
        <div role="status">
          <Note kind="works">{told}</Note>
        </div>
      )}
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : elevationQuestion(pending.row, pending.decision)}
        consequence={pending?.decision === "denied" ? sentences.recorded : sentences.what}
        confirmLabel={pending?.decision === "denied" ? ACT_LABELS.deny : ACT_LABELS.approve}
        cancelLabel={ACT_LABELS.notNow}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </>
  );
  return { decide, busy, drawn };
}

const EMPTY_ASK: ElevationAsk = Object.freeze({ capability: "", scope_slug: "", reason: "", explanation: "", hours: 1 });
const ASK_FORM = "elevation-ask";
export const ASK_DESCRIPTION = "One capability over one scope, for a few hours, decided by somebody other than you.";
export const REVIEW_ASK = "Review the request";

/** The drawer a person asks for more from. */
export function AskDrawer({
  reasons,
  longest,
  what,
  onClose,
  onAsked,
}: {
  readonly reasons: readonly string[];
  readonly longest: number;
  /** The API's sentence about what an elevation is, which the confirmation carries. */
  readonly what: string;
  readonly onClose: () => void;
  readonly onAsked: (sentence: string) => void;
}) {
  const [ask, setAsk] = useState<ElevationAsk>(EMPTY_ASK);
  const [blanks, setBlanks] = useState<readonly (keyof typeof ASK_BLANKS)[]>([]);
  const [shape, setShape] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const apiProblems = failure?.problems ?? [];

  const onAsk = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = askBlanks(ask);
    setBlanks(missing);
    const capability = ask.capability.trim() === "" ? null : capabilityProblem(ask.capability);
    setShape(capability);
    setFailure(null);
    if (missing.length === 0 && capability === null) {
      setConfirming(true);
    }
  };
  const sent: ElevationAsk = { ...ask, capability: ask.capability.trim(), scope_slug: ask.scope_slug.trim() };
  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(ELEVATION_REQUESTS_API_PATH, { method: "POST", body: sent });
      setBusy(false);
      setConfirming(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onAsked(askedSentence(sent, stamp(result.data, "requested_at")));
    })();
  };
  const blank = (name: keyof typeof ASK_BLANKS) => (blanks.includes(name) ? ASK_BLANKS[name] : null);

  return (
    <Drawer
      open
      onOpenChange={(next) => {
        if (!next && !busy) {
          onClose();
        }
      }}
      title={ACT_LABELS.ask}
      description={ASK_DESCRIPTION}
      footer={
        <>
          <Button variant="outline" disabled={busy} onClick={onClose}>
            {ACT_LABELS.notNow}
          </Button>
          <Button type="submit" form={ASK_FORM} disabled={busy}>
            {REVIEW_ASK}
          </Button>
        </>
      }
    >
      <form id={ASK_FORM} aria-label="Ask for an elevation" className="flex min-w-0 flex-col gap-4" noValidate onSubmit={onAsk}>
        {failure === null ? null : <FailureState failure={failure} />}
        <Field label="Capability" hint={CAPABILITY_HINT} problem={blank("capability") ?? shape} apiProblems={apiProblems} names={["capability"]}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              name="capability"
              autoComplete="off"
              className="font-mono"
              aria-describedby={describedBy === "" ? undefined : describedBy}
              aria-invalid={invalid || undefined}
              value={ask.capability}
              onChange={(event) => {
                setAsk({ ...ask, capability: event.target.value });
              }}
            />
          )}
        </Field>
        <Field label="Scope" hint={SCOPE_HINT} problem={blank("scope_slug")} apiProblems={apiProblems} names={["scope_slug"]}>
          {({ id, describedBy, invalid }) => (
            <Input
              id={id}
              name="scope_slug"
              autoComplete="off"
              aria-describedby={describedBy === "" ? undefined : describedBy}
              aria-invalid={invalid || undefined}
              value={ask.scope_slug}
              onChange={(event) => {
                setAsk({ ...ask, scope_slug: event.target.value });
              }}
            />
          )}
        </Field>
        <Field label="Why" hint="Chosen from the product's fixed list." problem={blank("reason")} apiProblems={apiProblems} names={["reason"]}>
          {(ids) => (
            <NativeSelect
              {...ids}
              value={ask.reason}
              onChange={(value) => {
                setAsk({ ...ask, reason: value });
              }}
            >
              <option value="">Choose a reason</option>
              {reasons.map((one) => (
                <option key={one} value={one}>
                  {reasonWords(one)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
        <Field label="What it is for" hint={EXPLANATION_HINT} problem={blank("explanation")} apiProblems={apiProblems} names={["explanation"]}>
          {({ id, describedBy, invalid }) => (
            <Textarea
              id={id}
              name="explanation"
              aria-describedby={describedBy === "" ? undefined : describedBy}
              aria-invalid={invalid || undefined}
              value={ask.explanation}
              onChange={(event) => {
                setAsk({ ...ask, explanation: event.target.value });
              }}
            />
          )}
        </Field>
        <Field label="Hours" hint={hoursHint(longest)} apiProblems={apiProblems} names={["hours"]}>
          {(ids) => (
            <NativeSelect
              {...ids}
              value={String(ask.hours)}
              onChange={(value) => {
                setAsk({ ...ask, hours: Number(value) });
              }}
            >
              {Array.from({ length: Math.max(longest, 1) }, (_, index) => index + 1).map((hours) => (
                <option key={hours} value={String(hours)}>
                  {hoursWords(hours)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
      </form>
      <ConfirmDialog
        open={confirming}
        question={askQuestion(sent)}
        consequence={what}
        confirmLabel={ACT_LABELS.askSend}
        cancelLabel={ACT_LABELS.notNow}
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </Drawer>
  );
}
