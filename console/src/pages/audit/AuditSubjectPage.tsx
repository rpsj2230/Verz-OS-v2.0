/**
 * One subject's page in the Audit log: everything recorded about it, and for a person or an agent,
 * every change to what it may do.
 *
 * **Two views, each an address.** `/audit/subject/{kind}/{id}` lists every entry about the subject
 * the reader may read (`GET /audit` narrowed to it with `subject_id`); `/permissions` is the
 * permission history `brain.console.auditor.permission_history` answers, which is the question an
 * auditor brings about a person: who gave them that, and who took it away. The second view is offered
 * only for the kinds whose reach a grant, a revocation or a leash changes.
 *
 * **Named, not numbered.** A person is titled with the name the API sent; any other subject with its
 * kind, and a legal hold with the reference it was placed under. The kind and the identifier are in
 * Advanced, for quoting in a support request.
 *
 * **Nothing here says whether the subject exists.** A subject nothing records and one whose entries
 * the reader may not read are one answer, an empty list with the same sentence, because the ledger
 * view decides entry by entry and this page draws what it sent.
 *
 * Task ids: M27.7.13, M27.16.1
 */

import { History, ListTree } from "lucide-react";
import type { ReactNode } from "react";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  DetailHeader,
  DetailPage,
  EmptyState,
  EntityTable,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  SectionCard,
  StatCard,
  ViewSwitch,
  type DetailView,
  type EntityColumn,
} from "../../components/kit";
import {
  AUDIT_PATH,
  DEFAULT_FILTERS,
  historyApiPath,
  readHistory,
  subjectAddress,
  when,
  type AuditFilters,
  type PermissionEvent,
} from "../auditQuery";
import { AUDIT_HEADING, READING_THE_LEDGER } from "./AuditPage";
import { actorWords, detailLines, kindWords, subjectWords, whatWords } from "./auditWords";
import { LedgerTable } from "./LedgerTable";
import { useLedger } from "./useLedger";

export const ENTRIES_VIEW = "Everything recorded";
export const PERMISSIONS_VIEW = "Access changes";
export const VIEWS_LABEL = "Views of this subject";
export const SUBJECT_ENTRIES_LABEL = "Entries about this subject";
export const HISTORY_LABEL = "Access changes";
export const LAST_RECORDED = "Last recorded";
export const LAST_BY = "By";
export const READING_HISTORY = "Reading the access changes.";
export const NOTHING_RECORDED = "Nothing recorded";
export const NOTHING_RECORDED_MORE = "Entries appear here when something about this changes.";
export const NO_PERMISSION_CHANGES = "No access changes";
export const NO_PERMISSION_CHANGES_MORE = "A grant, a removal, a leash change or emergency access appears here when one is made.";
export const HISTORY_FILLED_A_PAGE =
  "This history filled a whole page, so earlier changes are not shown. Read them under Everything recorded.";

/** The kinds whose reach a grant, a revocation, a leash change or break glass moves. */
const PERMISSION_KINDS = new Set(["principal", "agent", "leash"]);

/** Every entry about the subject, from the first. The period is all time: a subject's page is its record. */
const ALL_OF_IT: AuditFilters = Object.freeze({ ...DEFAULT_FILTERS, period: "all" });

function Permissions({ kind, id }: { readonly kind: string; readonly id: string }) {
  const answer = useResource<unknown>(historyApiPath(kind, id));
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy) {
    return <LoadingState label={READING_HISTORY} />;
  }
  const history = readHistory(answer.data);
  if (history.events.length === 0) {
    return <EmptyState title={NO_PERMISSION_CHANGES} description={NO_PERMISSION_CHANGES_MORE} />;
  }
  const placed = history.events.map((event, at) => ({ event, at }));
  const columns: EntityColumn<{ event: PermissionEvent; at: number }>[] = [
    {
      id: "when",
      header: "When",
      hideable: false,
      className: "whitespace-nowrap",
      cell: ({ event }) => <time dateTime={event.at}>{when(event.at)}</time>,
      text: ({ event }) => event.at,
    },
    {
      id: "who",
      header: "Who",
      cell: ({ event }) => actorWords(event.actor_id, history.people, event.details),
      text: ({ event }) => actorWords(event.actor_id, history.people, event.details),
    },
    {
      id: "what",
      header: "What",
      cell: ({ event }) => <span className="font-medium text-ink">{whatWords(event.action, event.details)}</span>,
      text: ({ event }) => whatWords(event.action, event.details),
    },
    {
      id: "details",
      header: "Details",
      cell: ({ event }) => detailLines(event.details).join("; "),
      text: ({ event }) => detailLines(event.details).join("; "),
    },
  ];
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <EntityTable
        caption={HISTORY_LABEL}
        columns={columns}
        rows={placed}
        rowId={(one) => String(one.at)}
        rowLabel={(one) => `${whatWords(one.event.action, one.event.details)}, ${when(one.event.at)}`}
        exportName="access-changes"
      />
      {history.full ? <Note>{HISTORY_FILLED_A_PAGE}</Note> : null}
    </div>
  );
}

export function AuditSubjectPage({
  kind,
  id,
  view,
}: {
  readonly kind: string;
  readonly id: string;
  readonly view: string | undefined;
}) {
  const subject = { kind, id };
  const ledger = useLedger(ALL_OF_IT, subject);
  const offersPermissions = PERMISSION_KINDS.has(kind);
  const current = offersPermissions && view === "permissions" ? "permissions" : "entries";
  const name = subjectWords(kind, id, ledger.people);
  const newest = ledger.rows[0];

  const views: DetailView[] = [
    { key: "entries", label: ENTRIES_VIEW, to: subjectAddress(kind, id), icon: <ListTree aria-hidden /> },
    { key: "permissions", label: PERMISSIONS_VIEW, to: subjectAddress(kind, id, "permissions"), icon: <History aria-hidden /> },
  ];

  let entries: ReactNode;
  if (ledger.failure !== null) {
    entries = <FailureState failure={ledger.failure} />;
  } else if (ledger.busy) {
    entries = <LoadingState label={READING_THE_LEDGER} />;
  } else if (ledger.rows.length === 0) {
    entries = <EmptyState title={NOTHING_RECORDED} description={NOTHING_RECORDED_MORE} />;
  } else {
    entries = (
      <LedgerTable
        ledger={ledger}
        caption={SUBJECT_ENTRIES_LABEL}
        exportName={`audit-${kind}`}
        showAbout={false}
        moreLabel="Show older entries"
      />
    );
  }

  const headingId = `audit-subject-${kind}`;
  return (
    <DetailPage
      crumbs={[{ label: AUDIT_HEADING, to: AUDIT_PATH }, { label: name }]}
      header={
        <DetailHeader
          name={name}
          headingId={headingId}
          pills={<Chip>{kindWords(kind)}</Chip>}
          figures={
            ledger.busy || ledger.failure !== null ? undefined : (
              <KpiStrip label="What was last recorded about it" count={2}>
                <StatCard label={LAST_RECORDED} value={newest === undefined ? undefined : when(newest.at)} />
                <StatCard
                  label={LAST_BY}
                  value={newest === undefined ? undefined : actorWords(newest.actor_id, ledger.people, newest.details)}
                  sub={newest === undefined ? undefined : whatWords(newest.action, newest.details)}
                />
              </KpiStrip>
            )
          }
        />
      }
      switcher={offersPermissions ? <ViewSwitch label={VIEWS_LABEL} views={views} current={current} /> : undefined}
    >
      <div className="flex min-w-0 flex-col gap-4">
        <SectionCard title={current === "permissions" ? HISTORY_LABEL : ENTRIES_VIEW}>
          {current === "permissions" ? <Permissions kind={kind} id={id} /> : entries}
        </SectionCard>
        <Advanced>
          <FactList>
            <Fact label="Kind">
              <code>{kind}</code>
            </Fact>
            <Fact label="Identifier">
              <code>{id}</code>
            </Fact>
          </FactList>
        </Advanced>
      </div>
    </DetailPage>
  );
}
