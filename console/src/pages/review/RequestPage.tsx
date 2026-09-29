/**
 * One elevation request: who asked, for what, over which scope, for how long and why; where it
 * stands, who decided it and when it lapses; and Approve and Deny where this reader may decide it.
 *
 * **Asked of the requests list by id** (`reviewQuery.requestApiPath`), so the request is exactly as
 * the list would show it to this reader, `decidable` included, and a request they may not see is the
 * same empty answer as one that never existed.
 *
 * Task ids: M27.7.8, M27.16.1
 */

import { History } from "lucide-react";
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
import { ELEVATION_DECISIONS, ELEVATION_PATH, readElevation, reasonWords, STATE_WORDS } from "../governPeopleQuery";
import { useElevationDecisions } from "./ElevationActs";
import { ELEVATION_HEADING } from "./ElevationPage";
import { nameOf, peopleIn, Pill, whenWords } from "./parts";
import { ACT_LABELS } from "./reviewActions";
import { hoursWords, requestApiPath, STATE_TONES } from "./reviewQuery";
import { REVIEW_CRUMB } from "./ReviewPage";

export const READING_REQUEST = "Reading the request.";
export const NO_REQUEST = "No request here";
export const NO_REQUEST_MORE = "The requests list shows every elevation request you may see.";

export function RequestPage({ requestId }: { readonly requestId: string }) {
  const [version, setVersion] = useState(0);
  const onDone = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const answer = useResource<unknown>(requestApiPath(requestId), version);
  const page = useMemo(() => readElevation(answer.data), [answer.data]);
  const people = useMemo(() => peopleIn(answer.data), [answer.data]);
  const decisions = useElevationDecisions({ what: page?.what ?? "", recorded: page?.recorded ?? "" }, onDone);
  const crumbs = [{ label: REVIEW_CRUMB }, { label: ELEVATION_HEADING, to: ELEVATION_PATH }];

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy && answer.data === null) {
    return <LoadingState label={READING_REQUEST} />;
  }
  const row = page?.items?.[0];
  if (row === undefined) {
    return (
      <DetailPage crumbs={[...crumbs, { label: NO_REQUEST }]} header={decisions.drawn}>
        <EmptyState
          title={NO_REQUEST}
          description={NO_REQUEST_MORE}
          action={
            <Button asChild variant="outline" className="text-ink no-underline">
              <Link to={ELEVATION_PATH}>{ELEVATION_HEADING}</Link>
            </Button>
          }
        />
      </DetailPage>
    );
  }
  const who = nameOf(people, row.principal_id, row.display_name);

  return (
    <DetailPage
      crumbs={[...crumbs, { label: `${row.capability}, ${who}` }]}
      header={
        <>
          <DetailHeader
            name={who}
            headingId={`request-${row.request_id}`}
            pills={<Pill tone={STATE_TONES[row.state]}>{STATE_WORDS[row.state]}</Pill>}
            subline={[row.capability, row.department].filter((one) => one !== null && one !== "").join(" · ")}
            actions={
              <>
                <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
                  <Link to={subjectAddress("principal", row.principal_id, "permissions")}>
                    <History aria-hidden /> {ACT_LABELS.history}
                  </Link>
                </Button>
                {row.decidable
                  ? ELEVATION_DECISIONS.map((decision) => (
                      <Button
                        key={decision}
                        size="sm"
                        variant={decision === "denied" ? "destructive" : "default"}
                        className="min-h-11 sm:min-h-8"
                        disabled={decisions.busy}
                        onClick={() => {
                          decisions.decide(row, decision);
                        }}
                      >
                        {decision === "approved" ? ACT_LABELS.approve : ACT_LABELS.deny}
                      </Button>
                    ))
                  : null}
              </>
            }
            figures={
              <KpiStrip label="This request's dates" count={3}>
                <StatCard label="Asked" value={whenWords(row.requested_at)} />
                <StatCard label="For" value={hoursWords(row.hours)} />
                <StatCard
                  label={row.lapses_at === null ? "Decided" : "Lapses"}
                  value={row.lapses_at === null ? (row.decided_at === null ? undefined : whenWords(row.decided_at)) : whenWords(row.lapses_at)}
                  sub={row.decided_by === null ? undefined : `by ${nameOf(people, row.decided_by)}`}
                />
              </KpiStrip>
            }
          />
          {decisions.drawn}
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        <SectionCard title="What was asked">
          <FactList>
            <Fact label="Capability">
              <Chip mono>{row.capability}</Chip>
            </Fact>
            <Fact label="Over">
              <Chip mono>{row.scope_slug}</Chip>
            </Fact>
            <Fact label="Why">{reasonWords(row.reason)}</Fact>
            <Fact label="What it is for">{row.explanation}</Fact>
          </FactList>
        </SectionCard>
        <Advanced>
          <FactList>
            <Fact label="Request">
              <code>{row.request_id}</code>
            </Fact>
            <Fact label="Asked by">
              <code>{row.principal_id}</code>
            </Fact>
            {row.decided_by === null ? null : (
              <Fact label="Decided by">
                <code>{row.decided_by}</code>
              </Fact>
            )}
          </FactList>
        </Advanced>
      </div>
    </DetailPage>
  );
}
