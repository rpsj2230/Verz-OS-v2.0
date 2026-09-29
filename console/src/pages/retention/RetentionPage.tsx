/**
 * Retention, legal holds and erasure on the shared page kit: one header and four views, each at its
 * own address. The sweep and how long each kind of thing is kept; the legal holds that stop it; the
 * requests to erase somebody's data; and the exports taken from the install.
 *
 * **One view per question, in the order a person deciding about a deletion asks them.** The old
 * screen was five cards on one page with three forms drawn open under them. Each form is now a drawer
 * behind the view's own button that says what every field takes, and a hold and an erasure request
 * each open a page of their own (`RetentionDetail.tsx`).
 *
 * **Nothing here decides who may act or what is listed.** The controls answer says which acts to
 * draw, from the retention module's own functions; the queue and the export log are the rows the API
 * admitted; a reader who may open the screen and may not read exports is told so in the API's own
 * sentence rather than shown an empty table, which would read as nothing having left the building.
 *
 * **The holds are those the newest report cited**, which is the one list of holds the API serves;
 * a hold placed since is lifted by its reference from the Legal holds view's second button.
 *
 * Task ids: M27.7.24, M27.16.1
 */

import { Archive, FileDown, Gavel, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  Chip,
  EmptyState,
  EntityTable,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
  StatCard,
  ViewSwitch,
  type DetailView,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { reasonLabel } from "../dataTransferQuery";
import {
  erasureState,
  EXPORT_LOG_API_PATH,
  exportEntriesSentence,
  exportVerdict,
  type CitedHold,
  type Controls,
  type ErasureRequest,
  type ExportLogEntry,
  type Kept,
  type Report,
  type StoreLine,
} from "../retentionQuery";
import { nameOf, peopleIn, Pill, whenWords } from "../review/parts";
import { ErasurePill } from "./pills";
import { ErasureDrawer, HoldDrawer, LiftDrawer, LIFT_LABEL, SweepActs, Told, useLift } from "./RetentionActs";
import { useRetention, type Retention } from "./useRetention";

export const RETENTION_HEADING = "Retention and erasure";
export const RETENTION_LEDE = "How long each kind of thing is kept, what stops it being removed, and requests to erase somebody's data.";
export const READING_RETENTION = "Reading what is kept and what is due.";
export const RETENTION_PATH = "/retention";
export const VIEWS_LABEL = "Retention views";

export const VIEWS = ["sweep", "holds", "erasures", "exports"] as const;
export type RetentionView = (typeof VIEWS)[number];
export const VIEW_LABELS: Readonly<Record<RetentionView, string>> = Object.freeze({
  sweep: "Sweep",
  holds: "Legal holds",
  erasures: "Erasure requests",
  exports: "Exports",
});

export function viewAddress(view: RetentionView): string {
  return view === "sweep" ? RETENTION_PATH : `${RETENTION_PATH}/${view}`;
}
export function holdAddress(holdId: string): string {
  return `${RETENTION_PATH}/holds/${encodeURIComponent(holdId)}`;
}
export function erasureAddress(requestId: string): string {
  return `${RETENTION_PATH}/erasures/${encodeURIComponent(requestId)}`;
}

export const NO_REPORT = "The sweep has not reported yet";
export const NO_REPORT_MORE = "The first report appears here after the sweep's next run.";
export const NO_STORES = "The newest report names no store it reaches.";
export const NO_WINDOWS = "This install declares no retention window.";
export const NO_HOLDS = "No legal hold is in force";
export const NO_HOLDS_MORE = "Holds are listed as the newest report cited them; one placed since appears after the next run.";
export const NO_ERASURES = "No erasure requests";
export const NO_ERASURES_MORE = "A request appears here when somebody files one to erase a person's data.";
export const NO_EXPORTS = "No exports taken";
export const NO_EXPORTS_MORE = "An export appears here when somebody takes one from Import and export or Access review.";
export const PLACE_HOLD = "Place a hold";
export const LIFT_BY_REFERENCE = "Lift a hold by reference";
export const FILE_ERASURE = "File an erasure request";
export const HOLD_NOT_YOURS = "Placing and lifting a hold need a company-wide authority you do not hold.";
export const ERASE_NOT_YOURS = "Filing an erasure request needs a company-wide authority you do not hold.";

function words(value: string): string {
  return value.replace(/_/g, " ");
}

function keptFor(line: { readonly days: number | null; readonly lifetime: string }): string {
  return line.days === null ? words(line.lifetime) : `${String(line.days)} days`;
}

function SweepView({ report, controls, onDone }: { readonly report: Report | null; readonly controls: Controls; readonly onDone: (told: string) => void }) {
  const stores: EntityColumn<StoreLine>[] = [
    {
      id: "store",
      header: "Store",
      hideable: false,
      cell: (line) => (
        <span className="flex flex-col">
          <span className="font-mono text-[12px] text-ink">{line.store}</span>
          {line.reached ? null : <span className="text-[12px] text-warn">{line.unreached_because}</span>}
        </span>
      ),
      text: (line) => line.store,
    },
    { id: "kept", header: "Kept as", cell: (line) => `${words(line.data_class)}, ${keptFor(line)}`, text: (line) => `${line.data_class}, ${keptFor(line)}` },
    { id: "beyond", header: "Past its window", align: "end", cell: (line) => (line.reached ? String(line.beyond_horizon) : ""), text: (line) => (line.reached ? String(line.beyond_horizon) : "") },
    { id: "held", header: "Held", align: "end", cell: (line) => (line.reached ? String(line.held) : ""), text: (line) => (line.reached ? String(line.held) : "") },
    { id: "due", header: "Due", align: "end", cell: (line) => (line.reached ? String(line.due) : ""), text: (line) => (line.reached ? String(line.due) : "") },
    { id: "removed", header: "Removed", align: "end", cell: (line) => (line.reached ? String(line.removed) : ""), text: (line) => (line.reached ? String(line.removed) : "") },
    {
      id: "queued",
      header: "Queued",
      align: "end",
      cell: (line) => (line.reached ? String(line.queued) : ""),
      text: (line) => (line.reached ? String(line.queued) : ""),
    },
    { id: "oldest", header: "Oldest, days", align: "end", hidden: true, cell: (line) => (line.oldest_days === null ? "" : String(line.oldest_days)), text: (line) => (line.oldest_days === null ? "" : String(line.oldest_days)) },
  ];
  const kept: EntityColumn<Kept>[] = [
    { id: "class", header: "Kind of thing", hideable: false, cell: (one) => words(one.data_class), text: (one) => one.data_class },
    { id: "how_long", header: "How long", cell: (one) => keptFor(one), text: (one) => keptFor(one) },
    { id: "why", header: "Why", cell: (one) => one.because, text: (one) => one.because },
  ];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      {report === null ? (
        <EmptyState title={NO_REPORT} description={NO_REPORT_MORE} icon={<Archive aria-hidden />} />
      ) : (
        <>
          <KpiStrip label="The newest retention report" count={4}>
            <StatCard label="Report of" value={whenWords(report.at)} sub={report.complete ? "every store counted" : "some stores not counted"} />
            <StatCard label="That run" value={report.report_only ? "Reported only" : `Removed ${String(report.removed)}`} />
            <StatCard label="Due now" value={String(report.stores.filter((one) => one.reached).reduce((total, one) => total + one.due, 0))} />
            <StatCard label="Next run" value={report.released ? "Removes what is due" : "Reports again"} />
          </KpiStrip>
          {report.failure === null ? null : <Note kind="not-yet">{`The last run removed nothing: ${report.failure}`}</Note>}
          <SectionCard title="What the sweep found in each store" action={<SweepActs report={report} controls={controls} onDone={onDone} />}>
            {report.stores.length === 0 ? (
              <Note>{NO_STORES}</Note>
            ) : (
              <EntityTable caption="What the sweep found in each store" columns={stores} rows={report.stores} rowId={(line) => line.store} rowLabel={(line) => line.store} exportName="retention-stores" />
            )}
            {report.findings.length === 0 ? null : (
              <ul aria-label="What the sweep found wrong" className="m-0 mt-3 flex list-disc flex-col gap-1 pl-5 text-[13px] text-warn">
                {report.findings.map((one) => (
                  <li key={one}>{one}</li>
                ))}
              </ul>
            )}
          </SectionCard>
        </>
      )}
      <SectionCard title="How long each kind of thing is kept">
        {controls.kept.length === 0 ? (
          <Note>{NO_WINDOWS}</Note>
        ) : (
          <EntityTable caption="How long each kind of thing is kept" columns={kept} rows={controls.kept} rowId={(one) => one.data_class} rowLabel={(one) => one.data_class} />
        )}
      </SectionCard>
    </div>
  );
}

function HoldsView({ report, controls, onDone }: { readonly report: Report | null; readonly controls: Controls; readonly onDone: (told: string) => void }) {
  const [open, setOpen] = useState<"place" | "lift" | null>(null);
  const lifting = useLift(controls, onDone);
  const holds = report?.holds ?? [];
  const columns: EntityColumn<CitedHold>[] = [
    {
      id: "hold",
      header: "Reference",
      hideable: false,
      cell: (one) => (
        <Link to={holdAddress(one.hold_id)} className="font-mono text-[12px] font-medium text-ink underline-offset-4 hover:underline">
          {one.hold_id}
        </Link>
      ),
      text: (one) => one.hold_id,
    },
    { id: "reason", header: "Reason", cell: (one) => words(one.reason_code), text: (one) => one.reason_code },
    { id: "covers", header: "Covers", cell: (one) => (one.company_wide ? <Pill tone="warn">Everybody</Pill> : "Named people"), text: (one) => (one.company_wide ? "Everybody" : "Named people") },
  ];
  return (
    <SectionCard
      title={VIEW_LABELS.holds}
      lede={NO_HOLDS_MORE}
      action={
        controls.may_hold ? (
          <>
            <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" onClick={() => setOpen("lift")}>
              {LIFT_BY_REFERENCE}
            </Button>
            <Button size="sm" className="min-h-11 sm:min-h-8" onClick={() => setOpen("place")}>
              <Plus aria-hidden /> {PLACE_HOLD}
            </Button>
          </>
        ) : undefined
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        {controls.may_hold ? null : <Note>{HOLD_NOT_YOURS}</Note>}
        {lifting.drawn}
        {holds.length === 0 ? (
          <EmptyState title={NO_HOLDS} description={NO_HOLDS_MORE} icon={<Gavel aria-hidden />} />
        ) : (
          <EntityTable
            caption={VIEW_LABELS.holds}
            columns={columns}
            rows={holds}
            rowId={(one) => one.hold_id}
            rowLabel={(one) => one.hold_id}
            exportName="legal-holds"
            rowActions={(one) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for legal hold ${one.hold_id}`}>
                    <MoreHorizontal aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem asChild>
                    <Link to={holdAddress(one.hold_id)}>Open</Link>
                  </DropdownMenuItem>
                  {controls.may_hold ? <DropdownMenuSeparator /> : null}
                  {controls.may_hold ? (
                    <DropdownMenuItem disabled={lifting.busy} onSelect={() => lifting.lift(one.hold_id)}>
                      {LIFT_LABEL}
                    </DropdownMenuItem>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        )}
      </div>
      {open === "place" ? <HoldDrawer controls={controls} onClose={() => setOpen(null)} onDone={(told) => { setOpen(null); onDone(told); }} /> : null}
      {open === "lift" ? (
        <LiftDrawer
          cited={holds.map((one) => one.hold_id)}
          onClose={() => setOpen(null)}
          onLift={(holdId) => {
            setOpen(null);
            lifting.lift(holdId);
          }}
        />
      ) : null}
    </SectionCard>
  );
}

function ErasuresView({ retention, controls, onDone }: { readonly retention: Retention; readonly controls: Controls; readonly onDone: (told: string) => void }) {
  const [filing, setFiling] = useState(false);
  const requests = retention.queue?.requests ?? [];
  const columns: EntityColumn<ErasureRequest>[] = [
    {
      id: "reference",
      header: "Reference",
      hideable: false,
      cell: (one) => (
        <Link to={erasureAddress(one.request_id)} className="font-mono text-[12px] font-medium text-ink underline-offset-4 hover:underline">
          {one.reason_reference}
        </Link>
      ),
      text: (one) => one.reason_reference,
    },
    { id: "filed", header: "Filed", className: "whitespace-nowrap", cell: (one) => whenWords(one.requested_at), text: (one) => whenWords(one.requested_at) },
    { id: "by", header: "Filed by", cell: (one) => nameOf(retention.filers, one.requested_by), text: (one) => nameOf(retention.filers, one.requested_by) },
    {
      id: "state",
      header: "Where it stands",
      cell: (one) => <ErasurePill outcome={one.outcome} />,
      text: (one) => erasureState(one, whenWords),
    },
  ];
  return (
    <SectionCard
      title={VIEW_LABELS.erasures}
      action={
        controls.may_erase ? (
          <Button size="sm" className="min-h-11 sm:min-h-8" onClick={() => setFiling(true)}>
            <Plus aria-hidden /> {FILE_ERASURE}
          </Button>
        ) : undefined
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        {controls.may_erase ? null : <Note>{ERASE_NOT_YOURS}</Note>}
        {requests.length === 0 ? (
          <EmptyState title={NO_ERASURES} description={NO_ERASURES_MORE} icon={<Trash2 aria-hidden />} />
        ) : (
          <EntityTable caption={VIEW_LABELS.erasures} columns={columns} rows={requests} rowId={(one) => one.request_id} rowLabel={(one) => one.reason_reference} exportName="erasure-requests" />
        )}
      </div>
      {filing ? <ErasureDrawer controls={controls} onClose={() => setFiling(false)} onDone={(told) => { setFiling(false); onDone(told); }} /> : null}
    </SectionCard>
  );
}

function ExportsView({ controls }: { readonly controls: Controls }) {
  const log = useResource<unknown>(controls.may_read_exports ? EXPORT_LOG_API_PATH : null);
  if (!controls.may_read_exports) {
    return (
      <SectionCard title={VIEW_LABELS.exports}>
        <Note>{controls.exports_not_yours}</Note>
      </SectionCard>
    );
  }
  const people = peopleIn(log.data);
  const exports: readonly ExportLogEntry[] =
    typeof log.data === "object" && log.data !== null && Array.isArray((log.data as { exports?: unknown }).exports)
      ? (log.data as { exports: ExportLogEntry[] }).exports
      : [];
  const columns: EntityColumn<ExportLogEntry>[] = [
    { id: "taken", header: "Taken", hideable: false, className: "whitespace-nowrap", cell: (one) => whenWords(one.produced_at), text: (one) => one.produced_at },
    { id: "what", header: "What", cell: (one) => <Chip>{words(one.data_set)}</Chip>, text: (one) => one.data_set },
    { id: "by", header: "By", cell: (one) => nameOf(people, one.requested_by), text: (one) => nameOf(people, one.requested_by) },
    { id: "why", header: "Why", cell: (one) => `${reasonLabel(one.reason)}, ${one.reason_reference}`, text: (one) => `${one.reason}, ${one.reason_reference}` },
    { id: "entries", header: "Entries", cell: (one) => exportEntriesSentence(one), text: (one) => exportEntriesSentence(one) },
    { id: "verdict", header: "Chain", cell: (one) => exportVerdict(one), text: (one) => exportVerdict(one) },
    { id: "digest", header: "Document digest", hidden: true, cell: (one) => <span className="font-mono text-[11px] [overflow-wrap:anywhere]">{one.document_digest}</span>, text: (one) => one.document_digest },
  ];
  let body: ReactNode;
  if (log.failure !== null) {
    body = <FailureState failure={log.failure} />;
  } else if (log.data === null) {
    body = <LoadingState label="Reading the export log." rows={2} />;
  } else if (exports.length === 0) {
    body = <EmptyState title={NO_EXPORTS} description={NO_EXPORTS_MORE} icon={<FileDown aria-hidden />} />;
  } else {
    body = <EntityTable caption="Exports taken from this install" columns={columns} rows={exports} rowId={(one) => one.export_id} rowLabel={(one) => one.reason_reference} exportName="exports" />;
  }
  return <SectionCard title={VIEW_LABELS.exports}>{body}</SectionCard>;
}

export function RetentionPage({ view }: { readonly view: string | undefined }) {
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
  const current: RetentionView = (VIEWS as readonly string[]).includes(view ?? "") ? (view as RetentionView) : "sweep";
  const views: DetailView[] = VIEWS.map((one) => ({ key: one, label: VIEW_LABELS[one], to: viewAddress(one) }));

  let body: ReactNode;
  if (retention.failure !== null) {
    body = <FailureState failure={retention.failure} />;
  } else if (retention.busy || retention.controls === null) {
    body = <LoadingState label={READING_RETENTION} />;
  } else if (current === "sweep") {
    body = <SweepView report={retention.report} controls={retention.controls} onDone={onDone} />;
  } else if (current === "holds") {
    body = <HoldsView report={retention.report} controls={retention.controls} onDone={onDone} />;
  } else if (current === "erasures") {
    body = <ErasuresView retention={retention} controls={retention.controls} onDone={onDone} />;
  } else {
    body = <ExportsView controls={retention.controls} />;
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: RETENTION_HEADING }]} title={RETENTION_HEADING} lede={RETENTION_LEDE} />
      <ViewSwitch label={VIEWS_LABEL} views={views} current={current} />
      <Told told={told} />
      {body}
    </div>
  );
}
