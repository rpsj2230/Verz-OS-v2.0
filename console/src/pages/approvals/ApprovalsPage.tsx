/**
 * The approvals waiting on this reader, on the shared page kit: the kit's header, search, filter,
 * order and states around the cards a phone can read and decide.
 *
 * **Nothing on this page decides who is offered what.** The API builds each card at the reader's
 * reach and filters before it bounds, and this page draws what arrived, in the order it arrived.
 * There is no count above the list and no card drawn for an approval the reader may not decide.
 *
 * **After a confirmed decision the queue is asked again**, rather than edited in place, and the
 * verdict is said above it with focus moved there, because the card that was pressed is gone and a
 * phone would otherwise be left looking at nothing (`A_CONFIRMATION_IS_DRAWN_WHERE_THE_THUMB_IS`).
 *
 * Task ids: M35.3.1.2, M35.3.1.1, M40.6.1.5, M40.1.2.3, M27.8.6, M27.16.1, M27.15.31
 */

import { CheckCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import type { components } from "../../api/schema";
import { EmptyState, FailureState, ListToolbar, LoadingState, Note, PageHeader } from "../../components/kit";
import { FETCHING_MORE, NOTHING_MATCHES, SHOW_MORE } from "../../components/ListControls";
import { narrows, NO_QUESTION, type FilterChoice, type SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { Button } from "../../components/ui/button";
import { WaitingPublishes } from "../agents/WaitingPublishes";
import { APPROVALS_API_PATH, readApprovalQueue } from "../approvalsQuery";
import { nameOf, peopleIn } from "../review/parts";
import { ApprovalCard, DecisionControls, said, type Verdict } from "./ApprovalCard";

/** Why the page moves focus to the sentence confirming a decision. */
export const A_CONFIRMATION_IS_DRAWN_WHERE_THE_THUMB_IS =
  "On a phone the decided card is scrolled to, and after a confirmed decision it is gone: the " +
  "queue is asked again and the card on its own loses its buttons, so the control somebody " +
  "pressed no longer exists and the sentence saying what happened is drawn at the top of a " +
  "page they are not looking at. Focus goes to that sentence, which scrolls it onto the " +
  "screen and has a screen reader read it, and only after the API has confirmed the decision.";

export const APPROVALS_HEADING = "Approvals";
export const APPROVALS_LEDE = "Actions waiting for you to decide, soonest to lapse first.";
export const NO_APPROVALS = "Nothing is waiting for you.";
export const NO_APPROVALS_MORE = "An approval appears here when an agent asks before acting on something you may decide.";
export const MORE_APPROVALS = "There are more approvals than this page shows.";
export const APPROVAL_LIST_LABEL = "Approvals waiting for you";
export const FILTERS_LABEL = "Narrow the approvals";
export const READING_APPROVALS = "Reading the approvals waiting for you.";

type QueueRow = components["schemas"]["ApprovalCardView"];

/** The filter the queue route declares that this page offers, over the people on cards drawn. */
export const QUEUE_FILTERS: readonly FilterChoice<QueueRow>[] = [
  { column: "runs_as", label: "Runs as", everything: "Anybody", read: (row) => row.runs_as },
];

export const QUEUE_SORTS: readonly SortChoice[] = [
  { value: "", label: "Soonest to lapse first" },
  { value: "-raised_at", label: "Most recently raised first" },
  { value: "runs_as", label: "By who it runs as" },
];

/** Put focus on the sentence confirming a decision, once, when the API has confirmed one. */
export function useConfirmationInView(sentence: RefObject<HTMLParagraphElement | null>, round: number): void {
  useEffect(() => {
    if (round > 0) {
      sentence.current?.focus();
    }
  }, [sentence, round]);
}

/** The sentence saying what the last confirmed decision was, which takes focus. */
export function Confirmed({ verdict, sentence }: { readonly verdict: Verdict | null; readonly sentence: RefObject<HTMLParagraphElement | null> }) {
  if (verdict === null) {
    return null;
  }
  return (
    <p ref={sentence} tabIndex={-1} role="status" className="m-0 rounded-md border border-line bg-ok-wash px-3 py-2 text-sm text-ok outline-hidden">
      {said(verdict)}
    </p>
  );
}

export function ApprovalsPage() {
  const [round, setRound] = useState(0);
  const [last, setLast] = useState<Verdict | null>(null);
  const decided = useCallback((verdict: Verdict) => {
    setLast(verdict);
    setRound((one) => one + 1);
  }, []);
  const sentence = useRef<HTMLParagraphElement | null>(null);
  useConfirmationInView(sentence, round);

  const listing = useListing<QueueRow>(APPROVALS_API_PATH, { choices: QUEUE_FILTERS, version: round });
  const people = useMemo(() => peopleIn(listing.body), [listing.body]);
  const choices = QUEUE_FILTERS.map((choice) => ({ ...choice, describe: (value: string) => nameOf(people, value) }));
  const read = readApprovalQueue(listing.body);

  let body: ReactNode;
  if (listing.failure !== null) {
    body = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    body = <LoadingState label={READING_APPROVALS} rows={2} />;
  } else if (read === null) {
    body = null;
  } else if (read.cards.length === 0) {
    body = narrows(listing.question) ? (
      <EmptyState
        title={NOTHING_MATCHES}
        description="Change the search or clear a filter."
        action={
          <Button
            variant="outline"
            onClick={() => {
              listing.ask({ ...NO_QUESTION, sort: listing.question.sort });
            }}
          >
            Clear search and filters
          </Button>
        }
      />
    ) : (
      <EmptyState title={NO_APPROVALS} description={NO_APPROVALS_MORE} icon={<CheckCheck aria-hidden />} />
    );
  } else {
    body = (
      <ul className="approval-list" aria-label={APPROVAL_LIST_LABEL}>
        {read.cards.map((card) => (
          <li key={card.suspensionId}>
            <ApprovalCard card={card} people={people} linked decision={<DecisionControls suspensionId={card.suspensionId} mayTakeOver={card.mayTakeOver} onDecided={decided} />} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div data-slot="list-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: APPROVALS_HEADING }]} title={APPROVALS_HEADING} lede={APPROVALS_LEDE} />
      <Confirmed verdict={last} sentence={sentence} />
      <section aria-label={APPROVAL_LIST_LABEL} className="flex min-w-0 flex-col gap-3">
        <ListToolbar label={FILTERS_LABEL} listing={listing} choices={choices} sorts={QUEUE_SORTS} />
        {body}
        {listing.moreFailure === null ? null : <FailureState failure={listing.moreFailure} />}
        {listing.fetchingMore ? (
          <p role="status" className="m-0 text-[12.5px] text-dim">
            {FETCHING_MORE}
          </p>
        ) : null}
        {listing.more ? (
          <div>
            <Button variant="outline" className="min-h-11 sm:min-h-9" disabled={listing.fetchingMore} onClick={listing.showMore}>
              {SHOW_MORE}
            </Button>
          </div>
        ) : null}
        {read?.truncated === true ? <Note>{MORE_APPROVALS}</Note> : null}
      </section>
      <WaitingPublishes />
    </div>
  );
}
