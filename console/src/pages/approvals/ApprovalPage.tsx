/**
 * One approval on its own page, where a link from a chat message lands: the approval's header and
 * its dates, then the card with the two decisions, and its identifiers in Advanced.
 *
 * **The refusal is the API's sentence**, the same for an approval that is not the reader's and one
 * that does not exist, so this page says nothing about which.
 *
 * Task ids: M35.3.1.2, M40.6.1.5, M27.16.1
 */

import { useMemo, useRef, useState } from "react";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  DetailHeader,
  DetailPage,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  PageHeader,
  StatCard,
} from "../../components/kit";
import { approvalApiPath, readApprovalCard } from "../approvalsQuery";
import { nameOf, peopleIn, Pill, whenWords } from "../review/parts";
import { APPROVALS_ADDRESS, ApprovalCard, DecisionControls, type Verdict } from "./ApprovalCard";
import { APPROVALS_HEADING, Confirmed, useConfirmationInView } from "./ApprovalsPage";

export const READING_APPROVAL = "Reading the approval.";
export const ONE_APPROVAL = "Approval";

/** The first line of the artefact names the action, which is what the page is called. */
function titleOf(artefact: string): string {
  return artefact.split("\n")[0]?.trim() || "An approval";
}

export function ApprovalPage({ suspensionId }: { readonly suspensionId: string }) {
  const answer = useResource<unknown>(approvalApiPath(suspensionId));
  const [decided, setDecided] = useState<Verdict | null>(null);
  const sentence = useRef<HTMLParagraphElement | null>(null);
  useConfirmationInView(sentence, decided === null ? 0 : 1);
  const people = useMemo(() => peopleIn(answer.data), [answer.data]);

  const trail = [{ label: APPROVALS_HEADING, to: APPROVALS_ADDRESS }, { label: ONE_APPROVAL }];
  if (answer.failure !== null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader crumbs={trail} title={ONE_APPROVAL} />
        <FailureState failure={answer.failure} />
      </div>
    );
  }
  if (answer.busy) {
    return <LoadingState label={READING_APPROVAL} rows={2} />;
  }
  const card = readApprovalCard(answer.data);
  if (card === null) {
    return null;
  }
  const title = titleOf(card.artefact);
  return (
    <DetailPage
      crumbs={[{ label: APPROVALS_HEADING, to: APPROVALS_ADDRESS }, { label: title }]}
      header={
        <DetailHeader
          name={title}
          headingId={`approval-${card.suspensionId}`}
          pills={
            decided === null ? (
              <Pill tone="warn">Waiting for you</Pill>
            ) : decided === "approved" ? (
              <Pill tone="ok">Approved</Pill>
            ) : decided === "taken_over" ? (
              <Pill tone="plain">Taken over</Pill>
            ) : (
              <Pill tone="plain">Rejected</Pill>
            )
          }
          figures={
            <KpiStrip label="This approval's dates" count={3}>
              <StatCard label="Runs as" value={nameOf(people, card.runsAs)} />
              <StatCard label="Raised" value={whenWords(card.raisedAt)} />
              <StatCard label="Lapses" value={whenWords(card.expiresAt)} />
            </KpiStrip>
          }
        />
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        <Confirmed verdict={decided} sentence={sentence} />
        <ApprovalCard
          card={card}
          people={people}
          linked={false}
          decision={decided === null ? <DecisionControls suspensionId={card.suspensionId} mayTakeOver={card.mayTakeOver} onDecided={setDecided} /> : null}
        />
        <Advanced>
          <FactList>
            <Fact label="Approval">
              <code>{card.suspensionId}</code>
            </Fact>
            <Fact label="Runs as">
              <code>{card.runsAs}</code>
            </Fact>
          </FactList>
        </Advanced>
      </div>
    </DetailPage>
  );
}
