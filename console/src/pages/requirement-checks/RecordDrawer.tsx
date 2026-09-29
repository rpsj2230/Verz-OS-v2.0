/**
 * One requirement, opened in a drawer: what the owner asked for, the leaves that prove it, what the
 * install's own acceptance checks said about those leaves, the newest check a person recorded, and
 * the form that records the next one.
 *
 * **The record is exactly what the old screen recorded, and how.** One `POST /requirements/checks`
 * with the requirement's id, passed or failed, and a sentence, sent as the person signed in against
 * the release this install runs. A check supersedes and never edits, so nothing here is confirmed as
 * destructive: `tests/destructive-confirmed.test.ts` records why.
 *
 * **The evidence is beside the form so a row can be checked in seconds.** An acceptance check that
 * passed on this release is the install saying the leaf works; a person still records what they saw,
 * because a check proves its leaf and the owner signs off the requirement.
 *
 * **The form says what it accepts before anything is sent**, and a blank field is said beside it and
 * nothing is sent (`requirementChecksQuery.DRAFT_PROBLEMS`).
 *
 * Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6, M27.16.1
 */

import { useId, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { Advanced, Chip, Drawer, Fact, FactList, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { Field, whenWords } from "../access/formParts";
import { useResource } from "../../api/useResource";
import { personApiPath, readPersonDetail } from "../people/peopleQuery";
import {
  CHECKS_API_PATH,
  DRAFT_PROBLEMS,
  EMPTY_DRAFT,
  NOTE_CHARS,
  OUTCOMES,
  OUTCOME_WORDS,
  checkBody,
  draftProblems,
  evidenceOf,
  proofOf,
  standingOf,
  type CheckDraft,
  type RequirementRow,
} from "../requirementChecksQuery";
import { EvidencePill, StandingPill } from "./pills";

export const RECORD_TITLE = "Record a check";
export const RECORD_DESCRIPTION = "Say what you saw this install do for this requirement.";
export const RECORD_LABEL = "Record the check";
export const KEEP_LABEL = "Close";
export const NOT_RECORDED_HEADING = "The check was not recorded";
export const OUTCOME_LABEL = "What you saw";
export const NOTE_LABEL = "What you did and saw";
export const NOTE_HINT = `A sentence or two, up to ${String(NOTE_CHARS)} characters. Describe the steps and the result, never a value from the company's data.`;
export const EVIDENCE_HEADING = "Automatic checks on this release";
export const NO_EVIDENCE = "No automatic check proves this requirement's leaves yet, so a person's check is the only evidence.";
export const NEVER_CHECKED = "Nobody has recorded a check of this requirement on this install.";

const FORM = "requirement-check";

function Evidence({ row }: { readonly row: RequirementRow }) {
  const found = evidenceOf(row);
  if (found.length === 0) {
    return <p className="m-0 text-[12.5px] text-dim">{NO_EVIDENCE}</p>;
  }
  return (
    <ul aria-label={EVIDENCE_HEADING} className="m-0 flex list-none flex-col divide-y divide-line rounded-md border border-line p-0">
      {found.map((one) => (
        <li key={one.name} className="flex min-w-0 flex-col gap-1 px-3 py-2 text-[13px]">
          <span className="flex flex-wrap items-center gap-2">
            <EvidencePill outcome={one.outcome} />
            <span className="min-w-0 text-ink [overflow-wrap:anywhere]">{one.sentence}</span>
          </span>
          {one.checked_at === "" && one.reason === "" ? null : (
            <span className="text-[12px] text-dim [overflow-wrap:anywhere]">
              {[one.checked_at === "" ? "" : whenWords(one.checked_at), one.reason].filter((part) => part !== "").join(". ")}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function RecordDrawer({
  row,
  told,
  onClose,
  onRecorded,
}: {
  readonly row: RequirementRow;
  /** The API's one sentence about what a check is. */
  readonly told: string;
  readonly onClose: () => void;
  readonly onRecorded: () => void;
}) {
  const outcomeId = useId();
  const [draft, setDraft] = useState<CheckDraft>({ ...EMPTY_DRAFT, requirementId: row.id });
  const [problems, setProblems] = useState<readonly (keyof typeof DRAFT_PROBLEMS)[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const latest = row.latest ?? null;
  // Whoever recorded the newest check, named by their own page in the directory as this reader may
  // see it; somebody they may not see is "a person", and the reference is under Advanced.
  const recorder = useResource<unknown>(latest === null ? null : personApiPath(latest.checked_by));
  const recorderName = readPersonDetail(recorder.data)?.person.displayName ?? "a person";

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = draftProblems(draft);
    setProblems(missing);
    if (missing.length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(CHECKS_API_PATH, { method: "POST", body: checkBody(draft) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onRecorded();
    })();
  };

  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose();
        }
      }}
      title={RECORD_TITLE}
      description={RECORD_DESCRIPTION}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {KEEP_LABEL}
          </Button>
          <Button type="submit" form={FORM} disabled={busy}>
            {RECORD_LABEL}
          </Button>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        <FactList>
          <Fact label="Reference">
            <code className="font-mono text-[12px]">{row.id}</code>
          </Fact>
          <Fact label="Requirement">{row.requirement}</Fact>
          <Fact label="Asked for in">{row.source}</Fact>
          <Fact label="Proved by">
            {proofOf(row).length === 0 ? (
              "No proof leaf is named"
            ) : (
              <span className="flex flex-wrap gap-1.5">
                {proofOf(row).map((leaf) => (
                  <Chip key={leaf} mono>
                    {leaf}
                  </Chip>
                ))}
              </span>
            )}
          </Fact>
          <Fact label="Newest check">
            {latest === null ? (
              NEVER_CHECKED
            ) : (
              <span className="flex min-w-0 flex-col gap-1">
                <span className="flex flex-wrap items-center gap-2">
                  <StandingPill standing={standingOf(row)} />
                  <span>
                    by {recorderName}, {whenWords(latest.checked_at)}
                  </span>
                </span>
                <span className="text-dim">{latest.note}</span>
              </span>
            )}
          </Fact>
        </FactList>

        <section aria-label={EVIDENCE_HEADING} className="flex min-w-0 flex-col gap-2">
          <h3 className="m-0 text-[13px] font-semibold text-ink">{EVIDENCE_HEADING}</h3>
          <Evidence row={row} />
        </section>

        {failure === null ? null : <FailureNotice failure={failure} title={NOT_RECORDED_HEADING} fields={["outcome", "note"]} />}
        <form id={FORM} aria-label={RECORD_TITLE} className="flex min-w-0 flex-col gap-4" noValidate onSubmit={submit}>
          <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0" aria-describedby={problems.includes("outcome") ? `${outcomeId}-problem` : undefined}>
            <legend className="mb-1 text-[13px] font-medium text-ink">{OUTCOME_LABEL}</legend>
            <span className="flex flex-wrap gap-4">
              {OUTCOMES.map((one) => (
                <label key={one} className="flex min-h-11 items-center gap-2 text-[13px] text-ink sm:min-h-8">
                  <input
                    type="radio"
                    name="outcome"
                    value={one}
                    className="size-4"
                    checked={draft.outcome === one}
                    disabled={busy}
                    onChange={() => {
                      setDraft({ ...draft, outcome: one });
                    }}
                  />
                  {OUTCOME_WORDS[one]}
                </label>
              ))}
            </span>
            {problems.includes("outcome") ? (
              <p id={`${outcomeId}-problem`} className="m-0 text-[12px] text-crit">
                {DRAFT_PROBLEMS.outcome}
              </p>
            ) : null}
          </fieldset>
          <Field label={NOTE_LABEL} hint={NOTE_HINT} problem={problems.includes("note") ? DRAFT_PROBLEMS.note : null} apiProblems={failure?.problems ?? []} names={["note"]}>
            {({ id, describedBy, invalid }) => (
              <Textarea
                id={id}
                name="note"
                rows={4}
                maxLength={NOTE_CHARS}
                aria-describedby={describedBy === "" ? undefined : describedBy}
                aria-invalid={invalid ? true : undefined}
                value={draft.note}
                disabled={busy}
                onChange={(event) => {
                  setDraft({ ...draft, note: event.target.value });
                }}
              />
            )}
          </Field>
          {told === "" ? null : <Note>{told}</Note>}
        </form>

        {latest === null ? null : (
          <Advanced>
            <FactList>
            <Fact label="Checked by">
              <code className="font-mono text-[12px]">{latest.checked_by}</code>
            </Fact>
            <Fact label="On release">
              <code className="font-mono text-[12px]">{latest.release_commit ?? "No release recorded"}</code>
            </Fact>
            </FactList>
          </Advanced>
        )}
      </div>
    </Drawer>
  );
}
