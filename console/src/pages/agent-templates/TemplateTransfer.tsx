/**
 * Withdrawing a template version and putting it back, saving a version as a document, and bringing
 * a document in, for the people who hold the install authority over the company.
 *
 * **A person who does not hold it sees none of this, and is told nothing about why.** Every route
 * answers them as it answers a version nobody published, so each card reads its state first and
 * draws nothing when the read fails: not an error, and not a sentence about what they are missing.
 *
 * **Withdrawing hides a version from new installs and nothing else.** The confirmation says so in
 * the words the API's own rule gives: an agent already installed from it keeps running and stays on
 * that version, and the act can be undone. Putting it back is confirmed too, though it adds and
 * removes nothing, because it changes what every colleague is offered.
 *
 * **An import is read before it is written.** Pasting a document asks the API to read it, which
 * writes nothing and names what it holds, so the person sees what it asks for, whether this install's
 * own key made its signature, and any detail that looks like a company's own, before pressing Add.
 * Adding names the digest that was shown, and the API signs the template again with this install's
 * key, because only the install that made a signature can check it (needs-rupash item 236).
 *
 * Task ids: M27.15.35
 */

import { useId, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Advanced, Chip, ConfirmDialog, Fact, FactList, FailureState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import {
  exportApiPath,
  exportFileName,
  IMPORT_API_PATH,
  parseDocument,
  readImport,
  readWithdrawal,
  readWithdrawn,
  undoApiPath,
  WITHDRAWN_API_PATH,
  withdrawalApiPath,
  type ImportReading,
  type WithdrawnVersion,
} from "./templateTransferQuery";

export const WITHDRAW_HEADING = "Offered to new installs";
export const WITHDRAW = "Withdraw version";
export const PUT_BACK = "Put back on offer";
export const EXPORT = "Save as a document";
export const CANCEL = "Change nothing";
export const REASON_LABEL = "Why is it being withdrawn?";
export const REASON_HINT = "One sentence, up to 240 characters. The people who read this list see it.";
export const REASON_NEEDED = "Say why this version is being withdrawn, in a sentence.";
export const NOT_WITHDRAWN = "The version was not withdrawn";
export const NOT_PUT_BACK = "The version was not put back";
export const NOT_EXPORTED = "The version was not saved";
export const WITHDRAWN_HEADING = "Withdrawn versions";
export const WITHDRAWN_LEDE = "Versions hidden from new installs. Agents already installed from one are not affected.";
export const NONE_WITHDRAWN = "Nothing is withdrawn.";
export const IMPORT_HEADING = "Bring in a template";
export const IMPORT_LEDE =
  "Paste a template document saved from another install. It is read first and nothing is added until you confirm.";
export const DOCUMENT_LABEL = "Template document";
export const DOCUMENT_NEEDED = "Paste the template document you saved from the other install.";
export const DOCUMENT_UNREADABLE = "That is not a document this page can read. Paste the whole file you saved.";
export const READ_IT = "Read it";
export const ADD_IT = "Add to the catalogue";
export const NOT_IMPORTED = "The template was not added";
export const SIGNED_HERE = "Signed by this install's key";
export const SIGNED_ELSEWHERE = "Signed somewhere else; this install signs it again when you add it";
export const REASON_MAX = 240;

const CONSEQUENCE_OF_WITHDRAWING =
  "No new agent can be installed from this version, and it leaves the catalogue for everybody. Agents already installed from it keep running and stay on it. You can put it back.";
const CONSEQUENCE_OF_PUTTING_BACK = "The version is offered to new installs again. Nothing already installed changes.";

function when(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Save one version's document as a file. A read: it changes nothing. Returns the failure, or null. */
export async function saveVersion(templateId: string, version: number, into: Document = globalThis.document): Promise<ApiFailure | null> {
  const result = await request<{ readonly document?: unknown }>(exportApiPath(templateId, version));
  if (!result.ok) {
    return result.failure;
  }
  if (typeof URL.createObjectURL === "function") {
    const address = URL.createObjectURL(new Blob([JSON.stringify(result.data.document ?? {}, null, 2)], { type: "application/json" }));
    const link = into.createElement("a");
    link.href = address;
    link.download = exportFileName(templateId, version);
    into.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(address);
  }
  return null;
}

type Asked = { readonly kind: "withdraw" } | { readonly kind: "put-back" };

/** One version's offer state, with the controls to withdraw it, put it back and save it. */
export function WithdrawCard({ templateId, version, name }: { readonly templateId: string; readonly version: number; readonly name: string }) {
  const [moved, setMoved] = useState(0);
  const state = useResource<unknown>(withdrawalApiPath(templateId, version), moved);
  const [reason, setReason] = useState("");
  const [blank, setBlank] = useState(false);
  const [pending, setPending] = useState<Asked | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ readonly title: string; readonly failure: ApiFailure } | null>(null);
  const fieldId = useId();

  const reading = state.failure === null ? readWithdrawal(state.data) : null;
  if (state.busy || reading === null) {
    return null;
  }

  function send(asked: Asked): void {
    setBusy(true);
    void (async () => {
      const result =
        asked.kind === "withdraw"
          ? await request<unknown>(withdrawalApiPath(templateId, version), { method: "POST", body: { reason: reason.trim() } })
          : await request<unknown>(undoApiPath(templateId, version), { method: "POST" });
      setBusy(false);
      if (!result.ok) {
        setFailure({ title: asked.kind === "withdraw" ? NOT_WITHDRAWN : NOT_PUT_BACK, failure: result.failure });
        return;
      }
      setPending(null);
      setReason("");
      setFailure(null);
      setMoved((one) => one + 1);
    })();
  }

  function save(): void {
    void saveVersion(templateId, version).then((problem) => {
      setFailure(problem === null ? null : { title: NOT_EXPORTED, failure: problem });
    });
  }

  return (
    <SectionCard title={WITHDRAW_HEADING} lede={`Version ${String(version)} of ${name}.`} action={<Chip>{reading.withdrawn ? "Withdrawn" : "Offered"}</Chip>}>
      <div className="flex min-w-0 flex-col gap-4">
        {reading.withdrawn ? (
          <div>
            <Button
              type="button"
              variant="outline"
              className="min-h-11 sm:min-h-9"
              disabled={busy}
              onClick={() => {
                setFailure(null);
                setPending({ kind: "put-back" });
              }}
            >
              {PUT_BACK}
            </Button>
          </div>
        ) : reading.unavailable === "" ? (
          <form
            className="flex min-w-0 flex-col gap-2"
            noValidate
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              setFailure(null);
              if (reason.trim() === "") {
                setBlank(true);
                return;
              }
              setBlank(false);
              setPending({ kind: "withdraw" });
            }}
          >
            <Label htmlFor={fieldId}>{REASON_LABEL}</Label>
            <Textarea
              id={fieldId}
              name="reason"
              rows={2}
              maxLength={REASON_MAX}
              value={reason}
              aria-describedby={`${fieldId}-hint`}
              {...(blank ? { "aria-invalid": true as const } : {})}
              onChange={(event) => {
                setReason(event.target.value);
              }}
            />
            <p id={`${fieldId}-hint`} className="m-0 text-[12.5px] leading-snug text-dim">
              {blank ? REASON_NEEDED : REASON_HINT}
            </p>
            <div>
              <Button type="submit" variant="outline" className="min-h-11 sm:min-h-9" disabled={busy}>
                {WITHDRAW}
              </Button>
            </div>
          </form>
        ) : (
          <Note kind="not-yet">{reading.unavailable}</Note>
        )}
        <div>
          <Button type="button" variant="outline" className="min-h-11 sm:min-h-9" disabled={reading.unavailable !== "" && !reading.withdrawn} onClick={save}>
            {EXPORT}
          </Button>
        </div>
        {failure === null ? null : <FailureState failure={failure.failure} title={failure.title} />}
        {reading.changes.length === 0 ? null : (
          <Advanced>
            <FactList>
              {reading.changes.map((one) => (
                <Fact key={`${one.at} ${one.set_by}`} label={one.withdrawn ? "Withdrawn" : "Put back"}>
                  {`${when(one.at)} by ${one.set_by}${one.reason === "" ? "" : `: ${one.reason}`}`}
                </Fact>
              ))}
            </FactList>
          </Advanced>
        )}
      </div>
      <ConfirmDialog
        open={pending !== null}
        question={
          pending?.kind === "put-back"
            ? `Put version ${String(version)} of ${name} back on offer?`
            : `Withdraw version ${String(version)} of ${name}?`
        }
        consequence={pending?.kind === "put-back" ? CONSEQUENCE_OF_PUTTING_BACK : CONSEQUENCE_OF_WITHDRAWING}
        details={failure === null ? undefined : <FailureState failure={failure.failure} title={failure.title} />}
        confirmLabel={pending?.kind === "put-back" ? PUT_BACK : WITHDRAW}
        cancelLabel={CANCEL}
        busy={busy}
        danger={pending?.kind !== "put-back"}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </SectionCard>
  );
}

/** The versions withdrawn now, each with its reason and a way to put it back. */
export function WithdrawnCard() {
  const [moved, setMoved] = useState(0);
  const answer = useResource<unknown>(WITHDRAWN_API_PATH, moved);
  const [pending, setPending] = useState<WithdrawnVersion | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const versions = answer.failure === null ? readWithdrawn(answer.data) : null;
  if (answer.busy || versions === null) {
    return null;
  }

  function send(one: WithdrawnVersion): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(undoApiPath(one.template_id, one.version), { method: "POST" });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setPending(null);
      setFailure(null);
      setMoved((n) => n + 1);
    })();
  }

  return (
    <SectionCard title={WITHDRAWN_HEADING} lede={WITHDRAWN_LEDE}>
      {versions.length === 0 ? (
        <Note>{NONE_WITHDRAWN}</Note>
      ) : (
        <ul className="m-0 flex min-w-0 list-none flex-col gap-3 p-0">
          {versions.map((one) => (
            <li key={`${one.template_id} ${String(one.version)}`} className="flex min-w-0 flex-col gap-1 border-b border-line pb-3 last:border-b-0 last:pb-0">
              <span className="min-w-0 text-[13px] font-medium text-ink [overflow-wrap:anywhere]">{`${one.display_name}, version ${String(one.version)}`}</span>
              <span className="min-w-0 text-[12.5px] text-dim [overflow-wrap:anywhere]">{one.reason}</span>
              <span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="min-h-11 sm:min-h-8"
                  disabled={busy}
                  aria-label={`${PUT_BACK}: ${one.display_name}, version ${String(one.version)}`}
                  onClick={() => {
                    setFailure(null);
                    setPending(one);
                  }}
                >
                  {PUT_BACK}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "Put this version back?" : `Put version ${String(pending.version)} of ${pending.display_name} back on offer?`}
        consequence={CONSEQUENCE_OF_PUTTING_BACK}
        details={failure === null ? undefined : <FailureState failure={failure} title={NOT_PUT_BACK} />}
        confirmLabel={PUT_BACK}
        cancelLabel={CANCEL}
        busy={busy}
        danger={false}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </SectionCard>
  );
}

/** Paste a document, read it, and add it with the digest that was shown. */
export function ImportCard({ onAdded }: { readonly onAdded?: (() => void) | undefined }) {
  const available = useResource<unknown>(WITHDRAWN_API_PATH);
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [reading, setReading] = useState<ImportReading | null>(null);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const fieldId = useId();

  if (available.busy || available.failure !== null || readWithdrawn(available.data) === null) {
    return null;
  }

  function read(): void {
    const document = parseDocument(text);
    setAdded(null);
    setFailure(null);
    if (text.trim() === "") {
      setProblem(DOCUMENT_NEEDED);
      return;
    }
    if (document === null) {
      setProblem(DOCUMENT_UNREADABLE);
      return;
    }
    setProblem(null);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(IMPORT_API_PATH, { method: "POST", body: { document } });
      setBusy(false);
      if (!result.ok) {
        setReading(null);
        setFailure(result.failure);
        return;
      }
      setReading(readImport(result.data));
    })();
  }

  function add(shown: ImportReading): void {
    const document = parseDocument(text);
    if (document === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(IMPORT_API_PATH, { method: "POST", body: { document, expected_digest: shown.content_digest } });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const done = readImport(result.data);
      setAsking(false);
      setFailure(null);
      setAdded(done?.says ?? "");
      setReading(null);
      setText("");
      onAdded?.();
    })();
  }

  return (
    <SectionCard title={IMPORT_HEADING} lede={IMPORT_LEDE}>
      <div className="flex min-w-0 flex-col gap-3">
        <form
          className="flex min-w-0 flex-col gap-2"
          noValidate
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            read();
          }}
        >
          <Label htmlFor={fieldId}>{DOCUMENT_LABEL}</Label>
          <Textarea
            id={fieldId}
            name="document"
            rows={6}
            className="font-mono text-[12px]"
            value={text}
            aria-describedby={problem === null ? undefined : `${fieldId}-problem`}
            {...(problem === null ? {} : { "aria-invalid": true as const })}
            onChange={(event) => {
              setText(event.target.value);
              setReading(null);
            }}
          />
          {problem === null ? null : (
            <p id={`${fieldId}-problem`} className="m-0 text-[12.5px] leading-snug text-dim">
              {problem}
            </p>
          )}
          <div>
            <Button type="submit" variant="outline" className="min-h-11 sm:min-h-9" disabled={busy}>
              {READ_IT}
            </Button>
          </div>
        </form>
        {added === null ? null : <Note kind="done">{added}</Note>}
        {failure === null ? null : <FailureState failure={failure} title={NOT_IMPORTED} />}
        {reading === null ? null : (
          <div className="flex min-w-0 flex-col gap-3">
            <FactList>
              <Fact label="Template">{reading.display_name}</Fact>
              {reading.summary === null || reading.summary === undefined ? null : <Fact label="What it is for">{reading.summary}</Fact>}
              <Fact label="Signature">{reading.signed_by_this_install ? SIGNED_HERE : SIGNED_ELSEWHERE}</Fact>
              <Fact label="Template ID">
                <span className="font-mono text-[12px]">{reading.template_id}</span>
              </Fact>
              {reading.company_details.length === 0 ? null : (
                <Fact label="Looks like a company's own">
                  {reading.company_details.map((one) => (
                    <Chip key={`${one.kind} ${one.places.join(" ")}`}>{`${one.kind} in ${one.places.join(", ")}`}</Chip>
                  ))}
                </Fact>
              )}
            </FactList>
            <div>
              <Button
                type="button"
                className="min-h-11 sm:min-h-9"
                disabled={busy || reading.company_details.length > 0}
                onClick={() => {
                  setFailure(null);
                  setAsking(true);
                }}
              >
                {ADD_IT}
              </Button>
            </div>
          </div>
        )}
      </div>
      <ConfirmDialog
        open={asking && reading !== null}
        question={reading === null ? "Add this template?" : `Add ${reading.display_name} to the catalogue?`}
        consequence="It is signed with this install's key as version one, published under your name, and offered to new installs. Nothing already installed changes."
        details={failure === null ? undefined : <FailureState failure={failure} title={NOT_IMPORTED} />}
        confirmLabel={ADD_IT}
        cancelLabel={CANCEL}
        busy={busy}
        danger={false}
        onConfirm={() => {
          if (reading !== null) {
            add(reading);
          }
        }}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </SectionCard>
  );
}
