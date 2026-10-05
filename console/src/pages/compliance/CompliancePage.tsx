/**
 * Compliance on the shared page kit: breach cases and the clock each is on, who a sensitive
 * question is routed to, what each connected source reads, and who answers for each escalation
 * queue (`EscalationQueues.tsx`, M8.3.2), as four views at their own addresses under one header,
 * and a page of its own for each breach case (`BreachPage.tsx`).
 *
 * `brain.compliance_routes` answers all three under one authority, `admin:compliance`, so they are
 * one module: the person who names the handler for grievances is the same person who records a
 * breach. The old screen drew all three with every form open under every case; the forms are now
 * drawers behind the act that opens them, and a case's steps are on its own page.
 *
 * **The clock and the findings are the server's, and drawn as served.** A page that recomputed a
 * deadline would be a second opinion on a legal deadline. **The tally is drawn as the API released
 * it**: a suppressed month says it is suppressed and draws no number.
 *
 * Task ids: M24.2.2, M24.2.3, M24.2.4, M27.16.1, M8.3.2
 */

import { FileWarning, MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  Chip,
  EmptyState,
  EntityTable,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
  ViewSwitch,
  type DetailView,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import {
  BREACHES_API_PATH,
  isOpen,
  REGISTER_API_PATH,
  tallySentence,
  TOPICS_API_PATH,
  type Breach,
  type BreachesAnswer,
  type RegisterAnswer,
  type RegisterRow,
  type Topic,
  type TopicsAnswer,
} from "../complianceQuery";
import { nameOf, peopleIn, Pill, whenWords } from "../review/parts";
import { NameDrawer, OpenCaseDrawer, OPEN_FORM_LABEL } from "./ComplianceActs";
import { EscalationQueuesView } from "./EscalationQueues";

export const COMPLIANCE_HEADING = "Compliance";
export const COMPLIANCE_LEDE = "Data breach cases and the clock each is on, who a sensitive question is routed to, and what each connected source reads.";
export const COMPLIANCE_PATH = "/compliance";
export const READING_COMPLIANCE = "Reading the compliance records.";

export const VIEWS = ["breaches", "topics", "register", "escalations"] as const;
export type ComplianceView = (typeof VIEWS)[number];
export const VIEW_LABELS: Readonly<Record<ComplianceView, string>> = Object.freeze({
  breaches: "Breach cases",
  topics: "Sensitive topics",
  register: "Processing register",
  escalations: "Escalation queues",
});

export function viewAddress(view: ComplianceView): string {
  return view === "breaches" ? COMPLIANCE_PATH : `${COMPLIANCE_PATH}/${view}`;
}
export function caseAddress(caseId: string): string {
  return `${COMPLIANCE_PATH}/breaches/${encodeURIComponent(caseId)}`;
}

export const NO_CASES = "No breach case has been opened";
export const NO_CASES_MORE = "A case is opened here when there is reason to believe personal data was breached, and its clock starts then.";
export const NO_TOPICS = "This install declares no sensitive topic, so there is nobody to name.";
export const NOBODY_NAMED = "Nobody is named";
export const NOTHING_CONNECTED = "Nothing is connected";
export const NOTHING_CONNECTED_MORE = "A source appears here once it is connected, with what it reads and keeps.";
export const NAME_A_PERSON = "Name a person";

/** Whether any of a case's obligations is overdue. The server decided each. */
export function overdue(one: Breach): boolean {
  return one.obligations.some((duty) => duty.overdue);
}

export function CaseStatePill({ one }: { readonly one: Breach }) {
  if (!isOpen(one)) {
    return <Pill tone="plain">Closed</Pill>;
  }
  return overdue(one) ? <Pill tone="crit">Overdue</Pill> : <Pill tone="warn">Open</Pill>;
}

function BreachesView({ onDone, version }: { readonly onDone: (told: string) => void; readonly version: number }) {
  const [opening, setOpening] = useState(false);
  const answer = useResource<BreachesAnswer>(BREACHES_API_PATH, version);
  const people = peopleIn(answer.data);
  const columns: EntityColumn<Breach>[] = [
    {
      id: "case",
      header: "Case",
      hideable: false,
      cell: (one) => (
        <Link to={caseAddress(one.case_id)} className="font-mono text-[12px] font-medium text-ink underline-offset-4 hover:underline">
          {one.evidence_reference}
        </Link>
      ),
      text: (one) => one.evidence_reference,
    },
    { id: "state", header: "Where it stands", cell: (one) => <CaseStatePill one={one} />, text: (one) => (isOpen(one) ? (overdue(one) ? "Overdue" : "Open") : "Closed") },
    { id: "clock", header: "Clock started", className: "whitespace-nowrap", cell: (one) => whenWords(one.clock_starts_at), text: (one) => one.clock_starts_at },
    { id: "assessed", header: "Assessment", cell: (one) => (one.assessed_at === null ? <span className="text-warn">Not yet made</span> : whenWords(one.assessed_at)), text: (one) => one.assessed_at ?? "" },
    { id: "commission", header: "Commission notified", cell: (one) => (one.commission_notified_at === null ? "Not recorded" : whenWords(one.commission_notified_at)), text: (one) => one.commission_notified_at ?? "" },
    { id: "recorded_by", header: "Recorded by", hidden: true, cell: (one) => nameOf(people, one.recorded_by), text: (one) => nameOf(people, one.recorded_by) },
  ];
  let body: ReactNode;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label={READING_COMPLIANCE} rows={2} />;
  } else if (answer.data.cases.length === 0) {
    body = <EmptyState title={NO_CASES} description={NO_CASES_MORE} icon={<FileWarning aria-hidden />} />;
  } else {
    body = <EntityTable caption={VIEW_LABELS.breaches} columns={columns} rows={answer.data.cases} rowId={(one) => one.case_id} rowLabel={(one) => one.evidence_reference} exportName="breach-cases" />;
  }
  return (
    <SectionCard
      title={VIEW_LABELS.breaches}
      action={
        <Button size="sm" className="min-h-11 sm:min-h-8" onClick={() => setOpening(true)}>
          <Plus aria-hidden /> {OPEN_FORM_LABEL}
        </Button>
      }
    >
      {body}
      {opening ? (
        <OpenCaseDrawer
          onClose={() => setOpening(false)}
          onDone={(told) => {
            setOpening(false);
            onDone(told);
          }}
        />
      ) : null}
    </SectionCard>
  );
}

function TopicsView({ onDone, version }: { readonly onDone: (told: string) => void; readonly version: number }) {
  const [naming, setNaming] = useState<Topic | null>(null);
  const answer = useResource<TopicsAnswer>(TOPICS_API_PATH, version);
  const people = peopleIn(answer.data);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    return <LoadingState label={READING_COMPLIANCE} rows={2} />;
  }
  const topics = answer.data;
  const label = (topic: string) => topics.topics.find((one) => one.topic === topic)?.label ?? topic;
  const columns: EntityColumn<Topic>[] = [
    { id: "topic", header: "Topic", hideable: false, cell: (one) => <span className="font-medium text-ink">{one.label}</span>, text: (one) => one.label },
    { id: "routed", header: "Routed to", cell: (one) => (one.named === null ? <span className="text-warn">{NOBODY_NAMED}</span> : nameOf(people, one.named.principal_id)), text: (one) => (one.named === null ? NOBODY_NAMED : nameOf(people, one.named.principal_id)) },
    { id: "named_by", header: "Named by", cell: (one) => (one.named === null ? null : `${nameOf(people, one.named.named_by)}, ${whenWords(one.named.named_at)}`), text: (one) => (one.named === null ? "" : nameOf(people, one.named.named_by)) },
  ];
  return (
    <SectionCard title={VIEW_LABELS.topics} lede={topics.routing}>
      <div className="flex min-w-0 flex-col gap-3">
        {topics.topics.length === 0 ? (
          <Note>{NO_TOPICS}</Note>
        ) : (
          <EntityTable
            caption="Who each sensitive topic is routed to"
            columns={columns}
            rows={topics.topics}
            rowId={(one) => one.topic}
            rowLabel={(one) => one.label}
            rowActions={(one) => (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${one.label}`}>
                    <MoreHorizontal aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem onSelect={() => setNaming(one)}>{NAME_A_PERSON}</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          />
        )}
        <Note>{tallySentence(topics.tally, label)}</Note>
        <FactList>
          <Fact label="The asker is told">{topics.referral}</Fact>
        </FactList>
      </div>
      {naming === null ? null : (
        <NameDrawer
          topic={naming}
          people={people}
          onClose={() => setNaming(null)}
          onDone={(told) => {
            setNaming(null);
            onDone(told);
          }}
        />
      )}
    </SectionCard>
  );
}

function Source({ row, people }: { readonly row: RegisterRow; readonly people: Readonly<Record<string, string>> }) {
  const entities: EntityColumn<RegisterRow["entities"][number]>[] = [
    { id: "entity", header: "What", hideable: false, cell: (one) => <span className="font-mono text-[12px]">{one.entity}</span>, text: (one) => one.entity },
    { id: "tier", header: "Kept as", cell: (one) => one.tier.replace(/_/g, " "), text: (one) => one.tier },
    { id: "fields", header: "Fields", cell: (one) => one.fields.join(", "), text: (one) => one.fields.join(", ") },
    { id: "classes", header: "Classes", cell: (one) => one.classes.join(", "), text: (one) => one.classes.join(", ") },
  ];
  return (
    <SectionCard title={row.label} headingLevel="h3" action={row.write_capable ? <Pill tone="warn">Can write</Pill> : <Pill tone="plain">Reads only</Pill>}>
      <div className="flex min-w-0 flex-col gap-3">
        <FactList>
          <Fact label="Connected">{`${whenWords(row.connected_at)}, by ${nameOf(people, row.connected_by)}`}</Fact>
          <Fact label="Categories of data">{row.categories.length === 0 ? "None declared." : row.categories.map((one) => <Chip key={one}>{one}</Chip>)}</Fact>
          <Fact label="Last read">{row.last_read_at === null ? "Never." : whenWords(row.last_read_at)}</Fact>
          <Fact label="Records read">{row.records_read === null ? "Not read yet." : String(row.records_read)}</Fact>
          <Fact label="Documents read">{row.documents_read === null ? "Not read yet." : String(row.documents_read)}</Fact>
          {row.problem === "" ? null : <Fact label="Problem">{row.problem}</Fact>}
        </FactList>
        {row.entities.length === 0 ? null : (
          <EntityTable caption={`What ${row.label} reads, by entity`} columns={entities} rows={row.entities} rowId={(one) => one.entity} rowLabel={(one) => one.entity} />
        )}
      </div>
    </SectionCard>
  );
}

function RegisterView({ version }: { readonly version: number }) {
  const answer = useResource<RegisterAnswer>(REGISTER_API_PATH, version);
  const people = peopleIn(answer.data);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    return <LoadingState label={READING_COMPLIANCE} rows={2} />;
  }
  if (answer.data.connectors.length === 0) {
    return <EmptyState title={NOTHING_CONNECTED} description={NOTHING_CONNECTED_MORE} />;
  }
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Note>{answer.data.counts}</Note>
      {answer.data.connectors.map((row) => (
        <Source key={row.connector} row={row} people={people} />
      ))}
    </div>
  );
}

export function CompliancePage({ view }: { readonly view: string | undefined }) {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const onDone = useCallback((sentence: string) => {
    setTold(sentence);
    setVersion((count) => count + 1);
  }, []);
  const current: ComplianceView = (VIEWS as readonly string[]).includes(view ?? "") ? (view as ComplianceView) : "breaches";
  const views: DetailView[] = VIEWS.map((one) => ({ key: one, label: VIEW_LABELS[one], to: viewAddress(one) }));
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: COMPLIANCE_HEADING }]} title={COMPLIANCE_HEADING} lede={COMPLIANCE_LEDE} />
      <ViewSwitch label="Compliance views" views={views} current={current} />
      {told === null ? null : (
        <div role="status">
          <Note kind="works">{told}</Note>
        </div>
      )}
      {current === "breaches" ? <BreachesView onDone={onDone} version={version} /> : null}
      {current === "topics" ? <TopicsView onDone={onDone} version={version} /> : null}
      {current === "register" ? <RegisterView version={version} /> : null}
      {current === "escalations" ? <EscalationQueuesView onDone={onDone} version={version} /> : null}
    </div>
  );
}
