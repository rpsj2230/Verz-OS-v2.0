/**
 * One person's memory on the shared page kit: their name, what is remembered and when it last
 * changed in the header, and two views at addresses of their own, Remembered (every statement in its
 * own words, each opened in a drawer with its own history) and History (every change, with its diff).
 *
 * **What is drawn is what the API admitted, and nothing is added.** A statement this reader may not
 * recall is absent, and a person with such statements and a person with none are the same page,
 * because the API made them the same answer. A diff is drawn only where the API sent one, which is
 * where this reader may read both sides. The figures count the statements drawn.
 *
 * **Named, never shown as a reference.** The person is named by their own page in the People
 * directory, as this reader may see it, one request for one person rather than a page of everybody;
 * the reference, and each memory's, is in Advanced.
 *
 * **Nothing here edits a memory, and the page says so once.** An edit is written by the person it is
 * about on their own memory tab (`learningActions.EDIT_NOT_OFFERED`); what an administrator may do
 * is undo a learning on the Learning page, and the change arrives in this history.
 *
 * Removed from the old screen: the reference as the card's heading, memory ids in every row and in
 * the history table, the "Learning tiers active" row that is an agent's setting, the paragraph on how
 * to read a diff, and the reference box drawn above every person's memory.
 *
 * Task ids: M27.7.22, M27.16.1
 */

import { Brain, History as HistoryIcon, ScrollText } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  DetailHeader,
  DetailPage,
  Drawer,
  EmptyState,
  EntityTable,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  NotOffered,
  RESET_LABEL,
  SectionCard,
  StatCard,
  ViewSwitch,
  type DetailView,
  type EntityColumn,
} from "../../components/kit";
import { NOTHING_MATCHES } from "../../components/ListControls";
import { Button } from "../../components/ui/button";
import { cn } from "../../lib/utils";
import { dayWords, whenWords } from "../access/formParts";
import { personApiPath, readPersonDetail } from "../people/peopleQuery";
import { EDIT_NOT_OFFERED, changeWords } from "../learning/learningActions";
import {
  KIND_WORDS,
  MEMORY_PATH,
  MEMORY_VIEWS,
  MEMORY_VIEW_LABELS,
  kilobytes,
  latestRevision,
  memoryApiPath,
  memoryViewAddress,
  readMemoryPage,
  rememberedOf,
  stepWords,
  stepsOf,
  type MemoryKind,
  type MemoryPage as Memory,
  type MemoryView,
  type Remembered,
  type Revision,
} from "../memoryQuery";
import { Narrowing } from "../requirement-checks/Narrowing";
import { MEMORY_HEADING } from "./MemoryPage";

export const LOADING_MEMORY = "Loading what is remembered about this person.";
export const VIEWS_LABEL = "Memory views";
export const UNNAMED = "A person";
export const NOTHING_TO_READ = "Nothing to read";
export const NOTHING_TO_READ_DESCRIPTION = "There is nothing remembered about this person that you can read.";
export const NO_CHANGE = "No change to read";
export const NO_CHANGE_DESCRIPTION = "A change appears here when a memory about this person forms, is replaced or is undone.";
export const CHOOSE_ANOTHER = "Choose somebody else";

const VIEW_ICONS: Readonly<Record<MemoryView, ReactNode>> = {
  remembered: <ScrollText aria-hidden />,
  history: <HistoryIcon aria-hidden />,
};

/** The bound on the load, in words, identical for every person. */
export function consideredSentence(perKind: number): string {
  return `This page reads at most the ${String(perKind)} most recent stated and ${String(perKind)} most recent extracted memories about a person.`;
}

function Diff({ lines }: { readonly lines: readonly string[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
      {lines.map((line, index) => (
        <li key={`${String(index)} ${line}`}>
          <code
            className={cn(
              "font-mono text-[12px] [overflow-wrap:anywhere]",
              line.startsWith("+") ? "text-ok" : line.startsWith("-") ? "text-crit" : "text-dim",
            )}
          >
            {line}
          </code>
        </li>
      ))}
    </ul>
  );
}

function changeCell(step: Revision): ReactNode {
  if (step.diff.length > 0) {
    return <Diff lines={step.diff} />;
  }
  return <span className="text-dim">{step.replaced_id === null ? "" : "No change you may read"}</span>;
}

function RememberedView({ memory, onOpen }: { readonly memory: Memory; readonly onOpen: (row: Remembered) => void }) {
  const [typed, setTyped] = useState("");
  const [kind, setKind] = useState("");
  const all = useMemo(() => rememberedOf(memory), [memory]);
  const words = typed.toLocaleLowerCase("en-GB").split(/\s+/u).filter((one) => one !== "");
  const rows = all.filter(
    (row) => (kind === "" || row.kind === kind) && words.every((one) => row.statement.toLocaleLowerCase("en-GB").includes(one)),
  );
  const reset = () => {
    setTyped("");
    setKind("");
  };
  const columns: readonly EntityColumn<Remembered>[] = [
    {
      id: "statement",
      header: "Statement",
      hideable: false,
      className: "min-w-[16rem] whitespace-normal [overflow-wrap:anywhere]",
      cell: (row) => (
        <button
          type="button"
          className="text-left text-ink underline-offset-4 [overflow-wrap:anywhere] hover:underline"
          onClick={() => {
            onOpen(row);
          }}
        >
          {row.statement}
        </button>
      ),
      text: (row) => row.statement,
    },
    { id: "kind", header: "Kind", cell: (row) => KIND_WORDS[row.kind], text: (row) => KIND_WORDS[row.kind] },
    { id: "formed", header: "Formed", cell: (row) => dayWords(row.formed_at), text: (row) => row.formed_at },
    {
      id: "confidence",
      header: "Confidence",
      align: "end",
      cell: (row) => `${String(Math.round(row.confidence * 100))}%`,
      text: (row) => row.confidence.toFixed(2),
    },
  ];
  return (
    <SectionCard
      title="What is remembered"
      lede="In its own words, newest first."
      footer={
        <NotOffered>
          {EDIT_NOT_OFFERED}{" "}
          <Link to="/learning" className="text-acc-text underline-offset-4 hover:underline">
            Open Learning
          </Link>
        </NotOffered>
      }
    >
      {all.length === 0 ? (
        <EmptyState title={NOTHING_TO_READ} description={NOTHING_TO_READ_DESCRIPTION} icon={<Brain aria-hidden />} />
      ) : (
        <div className="flex min-w-0 flex-col gap-3">
          <Narrowing
            label="Narrow what is remembered"
            search={typed}
            onSearch={setTyped}
            searchLabel="Search the statements"
            searchHint="Words in a statement"
            narrows={[
              {
                label: "Kind",
                everything: "Every kind",
                value: kind,
                options: (["stated", "extracted"] as const).map((one: MemoryKind) => ({ value: one, label: KIND_WORDS[one] })),
                onChange: setKind,
              },
            ]}
            onReset={reset}
          />
          {rows.length === 0 ? (
            <EmptyState
              title={NOTHING_MATCHES}
              description="Change the search or choose every kind."
              action={
                <Button variant="outline" onClick={reset}>
                  {RESET_LABEL}
                </Button>
              }
            />
          ) : (
            <EntityTable
              caption="Statements you may read"
              columns={columns}
              rows={rows}
              rowId={(row) => `${row.kind} ${row.memory_id}`}
              rowLabel={(row) => row.statement}
              exportName="memory"
            />
          )}
        </div>
      )}
    </SectionCard>
  );
}

function HistoryView({ memory }: { readonly memory: Memory }) {
  const steps = useMemo(() => [...memory.history].reverse(), [memory.history]);
  const columns: readonly EntityColumn<Revision>[] = [
    { id: "when", header: "When", hideable: false, cell: (row) => whenWords(row.at), text: (row) => row.at },
    { id: "what", header: "What happened", cell: (row) => stepWords(row), text: (row) => stepWords(row) },
    { id: "change", header: "Change", className: "min-w-[16rem] whitespace-normal [overflow-wrap:anywhere]", cell: (row) => changeCell(row), text: (row) => row.diff.join(" ") },
    {
      id: "why",
      header: "Prompted by",
      cell: (row) => (row.trigger === null ? "" : changeWords(row.trigger)),
      text: (row) => row.trigger ?? "",
    },
  ];
  return (
    <SectionCard
      title="Change history"
      lede="Newest first. A minus line is what it said before, a plus line what it says now."
      footer={<Note>{consideredSentence(memory.consideredPerKind)}</Note>}
    >
      {steps.length === 0 ? (
        <EmptyState title={NO_CHANGE} description={NO_CHANGE_DESCRIPTION} icon={<HistoryIcon aria-hidden />} />
      ) : (
        <EntityTable
          caption="Changes you may read, newest first"
          columns={columns}
          rows={steps}
          rowId={(row) => `${row.memory_id} ${row.at} ${row.replaced_id ?? ""}`}
          rowLabel={(row) => `${stepWords(row)} ${whenWords(row.at)}`}
          exportName="memory-history"
        />
      )}
    </SectionCard>
  );
}

function StatementDrawer({ row, memory, onClose }: { readonly row: Remembered; readonly memory: Memory; readonly onClose: () => void }) {
  const steps = stepsOf(memory.history, row.memory_id);
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      title="A remembered statement"
      description="One memory in its own words, and each change to it you may read."
    >
      <div className="flex min-w-0 flex-col gap-4">
        <FactList>
          <Fact label="Statement">{row.statement}</Fact>
          <Fact label="Kind">{KIND_WORDS[row.kind]}</Fact>
          <Fact label="Formed">{whenWords(row.formed_at)}</Fact>
          <Fact label="Confidence">{`${String(Math.round(row.confidence * 100))}%`}</Fact>
        </FactList>
        <section aria-label="Its history" className="flex min-w-0 flex-col gap-2">
          <h3 className="m-0 text-[13px] font-semibold text-ink">Its history</h3>
          {steps.length === 0 ? (
            <p className="m-0 text-[12.5px] text-dim">No change to it that you may read.</p>
          ) : (
            <ul className="m-0 flex list-none flex-col divide-y divide-line rounded-md border border-line p-0">
              {steps.map((step) => (
                <li key={`${step.memory_id} ${step.at}`} className="flex min-w-0 flex-col gap-1 px-3 py-2 text-[13px]">
                  <span className="text-ink">
                    {stepWords(step)}, {whenWords(step.at)}
                  </span>
                  {step.diff.length > 0 ? <Diff lines={step.diff} /> : null}
                </li>
              ))}
            </ul>
          )}
        </section>
        <Advanced>
          <FactList>
            <Fact label="Memory reference">
              <code className="font-mono text-[12px]">{row.memory_id}</code>
            </Fact>
          </FactList>
        </Advanced>
      </div>
    </Drawer>
  );
}

function MemoryAnswer({ subject, view }: { readonly subject: string; readonly view: MemoryView }) {
  const answer = useResource<unknown>(memoryApiPath(subject));
  // The one person's own page names them, as the People directory shows them to this reader; a
  // person this reader may not see is named by nothing more than the word for a person.
  const person = useResource<unknown>(personApiPath(subject));
  const [opened, setOpened] = useState<Remembered | null>(null);
  const name = readPersonDetail(person.data)?.person.displayName ?? UNNAMED;
  const crumbs = [{ label: MEMORY_HEADING, to: MEMORY_PATH }, { label: name }];

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    return <LoadingState label={LOADING_MEMORY} />;
  }
  const memory = readMemoryPage(answer.data, subject);
  const last = latestRevision(memory.history);
  const views: DetailView[] = MEMORY_VIEWS.map((one) => ({
    key: one,
    label: MEMORY_VIEW_LABELS[one],
    to: memoryViewAddress(subject, one),
    icon: VIEW_ICONS[one],
  }));

  return (
    <DetailPage
      crumbs={crumbs}
      header={
        <DetailHeader
          name={name}
          headingId="memory-heading"
          actions={
            <Button asChild size="sm" variant="outline" className="min-h-11 sm:min-h-8">
              <Link to={MEMORY_PATH}>{CHOOSE_ANOTHER}</Link>
            </Button>
          }
          figures={
            <KpiStrip label="What is remembered that you may read" count={3}>
              <StatCard label={KIND_WORDS.stated} value={String(memory.curated.length)} sub={`${kilobytes(memory.curated)} KB`} />
              <StatCard label={KIND_WORDS.extracted} value={String(memory.extracted.length)} sub={`${kilobytes(memory.extracted)} KB`} />
              <StatCard label="Last change" value={last === null ? "None" : dayWords(last.at)} />
            </KpiStrip>
          }
          footnote={memory.staleness === null ? undefined : <Note>{memory.staleness}</Note>}
        />
      }
      switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
    >
      <div className="flex min-w-0 flex-col gap-4">
        {view === "remembered" ? <RememberedView memory={memory} onOpen={setOpened} /> : <HistoryView memory={memory} />}
        <Advanced>
          <FactList>
            <Fact label="Person reference">
              <code className="font-mono text-[12px]">{memory.subject}</code>
            </Fact>
          </FactList>
        </Advanced>
      </div>
      {opened === null ? null : (
        <StatementDrawer
          row={opened}
          memory={memory}
          onClose={() => {
            setOpened(null);
          }}
        />
      )}
    </DetailPage>
  );
}

export function MemoryDetailPage({ subject, view }: { readonly subject: string; readonly view: MemoryView }) {
  return (
    <div data-slot="memory-detail-page" className="min-w-0">
      <MemoryAnswer key={subject} subject={subject} view={view} />
    </div>
  );
}
