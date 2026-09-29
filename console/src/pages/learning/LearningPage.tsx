/**
 * Learning on the shared page kit: what the system has learnt, one tier at a time, each learning
 * opened in a drawer, and the one act the API offers, undo, confirmed in the API's own words.
 *
 * **One view per tier, never one list with a tier column.** A change that has already happened and
 * a proposal waiting for a person sorted into one list sit side by side with controls that mean
 * different things, which `learningQuery.THREE_TIERS_ARE_THREE_TABLES` argues. So Applied, In shadow
 * and Waiting are views at addresses of their own, and About says what each tier is.
 *
 * **Undo is drawn only on a row the API offers it on** (`UNDO_IS_ASKED_OF_THE_SERVER_ROW_BY_ROW`),
 * and it is sent only from a confirmation whose consequence is the sentence the API serves for what
 * that undo writes. Promote and Decide have no route, so each is `kit/UnavailableAction` with its
 * reason (`learningActions.ts`); nothing is drawn that pretends to work.
 *
 * **Waiting is left out of the switch for a reader who may not be told where gated changes went.**
 * The API sends it as null, not as an empty list, and a view that reader may not open is not in the
 * switch (`kit/DetailPage`'s rule). Opened by its address anyway, it says so in one sentence.
 *
 * **Figures count the rows this reader was sent**, which the API narrowed to what they may recall
 * before sending; none is a count of anything they were not shown.
 *
 * Removed from the old screen: the memory ids in every table (each learning's reference is in its
 * drawer's Advanced section), the two "not recorded on this install" figures and the digest note,
 * the paragraph explaining where undo is offered, the three stacked tables on one page, and the
 * sentence under the figures.
 *
 * Task ids: M27.7.21, M27.16.1, M16.6.8, M16.5.4
 */

import { BookOpenCheck, CircleSlash, Hourglass, Info, TriangleAlert, Undo2 } from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  ConfirmDialog,
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
  PageHeader,
  RESET_LABEL,
  SectionCard,
  StatCard,
  UnavailableAction,
  ViewSwitch,
  type DetailView,
  type EntityColumn,
} from "../../components/kit";
import { NOTHING_MATCHES } from "../../components/ListControls";
import { Button } from "../../components/ui/button";
import { cn } from "../../lib/utils";
import { dayWords, whenWords } from "../access/formParts";
import {
  LEARNING_API_PATH,
  LEARNING_SETTINGS,
  LEARNING_VIEWS,
  LEARNING_VIEW_LABELS,
  RECENT_DAYS,
  TIER_WORDS,
  UNDO_API_PATH,
  consideredSentence,
  learnedRecently,
  learningAddress,
  readLearningPage,
  readUndone,
  undoBody,
  type LearningPage as Review,
  type LearningView,
  type TierOne,
  type TierThree,
  type TierTwo,
} from "../learningQuery";
import { LimitSettings } from "../operations/LimitSettings";
import { Narrowing } from "../requirement-checks/Narrowing";
import { UNAVAILABLE, changeWords, undoWritesWords } from "./learningActions";

export const LEARNING_HEADING = "Learning";
export const LEARNING_LEDE =
  "Learning that narrows, personalises or re-ranks applies by itself; learning that widens, publishes or changes behaviour waits for a person.";
export const LOADING_LEARNING = "Loading what the system has learnt.";
export const VIEWS_LABEL = "Learning views";
export const UNDO_LABEL = "Undo";
export const KEEP_IT = "Keep it";
export const DETAILS_LABEL = "Details";
export const NOT_UNDONE = "The learning was not undone";
export const APPLIED_WORD = "Applied";
export const UNDONE = "Undone";
export const READY_WORD = "Ready to promote";
export const PROVING_WORD = "Proving";
export const WAITING_WORD = "Waiting";
export const NOTHING_IN_TIER = "Nothing in this tier";
export const TIER_THREE_WITHHELD =
  "Where gated changes were routed is shown to a reader who holds the Scopes and departments screen for the whole company, because each one names the department that decides it.";
export const NOTIFY_DO_NOT_ASK =
  "Tier one lands silently and can be undone. Nobody approves every preference change; they skim and reverse what looks wrong. Forgetting something wrong never needs permission, or the system stays wrong while it waits.";
export const EVERY_KIND = "Every kind";
export const EVERY_STATE = "Every state";

const VIEW_ICONS: Readonly<Record<LearningView, ReactNode>> = {
  applied: <BookOpenCheck aria-hidden />,
  shadow: <CircleSlash aria-hidden />,
  waiting: <Hourglass aria-hidden />,
  about: <Info aria-hidden />,
};

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em] whitespace-nowrap";

/** Each state a learning can be in, in words and in the design's pill colours. */
const STATES = {
  applied: { word: APPLIED_WORD, classes: "bg-ok-wash text-ok" },
  undone: { word: UNDONE, classes: "bg-sunk text-dim" },
  ready: { word: READY_WORD, classes: "bg-ok-wash text-ok" },
  proving: { word: PROVING_WORD, classes: "bg-warn-wash text-warn" },
  waiting: { word: WAITING_WORD, classes: "bg-warn-wash text-warn" },
} as const;

function StatePill({ state }: { readonly state: keyof typeof STATES }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, STATES[state].classes)}>
      {STATES[state].word}
    </span>
  );
}

/** Which learning is open in the drawer, by tier. */
type Opened =
  | { readonly tier: 1; readonly row: TierOne }
  | { readonly tier: 2; readonly row: TierTwo }
  | { readonly tier: 3; readonly row: TierThree };

/** The distinct values of one field over the rows sent, for a narrowing's choices. */
function valuesOf<Row>(rows: readonly Row[], read: (row: Row) => string): readonly string[] {
  return [...new Set(rows.map(read))].sort((a, b) => a.localeCompare(b));
}

function NothingMatches({ onReset }: { readonly onReset: () => void }) {
  return (
    <EmptyState
      title={NOTHING_MATCHES}
      description="Change the choices above or clear them."
      action={
        <Button variant="outline" onClick={onReset}>
          {RESET_LABEL}
        </Button>
      }
    />
  );
}

function Applied({
  review,
  onOpen,
  onUndo,
  busy,
}: {
  readonly review: Review;
  readonly onOpen: (opened: Opened) => void;
  readonly onUndo: (row: TierOne) => void;
  readonly busy: boolean;
}) {
  const [kind, setKind] = useState("");
  const [state, setState] = useState("");
  const rows = review.tierOne.filter(
    (row) => (kind === "" || row.change === kind) && (state === "" || (state === "applied") === row.in_effect),
  );
  const columns: readonly EntityColumn<TierOne>[] = [
    {
      id: "change",
      header: "What it learned",
      hideable: false,
      cell: (row) => (
        <button
          type="button"
          className="text-left font-medium text-ink underline-offset-4 hover:underline"
          onClick={() => {
            onOpen({ tier: 1, row });
          }}
        >
          {changeWords(row.change)}
        </button>
      ),
      text: (row) => changeWords(row.change),
    },
    { id: "learned", header: "Learned", cell: (row) => dayWords(row.learned_at), text: (row) => row.learned_at },
    {
      id: "state",
      header: "State",
      cell: (row) => <StatePill state={row.in_effect ? "applied" : "undone"} />,
      text: (row) => (row.in_effect ? APPLIED_WORD : UNDONE),
    },
    { id: "undo", header: "Undoing it", cell: (row) => undoWritesWords(row.control_writes), text: (row) => undoWritesWords(row.control_writes) },
  ];
  return (
    <SectionCard title="Applied automatically" lede="Each of these applied by itself and can be undone.">
      {review.tierOne.length === 0 ? (
        <EmptyState title={NOTHING_IN_TIER} description="A preference, a correction or a re-ranking the system learns appears here once it applies." icon={<BookOpenCheck aria-hidden />} />
      ) : (
        <div className="flex min-w-0 flex-col gap-3">
          <Narrowing
            label="Narrow the applied learnings"
            narrows={[
              {
                label: "Kind",
                everything: EVERY_KIND,
                value: kind,
                options: valuesOf(review.tierOne, (row) => row.change).map((one) => ({ value: one, label: changeWords(one) })),
                onChange: setKind,
              },
              {
                label: "State",
                everything: EVERY_STATE,
                value: state,
                options: [
                  { value: "applied", label: APPLIED_WORD },
                  { value: "undone", label: UNDONE },
                ],
                onChange: setState,
              },
            ]}
            onReset={() => {
              setKind("");
              setState("");
            }}
          />
          {rows.length === 0 ? (
            <NothingMatches
              onReset={() => {
                setKind("");
                setState("");
              }}
            />
          ) : (
            <EntityTable
              caption="Learnings applied automatically"
              columns={columns}
              rows={rows}
              rowId={(row) => `${row.memory_id} ${row.learned_at}`}
              rowLabel={(row) => changeWords(row.change)}
              exportName="learning-applied"
              rowActions={(row) =>
                row.undo_offered && row.in_effect ? (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    aria-label={`${UNDO_LABEL} the ${changeWords(row.change).toLowerCase()} learned ${dayWords(row.learned_at)}`}
                    onClick={() => {
                      onUndo(row);
                    }}
                  >
                    <Undo2 aria-hidden /> {UNDO_LABEL}
                  </Button>
                ) : null
              }
            />
          )}
        </div>
      )}
    </SectionCard>
  );
}

function Shadow({ review, onOpen }: { readonly review: Review; readonly onOpen: (opened: Opened) => void }) {
  const [kind, setKind] = useState("");
  const [state, setState] = useState("");
  const rows = review.tierTwo.filter(
    (row) => (kind === "" || row.change === kind) && (state === "" || (state === "ready") === row.promote_ready),
  );
  const columns: readonly EntityColumn<TierTwo>[] = [
    {
      id: "change",
      header: "What it learned",
      hideable: false,
      cell: (row) => (
        <button
          type="button"
          className="text-left font-medium text-ink underline-offset-4 hover:underline"
          onClick={() => {
            onOpen({ tier: 2, row });
          }}
        >
          {changeWords(row.change)}
        </button>
      ),
      text: (row) => changeWords(row.change),
    },
    { id: "learned", header: "Learned", cell: (row) => dayWords(row.learned_at), text: (row) => row.learned_at },
    {
      id: "evidence",
      header: "Evidence",
      className: "whitespace-normal [overflow-wrap:anywhere]",
      cell: (row) => <span className="[overflow-wrap:anywhere]">{row.evidence.map(changeWords).join(", ")}</span>,
      text: (row) => row.evidence.join(", "),
    },
    {
      id: "state",
      header: "State",
      cell: (row) => <StatePill state={row.promote_ready ? "ready" : "proving"} />,
      text: (row) => (row.promote_ready ? READY_WORD : PROVING_WORD),
    },
  ];
  return (
    <SectionCard
      title="In shadow"
      lede="Rules proving themselves before they apply."
      action={<UnavailableAction label={UNAVAILABLE.promote.label} text={UNAVAILABLE.promote.label} reason={UNAVAILABLE.promote.reason} />}
    >
      {review.tierTwo.length === 0 ? (
        <EmptyState title={NOTHING_IN_TIER} description="A rule the system proposes from repeated evidence appears here while it proves itself." icon={<CircleSlash aria-hidden />} />
      ) : (
        <div className="flex min-w-0 flex-col gap-3">
          <Narrowing
            label="Narrow the rules in shadow"
            narrows={[
              {
                label: "Kind",
                everything: EVERY_KIND,
                value: kind,
                options: valuesOf(review.tierTwo, (row) => row.change).map((one) => ({ value: one, label: changeWords(one) })),
                onChange: setKind,
              },
              {
                label: "State",
                everything: EVERY_STATE,
                value: state,
                options: [
                  { value: "ready", label: READY_WORD },
                  { value: "proving", label: PROVING_WORD },
                ],
                onChange: setState,
              },
            ]}
            onReset={() => {
              setKind("");
              setState("");
            }}
          />
          {rows.length === 0 ? (
            <NothingMatches
              onReset={() => {
                setKind("");
                setState("");
              }}
            />
          ) : (
            <EntityTable
              caption="Rules in shadow"
              columns={columns}
              rows={rows}
              rowId={(row) => `${row.memory_id} ${row.learned_at}`}
              rowLabel={(row) => changeWords(row.change)}
              exportName="learning-shadow"
            />
          )}
        </div>
      )}
    </SectionCard>
  );
}

function Waiting({ review, onOpen }: { readonly review: Review; readonly onOpen: (opened: Opened) => void }) {
  const [department, setDepartment] = useState("");
  if (review.tierThree === null) {
    return (
      <SectionCard title="Waiting on a person">
        <NotOffered>{TIER_THREE_WITHHELD}</NotOffered>
      </SectionCard>
    );
  }
  const waiting = review.tierThree;
  const rows = waiting.filter((row) => department === "" || row.department === department);
  const columns: readonly EntityColumn<TierThree>[] = [
    {
      id: "department",
      header: "Decided in",
      hideable: false,
      cell: (row) => (
        <button
          type="button"
          className="text-left font-medium text-ink underline-offset-4 [overflow-wrap:anywhere] hover:underline"
          onClick={() => {
            onOpen({ tier: 3, row });
          }}
        >
          {row.department}
        </button>
      ),
      text: (row) => row.department,
    },
    { id: "state", header: "State", cell: () => <StatePill state="waiting" />, text: () => WAITING_WORD },
  ];
  return (
    <SectionCard
      title="Waiting on a person"
      lede="Changes that would widen who sees what, routed to the department that decides each."
      action={<UnavailableAction label={UNAVAILABLE.decide.label} text={UNAVAILABLE.decide.label} reason={UNAVAILABLE.decide.reason} />}
    >
      {review.queueAlarm?.raised === true ? (
        <p role="alert" data-slot="queue-alarm" className="m-0 mb-3 flex items-start gap-2 rounded-md bg-warn-wash px-3 py-2 text-[13px] text-warn">
          <TriangleAlert aria-hidden className="mt-[2px] size-4 shrink-0" />
          <span className="min-w-0">{review.queueAlarm.says}</span>
        </p>
      ) : null}
      {waiting.length === 0 ? (
        <EmptyState title={NOTHING_IN_TIER} description="A learned change that would widen who sees what waits here for a person." icon={<Hourglass aria-hidden />} />
      ) : (
        <div className="flex min-w-0 flex-col gap-3">
          <Narrowing
            label="Narrow the waiting changes"
            narrows={[
              {
                label: "Department",
                everything: "Every department",
                value: department,
                options: valuesOf(waiting, (row) => row.department).map((one) => ({ value: one, label: one })),
                onChange: setDepartment,
              },
            ]}
            onReset={() => {
              setDepartment("");
            }}
          />
          {rows.length === 0 ? (
            <NothingMatches
              onReset={() => {
                setDepartment("");
              }}
            />
          ) : (
            <EntityTable
              caption="Gated changes and where they were routed"
              columns={columns}
              rows={rows}
              rowId={(row) => row.memory_id}
              rowLabel={(row) => row.department}
              exportName="learning-waiting"
            />
          )}
        </div>
      )}
    </SectionCard>
  );
}

function About({ review }: { readonly review: Review }) {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title="The four tiers" lede="What each tier may change, and who has to agree.">
        <FactList>
          {review.tiers.map((rule) => (
            <Fact key={rule.tier} label={`Tier ${String(rule.tier)}`}>
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="font-medium">{TIER_WORDS[rule.tier]?.what ?? ""}</span>
                <span className="text-dim">{TIER_WORDS[rule.tier]?.how ?? ""}</span>
                <span className="text-[12px] text-dim">{rule.changes.map(changeWords).join(", ")}</span>
              </span>
            </Fact>
          ))}
        </FactList>
      </SectionCard>
      <SectionCard title="Notify, do not ask" footer={<Note>{consideredSentence(review.considered)}</Note>}>
        <p className="m-0 text-[13px] text-body">{NOTIFY_DO_NOT_ASK}</p>
        <p className="m-0 mt-2 text-[13px]">
          What a learning says is read on <Link to="/memory" className="text-acc-text underline-offset-4 hover:underline">Memory</Link>, one person at a time.
        </p>
      </SectionCard>
      <LimitSettings screen={LEARNING_SETTINGS} />
    </div>
  );
}

function LearningDrawer({
  opened,
  review,
  onClose,
  onUndo,
}: {
  readonly opened: Opened;
  readonly review: Review;
  readonly onClose: () => void;
  readonly onUndo: (row: TierOne) => void;
}) {
  let facts: ReactNode;
  let title: string;
  let footer: ReactNode = undefined;
  if (opened.tier === 1) {
    const row = opened.row;
    title = changeWords(row.change);
    facts = (
      <>
        <Fact label="Tier">One: applied by itself</Fact>
        <Fact label="Learned">{whenWords(row.learned_at)}</Fact>
        <Fact label="State">{row.in_effect ? APPLIED_WORD : UNDONE}</Fact>
        <Fact label="Undoing it">{review.undoSays[row.control_writes] ?? undoWritesWords(row.control_writes)}</Fact>
      </>
    );
    footer =
      row.undo_offered && row.in_effect ? (
        <Button
          variant="outline"
          onClick={() => {
            onUndo(row);
          }}
        >
          <Undo2 aria-hidden /> {UNDO_LABEL}
        </Button>
      ) : undefined;
  } else if (opened.tier === 2) {
    const row = opened.row;
    title = changeWords(row.change);
    facts = (
      <>
        <Fact label="Tier">Two: proving itself in shadow</Fact>
        <Fact label="Learned">{whenWords(row.learned_at)}</Fact>
        <Fact label="Evidence">{row.evidence.map(changeWords).join(", ") || "None recorded"}</Fact>
        <Fact label="State">{row.promote_ready ? READY_WORD : PROVING_WORD}</Fact>
      </>
    );
  } else {
    const row = opened.row;
    title = "A gated change";
    facts = (
      <>
        <Fact label="Tier">Three: a person decides</Fact>
        <Fact label="Decided in">{row.department}</Fact>
        <Fact label="State">{WAITING_WORD}</Fact>
      </>
    );
  }
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      title={title}
      description="One learning, as the review sent it. What it says is read on Memory."
      footer={footer}
    >
      <div className="flex min-w-0 flex-col gap-4">
        <FactList>{facts}</FactList>
        <Advanced>
          <FactList>
            <Fact label="Memory reference">
              <code className="font-mono text-[12px]">{opened.row.memory_id}</code>
            </Fact>
            {opened.tier === 3 ? (
              <Fact label="Agent reference">
                <code className="font-mono text-[12px]">{opened.row.back_to}</code>
              </Fact>
            ) : null}
          </FactList>
        </Advanced>
      </div>
    </Drawer>
  );
}

function Figures({ review }: { readonly review: Review }) {
  const withheld = review.tierThree === null;
  return (
    <KpiStrip label="Learnings you may see" count={withheld ? 3 : 4}>
      <StatCard label={`Learned in ${String(RECENT_DAYS)} days`} value={String(learnedRecently(review))} sub="tiers one and two" />
      <StatCard label="Applied automatically" value={String(review.tierOne.length)} sub="each can be undone" />
      <StatCard label="In shadow" value={String(review.tierTwo.length)} sub="proving themselves" />
      {review.tierThree === null ? null : <StatCard label="Waiting on a person" value={String(review.tierThree.length)} sub="tier three" />}
    </KpiStrip>
  );
}

export function LearningPage({ view }: { readonly view: LearningView }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(LEARNING_API_PATH, version);
  const review = useMemo(() => (answer.data === null ? null : readLearningPage(answer.data)), [answer.data]);
  const [opened, setOpened] = useState<Opened | null>(null);
  const [undoing, setUndoing] = useState<TierOne | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState("");

  const undo = useCallback((row: TierOne) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(UNDO_API_PATH, { method: "POST", body: undoBody(row.memory_id) });
      setBusy(false);
      setUndoing(null);
      setOpened(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setSaid(readUndone(result.data).told);
      setVersion((count) => count + 1);
    })();
  }, []);
  const askToUndo = useCallback((row: TierOne) => {
    setFailure(null);
    setSaid("");
    setUndoing(row);
  }, []);

  let content: ReactNode;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (review === null) {
    content = <LoadingState label={LOADING_LEARNING} />;
  } else {
    const shown = LEARNING_VIEWS.filter((one) => one !== "waiting" || review.tierThree !== null);
    const views: DetailView[] = shown.map((one) => ({ key: one, label: LEARNING_VIEW_LABELS[one], to: learningAddress(one), icon: VIEW_ICONS[one] }));
    const consequence = undoing === null ? "" : (review.undoSays[undoing.control_writes] ?? "");
    content = (
      <>
        {review.staleness === null ? null : <Note>{review.staleness}</Note>}
        <Figures review={review} />
        <div>
          <ViewSwitch label={VIEWS_LABEL} views={views} current={view} />
        </div>
        {view === "applied" ? <Applied review={review} onOpen={setOpened} onUndo={askToUndo} busy={busy} /> : null}
        {view === "shadow" ? <Shadow review={review} onOpen={setOpened} /> : null}
        {view === "waiting" ? <Waiting review={review} onOpen={setOpened} /> : null}
        {view === "about" ? <About review={review} /> : null}
        {opened === null ? null : (
          <LearningDrawer
            opened={opened}
            review={review}
            onClose={() => {
              setOpened(null);
            }}
            onUndo={askToUndo}
          />
        )}
        <ConfirmDialog
          open={undoing !== null && consequence !== ""}
          question={undoing === null ? "" : `${UNDO_LABEL} the ${changeWords(undoing.change).toLowerCase()} learned ${dayWords(undoing.learned_at)}?`}
          consequence={consequence}
          confirmLabel={UNDO_LABEL}
          cancelLabel={KEEP_IT}
          busy={busy}
          onConfirm={() => {
            if (undoing !== null) {
              undo(undoing);
            }
          }}
          onCancel={() => {
            setUndoing(null);
          }}
        />
      </>
    );
  }

  return (
    <div data-slot="learning-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: LEARNING_HEADING }]} title={LEARNING_HEADING} lede={LEARNING_LEDE} />
      {said === "" ? null : (
        <p role="status" className="m-0 text-[13px] text-ok">
          {said}
        </p>
      )}
      {failure === null ? null : <FailureState failure={failure} title={NOT_UNDONE} />}
      {content}
    </div>
  );
}
