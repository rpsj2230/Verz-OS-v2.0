/**
 * One legal hold and one erasure request on pages of their own, each read out of the answer the
 * Retention views read (the newest report's cited holds; the erasure queue), so a row the API did not
 * send is the same one sentence whether it was withheld or never existed.
 *
 * A hold's page says what it covers and why, lifts it through its confirmation, and links to its
 * history in the Audit log. An erasure request's page says where it stands and, once it has finished,
 * what it did store by store, in `retentionQuery.storeLines`' four terms, so a request that finished
 * incomplete names what still holds the person's data.
 *
 * Task ids: M27.7.24, M27.16.1
 */

import { History } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
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
  SectionCard,
  StatCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { subjectAddress } from "../auditQuery";
import { erasureState, storeLines } from "../retentionQuery";
import { nameOf, Pill, whenWords } from "../review/parts";
import { ErasurePill } from "./pills";
import { LIFT_LABEL, Told, useLift } from "./RetentionActs";
import { READING_RETENTION, RETENTION_HEADING, viewAddress, VIEW_LABELS } from "./RetentionPage";
import { useRetention } from "./useRetention";

export const NO_HOLD = "No legal hold here";
export const NO_HOLD_MORE = "It may have been lifted. The Legal holds view lists the holds the newest report cited.";
export const NO_ERASURE = "No erasure request here";
export const NO_ERASURE_MORE = "The Erasure requests view lists every request you may see.";
export const HISTORY = "History";

function Absent({ trail, title, lede, back }: { readonly trail: readonly { label: string; to?: string }[]; readonly title: string; readonly lede: string; readonly back: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[...trail, { label: title }]} title={title} lede={lede} actions={back} />
    </div>
  );
}

function BackTo({ view }: { readonly view: "holds" | "erasures" }) {
  return (
    <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
      <Link to={viewAddress(view)}>{VIEW_LABELS[view]}</Link>
    </Button>
  );
}

function HistoryLink({ kind, id }: { readonly kind: string; readonly id: string }) {
  return (
    <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
      <Link to={subjectAddress(kind, id)}>
        <History aria-hidden /> {HISTORY}
      </Link>
    </Button>
  );
}

export function HoldPage({ holdId }: { readonly holdId: string }) {
  const retention = useRetention();
  const [told, setTold] = useState<string | null>(null);
  const { again } = retention;
  const onDone = useCallback(
    (sentence: string) => {
      setTold(sentence);
      again();
    },
    [again],
  );
  const lifting = useLift(retention.controls, onDone);
  const trail = [{ label: RETENTION_HEADING, to: viewAddress("sweep") }, { label: VIEW_LABELS.holds, to: viewAddress("holds") }];

  if (retention.failure !== null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader crumbs={trail} title={VIEW_LABELS.holds} />
        <FailureState failure={retention.failure} />
      </div>
    );
  }
  if (retention.busy || retention.controls === null) {
    return <LoadingState label={READING_RETENTION} />;
  }
  const hold = retention.report?.holds.find((one) => one.hold_id === holdId);
  if (hold === undefined) {
    return (
      <>
        <Absent trail={trail} title={NO_HOLD} lede={NO_HOLD_MORE} back={<BackTo view="holds" />} />
        <Told told={told} />
      </>
    );
  }
  return (
    <DetailPage
      crumbs={[...trail, { label: hold.hold_id }]}
      header={
        <>
          <DetailHeader
            name={`Legal hold ${hold.hold_id}`}
            headingId={`hold-${hold.hold_id}`}
            pills={<Pill tone="warn">In force</Pill>}
            actions={
              <>
                <HistoryLink kind="legal_hold" id={hold.hold_id} />
                {retention.controls.may_hold ? (
                  <Button size="sm" variant="destructive" className="min-h-11 sm:min-h-8" disabled={lifting.busy} onClick={() => lifting.lift(hold.hold_id)}>
                    {LIFT_LABEL}
                  </Button>
                ) : null}
              </>
            }
            figures={
              <KpiStrip label="This hold" count={2}>
                <StatCard label="Covers" value={hold.company_wide ? "Everybody" : "Named people"} />
                <StatCard label="Cited by the report of" value={retention.report === null ? undefined : whenWords(retention.report.at)} />
              </KpiStrip>
            }
          />
          <Told told={told} />
          {lifting.drawn}
        </>
      }
    >
      <SectionCard title="What it holds">
        <FactList>
          <Fact label="Reason">{hold.reason_code.replace(/_/g, " ")}</Fact>
          <Fact label="Covers">{hold.company_wide ? "Everybody's data and actions, until it is lifted." : "The people and actions it names, until it is lifted."}</Fact>
          <Fact label="While in force">{retention.controls.holding}</Fact>
        </FactList>
      </SectionCard>
    </DetailPage>
  );
}

export function ErasurePage({ requestId }: { readonly requestId: string }) {
  const retention = useRetention();
  const trail = [{ label: RETENTION_HEADING, to: viewAddress("sweep") }, { label: VIEW_LABELS.erasures, to: viewAddress("erasures") }];

  if (retention.failure !== null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <PageHeader crumbs={trail} title={VIEW_LABELS.erasures} />
        <FailureState failure={retention.failure} />
      </div>
    );
  }
  if (retention.busy || retention.queue === null) {
    return <LoadingState label={READING_RETENTION} />;
  }
  const one = retention.queue.requests.find((request) => request.request_id === requestId);
  if (one === undefined) {
    return <Absent trail={trail} title={NO_ERASURE} lede={NO_ERASURE_MORE} back={<BackTo view="erasures" />} />;
  }
  const lines = storeLines(one);
  return (
    <DetailPage
      crumbs={[...trail, { label: one.reason_reference }]}
      header={
        <DetailHeader
          name={`Erasure ${one.reason_reference}`}
          headingId={`erasure-${one.request_id}`}
          pills={<ErasurePill outcome={one.outcome} />}
          actions={<HistoryLink kind="erasure" id={one.request_id} />}
          figures={
            <KpiStrip label="This request" count={3}>
              <StatCard label="Filed" value={whenWords(one.requested_at)} sub={`by ${nameOf(retention.filers, one.requested_by)}`} />
              <StatCard label="Finished" value={one.finished_at === null ? undefined : whenWords(one.finished_at)} />
              <StatCard label="Held by" value={one.holds.length === 0 ? "No hold" : one.holds.join(", ")} />
            </KpiStrip>
          }
        />
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        <SectionCard title="Where it stands">
          <FactList>
            <Fact label="Person, by reference">
              <span className="font-mono text-[12px]">{one.subject_id}</span>
            </Fact>
            <Fact label="Now">{erasureState(one, whenWords)}</Fact>
          </FactList>
        </SectionCard>
        {lines.length === 0 ? null : (
          <SectionCard title="What it did, store by store">
            <ul aria-label="What the request did" className="m-0 flex list-disc flex-col gap-1 pl-5 text-[13px] text-body">
              {lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </SectionCard>
        )}
        <Advanced>
          <FactList>
            <Fact label="Request">
              <code>{one.request_id}</code>
            </Fact>
            <Fact label="Filed by">
              <code>{one.requested_by}</code>
            </Fact>
          </FactList>
        </Advanced>
      </div>
    </DetailPage>
  );
}
