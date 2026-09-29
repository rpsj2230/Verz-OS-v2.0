/**
 * Verifying the ledger (M24.1.2, M24.3.3): walk every entry from the first, and optionally check
 * the head the outside anchor store last published.
 *
 * **Its own page rather than a card under the entries.** A verification is a check somebody runs
 * before an audit or after an incident, and on the old screen it sat below every entry as a form
 * nobody was looking for. The Audit log's header links here.
 *
 * **Two answers in words, never a tick.** A chain that holds is not a ledger that is complete: the
 * walk says whether any entry was edited, removed or reordered, and only the published head can say
 * whether entries were removed from the end. The API's caveats are drawn as sent.
 *
 * **The published head says what each field takes before it is sent**, and a half-copied head is
 * told what is missing without reaching the API (`auditQuery.headProblems`).
 *
 * Neither write changes anything, so neither is confirmed: `tests/destructive-confirmed.test.ts`
 * lists the walk as a read sent by POST.
 *
 * Task ids: M24.1.2, M24.3.3, M27.16.1
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { Fact, FactList, FailureState, PageHeader, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Field } from "../access/formParts";
import {
  AUDIT_PATH,
  COMPLETENESS_WORDS,
  continuityInWords,
  EMPTY_HEAD,
  HEAD_PROBLEMS,
  headProblems,
  readVerification,
  VERIFICATION_API_PATH,
  verificationBody,
  when,
  type PublishedHead,
  type Verification,
} from "../auditQuery";
import { AUDIT_HEADING } from "./AuditPage";

export const VERIFY_HEADING = "Verify the ledger";
export const VERIFY_LEDE = "Check that no entry was edited, removed or reordered since it was written.";
export const WALK_HEADING = "Walk the ledger";
export const WALK_LEDE = "Checks every entry from the first against the one before it.";
export const WALK_LABEL = "Walk the ledger";
export const HEAD_HEADING = "Check the published head";
export const HEAD_LEDE = "Also shows whether entries were removed from the end. Copy the three values from the newest anchor file.";
export const CHECK_HEAD_LABEL = "Walk and check the published head";
export const PUBLISHED_HEAD_LABEL = "The last published head";
export const WALKING = "Walking the ledger.";
export const RESULT_HEADING = "What the walk found";

/** What each field of the published head takes, said before anything is sent. */
export const HEAD_HINTS = Object.freeze({
  seq: "A whole number, the sequence number in the anchor file.",
  head: "64 characters, digits and the letters a to f, the head digest in the same file.",
  takenAt: "When the anchor was taken, as the file writes it, for example 2026-09-28T09:00:00Z.",
});

function Result({ found }: { readonly found: Verification }) {
  return (
    <SectionCard title={RESULT_HEADING}>
      <div role="status" className="flex min-w-0 flex-col gap-3">
        <FactList>
          <Fact label="Chain">{continuityInWords(found)}</Fact>
          <Fact label="Published head">{COMPLETENESS_WORDS[found.completeness] ?? found.completeness}</Fact>
          <Fact label="Walked">{`Entries ${String(found.first_seq ?? 0)} to ${String(found.last_seq ?? 0)}, at ${when(found.checked_at)}`}</Fact>
        </FactList>
        {found.caveats.length === 0 ? null : (
          <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-[13px] text-body">
            {found.caveats.map((one) => (
              <li key={one}>{one}</li>
            ))}
          </ul>
        )}
      </div>
    </SectionCard>
  );
}

export function VerifyPage() {
  const [head, setHead] = useState<PublishedHead>(EMPTY_HEAD);
  const [problems, setProblems] = useState<readonly (keyof typeof HEAD_PROBLEMS)[]>([]);
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState<Verification | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const walk = useCallback((published: PublishedHead | null) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(VERIFICATION_API_PATH, {
        method: "POST",
        body: verificationBody(published),
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        setFound(null);
        return;
      }
      setFailure(null);
      setFound(readVerification(result.data));
    })();
  }, []);

  const onCheck = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = headProblems(head);
    setProblems(missing);
    if (missing.length === 0) {
      walk(head);
    }
  };
  const problem = (name: keyof typeof HEAD_PROBLEMS) => (problems.includes(name) ? HEAD_PROBLEMS[name] : null);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: AUDIT_HEADING, to: AUDIT_PATH }, { label: VERIFY_HEADING }]}
        title={VERIFY_HEADING}
        lede={VERIFY_LEDE}
      />
      <div className="[display:grid] min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
        <SectionCard title={WALK_HEADING} lede={WALK_LEDE}>
          <Button
            className="min-h-11 sm:min-h-9"
            disabled={busy}
            onClick={() => {
              walk(null);
            }}
          >
            {WALK_LABEL}
          </Button>
        </SectionCard>
        <SectionCard title={HEAD_HEADING} lede={HEAD_LEDE}>
          <form aria-label={PUBLISHED_HEAD_LABEL} className="flex min-w-0 flex-col gap-3" onSubmit={onCheck} noValidate>
            <Field label="Sequence number" hint={HEAD_HINTS.seq} problem={problem("seq")}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  aria-describedby={describedBy}
                  aria-invalid={invalid || undefined}
                  value={head.seq}
                  onChange={(event) => {
                    setHead({ ...head, seq: event.target.value });
                  }}
                />
              )}
            </Field>
            <Field label="Head digest" hint={HEAD_HINTS.head} problem={problem("head")}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  maxLength={64}
                  className="font-mono"
                  aria-describedby={describedBy}
                  aria-invalid={invalid || undefined}
                  value={head.head}
                  onChange={(event) => {
                    setHead({ ...head, head: event.target.value });
                  }}
                />
              )}
            </Field>
            <Field label="Taken at" hint={HEAD_HINTS.takenAt} problem={problem("takenAt")}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={invalid || undefined}
                  value={head.takenAt}
                  onChange={(event) => {
                    setHead({ ...head, takenAt: event.target.value });
                  }}
                />
              )}
            </Field>
            <div>
              <Button type="submit" variant="outline" className="min-h-11 sm:min-h-9" disabled={busy}>
                {CHECK_HEAD_LABEL}
              </Button>
            </div>
          </form>
        </SectionCard>
      </div>
      {busy ? (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {WALKING}
        </p>
      ) : null}
      {failure === null ? null : <FailureState failure={failure} />}
      {found === null ? null : <Result found={found} />}
    </div>
  );
}
