/**
 * What a person may do to one document from an agent's Knowledge section: retire it, and fetch a
 * link again for a newer version of it (M39.9.1.5).
 *
 * **A document is the company's, so both acts change it for every agent and every person, and each
 * is confirmed first in a sentence that says so.** Retiring stops every answer using it and keeps it
 * on file with its history; fetching again replaces the version answers are drawn from with what
 * the page says now. Neither is a setting of this agent.
 *
 * **Nothing here decides who may.** An act is drawn only where the API said this reader may act on
 * this document (`canRetire`, and `canRefetch` for a link), and the API decides it again when it
 * arrives, in the one sentence an absent document gets. **A link is fetched again only when this
 * button is pressed**: nothing here schedules a fetch or asks the page on a timer.
 *
 * Task ids: M39.9.1.5
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { FORM, NEW_VERSION_CONSEQUENCE, ReviewField, reviewProblem, Submit } from "../knowledge/formParts";
import { defaultReviewDay, instantOf, LIFECYCLE_FIELDS } from "../knowledgeLifecycleQuery";
import { agentKnowledgeRefetchApiPath, agentKnowledgeRetireApiPath, type KnowledgeItem } from "./agentKnowledgeQuery";

export const RETIRE = "Retire";
export const FETCH_AGAIN = "Fetch the page again";
export const RETIRE_CONSEQUENCE =
  "No agent answers from it from now on, this one and every other. It stays on file with its history, readable by the people who could read it, and the change is recorded in the audit trail.";
export const FETCH_CONSEQUENCE = `The page is read once more, now, from the address it was added from. ${NEW_VERSION_CONSEQUENCE}`;

function Retire({ agentId, item, onDone }: { readonly agentId: string; readonly item: KnowledgeItem; readonly onDone: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(agentKnowledgeRetireApiPath(agentId, item.itemId), { method: "POST" });
      setBusy(false);
      setConfirming(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <Button
        variant="quiet"
        size="xs"
        className="min-h-11 sm:min-h-6"
        onClick={() => {
          setConfirming(true);
        }}
      >
        {RETIRE}
      </Button>
      <ConfirmDialog
        open={confirming}
        question={`Retire ${item.title}?`}
        consequence={RETIRE_CONSEQUENCE}
        confirmLabel={RETIRE}
        cancelLabel="Keep it as it is"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </>
  );
}

function FetchAgainForm({ agentId, item, onDone }: { readonly agentId: string; readonly item: KnowledgeItem; readonly onDone: () => void }) {
  const [day, setDay] = useState(defaultReviewDay());
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const problem = reviewProblem(day);
    setProblems(problem === null ? [] : [problem]);
    setConfirming(problem === null);
  };

  const send = () => {
    const instant = instantOf(day);
    if (instant === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(agentKnowledgeRefetchApiPath(agentId, item.itemId), { method: "POST", body: { review_by: instant } });
      setBusy(false);
      setConfirming(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <>
      <form className={FORM} aria-label="Fetch the page again" onSubmit={onSubmit} noValidate>
        {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
        <ReviewField value={day} onChange={setDay} problems={problems} />
        <Submit label={FETCH_AGAIN} busy={busy} />
      </form>
      <ConfirmDialog
        open={confirming}
        question={`Fetch ${item.title} again and replace it?`}
        consequence={FETCH_CONSEQUENCE}
        confirmLabel={FETCH_AGAIN}
        cancelLabel="Keep the current version"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </>
  );
}

/** The acts offered on one document, or nothing at all where the API offered none. */
export function ItemActs({ agentId, item, onChanged }: { readonly agentId: string; readonly item: KnowledgeItem; readonly onChanged: () => void }) {
  const [fetching, setFetching] = useState(false);
  if (!item.canRetire && !item.canRefetch) {
    return null;
  }
  return (
    <div data-slot="knowledge-acts" className="flex min-w-0 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        {item.canRefetch ? (
          <Button
            variant="quiet"
            size="xs"
            className="min-h-11 sm:min-h-6"
            aria-expanded={fetching}
            onClick={() => {
              setFetching((was) => !was);
            }}
          >
            {FETCH_AGAIN}
          </Button>
        ) : null}
        {item.canRetire ? <Retire agentId={agentId} item={item} onDone={onChanged} /> : null}
      </div>
      {fetching ? (
        <div data-slot="knowledge-fetch-again" className="max-w-xl">
          <FetchAgainForm agentId={agentId} item={item} onDone={onChanged} />
        </div>
      ) : null}
    </div>
  );
}
