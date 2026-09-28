/**
 * The Routing page on the shared kit: the failover matrix as the owner drew it on 2026-09-03, one
 * table of Complexity, Step, Provider, Model and Role, and what changing it takes.
 *
 * **Top to bottom**: a change the gate just held, with why and the three steps that get it through;
 * a notice when a level cannot answer; the matrix; one step's editor when its address is open; the
 * golden questions every change is asked; the recent changes; and, under Advanced, each level's
 * numbers and the residency rules (`components/RoutingSettings.tsx`), which are tuning.
 *
 * **Every change goes through the matrix gate, and says so before it is sent.** Adding, editing,
 * moving and retiring a step are each confirmed with a sentence saying it is tried against the
 * golden questions first; the answer is the change as `ops.routing_change` recorded it, applied or
 * held, and a held one is drawn above the matrix. The matrix is then asked again, never patched.
 *
 * **What is asked, and of whom.** The matrix is `GET /routing/rungs` under the list contract, in
 * the chain's one order with a search, the level, provider and in-use filters the route declares,
 * and "Show more" when it says there is more; a level is numbered from the rows drawn. The plan
 * (`GET /models/providers`) gives each step's role as the next call derives it and the marker on a
 * step that will not answer. Both are asked for every reader. The changes, the golden questions and
 * the people are asked only when the matrix says this reader may change it, which is presentation:
 * every write is refused by the route without the matrix write over everything.
 *
 * **What was removed from the old screens**: the id and deployment columns (under Advanced in a
 * step's editor); the Models page's second copy of the matrix and its Edit link here; "by" and a
 * principal id on every change; the figures and each step's health table; and a paragraph on the
 * page's own implementation.
 *
 * Task ids: M5.3.3, M27.15.38, M5.6.2, M5.7.2, M27.16.1
 */

import { ArrowDown, ArrowUp, Download, MoreHorizontal, Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, EmptyState, FailureState, ListToolbar, LoadingState, Note, PageHeader, SectionCard } from "../../components/kit";
import { NOTHING_MATCHES, SHOW_MORE } from "../../components/ListControls";
import { narrows } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { RoutingSettings } from "../../components/RoutingSettings";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import {
  APPLIED,
  changeWords,
  CHANGES_API_PATH,
  GOLDEN_API_PATH,
  HELD,
  heldSentence,
  NO_CHANGES,
  readChange,
  readChanges,
  readGolden,
  type ChangeRow,
} from "../matrixGateQuery";
import { CHAIN_PAGE_SIZE, MATRIX_API_PATH, MATRIX_FILTERS, MATRIX_PATH, readMatrixPage, rungAddress, type RungRow } from "../matrixQuery";
import {
  exhaustedSentence,
  LEVELS_CANNOT_ANSWER,
  NO_STEP_FOR_THE_LEVEL,
  PROVIDERS_API_PATH,
  readProviders,
} from "../modelsQuery";
import { AddStep } from "./AddStep";
import { GoldenQuestions } from "./GoldenQuestions";
import { HeldExplanation } from "./HeldChange";
import { EXPORT_API_PATH, MODULE_LABEL, moveStepApiPath, retireStepApiPath, saveText } from "./modelsActions";
import { MarkerPill, RolePill } from "./pills";
import { dayWords } from "./providerWords";
import { RungEditor } from "./RungEditor";
import {
  KEEP_STEP,
  matrixLines,
  MOVE_DOWN,
  MOVE_STEP,
  MOVE_UP,
  moveConsequence,
  moveQuestion,
  RETIRE_STEP,
  retireConsequence,
  retireQuestion,
  type MatrixLine,
} from "./routingWords";

export const ROUTING_HEADING = "Routing";
export const ROUTING_LEDE = "Which model answers each level of question, and what happens when it fails.";
export const FAILOVER_MATRIX = "Failover matrix: what answers, and what happens when it fails";
export const MATRIX_LEDE =
  "A question is answered by its level's first step. When a step fails, is too slow or is turned away, the next step is tried.";
export const LOADING_MATRIX = "Loading the failover matrix.";
export const FILTERS_LABEL = "Narrow the matrix";
export const SEARCH_HINT = "Search steps";
export const ADD_A_STEP = "Add a step";
export const EXPORT = "Export";
export const EXPORT_SAYS = "Downloads the steps, the providers and each level's numbers as a file, with no key in it.";
export const THERE_IS_MORE = "The matrix came back full, so there are more steps than it shows.";
export const NO_SUCH_STEP = "No step on the matrix matches this address.";
export const HELD_HEADING = "The change was held";
export const CHANGES_HEADING = "Recent changes";
export const CHANGES_LEDE = "Each change to the matrix and whether it was applied or held.";
export const ADVANCED = "Advanced";
export const SETTINGS_HEADING = "Each level's context window and escalation, and the rules on where a department's questions may be answered.";

/** A write the matrix's own rows send, held while its confirmation is open. */
type Pending =
  | { readonly kind: "move"; readonly line: MatrixLine; readonly rungId: string; readonly step: number }
  | { readonly kind: "retire"; readonly line: MatrixLine; readonly rungId: string };

function StepMenu({ line, onAsk }: { readonly line: MatrixLine; readonly onAsk: (pending: Pending) => void }) {
  const rung = line.rung;
  if (rung === null || line.step === null) {
    return null;
  }
  const step = line.step;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for step ${String(step)} of ${line.provider} ${line.model}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuItem asChild>
          <Link to={rungAddress(rung.id)}>Edit</Link>
        </DropdownMenuItem>
        {step > 1 ? (
          <DropdownMenuItem
            onSelect={() => {
              onAsk({ kind: "move", line, rungId: rung.id, step: step - 1 });
            }}
          >
            <ArrowUp aria-hidden /> {MOVE_UP}
          </DropdownMenuItem>
        ) : null}
        {step < line.of ? (
          <DropdownMenuItem
            onSelect={() => {
              onAsk({ kind: "move", line, rungId: rung.id, step: step + 1 });
            }}
          >
            <ArrowDown aria-hidden /> {MOVE_DOWN}
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            onAsk({ kind: "retire", line, rungId: rung.id });
          }}
        >
          {RETIRE_STEP}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function FailoverMatrix({
  lines,
  editable,
  openId,
  onAsk,
}: {
  readonly lines: readonly MatrixLine[];
  readonly editable: boolean;
  readonly openId: string | undefined;
  readonly onAsk: (pending: Pending) => void;
}) {
  return (
    <Table className="text-[13px]">
      <TableCaption className="sr-only">{FAILOVER_MATRIX}</TableCaption>
      <TableHeader className="bg-sunk">
        <TableRow className="hover:bg-transparent">
          <TableHead scope="col">Complexity</TableHead>
          <TableHead scope="col">Step</TableHead>
          <TableHead scope="col">Provider</TableHead>
          <TableHead scope="col">Model</TableHead>
          <TableHead scope="col">Role</TableHead>
          {editable ? (
            <TableHead scope="col" className="w-12">
              <span className="sr-only">Actions</span>
            </TableHead>
          ) : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {lines.map((line) => (
          <TableRow
            key={line.key}
            data-state={line.rung !== null && line.rung.id === openId ? "selected" : undefined}
            className={line.level === null ? undefined : "border-t-2 border-t-line"}
          >
            <TableCell className="font-semibold text-ink">{line.level ?? ""}</TableCell>
            <TableCell className="tabular-nums">{line.step === null ? "" : String(line.step)}</TableCell>
            {line.rung === null ? (
              <TableCell colSpan={editable ? 4 : 3} className="text-dim">
                {NO_STEP_FOR_THE_LEVEL}
              </TableCell>
            ) : (
              <>
                <TableCell className="[overflow-wrap:anywhere] whitespace-normal">{line.provider}</TableCell>
                <TableCell className="font-mono text-[12px] [overflow-wrap:anywhere] whitespace-normal">{line.model}</TableCell>
                <TableCell>
                  <span className="flex flex-wrap items-center gap-1.5">
                    <RolePill role={line.role} />
                    {line.marker === null ? null : <MarkerPill marker={line.marker} />}
                  </span>
                </TableCell>
                {editable ? (
                  <TableCell className="w-12 py-1.5">
                    <StepMenu line={line} onAsk={onAsk} />
                  </TableCell>
                ) : null}
              </>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function RecentChanges({ changes }: { readonly changes: readonly ChangeRow[] }) {
  if (changes.length === 0) {
    return <Note>{NO_CHANGES}</Note>;
  }
  return (
    <ol className="m-0 flex list-none flex-col gap-2 p-0">
      {changes.map((change) => (
        <li key={change.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[13px]">
          {change.status === "held" ? (
            <span className="rounded-[2px] bg-warn-wash px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-warn">{HELD}</span>
          ) : (
            <span className="rounded-[2px] bg-ok-wash px-1.5 py-0.5 font-mono text-[10.5px] font-medium text-ok">{APPLIED}</span>
          )}
          <span className="text-ink">{changeWords(change.kind)}</span>
          <span className="font-mono text-[11.5px] text-dim">{dayWords(change.decided_at)}</span>
          {change.status === "held" ? <span className="min-w-0 text-dim [overflow-wrap:anywhere]">{heldSentence(change)}</span> : null}
        </li>
      ))}
    </ol>
  );
}

export function RoutingPage() {
  const { rungId } = useParams();
  // A counter, so two changes in a row ask again twice. Never drawn.
  const [version, setVersion] = useState(0);
  const listing = useListing<RungRow>(MATRIX_API_PATH, { choices: MATRIX_FILTERS, version, pageSize: CHAIN_PAGE_SIZE });
  const plan = useResource<unknown>(PROVIDERS_API_PATH, version);
  const page = useMemo(() => readMatrixPage(listing.body), [listing.body]);
  const body = useMemo(() => readProviders(plan.data), [plan.data]);
  const editable = page.editable;
  const changes = useResource<unknown>(editable ? CHANGES_API_PATH : null, version);
  const golden = useResource<unknown>(editable ? GOLDEN_API_PATH : null, version);
  const [decided, setDecided] = useState<ChangeRow | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const lines = useMemo(() => matrixLines(page.rungs, body?.rungs ?? [], body?.providers ?? []), [page.rungs, body]);
  const open = rungId === undefined ? null : (lines.find((one) => one.rung?.id === rungId) ?? null);
  const goldenRows = golden.data === null ? [] : readGolden(golden.data);
  const goldenCount = golden.data === null || golden.failure !== null ? null : goldenRows.length;

  const onDecided = useCallback((change: ChangeRow | null) => {
    setDecided(change);
    setAdding(false);
    setVersion((count) => count + 1);
  }, []);

  const send = useCallback(
    (asked: Pending) => {
      setBusy(true);
      void (async () => {
        const result =
          asked.kind === "move"
            ? await request<unknown>(moveStepApiPath(asked.rungId), { method: "POST", body: { tier: asked.line.tier, step: asked.step } })
            : await request<unknown>(retireStepApiPath(asked.rungId), { method: "POST" });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onDecided(readChange(result.data));
      })();
    },
    [onDecided],
  );

  const exportRouting = useCallback(() => {
    void (async () => {
      const result = await request<unknown>(EXPORT_API_PATH);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const filename =
        typeof result.data === "object" && result.data !== null && typeof (result.data as { filename?: unknown }).filename === "string"
          ? (result.data as { filename: string }).filename
          : "routing-configuration.json";
      saveText(filename, `${JSON.stringify(result.data, null, 2)}\n`, "application/json");
    })();
  }, []);

  const onAsk = (asked: Pending) => {
    setFailure(null);
    setPending(asked);
  };

  let matrixBody;
  if (listing.failure !== null) {
    matrixBody = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    matrixBody = <LoadingState label={LOADING_MATRIX} />;
  } else if (page.rungs.length === 0 && narrows(listing.question)) {
    matrixBody = <EmptyState title={NOTHING_MATCHES} description="Change the search or clear a filter." />;
  } else {
    matrixBody = <FailoverMatrix lines={lines} editable={editable} openId={rungId} onAsk={onAsk} />;
  }

  return (
    <div data-slot="routing-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: MODULE_LABEL }, { label: ROUTING_HEADING }]}
        title={ROUTING_HEADING}
        lede={ROUTING_LEDE}
        primary={
          editable ? (
            <Button
              className="min-h-11 sm:min-h-8"
              aria-expanded={adding}
              onClick={() => {
                setAdding((now) => !now);
              }}
            >
              <Plus aria-hidden />
              {ADD_A_STEP}
            </Button>
          ) : undefined
        }
        actions={
          body === null ? undefined : (
            <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" title={EXPORT_SAYS} onClick={exportRouting}>
              <Download aria-hidden /> {EXPORT}
            </Button>
          )
        }
      />

      {decided === null ? null : decided.status === "held" ? (
        <section role="status" aria-label={HELD_HEADING} className="rounded-md border border-line bg-warn-wash px-4 py-3">
          <h2 className="m-0 mb-2 text-sm font-semibold text-ink">{HELD_HEADING}</h2>
          <HeldExplanation change={decided} golden={goldenRows} goldenCount={goldenCount} />
        </section>
      ) : (
        <div role="status">
          <Note kind="works">{`${changeWords(decided.kind)}: applied. The next question uses it.`}</Note>
        </div>
      )}
      {failure === null ? null : <FailureState failure={failure} />}
      {body === null || body.exhausted_tiers.length === 0 ? null : (
        <section aria-label={LEVELS_CANNOT_ANSWER} className="flex flex-col gap-1 rounded-md border border-line bg-panel px-4 py-3">
          <h2 className="m-0 text-sm font-semibold text-ink">{LEVELS_CANNOT_ANSWER}</h2>
          {body.exhausted_tiers.map((tier) => (
            <Note key={tier} kind="not-yet">
              {exhaustedSentence(tier)}
            </Note>
          ))}
        </section>
      )}

      {adding && editable ? (
        <AddStep
          providers={body?.providers ?? []}
          plan={body?.rungs ?? []}
          onDecided={onDecided}
          onClose={() => {
            setAdding(false);
          }}
        />
      ) : null}

      <SectionCard title={FAILOVER_MATRIX} lede={MATRIX_LEDE}>
        <div className="flex min-w-0 flex-col gap-3">
          <ListToolbar label={FILTERS_LABEL} listing={listing} choices={MATRIX_FILTERS} searchHint={SEARCH_HINT} />
          {matrixBody}
          {listing.moreFailure === null ? null : <FailureState failure={listing.moreFailure} />}
          {listing.more ? (
            <Button
              variant="outline"
              className="min-h-11 self-start sm:min-h-9"
              disabled={listing.fetchingMore}
              onClick={() => {
                listing.showMore();
              }}
            >
              {SHOW_MORE}
            </Button>
          ) : null}
          {page.truncated ? <Note>{THERE_IS_MORE}</Note> : null}
        </div>
      </SectionCard>

      {open !== null && editable ? <RungEditor key={open.key} line={open} onDecided={onDecided} /> : null}
      {rungId !== undefined && open === null && !listing.busy && listing.failure === null && !narrows(listing.question) ? (
        <Note>
          {NO_SUCH_STEP} <Link to={MATRIX_PATH}>{ROUTING_HEADING}</Link>
        </Note>
      ) : null}

      {editable ? (
        <>
          <GoldenQuestions
            golden={golden}
            version={version}
            onChanged={() => {
              setVersion((count) => count + 1);
            }}
          />
          <SectionCard title={CHANGES_HEADING} lede={CHANGES_LEDE}>
            {changes.failure !== null ? (
              <FailureState failure={changes.failure} />
            ) : changes.busy ? null : (
              <RecentChanges changes={changes.data === null ? [] : readChanges(changes.data)} />
            )}
          </SectionCard>
        </>
      ) : null}

      {plan.data === null ? null : (
        <details data-slot="routing-advanced" className="rounded-md border border-line bg-panel">
          <summary className="flex min-h-11 cursor-pointer items-center px-4 text-[13px] font-medium text-ink sm:min-h-9">
            {ADVANCED}
          </summary>
          <div className="flex min-w-0 flex-col gap-2 border-t border-line px-4 py-3">
            <p className="m-0 text-[12px] text-dim">{SETTINGS_HEADING}</p>
            <RoutingSettings
              data={plan.data}
              onWritten={() => {
                setVersion((count) => count + 1);
              }}
            />
          </div>
        </details>
      )}

      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : pending.kind === "move" ? moveQuestion(pending.line, pending.line.tier, pending.step) : retireQuestion(pending.line)}
        consequence={pending === null ? "" : pending.kind === "move" ? moveConsequence(pending.line.tier, pending.step) : retireConsequence(pending.line)}
        confirmLabel={pending?.kind === "retire" ? RETIRE_STEP : MOVE_STEP}
        cancelLabel={KEEP_STEP}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </div>
  );
}
