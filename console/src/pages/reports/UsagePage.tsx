/**
 * Usage, the first view of Usage and cost: how much people ask, in which departments, who asks
 * most, and the tokens their questions' model calls consumed.
 *
 * **Every figure is the API's or a count of lines it sent.** The questions figure is the API's
 * total, never a sum of the tables under it; the token totals are each breakdown's own; the people
 * figure is the number of person lines this reader was sent. See `usageQuery.ts`.
 *
 * **Nothing is drawn as nought unless something counted it.** A measure the API names as not
 * measured reads "Not recorded yet" with the reason on hover and focus, and a table the reader is
 * not offered is not drawn at all, with no heading saying it is missing.
 *
 * **People are named.** A person line carries the directory's name, and the tokens by person are
 * named from the same lines; a reference is in the export and nowhere on the page.
 *
 * What was removed from the old page: the person search, order and pager over the lines already
 * held (the list is now the ten who ask most, with the rest one press away and in the export), the
 * lede sending cost to another screen, the "Find a person by their reference" box, and a paragraph
 * per measure the ledger did not fill. Cost is its own tab, Spend.
 *
 * Task ids: M27.7.14, M27.16.1
 */

import { useState } from "react";
import { useResource } from "../../api/useResource";
import { EmptyState, FailureState, KpiStrip, LoadingState, SectionCard, StatCard } from "../../components/kit";
import { countWords } from "../agents/agentStats";
import {
  NO_MODEL_CALL,
  RUNS_HEADING,
  glanceTokens,
  namesOf,
  notMeasuredSentence,
  personWords,
  readUsage,
  tokenKeyWords,
  tokensKeyHeading,
  usageApiPath,
  type TokenBreakdown,
  type UsageBody,
} from "../usageQuery";
import {
  BarList,
  DEFAULT_PERIOD,
  Quiet,
  REPORTS_CRUMB,
  ReportHeader,
  Switch,
  counted,
  periodWords,
  sheetOf,
  type ReportPeriod,
  type Sheet,
} from "./reportParts";

export const USAGE_HEADING = "Usage";
export const USAGE_LEDE = "How much people ask, where they ask it, and what the answers consumed.";
export const USAGE_AND_COST = "Usage and cost";
export const USAGE_CRUMBS = [REPORTS_CRUMB, { label: USAGE_AND_COST, to: "/usage" }, { label: USAGE_HEADING }];

export const LOADING_USAGE = "Loading usage.";
export const NO_USAGE = "No usage to show";
export const NO_USAGE_MORE = "Usage appears here as people ask questions.";
export const NOBODY_ASKED = "Nobody asked a question in this period.";
export const NO_DEPARTMENT = "No department to show for this period.";

export const FIGURES_LABEL = "Usage figures";
export const QUESTIONS_LABEL = "Questions";
export const PEOPLE_LABEL = "People asking";
export const TOKENS_IN_LABEL = "Tokens in";
export const TOKENS_OUT_LABEL = "Tokens out";
export const WITHOUT_AUTOMATION = "people only, automation not counted";
export const WITH_AUTOMATION = "automation included";
export const ASKED_ONE = "asked at least one";

export const BY_DEPARTMENT = "Questions by department";
export const BY_PERSON = "Who asks most";
export const TOKENS_HEADING = "Tokens";
export const TOKENS_LEDE = "What the questions' model calls consumed.";
export const TOKEN_AXIS_LABEL = "Tokens by";

/** How many people the "Who asks most" card draws before "Show all". */
export const PEOPLE_SHOWN = 10;

/** "12,000 in, 3,400 out". */
export function tokensWords(tokensIn: number, tokensOut: number): string {
  return `${tokensIn.toLocaleString("en-GB")} in, ${tokensOut.toLocaleString("en-GB")} out`;
}

/** Every table the page draws, as the export menu saves them. */
export function usageSheets(body: UsageBody, period: ReportPeriod): Sheet[] {
  const names = namesOf(body.people);
  const sheets: Sheet[] = [];
  const days = `${String(period)}-days`;
  if (body.departments !== null) {
    sheets.push(
      sheetOf(
        BY_DEPARTMENT,
        `usage-by-department-${days}`,
        [
          { header: "Department", text: (row) => row.department },
          { header: "Questions", text: (row) => String(row.questions) },
          { header: "People", text: (row) => String(row.people) },
        ],
        body.departments,
      ),
    );
  }
  if (body.people !== null) {
    sheets.push(
      sheetOf(
        "Questions by person",
        `usage-by-person-${days}`,
        [
          { header: "Person", text: (row) => personWords(row.person, names) },
          { header: "Reference", text: (row) => row.person },
          { header: "Questions", text: (row) => String(row.questions) },
        ],
        body.people,
      ),
    );
  }
  for (const breakdown of body.tokens) {
    sheets.push(
      sheetOf(
        `Tokens by ${breakdown.axis}`,
        `usage-tokens-by-${breakdown.axis}-${days}`,
        [
          { header: tokensKeyHeading(breakdown.axis), text: (row) => tokenKeyWords(breakdown.axis, row.key, names) },
          ...(breakdown.axis === "person" ? [{ header: "Reference", text: (row: TokenBreakdown["lines"][number]) => row.key }] : []),
          { header: RUNS_HEADING, text: (row) => String(row.runs) },
          { header: TOKENS_IN_LABEL, text: (row) => String(row.tokens_in) },
          { header: TOKENS_OUT_LABEL, text: (row) => String(row.tokens_out) },
        ],
        breakdown.lines,
      ),
    );
  }
  return sheets;
}

function Figures({ body }: { readonly body: UsageBody }) {
  const tokens = glanceTokens(body.tokens);
  const unmeasured = body.not_measured.includes("tokens");
  const cards = [];
  if (body.questions !== null) {
    cards.push(
      <StatCard
        key="questions"
        label={QUESTIONS_LABEL}
        value={countWords(body.questions)}
        sub={body.machine_included ? WITH_AUTOMATION : WITHOUT_AUTOMATION}
      />,
    );
  }
  if (body.people !== null) {
    cards.push(<StatCard key="people" label={PEOPLE_LABEL} value={countWords(body.people.length)} sub={ASKED_ONE} />);
  }
  if (tokens !== null) {
    cards.push(<StatCard key="in" label={TOKENS_IN_LABEL} value={countWords(tokens.tokensIn)} />);
    cards.push(<StatCard key="out" label={TOKENS_OUT_LABEL} value={countWords(tokens.tokensOut)} />);
  } else if (unmeasured) {
    cards.push(<StatCard key="in" label={TOKENS_IN_LABEL} unrecordedWhy={notMeasuredSentence("tokens")} />);
    cards.push(<StatCard key="out" label={TOKENS_OUT_LABEL} unrecordedWhy={notMeasuredSentence("tokens")} />);
  }
  if (cards.length === 0) {
    return null;
  }
  return (
    <KpiStrip label={FIGURES_LABEL} count={cards.length}>
      {cards}
    </KpiStrip>
  );
}

function Departments({ lines }: { readonly lines: NonNullable<UsageBody["departments"]> }) {
  const ordered = [...lines].sort((a, b) => b.questions - a.questions);
  return (
    <SectionCard title={BY_DEPARTMENT}>
      {ordered.length === 0 ? (
        <Quiet>{NO_DEPARTMENT}</Quiet>
      ) : (
        <BarList
          caption={BY_DEPARTMENT}
          keyHeading="Department"
          valueHeading="Questions and people"
          bars={ordered.map((line) => ({
            key: line.department,
            label: line.department,
            value: line.questions,
            figure: `${counted(line.questions, "question", "questions")} · ${counted(line.people, "person", "people")}`,
          }))}
        />
      )}
    </SectionCard>
  );
}

function People({ lines }: { readonly lines: NonNullable<UsageBody["people"]> }) {
  const names = namesOf(lines);
  return (
    <SectionCard title={BY_PERSON}>
      {lines.length === 0 ? (
        <Quiet>{NOBODY_ASKED}</Quiet>
      ) : (
        <BarList
          caption={BY_PERSON}
          keyHeading="Person"
          valueHeading="Questions"
          limit={PEOPLE_SHOWN}
          bars={lines.map((line) => ({
            key: line.person,
            label: personWords(line.person, names),
            value: line.questions,
            figure: counted(line.questions, "question", "questions"),
          }))}
        />
      )}
    </SectionCard>
  );
}

/** The axis drawn first: by model where the API sent it, because that is where tokens differ. */
function firstAxis(tokens: readonly TokenBreakdown[]): string {
  return (tokens.find((one) => one.axis === "model") ?? tokens[0])?.axis ?? "";
}

function Tokens({ body }: { readonly body: UsageBody }) {
  const [axis, setAxis] = useState(() => firstAxis(body.tokens));
  const names = namesOf(body.people);
  const breakdown = body.tokens.find((one) => one.axis === axis) ?? body.tokens[0];
  if (breakdown === undefined) {
    return body.not_measured.includes("tokens") ? (
      <SectionCard title={TOKENS_HEADING}>
        <Quiet>{notMeasuredSentence("tokens")}</Quiet>
      </SectionCard>
    ) : null;
  }
  return (
    <SectionCard
      title={TOKENS_HEADING}
      lede={TOKENS_LEDE}
      action={
        body.tokens.length > 1 ? (
          <Switch
            label={TOKEN_AXIS_LABEL}
            value={breakdown.axis}
            options={body.tokens.map((one) => ({ value: one.axis, label: tokensKeyHeading(one.axis) }))}
            onChange={setAxis}
          />
        ) : undefined
      }
      footer={
        breakdown.lines.length === 0 ? undefined : (
          <p className="m-0 text-[12px] text-dim">
            Total {tokensWords(breakdown.total_tokens_in, breakdown.total_tokens_out)}, over{" "}
            {counted(breakdown.total_runs, "request", "requests")} with a model call.
          </p>
        )
      }
    >
      {breakdown.lines.length === 0 ? (
        <Quiet>{NO_MODEL_CALL}</Quiet>
      ) : (
        <BarList
          caption={`${TOKENS_HEADING} by ${breakdown.axis}`}
          keyHeading={tokensKeyHeading(breakdown.axis)}
          valueHeading="Tokens in and out"
          limit={PEOPLE_SHOWN}
          bars={[...breakdown.lines]
            .sort((a, b) => b.tokens_in + b.tokens_out - (a.tokens_in + a.tokens_out))
            .map((line) => ({
              key: line.key,
              label: tokenKeyWords(breakdown.axis, line.key, names),
              value: line.tokens_in + line.tokens_out,
              figure: tokensWords(line.tokens_in, line.tokens_out),
            }))}
        />
      )}
    </SectionCard>
  );
}

/** Whether the answer offers this reader anything: a table, or a token measure to speak of. */
function offersAnything(body: UsageBody): boolean {
  return body.departments !== null || body.people !== null || body.tokens.length > 0 || body.not_measured.includes("tokens");
}

export function UsagePage() {
  const [period, setPeriod] = useState<ReportPeriod>(DEFAULT_PERIOD);
  const answer = useResource<unknown>(usageApiPath(period));
  const body = answer.data === null ? null : readUsage(answer.data);
  const ready = !answer.busy && answer.failure === null && body !== null && offersAnything(body);

  let content;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.busy) {
    content = <LoadingState label={LOADING_USAGE} />;
  } else if (body === null || !offersAnything(body)) {
    content = <EmptyState title={NO_USAGE} description={NO_USAGE_MORE} />;
  } else {
    content = (
      <>
        <Figures body={body} />
        <div className="[display:grid] min-w-0 items-start gap-4 xl:grid-cols-2">
          {body.departments === null ? null : <Departments lines={body.departments} />}
          {body.people === null ? null : <People key={period} lines={body.people} />}
        </div>
        <Tokens key={period} body={body} />
      </>
    );
  }

  return (
    <div data-slot="report-page" className="flex min-w-0 flex-col gap-4">
      <ReportHeader
        crumbs={USAGE_CRUMBS}
        title={USAGE_HEADING}
        lede={`${USAGE_LEDE} ${periodWords(period)}.`}
        period={period}
        onPeriod={setPeriod}
        sheets={ready && body !== null ? usageSheets(body, period) : []}
      />
      {content}
    </div>
  );
}
