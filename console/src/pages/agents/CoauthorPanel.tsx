/**
 * Ask the co-author for changes to a draft, see each proposed change as before and after, and take
 * the ones you choose.
 *
 * **A suggestion is not a change.** Asking sends the draft's words and the request to the model
 * provider this install uses, and writes nothing; the answer is a list, each change a place on the
 * form with what is there now and what is proposed. Nothing is chosen for the author: every change
 * starts unticked, and taking sends exactly the ones they ticked, as a new version of the draft
 * through the same save a typed edit goes through. What is not taken is dropped, and dropping the
 * whole list is a button that sends nothing, because rejecting writes nothing.
 *
 * **Both writes are confirmed**, and the first says where the words go: asking sends the draft to a
 * model provider, which an author should know before it happens. A refusal is the API's own sentence:
 * a draft that has moved on since the question, a reply that was not a proposal, no model set up.
 *
 * **What it cannot propose is not drawn.** The API never sends a change to what an agent may reach
 * or how closely it is watched, so there is nothing here to hide and no flag to read; a change the
 * co-author named for such a path arrives as a sentence under "not proposed".
 *
 * Task ids: M20.1.3
 */

import { useId, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";
import {
  ASK_BUTTON,
  ASK_CONSEQUENCE,
  ASK_LABEL,
  ASK_NEEDED,
  ASK_QUESTION,
  askBody,
  COAUTHOR_HEADING,
  COAUTHOR_LEDE,
  DROP_BUTTON,
  KEEP_LABEL,
  NOT_CHANGED,
  NOTHING_SUGGESTED,
  readNotChanged,
  readSuggestion,
  SOMETHING_DID_NOT_WORK,
  suggestApiPath,
  suggestedWords,
  TAKE_BUTTON,
  TAKE_CONSEQUENCE,
  TAKE_QUESTION,
  takeApiPath,
  takeBody,
  TAKEN,
  type Suggestion,
} from "./agentCoauthorQuery";

type Step = "ask" | "take";

interface Refused {
  readonly failure: ApiFailure;
  readonly title: string;
  readonly sentence?: string;
}

export function CoauthorPanel({
  draftId,
  revision,
  onTaken,
}: {
  readonly draftId: string;
  /** The draft's latest revision as the page drew it, which both writes name. */
  readonly revision: number;
  /** Called after changes were taken, so the page asks for the draft again. */
  readonly onTaken: () => void;
}) {
  const askId = useId();
  const [words, setWords] = useState("");
  const [missing, setMissing] = useState(false);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const [step, setStep] = useState<Step | null>(null);
  const [sending, setSending] = useState(false);
  const [told, setTold] = useState<string | null>(null);
  const [refused, setRefused] = useState<Refused | null>(null);

  const refuse = (failure: ApiFailure, body: unknown) => {
    const notChanged = failure.status === 409 ? readNotChanged(body) : null;
    setTold(null);
    setRefused(
      notChanged === null
        ? { failure, title: SOMETHING_DID_NOT_WORK }
        : { failure, title: NOT_CHANGED, sentence: notChanged.sentence },
    );
  };

  const tick = (path: string, on: boolean) => {
    setChosen((now) => {
      const next = new Set(now);
      if (on) {
        next.add(path);
      } else {
        next.delete(path);
      }
      return next;
    });
  };

  const begin = () => {
    if (words.trim() === "") {
      setMissing(true);
      return;
    }
    setMissing(false);
    setRefused(null);
    setStep("ask");
  };

  const confirm = () => {
    if (step === "ask") {
      setSending(true);
      void (async () => {
        const result = await request<unknown>(suggestApiPath(draftId), {
          method: "POST",
          body: askBody(revision, words),
        });
        setSending(false);
        setStep(null);
        if (!result.ok) {
          refuse(result.failure, result.body);
          return;
        }
        setTold(null);
        setSuggestion(readSuggestion(result.data));
        setChosen(new Set());
      })();
      return;
    }
    if (step === "take" && suggestion !== null) {
      const taking = suggestion;
      setSending(true);
      void (async () => {
        const result = await request<unknown>(takeApiPath(draftId), {
          method: "POST",
          body: takeBody(taking, [...chosen]),
        });
        setSending(false);
        setStep(null);
        if (!result.ok) {
          refuse(result.failure, result.body);
          return;
        }
        setRefused(null);
        setTold(TAKEN);
        setSuggestion(null);
        setChosen(new Set());
        setWords("");
        onTaken();
      })();
    }
  };

  const notice =
    refused !== null ? (
      <FailureNotice
        failure={refused.failure}
        title={refused.title}
        {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
      />
    ) : told !== null ? (
      <Notice title={told}>
        <p>{words === "" ? "The draft has a new version." : words}</p>
      </Notice>
    ) : null;

  return (
    <>
      {notice}
      <SectionCard title={COAUTHOR_HEADING} lede={COAUTHOR_LEDE}>
        <div data-slot="coauthor" className="flex min-w-0 flex-col gap-3 p-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={askId}>{ASK_LABEL}</Label>
            <Textarea
              id={askId}
              value={words}
              aria-invalid={missing}
              onChange={(event) => {
                setWords(event.target.value);
                setMissing(false);
              }}
            />
            {missing ? <p className="m-0 text-[12px] text-danger-text">{ASK_NEEDED}</p> : null}
          </div>
          <div>
            <Button size="sm" disabled={sending} onClick={begin}>
              {ASK_BUTTON}
            </Button>
          </div>
          {suggestion === null ? null : (
            <div data-slot="coauthor-suggestion" className="flex min-w-0 flex-col gap-3">
              <Note>{suggestion.note}</Note>
              {suggestion.changes.length === 0 ? <Note>{NOTHING_SUGGESTED}</Note> : null}
              <ul className="m-0 flex list-none flex-col gap-3 p-0">
                {suggestion.changes.map((one) => (
                  <li key={one.path} className="flex flex-col gap-1.5 rounded-md border border-line p-3">
                    <label className="flex items-center gap-2 text-[13px] font-medium text-ink">
                      <input
                        type="checkbox"
                        checked={chosen.has(one.path)}
                        onChange={(event) => {
                          tick(one.path, event.target.checked);
                        }}
                      />
                      {one.where}
                    </label>
                    <div className="flex flex-wrap gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-dim">Now</div>
                        <div className="[overflow-wrap:anywhere] text-[13px] text-ink">{suggestedWords(one.before)}</div>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-semibold uppercase tracking-wide text-dim">Proposed</div>
                        <div className="[overflow-wrap:anywhere] text-[13px] text-ink">{suggestedWords(one.after)}</div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              {suggestion.dropped.length === 0 ? null : (
                <div className="flex flex-col gap-1">
                  <p className="m-0 text-[13px] font-semibold text-ink">Not proposed</p>
                  <ul className="m-0 flex list-none flex-col gap-1 p-0">
                    {suggestion.dropped.map((one, index) => (
                      <li key={`${String(index)} ${one.message}`}>
                        <Note>{one.message}</Note>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  disabled={sending || chosen.size === 0}
                  onClick={() => {
                    setRefused(null);
                    setStep("take");
                  }}
                >
                  {TAKE_BUTTON}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={sending}
                  onClick={() => {
                    setSuggestion(null);
                    setChosen(new Set());
                  }}
                >
                  {DROP_BUTTON}
                </Button>
              </div>
            </div>
          )}
        </div>
      </SectionCard>
      <ConfirmDialog
        open={step !== null}
        question={step === "take" ? TAKE_QUESTION : ASK_QUESTION}
        consequence={step === "take" ? TAKE_CONSEQUENCE : ASK_CONSEQUENCE}
        confirmLabel={step === "take" ? TAKE_BUTTON : ASK_BUTTON}
        cancelLabel={KEEP_LABEL}
        danger={false}
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setStep(null);
        }}
      />
    </>
  );
}
