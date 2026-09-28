/**
 * The Overview, the first screen an administrator sees: is the install healthy, and is anything
 * waiting on me? `docs/screens.html` SCREEN 1 is the design, built on the shared page kit.
 *
 * **Five blocks, each from the route that owns it** (see `overviewQuery.ts`): a health strip, the
 * last week's figures, Needs you, recent activity and quick actions. A block whose route answers
 * 404 is not this reader's and is left out, exactly as its screen is left out of their menu; a 404
 * that says a second factor is needed, and every other failure, is drawn in the API's own words
 * with its reference, because leaving those out would read as nothing wrong.
 *
 * **Nothing is drawn as nought unless something counted it.** A figure the API lists as not
 * recorded reads "Not recorded yet" with the API's reason on hover and focus, and a figure nothing
 * sent is not drawn at all. A queue the reader may not act on was never sent, so it is absent and
 * never "0". See `kit/KpiStrip.tsx` and `brain.console.needs_you`.
 *
 * **What is stopped is said in words, and a stop nobody can read is a stop.** Each halt in force
 * reads "Stopped: agent X since 14:05"; none reads "Nothing stopped"; and when the API could not read
 * the halts (`halts_known` false) the strip says "Stop state unknown, treated as stopped", because
 * admission refuses everything then and "Nothing stopped" would be the reassuring answer nobody
 * measured. A halt on one person never names them: their id belongs in Advanced.
 *
 * **Identifiers are in Advanced and nowhere else.** The audit feed says what was done and to what
 * kind of thing, and links to the entry's history, whose address carries the identifier; the
 * signed-in person's principal and entitlement digest are in the Advanced section at the foot.
 *
 * **What was removed from the old Overview, and why.** The "You" card's nine rows (principal id,
 * entitlement digest, employment, assurance, channel, withheld verbs, second factor, department,
 * name): identifiers belong in Advanced and the sign-in banner already says what a person can act
 * on. The install card's commit hash and its "decides readiness" and "reported only" chips on every
 * part, which described the readiness probe rather than the install. The lede that explained the
 * page was "according to the API". The readiness parts are kept, as one line of plain words.
 *
 * Task ids: M27.15.17, M27.16.1, M31.4.1
 */

import { ArrowUpRight, BookPlus, KeyRound, MessageSquare, Plug } from "lucide-react";
import { Fragment, useId, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ApiFailure } from "../../api/errors";
import type { Resource } from "../../api/useResource";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  PageHeader,
  SectionCard,
  StatCard,
  StatsStrip,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../components/ui/tooltip";
import { NAVIGATION_API_PATH, readNavigation } from "../../layout/navigationQuery";
import { cn } from "../../lib/utils";
import { historyAddress } from "../auditQuery";
import { countWords, whenWords } from "../agents/agentStats";
import {
  ACTIVITY_API_PATH,
  AGENTS_API_PATH,
  AUDIT_PATH,
  FIGURES_API_PATH,
  HEALTH_FIGURES,
  NOTHING_STOPPED,
  STOP_STATE_UNKNOWN,
  OVERVIEW_API_PATH,
  QUEUE_PAGES,
  SOURCES_API_PATH,
  activeAgents,
  activityWords,
  basisWords,
  connectedSources,
  haltWords,
  partIsReady,
  partWords,
  queueLabel,
  readFigures,
  readOverview,
  readinessWords,
  recentActivity,
  waitingWords,
  type Counted,
  type Halt,
  type NotRecorded,
  type OverviewAnswer,
} from "./overviewQuery";

export const OVERVIEW_HEADING = "Overview";
export const OVERVIEW_LEDE = "Is the install healthy, and is anything waiting on you?";
/** The menu group the page sits in, which is the whole of its trail. */
export const HOME_CRUMB = "Home";

export const HEALTH_LABEL = "This install";
export const READINESS_LABEL = "Readiness";
export const WORKER_LABEL = "Worker last seen";
export const WORKER_SUB = "newest scheduled run you can see";
export const HALTS_LABEL = "Stopped";

export const FIGURES_LABEL = "Last 7 days";
export const ANSWERED_LABEL = "Questions answered";
export const NOTHING_RETURNED_LABEL = "Refused or abstained";
export const NOTHING_RETURNED_SUB = "refused or nothing found, as one figure";
export const AGENTS_LABEL = "Active agents";
export const SOURCES_LABEL = "Connected sources";
export const COST_LABEL = "Cost";
export const YOU_CAN_SEE = "that you can see";

export const NEEDS_YOU = "Needs you";
export const NEEDS_YOU_LEDE = "Each queue you may act on, with how much is waiting in it.";
export const NOTHING_WAITING = "Nothing is waiting on you.";
export const NOTHING_WAITING_MORE = "A queue appears here when there is one you may act on.";
export const LOADING_QUEUES = "Loading what is waiting on you.";
export const NOT_COUNTED = "Not counted yet";
export const OPEN = "Open";

export const ACTIVITY = "Recent activity";
export const ACTIVITY_LEDE = "The newest changes you may read on the audit log.";
export const NO_ACTIVITY = "No activity to show yet.";
export const NO_ACTIVITY_MORE = "Changes to people, grants, agents and settings appear here as they happen.";
export const LOADING_ACTIVITY = "Loading the newest activity.";
export const FULL_AUDIT = "Full audit log";

export const QUICK_ACTIONS = "Quick actions";
export const SIGNED_IN_AS = "Signed in as";

/** The quick actions, each shown only when its page is in this reader's menu. Ask always is. */
export const ACTIONS: readonly { readonly label: string; readonly to: string; readonly icon: ReactNode; readonly always?: boolean }[] = [
  { label: "Add a document", to: "/library", icon: <BookPlus aria-hidden /> },
  { label: "Connect a source", to: "/connectors", icon: <Plug aria-hidden /> },
  { label: "Invite or grant access", to: "/people", icon: <KeyRound aria-hidden /> },
  { label: "Open Ask", to: "/ask", icon: <MessageSquare aria-hidden />, always: true },
];

/** A block whose route answered a plain 404 is not this reader's, and is left out. */
export function isNotTheirs(failure: ApiFailure | null): boolean {
  return failure !== null && failure.status === 404 && !failure.secondFactorNeeded;
}

/** A link at the right of a card's heading. */
function CardLink({ to, children }: { readonly to: string; readonly children: ReactNode }) {
  return (
    <Link to={to} className="inline-flex min-h-11 items-center gap-1 text-[12px] text-acc-text underline-offset-4 hover:underline sm:min-h-0">
      {children} <ArrowUpRight aria-hidden className="size-3" />
    </Link>
  );
}

/** "Not counted yet", with the API's reason on hover and on focus. */
function NotCounted({ why }: { readonly why: string }) {
  const describedBy = useId();
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            tabIndex={0}
            aria-describedby={describedBy}
            className="cursor-help text-[12.5px] text-dim underline decoration-dotted underline-offset-4 outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
          >
            {NOT_COUNTED}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[18rem] text-[12px] leading-snug">
          {why}
        </TooltipContent>
      </Tooltip>
      <span id={describedBy} className="sr-only">
        {why}
      </span>
    </TooltipProvider>
  );
}

function whyOf(rows: readonly NotRecorded[], figure: string): string | undefined {
  return rows.find((one) => one.figure === figure)?.why;
}

// ------------------------------------------------------------------------------ the health strip

/**
 * What is stopped, in words: nothing, each halt in force, or that nobody can tell. The last is drawn
 * as a stop, because admission refuses everything while the halts cannot be read.
 */
function HaltsValue({ halts, known }: { readonly halts: readonly Halt[]; readonly known: boolean }) {
  if (!known) {
    return (
      <span data-halts="unknown" className="text-[14px] leading-snug font-medium tracking-normal text-crit">
        {STOP_STATE_UNKNOWN}
      </span>
    );
  }
  if (halts.length === 0) {
    return <span data-halts="none">{NOTHING_STOPPED}</span>;
  }
  return (
    <ul data-halts="stopped" className="m-0 flex list-none flex-col gap-1 p-0 text-[14px] leading-snug font-medium tracking-normal text-crit">
      {halts.map((halt) => (
        <li key={`${halt.scope} ${halt.target} ${halt.since}`} className="min-w-0 [overflow-wrap:anywhere]">
          {haltWords(halt)}
        </li>
      ))}
    </ul>
  );
}

function HealthStrip({ overview }: { readonly overview: Resource<unknown> }) {
  if (isNotTheirs(overview.failure)) {
    return null;
  }
  const read = overview.data === null ? null : readOverview(overview.data);
  // The halts card when the API says what is stopped; otherwise whatever it names as not recorded.
  const haltsKnown = read?.haltsKnown;
  const health = Object.entries(HEALTH_FIGURES).filter(
    ([figure]) => !(figure === "halts" && haltsKnown !== undefined) && read?.healthNotRecorded.some((one) => one.figure === figure),
  );
  const cards = 2 + (haltsKnown === undefined ? 0 : 1) + health.length;
  return (
    <section aria-label={HEALTH_LABEL} className="flex min-w-0 flex-col gap-2">
      <StatsStrip label={HEALTH_LABEL} busy={overview.busy} failure={overview.failure} count={cards}>
        <StatCard label={READINESS_LABEL} value={read === null ? undefined : readinessWords(read.status)} />
        {read === null || haltsKnown === undefined ? null : (
          <StatCard label={HALTS_LABEL} value={<HaltsValue halts={read.halts} known={haltsKnown} />} />
        )}
        <StatCard label={WORKER_LABEL} value={whenWords(read?.workerLastSeen)} sub={WORKER_SUB} />
        {health.map(([figure, label]) => (
          <StatCard key={figure} label={label} unrecordedWhy={whyOf(read?.healthNotRecorded ?? [], figure)} />
        ))}
      </StatsStrip>
      {read === null || read.parts.length === 0 ? null : (
        <ul aria-label="Parts of this install" className="m-0 flex list-none flex-wrap gap-1.5 p-0">
          {read.parts.map((part) => (
            <li
              key={part.name}
              data-ready={partIsReady(part) ? "" : undefined}
              className={cn(
                "inline-flex min-h-7 max-w-full items-center rounded-full border px-2.5 text-[12px] [overflow-wrap:anywhere]",
                partIsReady(part) ? "border-line bg-panel text-ink" : "border-dashed border-line bg-transparent text-dim",
              )}
            >
              {partWords(part)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ------------------------------------------------------------------------------- the figure row

interface Card {
  readonly key: string;
  readonly node: ReactNode;
}

function countedWords(counted: Counted): string | undefined {
  const figure = countWords(counted.value);
  return counted.atLeast && figure !== undefined ? `${figure}+` : figure;
}

function FigureRow({
  figures,
  agents,
  sources,
}: {
  readonly figures: Resource<unknown>;
  readonly agents: Resource<unknown>;
  readonly sources: Resource<unknown>;
}) {
  const busy = figures.busy || agents.busy || sources.busy;
  const failure = isNotTheirs(figures.failure) ? null : figures.failure;
  const read = figures.data === null ? null : readFigures(figures.data);
  const agentCount = agents.data === null ? undefined : activeAgents(agents.data);
  const sourceCount = sources.data === null ? undefined : connectedSources(sources.data);

  const cards: Card[] = [];
  if (read !== null) {
    const whose = basisWords(read.basis);
    cards.push({ key: "answered", node: <StatCard label={ANSWERED_LABEL} value={countWords(read.answered)} sub={whose} /> });
    cards.push({
      key: "nothing",
      node: <StatCard label={NOTHING_RETURNED_LABEL} value={countWords(read.nothingReturned)} sub={NOTHING_RETURNED_SUB} />,
    });
  }
  if (agentCount !== undefined) {
    cards.push({
      key: "agents",
      node: <StatCard label={AGENTS_LABEL} value={countedWords(agentCount)} sub={YOU_CAN_SEE} />,
    });
  }
  if (sourceCount !== undefined) {
    cards.push({
      key: "sources",
      node:
        "unread" in sourceCount ? (
          <StatCard label={SOURCES_LABEL} unrecordedWhy={sourceCount.unread} />
        ) : (
          <StatCard label={SOURCES_LABEL} value={countedWords(sourceCount)} sub={YOU_CAN_SEE} />
        ),
    });
  }
  const cost = read === null ? undefined : whyOf(read.notRecorded, "cost");
  if (cost !== undefined) {
    cards.push({ key: "cost", node: <StatCard label={COST_LABEL} unrecordedWhy={cost} /> });
  }

  if (!busy && failure === null && cards.length === 0) {
    return null;
  }
  return (
    <section aria-label={FIGURES_LABEL} className="flex min-w-0 flex-col gap-2">
      <h2 className="m-0 text-sm font-semibold text-ink">{FIGURES_LABEL}</h2>
      <StatsStrip label={FIGURES_LABEL} busy={busy} failure={failure} count={cards.length}>
        {cards.map((one) => (
          <Fragment key={one.key}>{one.node}</Fragment>
        ))}
      </StatsStrip>
    </section>
  );
}

// ---------------------------------------------------------------------------------- Needs you

function QueueLine({ label, figure, to }: { readonly label: string; readonly figure: ReactNode; readonly to?: string | undefined }) {
  return (
    <li className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-line py-2.5 last:border-b-0">
      <span className="min-w-0 text-[13px] text-ink [overflow-wrap:anywhere]">{label}</span>
      <span className="flex items-center gap-3">
        {figure}
        {to === undefined ? null : (
          <Link to={to} className="inline-flex min-h-11 items-center text-[12px] text-acc-text underline-offset-4 hover:underline sm:min-h-0">
            {OPEN}
            <span className="sr-only"> {label}</span>
          </Link>
        )}
      </span>
    </li>
  );
}

function NeedsYou({ overview }: { readonly overview: Resource<unknown> }) {
  if (isNotTheirs(overview.failure)) {
    return null;
  }
  const read: OverviewAnswer | null = overview.data === null ? null : readOverview(overview.data);
  let body: ReactNode;
  if (overview.failure !== null) {
    body = <FailureState failure={overview.failure} />;
  } else if (overview.busy) {
    body = <LoadingState label={LOADING_QUEUES} rows={3} />;
  } else if (read === null) {
    // A body that is not an overview claims nothing, so nothing is drawn in its place.
    return null;
  } else if (read.needsYou.length === 0 && read.uncounted.length === 0) {
    body = <EmptyState title={NOTHING_WAITING} description={NOTHING_WAITING_MORE} />;
  } else {
    body = (
      <ul aria-label={NEEDS_YOU} className="m-0 flex list-none flex-col p-0">
        {read.needsYou.map((line) => (
          <QueueLine
            key={line.queue}
            label={queueLabel(line.queue)}
            figure={<span className="text-[15px] font-semibold text-ink tabular-nums">{waitingWords(line)}</span>}
            to={line.opens}
          />
        ))}
        {read.uncounted.map((one) => (
          <QueueLine key={one.figure} label={queueLabel(one.figure)} figure={<NotCounted why={one.why} />} to={QUEUE_PAGES[one.figure]} />
        ))}
      </ul>
    );
  }
  return (
    <SectionCard title={NEEDS_YOU} lede={NEEDS_YOU_LEDE}>
      {body}
    </SectionCard>
  );
}

// -------------------------------------------------------------------------------- activity

function Activity({ audit }: { readonly audit: Resource<unknown> }) {
  if (isNotTheirs(audit.failure)) {
    return null;
  }
  const rows = audit.data === null ? [] : recentActivity(audit.data);
  let body: ReactNode;
  if (audit.failure !== null) {
    body = <FailureState failure={audit.failure} />;
  } else if (audit.busy) {
    body = <LoadingState label={LOADING_ACTIVITY} rows={3} />;
  } else if (rows.length === 0) {
    body = <EmptyState title={NO_ACTIVITY} description={NO_ACTIVITY_MORE} />;
  } else {
    body = (
      <ol aria-label={ACTIVITY} className="m-0 flex list-none flex-col p-0">
        {rows.map((row) => (
          <li
            key={`${row.at}-${row.action}-${row.subject_kind}-${row.subject_id}-${row.actor_id}`}
            className="[display:grid] grid-cols-[4.5rem_minmax(0,1fr)] items-baseline gap-3 border-b border-line py-2 text-[13px] last:border-b-0 sm:grid-cols-[7.5rem_minmax(0,1fr)]"
          >
            <span className="font-mono text-[11px] text-dim">{whenWords(row.at)}</span>
            <Link
              to={historyAddress(new URLSearchParams(), row.subject_kind, row.subject_id)}
              className="min-w-0 text-ink underline-offset-4 [overflow-wrap:anywhere] hover:underline"
            >
              {activityWords(row)}
            </Link>
          </li>
        ))}
      </ol>
    );
  }
  return (
    <SectionCard title={ACTIVITY} lede={ACTIVITY_LEDE} action={<CardLink to={AUDIT_PATH}>{FULL_AUDIT}</CardLink>}>
      {body}
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------- quick actions

function QuickActions() {
  const navigation = useResource<unknown>(NAVIGATION_API_PATH);
  const given = navigation.data === null ? null : readNavigation(navigation.data);
  const reachable = new Set(
    (given?.groups ?? []).flatMap((group) => group.sections.flatMap((section) => [section.to, ...section.tabs.map((tab) => tab.to)])),
  );
  const shown = ACTIONS.filter((one) => one.always === true || reachable.has(one.to));
  return (
    <SectionCard title={QUICK_ACTIONS}>
      <ul className="m-0 [display:grid] list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2">
        {shown.map((one) => (
          <li key={one.to} className="min-w-0">
            <Button asChild variant="outline" className="min-h-11 w-full justify-start text-ink no-underline sm:min-h-9">
              <Link to={one.to}>
                {one.icon}
                {one.label}
              </Link>
            </Button>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}

// ------------------------------------------------------------------------------- the signed-in

interface Caller {
  readonly name?: string;
  readonly principal?: string;
  readonly digest?: string;
}

function callerOf(payload: unknown): Caller | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Readonly<Record<string, unknown>>;
  const said = (key: string): string | undefined => {
    const value = body[key];
    return typeof value === "string" && value !== "" ? value : undefined;
  };
  const name = said("display_name");
  const principal = said("principal_id");
  const digest = said("ent_hash");
  return {
    ...(name === undefined ? {} : { name }),
    ...(principal === undefined ? {} : { principal }),
    ...(digest === undefined ? {} : { digest }),
  };
}

function SignedIn() {
  const me = useResource<unknown>("/me");
  const caller = me.data === null ? null : callerOf(me.data);
  if (caller === null || caller.principal === undefined) {
    return null;
  }
  return (
    <Advanced>
      <FactList>
        {caller.name === undefined ? null : <Fact label={SIGNED_IN_AS}>{caller.name}</Fact>}
        <Fact label="Principal">
          <code className="font-mono text-[12px]">{caller.principal}</code>
        </Fact>
        {caller.digest === undefined ? null : (
          <Fact label="Entitlement digest">
            <code className="font-mono text-[12px]">{caller.digest}</code>
          </Fact>
        )}
      </FactList>
    </Advanced>
  );
}

// ------------------------------------------------------------------------------------ the page

export function OverviewPage() {
  const overview = useResource<unknown>(OVERVIEW_API_PATH);
  const figures = useResource<unknown>(FIGURES_API_PATH);
  const agents = useResource<unknown>(AGENTS_API_PATH);
  const sources = useResource<unknown>(SOURCES_API_PATH);
  const audit = useResource<unknown>(ACTIVITY_API_PATH);

  return (
    <div data-slot="overview-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: HOME_CRUMB }]} title={OVERVIEW_HEADING} lede={OVERVIEW_LEDE} />
      <HealthStrip overview={overview} />
      <FigureRow figures={figures} agents={agents} sources={sources} />
      <div
        className={cn(
          "[display:grid] min-w-0 items-start gap-4",
          isNotTheirs(overview.failure) ? null : "xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]",
        )}
      >
        <NeedsYou overview={overview} />
        <QuickActions />
      </div>
      <Activity audit={audit} />
      <SignedIn />
    </div>
  );
}
