/**
 * The Skills list, built on the shared page kit: every version in the library this reader may list,
 * with its state, its categories and how many of the reader's agents run it.
 *
 * **The list is the route's answer to the reader's question (M27.11.8).** `GET /skills/library` is
 * one row per version and it searches, filters and orders on the server (`brain.skill_routes.
 * LIBRARY_LISTING`), so a search or a filter here changes the request and never the rows already in
 * the browser. The state filter offers the review words the rows carry, the retired filter the two
 * values the rows carry, and the category chips are the API's `categories`, drawn from the versions
 * this reader may list and no others. Nothing on the page is a count of anything withheld; the one
 * summary is the review queue's, over exactly the versions waiting that this reader may see, and the
 * route computes it.
 *
 * **The queue's summary counts an edit as an edit.** Until 2026-09-28 it said "0 of them edits"
 * beside a waiting edit whenever no version of the skill had been approved yet;
 * `brain.console.skill_library.queue_entries` now diffs an edit against the version it came from.
 *
 * **Adding and importing open in a drawer**, each form saying what it accepts before anything is
 * pressed (`SkillForms.tsx`), and only for a reader the API says may add.
 *
 * **What was removed from the old page.** The lede explaining that import is the security boundary;
 * the "skills in use" list, which listed the same skills a second time keyed by agent, and its
 * principal ids and digests; the version drift card, which now sits on the skill's own page where it
 * applies; the sentences about truncated loads under every list; and the add and import forms drawn
 * open above the library for every visit.
 *
 * Task ids: M27.16.1, M27.11.8, M27.15.55, M27.15.56
 */

import { Plus, Sparkles } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Chip, Drawer, ListPage, NOT_RECORDED, Note, SectionCard, type EntityColumn } from "../../components/kit";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { Button } from "../../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { useListing, type Listing } from "../../components/useListing";
import { CATEGORY_COLUMN, LIBRARY_API_PATH, skillAddress, type LibraryRow } from "../skillsQuery";
import { AddSkillForm, ImportSkillForm, type Told } from "./SkillForms";
import { ReviewPill, RetiredPill } from "./pills";
import { retiredWords, reviewPill } from "./skillActions";

export const SKILLS_HEADING = "Skills";
export const SKILLS_LEDE =
  "Instructions an agent can follow, each reviewed by a named person before any agent may use it.";
export const LOADING_SKILLS = "Loading the skill library.";
export const NO_SKILLS = "No skills to show";
export const NO_SKILLS_DESCRIPTION =
  "A skill appears here once somebody who may add skills pastes, uploads or imports one.";
export const LIST_LABEL = "Skills in the library";
export const FILTERS_LABEL = "Narrow the skills";
export const SEARCH_HINT = "Search skills";
export const ADD_SKILL = "Add a skill";
export const ADD_DESCRIPTION = "A skill is added unreviewed and reaches no agent until it is approved and assigned.";
export const CHIPS_LABEL = "Show one category";
export const EVERY_CATEGORY = "Every category";

export const SKILL_COLUMN = "Skill";
export const VERSION_COLUMN = "Version";
export const STATE_COLUMN = "State";
export const CATEGORIES_COLUMN = "Categories";
export const AGENTS_COLUMN = "Agents using it";
export const LAST_USED_COLUMN = "Last used";
export const ADDED_COLUMN = "Added";

/** The last-used figure: nothing records a run's use of a skill yet. */
export const LAST_USED_WHY = "Nothing records that a run used a skill yet, so there is no last use to show.";

/** The review queue's summary, in words, over exactly the versions it lists. */
export function queueWords(waiting: number, edits: number, stale: number): string {
  const edit = edits === 1 ? "1 of them an edit" : `${String(edits)} of them edits`;
  const overdue = stale === 0 ? "none waiting over a week" : `${String(stale)} waiting over a week`;
  return `${String(waiting)} waiting for review: ${edit}, ${overdue}.`;
}

/** One version as the list draws it, read keeping only fields that were sent. */
export function readLibraryRows(payload: unknown): readonly LibraryRow[] {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return [];
  }
  // A cast at the boundary: each row is checked for the fields the page draws before it is kept.
  const items = (payload as Readonly<Record<string, unknown>>)["items"];
  if (!Array.isArray(items)) {
    return [];
  }
  const seen = new Set<string>();
  const rows: LibraryRow[] = [];
  for (const item of items as readonly unknown[]) {
    const row = item as Partial<LibraryRow> | null;
    if (
      row === null ||
      typeof row !== "object" ||
      typeof row.digest !== "string" ||
      typeof row.name !== "string" ||
      typeof row.version !== "string" ||
      seen.has(row.digest)
    ) {
      continue;
    }
    seen.add(row.digest);
    rows.push({
      digest: row.digest,
      name: row.name,
      version: row.version,
      description: typeof row.description === "string" ? row.description : "",
      review: typeof row.review === "string" ? row.review : "",
      retired: row.retired === true,
      categories: Array.isArray(row.categories) ? row.categories.filter((one): one is string => typeof one === "string") : [],
      agents_running: typeof row.agents_running === "number" && row.agents_running >= 0 ? row.agents_running : 0,
      source: typeof row.source === "string" ? row.source : "",
      submitted_at: typeof row.submitted_at === "string" ? row.submitted_at : "",
    });
  }
  return rows;
}

/** The rest of the library's first page: the queue's summary, whether the reader may add, the chips. */
export interface LibraryPage {
  readonly waiting: number;
  readonly edits: number;
  readonly stale: number;
  readonly mayAdd: boolean;
  readonly categories: readonly string[];
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : 0;
}

export function readLibraryPage(payload: unknown): LibraryPage {
  const body = (typeof payload === "object" && payload !== null ? payload : {}) as Readonly<Record<string, unknown>>;
  const queue = (typeof body["queue"] === "object" && body["queue"] !== null ? body["queue"] : {}) as Readonly<Record<string, unknown>>;
  const categories = body["categories"];
  return {
    waiting: count(queue["waiting"]),
    edits: count(queue["edits"]),
    stale: count(queue["stale"]),
    mayAdd: body["may_add"] === true,
    categories: Array.isArray(categories) ? categories.filter((one): one is string => typeof one === "string") : [],
  };
}

export const SKILL_FILTERS: readonly FilterChoice<LibraryRow>[] = [
  { column: "review", label: STATE_COLUMN, everything: "Any state", read: (row) => row.review, describe: reviewPill },
  { column: "retired", label: "Retired", everything: "Retired or not", read: (row) => row.retired, describe: retiredWords },
];

export const SKILL_SORTS: readonly SortChoice[] = [
  { value: "", label: "Name" },
  { value: "-submitted_at", label: "Newest first" },
  { value: "-agents_running", label: "Most agents" },
];

function dateWords(at: string): string {
  const parsed = Date.parse(at);
  return Number.isNaN(parsed) ? "" : new Date(parsed).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function CategoryChips({ listing, categories }: { readonly listing: Listing<LibraryRow>; readonly categories: readonly string[] }) {
  if (categories.length === 0) {
    return null;
  }
  const chosen = listing.question.filters[CATEGORY_COLUMN] ?? "";
  return (
    <div role="group" aria-label={CHIPS_LABEL} className="flex flex-wrap items-center gap-1.5">
      {["", ...categories].map((category) => (
        <Button
          key={category === "" ? "every" : category}
          type="button"
          size="xs"
          variant={chosen === category ? "secondary" : "outline"}
          aria-pressed={chosen === category}
          className="h-auto min-h-11 rounded-full px-3 py-1 whitespace-normal [overflow-wrap:anywhere] sm:min-h-7"
          onClick={() => {
            listing.ask({ ...listing.question, filters: { ...listing.question.filters, [CATEGORY_COLUMN]: category } });
          }}
        >
          {category === "" ? EVERY_CATEGORY : category}
        </Button>
      ))}
    </div>
  );
}

function QueueCard({ page, listing }: { readonly page: LibraryPage; readonly listing: Listing<LibraryRow> }) {
  if (page.waiting === 0) {
    return null;
  }
  return (
    <SectionCard
      title="Waiting for review"
      action={
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="min-h-11 sm:min-h-8"
          onClick={() => {
            listing.ask({ ...listing.question, filters: { ...listing.question.filters, review: "pending" } });
          }}
        >
          Show them
        </Button>
      }
    >
      <p className="m-0 text-[13px] text-ink">{queueWords(page.waiting, page.edits, page.stale)}</p>
    </SectionCard>
  );
}

function AddDrawer({ open, onOpenChange, onTold }: { readonly open: boolean; readonly onOpenChange: (open: boolean) => void; readonly onTold: (told: Told) => void }) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange} title={ADD_SKILL} description={ADD_DESCRIPTION}>
      <Tabs defaultValue="paste">
        <TabsList>
          <TabsTrigger value="paste">Paste or upload</TabsTrigger>
          <TabsTrigger value="import">Import</TabsTrigger>
        </TabsList>
        <TabsContent value="paste" className="pt-2">
          <AddSkillForm onTold={onTold} />
        </TabsContent>
        <TabsContent value="import" className="pt-2">
          <ImportSkillForm onTold={onTold} />
        </TabsContent>
      </Tabs>
    </Drawer>
  );
}

export function SkillsPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<Told | null>(null);
  const [adding, setAdding] = useState(false);
  const listing = useListing<LibraryRow>(LIBRARY_API_PATH, { choices: SKILL_FILTERS, version });
  const rows = useMemo(() => readLibraryRows(listing.body), [listing.body]);
  const page = useMemo(() => readLibraryPage(listing.body), [listing.body]);

  function onTold(next: Told) {
    setTold(next);
    if (next.ok) {
      setAdding(false);
      setVersion((one) => one + 1);
    }
  }

  const columns: readonly EntityColumn<LibraryRow>[] = [
    {
      id: "name",
      header: SKILL_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[14rem] flex-col">
          <Link to={skillAddress(row.name)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
            {row.name}
          </Link>
          <span className="line-clamp-2 text-[12px] text-dim">{row.description}</span>
        </span>
      ),
      text: (row) => row.name,
    },
    {
      id: "version",
      header: VERSION_COLUMN,
      cell: (row) => <span className="font-mono text-[12px] text-ink">{row.version}</span>,
      text: (row) => row.version,
    },
    {
      id: "state",
      header: STATE_COLUMN,
      cell: (row) => (
        <span className="flex flex-wrap gap-1">
          <ReviewPill review={row.review} />
          {row.retired ? <RetiredPill /> : null}
        </span>
      ),
      text: (row) => [reviewPill(row.review), row.retired ? "Retired" : ""].filter((one) => one !== "").join(", "),
    },
    {
      id: "categories",
      header: CATEGORIES_COLUMN,
      cell: (row) =>
        row.categories.length === 0 ? null : (
          <span className="flex flex-wrap gap-1">
            {row.categories.map((one) => (
              <Chip key={one}>{one}</Chip>
            ))}
          </span>
        ),
      text: (row) => row.categories.join("; "),
    },
    {
      id: "agents",
      header: AGENTS_COLUMN,
      align: "end",
      cell: (row) => <span className="font-mono text-[12px] text-ink tabular-nums">{String(row.agents_running)}</span>,
      text: (row) => String(row.agents_running),
    },
    {
      id: "last_used",
      header: LAST_USED_COLUMN,
      hidden: true,
      cell: () => (
        <span className="text-[12px] text-dim" title={LAST_USED_WHY}>
          {NOT_RECORDED}
        </span>
      ),
      text: () => "",
    },
    {
      id: "added",
      header: ADDED_COLUMN,
      hidden: true,
      cell: (row) => <span className="text-[12px] text-dim">{dateWords(row.submitted_at)}</span>,
      text: (row) => row.submitted_at,
    },
  ];

  const notice: ReactNode = (
    <>
      {told === null ? null : (
        <div role={told.ok ? "status" : "alert"}>
          <Note kind={told.ok ? "done" : "info"}>{told.sentence}</Note>
        </div>
      )}
      <QueueCard page={page} listing={listing} />
      <CategoryChips listing={listing} categories={page.categories} />
    </>
  );

  return (
    <>
      <ListPage
        crumbs={[{ label: SKILLS_HEADING }]}
        title={SKILLS_HEADING}
        lede={SKILLS_LEDE}
        primary={
          page.mayAdd ? (
            <Button
              className="min-h-11 sm:min-h-9"
              onClick={() => {
                setAdding(true);
              }}
            >
              <Plus aria-hidden /> {ADD_SKILL}
            </Button>
          ) : undefined
        }
        notice={notice}
        listing={listing}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={SKILL_FILTERS}
        sorts={SKILL_SORTS}
        searchHint={SEARCH_HINT}
        caption={LIST_LABEL}
        columns={columns}
        rowId={(row) => row.digest}
        rowLabel={(row) => `${row.name} ${row.version}`}
        exportName="skills"
        loading={LOADING_SKILLS}
        emptyTitle={NO_SKILLS}
        emptyDescription={NO_SKILLS_DESCRIPTION}
        emptyIcon={<Sparkles aria-hidden />}
      />
      {page.mayAdd ? <AddDrawer open={adding} onOpenChange={setAdding} onTold={onTold} /> : null}
    </>
  );
}
