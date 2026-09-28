/**
 * The Knowledge list, built on the shared page kit: every document the reader may open, with its
 * department, who it reaches, its steward, its verification, its review date and its state.
 *
 * **This is SCREEN 7's library, answered in full.** The old page drew three of the design's eight
 * columns and a paragraph for each missing one, because it read the existence-plane library, which
 * refuses titles. This reads `GET /knowledge/documents`, the detail route's own rule over many rows,
 * so every row is a document the reader may open and every column is a field that row carries. Used
 * 30d is not drawn: nothing records retrievals, and a column of blanks would read as a library nobody
 * uses. The design's filters are the route's: department, who it reaches, state and Review due.
 *
 * **Adding is one menu with three ways in**, each a drawer over the list: a file, a web page by its
 * link, or many files for the background worker. The menu is drawn only when the API offered this
 * reader somewhere to add; to anybody else there is nothing to press and nothing is said.
 *
 * **The bulk act is Verify, and it is several single verifications.** The route verifies each row
 * the reader ticked as its own act and reports each outcome, which is said under the list. Export
 * and Archive are drawn and inert with their reasons (`knowledgeActions.ts`): neither has a route,
 * and an unrecorded export of titles is the channel the Exports screen watches.
 *
 * **What was removed from the old page, and why.** The long lede about bounded knowledge; the "At a
 * glance" figures, two of which were "Not measured on this install" paragraphs; the coverage card and
 * the "What the company view adds" table, which described the screen rather than the documents; the
 * item's internal reference as the row's name; the sentences explaining absent columns and absent
 * controls; and the lifecycle, intake and solutions cards stacked above the list, which are now a
 * document's own page, the Add menu and the Solutions tab.
 *
 * Task ids: M27.15.40, M27.16.1, M7.6.3, M7.1.2, M7.1.5
 */

import { BookOpen, ChevronDown, Download, MoreHorizontal, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  ConfirmDialog,
  Drawer,
  ListPage,
  Note,
  SectionCard,
  UnavailableAction,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { Input } from "../../components/ui/input";
import { useListing, type Listing } from "../../components/useListing";
import { FailureNotice } from "../../ui/FailureNotice";
import { defaultReviewDay, instantOf, TASKS_API_PATH } from "../knowledgeLifecycleQuery";
import { readUploadOptions, UPLOAD_OPTIONS_API_PATH, type UploadOptions } from "../knowledgeQuery";
import { AddFileForm, AddLinkForm, AddManyForm, levelsOf } from "./addForms";
import { REVIEW_HINT, REVIEW_LABEL, reviewProblem } from "./formParts";
import { UNAVAILABLE } from "./knowledgeActions";
import {
  dayWords,
  DOCUMENT_FILTERS,
  KNOWLEDGE_HEADING,
  DOCUMENT_SORTS,
  DOCUMENTS_API_PATH,
  documentAddress,
  levelWords,
  readDocRows,
  readTasks,
  SOLUTIONS_ADDRESS,
  stateWords,
  verifiedWords,
  VERIFICATIONS_API_PATH,
  type DocRow,
} from "./knowledgeDocuments";
import { DuePill, StatePill, TaskList } from "./parts";

export { KNOWLEDGE_HEADING };

export const KNOWLEDGE_LEDE = "Every document you can open, who looks after it, and when it is next reviewed.";
export const LOADING_DOCUMENTS = "Loading documents.";
export const NO_DOCUMENTS = "No documents to show";
export const NO_DOCUMENTS_DESCRIPTION =
  "A document appears here once somebody adds one to a department you can read, or to you alone.";
export const LIST_LABEL = "Documents you can open";
export const FILTERS_LABEL = "Narrow the documents";
export const SEARCH_HINT = "Search titles and stewards";
export const ADD_LABEL = "Add documents";
export const SOLUTIONS_LINK = "Solutions";
export const EXPORT_LABEL = "Export inventory";
export const TASKS_HEADING = "Your tasks";
export const MORE_DOCUMENTS = "More documents are on file than one reading covers; search or filter to reach the rest.";

export const DOCUMENT_COLUMN = "Document";
export const DEPARTMENT_COLUMN = "Department";
export const LEVEL_COLUMN = "Visible to";
export const STEWARD_COLUMN = "Steward";
export const VERIFIED_COLUMN = "Verified";
export const REVIEW_COLUMN = "Review due";
export const STATE_COLUMN = "State";

/** The three ways a document is added, each a drawer. */
export const ADD_WAYS = Object.freeze({
  file: { label: "Upload a file", description: "A plain text, Markdown, PDF or Word document, read now and answered from straight away." },
  link: { label: "Add a web page", description: "The page is fetched once, now, and kept as your company's own document. Nothing re-reads the site." },
  many: { label: "Add many files", description: "Each file is checked here and read by the background worker one at a time." },
});
type AddWay = keyof typeof ADD_WAYS;

export const BULK_VERIFY = "Verify";
export const BULK_VERIFY_CONSEQUENCE =
  "You vouch that each is right today, and its steward is asked again on the review date. A document you may not verify is left as it is and said below.";

function AddMenu({ onChoose }: { readonly onChoose: (way: AddWay) => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button className="min-h-11 sm:min-h-9">
          <Plus aria-hidden /> {ADD_LABEL} <ChevronDown aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        {(Object.keys(ADD_WAYS) as AddWay[]).map((way) => (
          <DropdownMenuItem
            key={way}
            onSelect={() => {
              onChoose(way);
            }}
          >
            {ADD_WAYS[way].label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function AddDrawer({
  way,
  options,
  onClose,
  onAdded,
}: {
  readonly way: AddWay | null;
  readonly options: UploadOptions;
  readonly onClose: () => void;
  readonly onAdded: () => void;
}) {
  const shown = way ?? "file";
  return (
    <Drawer
      open={way !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      title={ADD_WAYS[shown].label}
      description={ADD_WAYS[shown].description}
    >
      {shown === "file" ? <AddFileForm options={options} onAdded={onAdded} /> : null}
      {shown === "link" ? <AddLinkForm options={options} onAdded={onAdded} /> : null}
      {shown === "many" ? <AddManyForm options={options} onAdded={onAdded} /> : null}
    </Drawer>
  );
}

/** One document's outcome of a bulk verification, as the route reports it. */
export interface Outcome {
  readonly itemId: string;
  readonly verified: boolean;
  readonly says: string;
}

export function readOutcomes(payload: unknown): readonly Outcome[] {
  const outcomes = typeof payload === "object" && payload !== null ? (payload as { outcomes?: unknown }).outcomes : undefined;
  return (Array.isArray(outcomes) ? (outcomes as readonly unknown[]) : []).flatMap((one) => {
    const row = typeof one === "object" && one !== null ? (one as Record<string, unknown>) : {};
    return typeof row["item_id"] === "string" && typeof row["says"] === "string"
      ? [{ itemId: row["item_id"], verified: row["verified"] === true, says: row["says"] }]
      : [];
  });
}

/** What a bulk verification says afterwards: how many of the reader's own ticks, and each refusal. */
export function outcomeWords(outcomes: readonly Outcome[], titles: ReadonlyMap<string, string>): readonly string[] {
  const done = outcomes.filter((one) => one.verified).length;
  return [
    `Verified ${String(done)} of the ${String(outcomes.length)} you chose.`,
    ...outcomes.filter((one) => !one.verified).map((one) => `${titles.get(one.itemId) ?? "A document"}: ${one.says}.`),
  ];
}

function BulkVerify({ rows, onDone }: { readonly rows: readonly DocRow[]; readonly onDone: (said: readonly string[]) => void }) {
  const [open, setOpen] = useState(false);
  const [day, setDay] = useState(defaultReviewDay());
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const send = () => {
    const found = reviewProblem(day);
    setProblem(found);
    const instant = instantOf(day);
    if (found !== null || instant === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(VERIFICATIONS_API_PATH, {
        method: "POST",
        body: { item_ids: rows.map((one) => one.itemId), review_by: instant },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setOpen(false);
      onDone(outcomeWords(readOutcomes(result.data), new Map(rows.map((one) => [one.itemId, one.title]))));
    })();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className="min-h-11 sm:min-h-8"
        onClick={() => {
          setOpen(true);
        }}
      >
        {BULK_VERIFY}
      </Button>
      <ConfirmDialog
        open={open}
        question={`Verify ${rows.length === 1 ? (rows[0]?.title ?? "this document") : `these ${String(rows.length)} documents`}?`}
        consequence={BULK_VERIFY_CONSEQUENCE}
        details={
          <div className="flex flex-col gap-1.5">
            {failure === null ? null : <FailureNotice failure={failure} />}
            <label htmlFor="bulk-review-by" className="text-[13px] font-medium text-ink">
              {REVIEW_LABEL}
            </label>
            <Input
              id="bulk-review-by"
              type="date"
              className="h-11 sm:h-9"
              value={day}
              onChange={(event) => {
                setDay(event.target.value);
              }}
            />
            <p className="m-0 text-[12px] text-dim">{REVIEW_HINT}</p>
            {problem === null ? null : <p className="m-0 text-[12.5px] text-crit">{problem}</p>}
          </div>
        }
        confirmLabel="Verify them"
        cancelLabel="Not now"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setOpen(false);
        }}
      />
    </>
  );
}

function RowMenu({ row }: { readonly row: DocRow }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.title}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuItem asChild>
          <Link to={documentAddress(row.itemId)}>Open</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[11px] font-normal text-dim">Coming soon</DropdownMenuLabel>
        <DropdownMenuItem disabled className="flex-col items-start gap-0.5">
          <span>Archive</span>
          <span className="text-[11px] leading-snug text-dim">{UNAVAILABLE.archive.reason}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const COLUMNS: readonly EntityColumn<DocRow>[] = [
  {
    id: "title",
    header: DOCUMENT_COLUMN,
    hideable: false,
    cell: (row) => (
      <span className="flex min-w-[12rem] flex-col">
        <Link to={documentAddress(row.itemId)} className="font-medium text-ink underline-offset-4 [overflow-wrap:anywhere] hover:text-acc-text hover:underline">
          {row.title}
        </Link>
        {row.kindLabel === undefined ? null : <span className="text-[12px] text-dim">{row.kindLabel}</span>}
      </span>
    ),
    text: (row) => row.title,
  },
  {
    id: "department",
    header: DEPARTMENT_COLUMN,
    cell: (row) => row.department ?? null,
    text: (row) => row.department ?? "",
  },
  { id: "level", header: LEVEL_COLUMN, cell: (row) => levelWords(row.level), text: (row) => levelWords(row.level) },
  { id: "steward", header: STEWARD_COLUMN, cell: (row) => row.stewardName ?? null, text: (row) => row.stewardName ?? "" },
  {
    id: "verified",
    header: VERIFIED_COLUMN,
    cell: (row) => <span className="text-[12.5px]">{verifiedWords(row)}</span>,
    text: (row) => verifiedWords(row),
  },
  {
    id: "review",
    header: REVIEW_COLUMN,
    cell: (row) => (
      <span className="flex flex-wrap items-center gap-1.5 whitespace-nowrap">
        {dayWords(row.reviewBy) ?? null}
        {row.due ? <DuePill /> : null}
      </span>
    ),
    text: (row) => dayWords(row.reviewBy) ?? "",
  },
  { id: "state", header: STATE_COLUMN, cell: (row) => <StatePill state={row.state} />, text: (row) => stateWords(row.state) },
];

export function KnowledgePage() {
  // Moved after anything is added or verified, so the list and the tasks are asked again.
  const [version, setVersion] = useState(0);
  const changed = () => {
    setVersion((was) => was + 1);
  };
  const listing = useListing<Readonly<Record<string, unknown>>>(DOCUMENTS_API_PATH, { choices: DOCUMENT_FILTERS, version });
  const rows = useMemo(() => readDocRows(listing.body), [listing.body]);
  // The table draws the rows read out of the body; every other part of the listing is the route's.
  const table: Listing<DocRow> = { ...listing, rows };
  const truncated = typeof listing.body === "object" && listing.body !== null && (listing.body as { truncated?: unknown }).truncated === true;

  const offered = useResource<unknown>(UPLOAD_OPTIONS_API_PATH);
  const options = offered.failure === null ? readUploadOptions(offered.data) : null;
  const mayAdd = options !== null && levelsOf(options).length > 0;
  const [adding, setAdding] = useState<AddWay | null>(null);

  const tasks = useResource<unknown>(TASKS_API_PATH, version);
  const mine = tasks.failure === null ? readTasks(tasks.data) : [];
  const [said, setSaid] = useState<readonly string[]>([]);

  const notice = (
    <>
      {mine.length === 0 ? null : (
        <SectionCard title={TASKS_HEADING}>
          <TaskList tasks={mine} onChanged={changed} />
        </SectionCard>
      )}
      {said.length === 0 ? null : (
        <div role="status" className="flex flex-col gap-1 rounded-md border border-line bg-panel px-4 py-3">
          {said.map((line) => (
            <p key={line} className="m-0 text-[13px] text-ink [overflow-wrap:anywhere]">
              {line}
            </p>
          ))}
        </div>
      )}
    </>
  );

  return (
    <>
      <ListPage
        crumbs={[{ label: KNOWLEDGE_HEADING }]}
        title={KNOWLEDGE_HEADING}
        lede={KNOWLEDGE_LEDE}
        primary={mayAdd ? <AddMenu onChoose={setAdding} /> : undefined}
        actions={
          <>
            <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
              <Link to={SOLUTIONS_ADDRESS}>{SOLUTIONS_LINK}</Link>
            </Button>
            <UnavailableAction label={EXPORT_LABEL} text={EXPORT_LABEL} icon={<Download aria-hidden />} reason={UNAVAILABLE.exportInventory.reason} />
          </>
        }
        notice={notice}
        listing={table}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={DOCUMENT_FILTERS}
        sorts={DOCUMENT_SORTS}
        searchHint={SEARCH_HINT}
        caption={LIST_LABEL}
        columns={COLUMNS}
        rowId={(row) => row.itemId}
        rowLabel={(row) => row.title}
        rowActions={(row) => <RowMenu row={row} />}
        bulkActions={(selected, clear) => (
          <BulkVerify
            rows={selected}
            onDone={(lines) => {
              setSaid(lines);
              clear();
              changed();
            }}
          />
        )}
        loading={LOADING_DOCUMENTS}
        emptyTitle={NO_DOCUMENTS}
        emptyDescription={NO_DOCUMENTS_DESCRIPTION}
        emptyIcon={<BookOpen aria-hidden />}
        footer={truncated ? <Note>{MORE_DOCUMENTS}</Note> : undefined}
      />
      {options === null ? null : (
        <AddDrawer
          way={adding}
          options={options}
          onClose={() => {
            setAdding(null);
          }}
          onAdded={changed}
        />
      )}
    </>
  );
}
