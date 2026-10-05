/**
 * Whether a document is public for the website widget, on its Dashboard (M10.7.2).
 *
 * The route is `brain.knowledge_public_routes`: it says whether the document is public, who made it
 * so and when, and whether this reader may move it the other way, with the reason when not. **The
 * card draws the button the API said would be taken, or the API's sentence, never a button that is
 * refused**, and nothing here decides who may mark what.
 *
 * **Both directions are confirmed first.** Making a document public is a one-way door in practice,
 * because a visitor who has read an answer keeps it; stopping it switches off something visitors
 * are being shown. Each dialog says which (`tests/destructive-confirmed.test.ts`).
 *
 * Task ids: M10.7.2
 */

import { useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Fact, FactList, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { publicPath } from "../knowledgeLifecycleQuery";
import { dayWords } from "./knowledgeDocuments";

export const PUBLIC_HEADING = "Website widget";
export const MAKE_PUBLIC = "Make public";
export const STOP_PUBLIC = "Stop showing it";
export const MAKE_PUBLIC_CONSEQUENCE =
  "Anybody on your website's chat widget can then be answered from this document, word for word. " +
  "Stopping it later does not take back what a visitor has already read.";
export const STOP_PUBLIC_CONSEQUENCE =
  "The website's chat widget stops answering from this document from the next question. " +
  "A visitor asking about it is told it was not found.";

/** One document's marking, as the route answers it. */
export interface PublicMarking {
  readonly public: boolean;
  readonly markedByName: string | undefined;
  readonly markedBy: string | undefined;
  readonly markedAt: string | undefined;
  readonly mayChange: boolean;
  readonly says: string | undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

/** The route's answer read into a marking, or null for anything else. */
export function readPublicMarking(data: unknown): PublicMarking | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const one = data as Record<string, unknown>;
  if (typeof one.public !== "boolean" || typeof one.may_change !== "boolean") {
    return null;
  }
  return {
    public: one.public,
    markedBy: text(one.marked_by),
    markedByName: text(one.marked_by_name),
    markedAt: text(one.marked_at),
    mayChange: one.may_change,
    says: text(one.says),
  };
}

/** What the card says about the marking, in a sentence. */
export function publicWords(marking: PublicMarking): string {
  if (!marking.public) {
    return "Not public";
  }
  const who = marking.markedByName ?? marking.markedBy;
  const when = dayWords(marking.markedAt);
  return ["Public", when === undefined ? undefined : `since ${when}`, who === undefined ? undefined : `made so by ${who}`]
    .filter((one): one is string => one !== undefined)
    .join(", ");
}

export function PublicMarkingCard({ itemId, title }: { readonly itemId: string; readonly title: string }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(publicPath(itemId), version);
  const marking = useMemo(() => readPublicMarking(answer.data), [answer.data]);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  if (answer.failure !== null || marking === null) {
    return null;
  }
  const next = !marking.public;
  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(publicPath(itemId), { method: "PUT", body: { public: next } });
      setBusy(false);
      setConfirming(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        setVersion((was) => was + 1);
      }
    })();
  };

  return (
    <SectionCard
      title={PUBLIC_HEADING}
      action={
        marking.mayChange ? (
          <Button
            size="sm"
            variant="outline"
            className="min-h-11 sm:min-h-8"
            onClick={() => {
              setConfirming(true);
            }}
          >
            {next ? MAKE_PUBLIC : STOP_PUBLIC}
          </Button>
        ) : undefined
      }
    >
      {failure === null ? null : <FailureNotice failure={failure} fields={["public", "item"]} />}
      <FactList>
        <Fact label="Answers website visitors">{publicWords(marking)}</Fact>
      </FactList>
      {marking.mayChange || marking.says === undefined ? null : <Note>{marking.says}</Note>}
      <ConfirmDialog
        open={confirming}
        question={next ? `Make ${title} public?` : `Stop showing ${title} to website visitors?`}
        consequence={next ? MAKE_PUBLIC_CONSEQUENCE : STOP_PUBLIC_CONSEQUENCE}
        confirmLabel={next ? MAKE_PUBLIC : STOP_PUBLIC}
        cancelLabel="Leave it as it is"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </SectionCard>
  );
}
