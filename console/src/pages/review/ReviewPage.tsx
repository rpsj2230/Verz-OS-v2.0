/**
 * Access review on the shared page kit: every grant and pack this reviewer could have written, who
 * holds it, who granted it, when it lapses and when it was last reviewed, kept or removed from here.
 *
 * `docs/screens.html` SCREEN 10 draws a person's entitlement as Capability, Scope, By and Lapses, and
 * says grants are "additive capability strings bound to a scope" which is "why it can be audited and
 * reduced". This is that table across everybody a reviewer may decide, with the holder and the last
 * decision beside each row. A row opens the holding's own page (`HoldingPage.tsx`).
 *
 * **Nothing here decides who may see or decide a grant.** The rows are
 * `brain.console.govern.recertifiable`'s answer and the route asks `govern.certify` again under the
 * row's lock, so every row carries both acts and a refused press is the API's refusal. Removal
 * retires the grant row: there is no revocation by denial anywhere, because entitlements only add.
 *
 * **Names, not ids.** The holder is their display name, and who granted and who last decided each
 * row are named from the answer's `people`; the principal ids the old table printed are on the
 * holding's own page, in Advanced.
 *
 * Task ids: M27.7.9, M27.8.6, M27.16.1
 */

import { MoreHorizontal, ShieldCheck } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Chip, ListPage, Note, type EntityColumn } from "../../components/kit";
import { useListing } from "../../components/useListing";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import {
  DECISIONS,
  holdingKey,
  MOST_DECIDED_AT_ONCE,
  readReview,
  REVIEW_API_PATH,
  REVIEW_FILTERS,
  REVIEW_SORTS,
  type ReviewRow,
} from "../governPeopleQuery";
import { scopeLines } from "../scopeText";
import { CertificationExport } from "./CertificationExport";
import { LINK, nameOf, peopleIn, Pill, whenWords } from "./parts";
import { ACT_LABELS } from "./reviewActions";
import { holdingAddress, holdingTitle, kindWords, reviewWords } from "./reviewQuery";
import { useReviewActs } from "./ReviewActs";

export const REVIEW_HEADING = "Access review";
export const REVIEW_CRUMB = "Access reviews and elevation";
export const REVIEW_LEDE = "Keep what still belongs and remove what does not. Every decision is recorded with your name.";
export const READING_REVIEW = "Reading the grants you may review.";
export const NOTHING_TO_REVIEW = "No grants to review";
export const NOTHING_TO_REVIEW_MORE = "A grant appears here when somebody is given access you could have granted yourself.";
export const REVIEW_LABEL = "Grants to review";
export const FILTERS_LABEL = "Narrow the grants";
export const SEARCH_HINT = "Search people and grants";
export const MORE_GRANTS = "This list came back full, so there are more grants than it shows. Narrow it to review the rest.";
export const TOO_MANY_TICKED = "One decision covers at most fifty grants. Untick some and decide the rest afterwards.";
export const DOES_NOT_LAPSE = "Does not lapse";

export const PERSON_COLUMN = "Person";
export const HOLDING_COLUMN = "Holds";
export const GRANTED_COLUMN = "Granted";
export const LAPSES_COLUMN = "Lapses";
export const REVIEWED_COLUMN = "Last review";

function RowMenu({
  row,
  busy,
  onDecide,
}: {
  readonly row: ReviewRow;
  readonly busy: boolean;
  readonly onDecide: (row: ReviewRow, decision: (typeof DECISIONS)[number]) => void;
}) {
  const who = nameOf({}, row.principal_id, row.display_name);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${holdingTitle(row)}, ${who}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem asChild>
          <Link to={holdingAddress(row)}>{ACT_LABELS.open}</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {DECISIONS.map((decision) => (
          <DropdownMenuItem
            key={decision}
            disabled={busy}
            onSelect={() => {
              onDecide(row, decision);
            }}
          >
            {decision === "keep" ? ACT_LABELS.keep : ACT_LABELS.remove}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ReviewPage() {
  const [version, setVersion] = useState(0);
  const onDecided = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const listing = useListing<ReviewRow>(REVIEW_API_PATH, { choices: REVIEW_FILTERS, version });
  const review = useMemo(() => readReview(listing.body), [listing.body]);
  const people = useMemo(() => peopleIn(listing.body), [listing.body]);
  const acts = useReviewActs(review, onDecided);

  // The person filter offers the people on rows drawn, by the name each row carries.
  const names = new Map(listing.rows.map((row) => [row.principal_id, nameOf(people, row.principal_id, row.display_name)]));
  const choices = REVIEW_FILTERS.map((choice) =>
    choice.column === "principal_id" ? { ...choice, describe: (value: string) => names.get(value) ?? value } : choice,
  );

  const columns: readonly EntityColumn<ReviewRow>[] = [
    {
      id: "person",
      header: PERSON_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[10rem] flex-col">
          <Link to={holdingAddress(row)} className={LINK}>
            {nameOf(people, row.principal_id, row.display_name)}
          </Link>
          {row.department === null ? null : <span className="text-[12px] text-dim">{row.department}</span>}
        </span>
      ),
      text: (row) => nameOf(people, row.principal_id, row.display_name),
    },
    {
      id: "holding",
      header: HOLDING_COLUMN,
      cell: (row) => (
        <span className="flex min-w-0 flex-col gap-1">
          <span className="font-mono text-[12px] text-ink [overflow-wrap:anywhere]">{holdingTitle(row)}</span>
          {row.pack === null ? null : <span className="text-[12px] text-dim">{`${kindWords(row.kind)}: ${row.capabilities.join(", ")}`}</span>}
        </span>
      ),
      text: (row) => (row.pack === null ? holdingTitle(row) : `${holdingTitle(row)}: ${row.capabilities.join(", ")}`),
    },
    {
      id: "granted",
      header: GRANTED_COLUMN,
      cell: (row) => (
        <span className="flex flex-col">
          <span>{nameOf(people, row.granted_by)}</span>
          <span className="text-[12px] text-dim">{whenWords(row.granted_at)}</span>
        </span>
      ),
      text: (row) => `${nameOf(people, row.granted_by)}, ${whenWords(row.granted_at)}`,
    },
    {
      id: "lapses",
      header: LAPSES_COLUMN,
      className: "whitespace-nowrap",
      cell: (row) => (row.lapses_at === null ? <span className="text-dim">{DOES_NOT_LAPSE}</span> : whenWords(row.lapses_at)),
      text: (row) => (row.lapses_at === null ? DOES_NOT_LAPSE : whenWords(row.lapses_at)),
    },
    {
      id: "reviewed",
      header: REVIEWED_COLUMN,
      cell: (row) => (
        <span className="flex flex-col gap-0.5">
          <span>
            <Pill tone={row.last_decision === null ? "warn" : row.last_decision === "keep" ? "ok" : "plain"}>
              {reviewWords(row.last_decision)}
            </Pill>
          </span>
          {row.last_decided_at === null ? null : (
            <span className="text-[12px] text-dim">{`${nameOf(people, row.last_decided_by)}, ${whenWords(row.last_decided_at)}`}</span>
          )}
        </span>
      ),
      text: (row) => reviewWords(row.last_decision),
    },
    {
      id: "scope",
      header: "Scope",
      hidden: true,
      cell: (row) => (
        <span className="flex flex-wrap gap-1">
          {scopeLines(row.scope).map((line) => (
            <Chip key={line} mono>
              {line}
            </Chip>
          ))}
        </span>
      ),
      text: (row) => scopeLines(row.scope).join("; "),
    },
    {
      id: "reason",
      header: "Why it was granted",
      hidden: true,
      cell: (row) => row.reason,
      text: (row) => row.reason,
    },
  ];

  return (
    <ListPage
      crumbs={[{ label: REVIEW_CRUMB }, { label: REVIEW_HEADING }]}
      title={REVIEW_HEADING}
      lede={REVIEW_LEDE}
      primary={<CertificationExport />}
      notice={acts.drawn}
      listing={listing}
      rows={review.rows}
      filtersLabel={FILTERS_LABEL}
      choices={choices}
      sorts={REVIEW_SORTS}
      searchHint={SEARCH_HINT}
      caption={REVIEW_LABEL}
      columns={columns}
      rowId={holdingKey}
      rowLabel={(row) => `${holdingTitle(row)} for ${nameOf(people, row.principal_id, row.display_name)}`}
      rowActions={(row) => <RowMenu row={row} busy={acts.busy} onDecide={acts.decide} />}
      bulkActions={(selected, clear) =>
        selected.length > MOST_DECIDED_AT_ONCE ? (
          <span className="text-[12.5px] text-warn">{TOO_MANY_TICKED}</span>
        ) : (
          <>
            {DECISIONS.map((decision) => (
              <Button
                key={decision}
                size="sm"
                variant={decision === "remove" ? "destructive" : "outline"}
                disabled={acts.busy}
                onClick={() => {
                  acts.decideMany(selected, decision);
                  clear();
                }}
              >
                {decision === "keep" ? ACT_LABELS.keepSelected : ACT_LABELS.removeSelected}
              </Button>
            ))}
          </>
        )
      }
      exportName="access-review"
      loading={READING_REVIEW}
      emptyTitle={NOTHING_TO_REVIEW}
      emptyDescription={NOTHING_TO_REVIEW_MORE}
      emptyIcon={<ShieldCheck aria-hidden />}
      footer={review.truncated ? <Note>{MORE_GRANTS}</Note> : undefined}
    />
  );
}
