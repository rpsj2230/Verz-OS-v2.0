/**
 * One holding under review: a grant or a pack, who holds it, who granted it and why, when it lapses,
 * its last review, and the two decisions.
 *
 * **Asked of the review list by id** (`reviewQuery.holdingApiPath`), so the row is exactly what the
 * review screen would show this reviewer and a holding they may not decide is the same empty answer
 * as one that never existed: one sentence and a way back, with nothing about why.
 *
 * **The people are named; their ids are in Advanced.** The holder's page and their access changes in
 * the Audit log are one link each, because "who gave them that" is the next question a reviewer asks.
 *
 * Task ids: M27.7.9, M27.16.1
 */

import { History, UserRound } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  DetailHeader,
  DetailPage,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  SectionCard,
  StatCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { subjectAddress } from "../auditQuery";
import { DECISIONS, personAddress, readReview, REVIEW_PATH } from "../governPeopleQuery";
import { scopeLines } from "../scopeText";
import { nameOf, peopleIn, Pill, whenWords } from "./parts";
import { ACT_LABELS } from "./reviewActions";
import { holdingApiPath, holdingTitle, kindWords, reviewWords } from "./reviewQuery";
import { useReviewActs } from "./ReviewActs";
import { DOES_NOT_LAPSE, REVIEW_CRUMB, REVIEW_HEADING } from "./ReviewPage";

export const READING_HOLDING = "Reading the grant.";
export const NO_HOLDING = "No grant to review here";
export const NO_HOLDING_MORE = "It may have been removed. The review lists every grant you may decide.";

export function HoldingPage({ kind, rowId }: { readonly kind: string; readonly rowId: string }) {
  const [version, setVersion] = useState(0);
  const onDecided = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const answer = useResource<unknown>(holdingApiPath(kind, rowId), version);
  const review = useMemo(() => readReview(answer.data), [answer.data]);
  const people = useMemo(() => peopleIn(answer.data), [answer.data]);
  const acts = useReviewActs(review, onDecided);
  const crumbs = [{ label: REVIEW_CRUMB }, { label: REVIEW_HEADING, to: REVIEW_PATH }];

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy && answer.data === null) {
    return <LoadingState label={READING_HOLDING} />;
  }
  const row = review.rows[0];
  if (row === undefined) {
    return (
      <DetailPage crumbs={[...crumbs, { label: NO_HOLDING }]} header={acts.drawn}>
        <EmptyState
          title={NO_HOLDING}
          description={NO_HOLDING_MORE}
          action={
            <Button asChild variant="outline" className="text-ink no-underline">
              <Link to={REVIEW_PATH}>{REVIEW_HEADING}</Link>
            </Button>
          }
        />
      </DetailPage>
    );
  }
  const holder = nameOf(people, row.principal_id, row.display_name);
  const title = holdingTitle(row);

  return (
    <DetailPage
      crumbs={[...crumbs, { label: `${title}, ${holder}` }]}
      header={
        <>
          <DetailHeader
            name={holder}
            headingId={`holding-${row.row_id}`}
            pills={
              <>
                <Pill tone="plain">{kindWords(row.kind)}</Pill>
                <Pill tone={row.last_decision === null ? "warn" : row.last_decision === "keep" ? "ok" : "plain"}>
                  {reviewWords(row.last_decision)}
                </Pill>
              </>
            }
            subline={[title, row.department].filter((one) => one !== null && one !== "").join(" · ")}
            actions={
              <>
                <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
                  <Link to={subjectAddress("principal", row.principal_id, "permissions")}>
                    <History aria-hidden /> {ACT_LABELS.history}
                  </Link>
                </Button>
                {DECISIONS.map((decision) => (
                  <Button
                    key={decision}
                    size="sm"
                    variant={decision === "remove" ? "destructive" : "default"}
                    className="min-h-11 sm:min-h-8"
                    disabled={acts.busy}
                    onClick={() => {
                      acts.decide(row, decision);
                    }}
                  >
                    {decision === "keep" ? ACT_LABELS.keep : ACT_LABELS.remove}
                  </Button>
                ))}
              </>
            }
            figures={
              <KpiStrip label="This grant's dates" count={3}>
                <StatCard label="Granted" value={whenWords(row.granted_at)} sub={nameOf(people, row.granted_by)} />
                <StatCard label="Lapses" value={row.lapses_at === null ? DOES_NOT_LAPSE : whenWords(row.lapses_at)} />
                <StatCard
                  label="Last review"
                  value={row.last_decided_at === null ? reviewWords(null) : whenWords(row.last_decided_at)}
                  sub={row.last_decided_at === null ? undefined : `${reviewWords(row.last_decision)} by ${nameOf(people, row.last_decided_by)}`}
                />
              </KpiStrip>
            }
          />
          {acts.drawn}
        </>
      }
    >
      <div className="[display:grid] min-w-0 grid-cols-1 gap-4 lg:grid-cols-2">
        <SectionCard title="What is held">
          <FactList>
            <Fact label={row.pack === null ? "Capability" : "Capabilities"}>
              <span className="flex flex-wrap gap-1">
                {row.capabilities.map((one) => (
                  <Chip key={one} mono>
                    {one}
                  </Chip>
                ))}
              </span>
            </Fact>
            {row.pack === null ? null : <Fact label="Pack">{row.pack}</Fact>}
            <Fact label="Over">
              <span className="flex flex-wrap gap-1">
                {scopeLines(row.scope).map((line) => (
                  <Chip key={line} mono>
                    {line}
                  </Chip>
                ))}
              </span>
            </Fact>
          </FactList>
        </SectionCard>
        <SectionCard title="Why it was granted">
          <FactList>
            <Fact label="Granted by">{nameOf(people, row.granted_by)}</Fact>
            <Fact label="When">{whenWords(row.granted_at)}</Fact>
            <Fact label="Reason">{row.reason}</Fact>
            <Fact label="Holder">
              <Link to={personAddress(row.principal_id)} className="inline-flex items-center gap-1 text-ink underline-offset-4 hover:underline">
                <UserRound aria-hidden className="size-3.5" /> {holder}
              </Link>
            </Fact>
          </FactList>
        </SectionCard>
      </div>
      <div className="mt-4">
        <Advanced>
          <FactList>
            <Fact label="Holding">
              <code>{`${row.kind}:${row.row_id}`}</code>
            </Fact>
            <Fact label="Holder">
              <code>{row.principal_id}</code>
            </Fact>
            <Fact label="Granted by">
              <code>{row.granted_by}</code>
            </Fact>
          </FactList>
        </Advanced>
      </div>
    </DetailPage>
  );
}
