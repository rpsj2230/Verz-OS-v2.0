/**
 * The Routing page on the shared kit: the failover matrix as the owner drew it on 2026-09-03 and
 * restated on 2026-09-29 (`FailoverMatrixCard`, the card the Models page draws too), and what
 * changing it takes.
 *
 * **Top to bottom**: a change the gate just held, with why and the three steps that get it through;
 * a notice when a level cannot answer; one line, before anybody tries, when no golden question is
 * recorded, because every change would be held; the matrix; the golden questions every change is
 * asked; the recent changes; and, under Advanced, each level's numbers and the residency rules
 * (`components/RoutingSettings.tsx`), which are tuning. One step's editor opens at its own address
 * in a drawer over the matrix.
 *
 * **Every change goes through the matrix gate, and says so before it is sent.** Adding, editing,
 * moving and retiring a step are each confirmed with a sentence saying it is tried against the
 * golden questions first; the answer is the change as `ops.routing_change` recorded it, applied or
 * held, and a held one is drawn above the matrix. The matrix is then asked again, never patched.
 *
 * **What is asked, and of whom.** The matrix is `GET /routing/rungs`, the whole chain in one page
 * (`CHAIN_PAGE_SIZE` is every step the route loads) in the chain's one order, with "Show more" only
 * when the API says there is more; a level is numbered from the rows drawn. The plan
 * (`GET /models/providers`) gives each step's role as the next call derives it and the marker on a
 * step that will not answer. Both are asked for every reader. The changes, the golden questions and
 * the people are asked only when the matrix says this reader may change it, which is presentation:
 * every write is refused by the route without the matrix write over everything.
 *
 * **What was removed on 2026-09-29, to match the owner's screenshot**: the card's lede, its search
 * and its three filters, the heavy line between levels, the square default pill, the visible
 * column of buttons, and the editor drawn as a panel under the table. Earlier: the id and
 * deployment columns (under Advanced in a step's editor), the Models page's second copy of the
 * matrix, "by" and a principal id on every change, the figures and each step's health table, and a
 * paragraph on the page's own implementation.
 *
 * Task ids: M5.3.3, M27.15.38, M5.6.2, M5.7.2, M27.16.1
 */

import { Download, Plus } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, FailureState, LoadingState, Note, PageHeader, SectionCard } from "../../components/kit";
import { SHOW_MORE } from "../../components/ListControls";
import { useListing } from "../../components/useListing";
import { RoutingSettings } from "../../components/RoutingSettings";
import { Button } from "../../components/ui/button";
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
import { CHAIN_PAGE_SIZE, MATRIX_API_PATH, MATRIX_PATH, readMatrixPage, rungAddress, type RungRow } from "../matrixQuery";
import { exhaustedSentence, LEVELS_CANNOT_ANSWER, PROVIDERS_API_PATH, readProviders } from "../modelsQuery";
import { AddStep } from "./AddStep";
import { FailoverMatrixCard, type StepAsk } from "./FailoverMatrixCard";
import { GOLDEN_QUESTION_FIELD, GoldenQuestions } from "./GoldenQuestions";
import { HeldExplanation } from "./HeldChange";
import { EXPORT_API_PATH, MODULE_LABEL, moveStepApiPath, retireStepApiPath, saveText } from "./modelsActions";
import { dayWords } from "./providerWords";
import { RungEditor } from "./RungEditor";
import {
  ADD_A_GOLDEN_QUESTION,
  HELD_UNTIL_A_GOLDEN_QUESTION,
  KEEP_STEP,
  matrixLines,
  MOVE_STEP,
  moveConsequence,
  moveQuestion,
  RETIRE_STEP,
  retireConsequence,
  retireQuestion,
} from "./routingWords";

export { FAILOVER_MATRIX } from "./FailoverMatrixCard";

export const ROUTING_HEADING = "Routing";
export const LOADING_MATRIX = "Loading the failover matrix.";
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

/** Takes the reader to the golden question's first field, where the next one is added. */
function goToGoldenQuestion(): void {
  const field = document.getElementById(GOLDEN_QUESTION_FIELD);
  field?.scrollIntoView({ block: "center" });
  field?.focus();
}

/** The one line said before anybody tries a change that would be held for want of a golden question. */
export function GoldenFirst() {
  return (
    <p data-slot="golden-first" className="m-0 flex flex-wrap items-baseline gap-x-2 text-[13px] text-body">
      <span>{HELD_UNTIL_A_GOLDEN_QUESTION}</span>
      <Button variant="link" className="h-auto min-h-11 p-0 text-[13px] text-acc-text sm:min-h-0" onClick={goToGoldenQuestion}>
        {ADD_A_GOLDEN_QUESTION}
      </Button>
    </p>
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
  const navigate = useNavigate();
  // A counter, so two changes in a row ask again twice. Never drawn.
  const [version, setVersion] = useState(0);
  const listing = useListing<RungRow>(MATRIX_API_PATH, { version, pageSize: CHAIN_PAGE_SIZE });
  const plan = useResource<unknown>(PROVIDERS_API_PATH, version);
  const page = useMemo(() => readMatrixPage(listing.body), [listing.body]);
  const body = useMemo(() => readProviders(plan.data), [plan.data]);
  const editable = page.editable;
  const changes = useResource<unknown>(editable ? CHANGES_API_PATH : null, version);
  const golden = useResource<unknown>(editable ? GOLDEN_API_PATH : null, version);
  const [decided, setDecided] = useState<ChangeRow | null>(null);
  const [pending, setPending] = useState<StepAsk | null>(null);
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
    (asked: StepAsk) => {
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

  let state;
  if (listing.failure !== null) {
    state = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    state = <LoadingState label={LOADING_MATRIX} />;
  }

  return (
    <div data-slot="routing-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: MODULE_LABEL }, { label: ROUTING_HEADING }]}
        title={ROUTING_HEADING}
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
          <Note kind="done">{`${changeWords(decided.kind)}: applied. The next question uses it.`}</Note>
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
      {editable && goldenCount === 0 && decided === null ? <GoldenFirst /> : null}

      {adding && editable ? (
        <AddStep
          providers={body?.providers ?? []}
          plan={body?.rungs ?? []}
          goldenCount={goldenCount}
          onDecided={onDecided}
          onClose={() => {
            setAdding(false);
          }}
        />
      ) : null}

      <FailoverMatrixCard
        lines={lines}
        openId={rungId}
        state={state}
        acts={
          editable
            ? {
                open: (line) => {
                  if (line.rung !== null) {
                    void navigate(rungAddress(line.rung.id));
                  }
                },
                ask: (asked) => {
                  setFailure(null);
                  setPending(asked);
                },
              }
            : undefined
        }
        footer={
          listing.moreFailure === null && !listing.more && !page.truncated ? undefined : (
            <>
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
            </>
          )
        }
      />

      {open !== null && editable ? (
        <RungEditor
          key={open.key}
          line={open}
          onDecided={(change) => {
            onDecided(change);
            void navigate(MATRIX_PATH);
          }}
          onClose={() => {
            void navigate(MATRIX_PATH);
          }}
        />
      ) : null}
      {rungId !== undefined && open === null && !listing.busy && listing.failure === null ? (
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
