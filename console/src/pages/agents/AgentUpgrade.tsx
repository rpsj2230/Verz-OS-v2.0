/**
 * A newer version of an agent's template: what it changes, a choice for every change this install
 * had made itself, and the two things a person may do, upgrade or say no.
 *
 * **It is asked for, and a reader who may not act sees nothing of it.** `GET /agents/{id}/upgrade`
 * answers an administrator over the agent and is the one 404 for everybody else, an agent that is
 * hidden and an agent that does not exist among them, so a 404 here draws no card and no sentence:
 * a card that said "you cannot upgrade this" would be the oracle the route was written to close. An
 * agent already on the newest version draws nothing either, because there is nothing to decide.
 *
 * **Every change this install claimed is answered by the person, with no default.** A conflict is a
 * path the new version moves that somebody here had set, and the page draws the three columns, what
 * the template said, what it says now and what is set here, with two answers beside them: keep ours
 * or use the new version's. The upgrade button stays disabled until every conflict has one, and
 * says why, because a default would decide for the person and a merge would write a value nobody
 * wrote. The changes nobody here claimed apply as they are, and the five that an install can never
 * change, the leash and the largest side effect among them, are marked, because they are the part an
 * accepter cannot resolve and has to read.
 *
 * **A version the API says cannot be accepted is shown, with its sentence, and can still be turned
 * down.** The sentence is the API's: a version that would raise a rung, a process with no signing
 * key, an archived agent. The decline button does not wait on it.
 *
 * **Both writes are confirmed, and both name what the page drew.** The version and the
 * configuration digest the review was read against go back with the request, and a page that went
 * stale is told so in the API's own sentence and nothing is changed.
 *
 * Task ids: M13.4.2, M13.4.3, M13.4.4, M13.4.5
 */

import { useCallback, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";
import {
  ACCEPT_CONSEQUENCE,
  ACCEPT_LABEL,
  acceptBody,
  agentUpgradeAcceptApiPath,
  agentUpgradeApiPath,
  agentUpgradeDeclineApiPath,
  allAnswered,
  ANSWER_EVERY_CONFLICT,
  DECLINE_CONSEQUENCE,
  DECLINE_LABEL,
  declineBody,
  DONE_DECLINED,
  DONE_UPGRADED,
  hasAnOffer,
  KEEP_LABEL,
  NOT_CHANGED,
  readNotChanged,
  readUpgrade,
  RESOLUTION_LABELS,
  SOMETHING_DID_NOT_WORK,
  UPGRADE_HEADING,
  valueWords,
  type AgentUpgrade as Review,
  type Resolution,
} from "./agentUpgradeQuery";

type Step = "accept" | "decline";

interface Refused {
  readonly failure: ApiFailure;
  readonly title: string;
  readonly sentence?: string;
}

/** One value under its column heading. */
function Column({ heading, value }: { readonly heading: string; readonly value: unknown }) {
  return (
    <div className="min-w-0 flex-1">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-dim">{heading}</div>
      <div className="[overflow-wrap:anywhere] text-[13px] text-ink">{valueWords(value)}</div>
    </div>
  );
}

function Conflicts({
  review,
  chosen,
  onChoose,
}: {
  readonly review: Review;
  readonly chosen: Readonly<Record<string, Resolution>>;
  readonly onChoose: (path: string, answer: Resolution) => void;
}) {
  if (review.conflicts.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-3">
      <h3 className="m-0 text-[13px] font-semibold text-ink">Changes you made here that this version also changes</h3>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {review.conflicts.map((one) => (
          <li key={one.path} className="flex flex-col gap-2 rounded-md border border-line p-3">
            <div className="text-[13px] font-medium text-ink">{one.where}</div>
            <div className="flex flex-wrap gap-4">
              <Column heading="The old version said" value={one.was} />
              <Column heading="The new version says" value={one.now} />
              <Column heading="Set here" value={one.local} />
            </div>
            <fieldset className="m-0 flex flex-wrap gap-4 border-0 p-0">
              <legend className="sr-only">{`What to do about ${one.where}`}</legend>
              {(["keep_local", "take_template"] as const).map((answer) => (
                <label key={answer} className="flex items-center gap-1.5 text-[13px] text-ink">
                  <input
                    type="radio"
                    name={`resolution-${one.path}`}
                    checked={chosen[one.path] === answer}
                    onChange={() => {
                      onChoose(one.path, answer);
                    }}
                  />
                  {RESOLUTION_LABELS[answer]}
                </label>
              ))}
            </fieldset>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Updates({ review }: { readonly review: Review }) {
  if (review.updates.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-2">
      <h3 className="m-0 text-[13px] font-semibold text-ink">What else changes</h3>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {review.updates.map((one) => (
          <li key={one.path} className="flex flex-wrap gap-4 text-[13px]">
            <span className="min-w-40 font-medium text-ink">
              {one.where}
              {one.sealed ? <span className="ml-1.5 text-[11px] font-normal text-warn">set by the publisher</span> : null}
            </span>
            <Column heading="Was" value={one.was} />
            <Column heading="Becomes" value={one.now} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** What the page holds of an agent's upgrade: the review once it has answered, and a way to ask again. */
export interface UpgradeReview {
  readonly review: Review | null;
  /** True while the first answer, or a fresh one after a write, is on its way. */
  readonly busy: boolean;
  readonly refresh: () => void;
}

/** Asks for the review, and asks again whenever `refresh` is called. A 404 is `review: null`. */
export function useUpgradeReview(agentId: string): UpgradeReview {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentUpgradeApiPath(agentId), version);
  const review = useMemo(
    () => (answer.failure !== null || answer.data === null ? null : readUpgrade(answer.data)),
    [answer.data, answer.failure],
  );
  const refresh = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  return { review, busy: answer.busy, refresh };
}

export function AgentUpgrade({
  agentId,
  upgrade,
  onChanged,
}: {
  readonly agentId: string;
  readonly upgrade: UpgradeReview;
  readonly onChanged: () => void;
}) {
  const { review, busy, refresh } = upgrade;
  const [chosen, setChosen] = useState<Readonly<Record<string, Resolution>>>({});
  const [step, setStep] = useState<Step | null>(null);
  const [sending, setSending] = useState(false);
  const [told, setTold] = useState<string | null>(null);
  const [refused, setRefused] = useState<Refused | null>(null);

  const choose = useCallback((path: string, resolution: Resolution) => {
    setChosen((now) => ({ ...now, [path]: resolution }));
  }, []);

  /** What happens once the API has answered a write: a sentence, and the review asked again. */
  const settled = (what: Step, result: Awaited<ReturnType<typeof request<unknown>>>) => {
    setSending(false);
    setStep(null);
    if (result.ok) {
      setRefused(null);
      setTold(what === "accept" ? DONE_UPGRADED : DONE_DECLINED);
      setChosen({});
      refresh();
      onChanged();
      return;
    }
    setTold(null);
    const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
    setRefused(
      notChanged === null
        ? { failure: result.failure, title: SOMETHING_DID_NOT_WORK }
        : { failure: result.failure, title: NOT_CHANGED, sentence: notChanged.sentence },
    );
  };

  const confirm = () => {
    if (step === null || !hasAnOffer(review)) {
      return;
    }
    const what = step;
    setSending(true);
    void (async () => {
      if (what === "accept") {
        settled(
          what,
          await request<unknown>(agentUpgradeAcceptApiPath(agentId), {
            method: "POST",
            body: acceptBody(review, chosen),
          }),
        );
        return;
      }
      settled(
        what,
        await request<unknown>(agentUpgradeDeclineApiPath(agentId), { method: "POST", body: declineBody(review) }),
      );
    })();
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
        <p>{review?.displayName ?? ""}</p>
      </Notice>
    ) : null;

  // A 404 is the one answer for a reader who may not act and an agent that is not there: no card.
  if (busy || !hasAnOffer(review)) {
    return notice === null ? null : <div className="min-w-0">{notice}</div>;
  }

  const ready = allAnswered(review, chosen);
  const blocked = review.acceptUnavailable;
  const lede = `Version ${String(review.fromVersion)} is running. Version ${String(review.toVersion)} is on offer.${
    review.badge === "declined" ? " You said no to it before." : ""
  }`;
  return (
    <>
      {notice}
      <SectionCard
        title={UPGRADE_HEADING}
        lede={lede}
        action={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={sending}
              onClick={() => {
                setStep("decline");
              }}
            >
              {DECLINE_LABEL}
            </Button>
            <Button
              size="sm"
              disabled={sending || !ready || blocked !== undefined}
              onClick={() => {
                setStep("accept");
              }}
            >
              {ACCEPT_LABEL}
            </Button>
          </div>
        }
        footer={
          blocked !== undefined ? (
            <Note kind="info">{blocked}</Note>
          ) : ready ? undefined : (
            <Note kind="info">{ANSWER_EVERY_CONFLICT}</Note>
          )
        }
      >
        <div className="flex min-w-0 flex-col gap-4 p-4">
          <Conflicts review={review} chosen={chosen} onChoose={choose} />
          <Updates review={review} />
          {review.conflicts.length === 0 && review.updates.length === 0 ? (
            <Note kind="info">This version changes nothing a person can read here.</Note>
          ) : null}
        </div>
      </SectionCard>
      <ConfirmDialog
        open={step !== null}
        question={
          step === "decline"
            ? `Say no to version ${String(review.toVersion)} of ${review.displayName}?`
            : `Upgrade ${review.displayName} to version ${String(review.toVersion)}?`
        }
        consequence={step === "decline" ? DECLINE_CONSEQUENCE : ACCEPT_CONSEQUENCE}
        confirmLabel={step === "decline" ? DECLINE_LABEL : ACCEPT_LABEL}
        cancelLabel={KEEP_LABEL}
        danger={step === "decline"}
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setStep(null);
        }}
      />
    </>
  );
}
