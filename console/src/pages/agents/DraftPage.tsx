/**
 * One draft of an agent, in four steps each at its own address: write it, draw a procedure, check
 * and rehearse it, and publish it, or approve it as the second person.
 *
 * **The form is the API's.** The Write step mounts `ManifestForm` over the sections
 * `GET /api/v1/builder/form` sends, each cut from the manifest's own schema by `brain.builder.form`,
 * so a field the manifest gains is a field here with no edit to this page. A section's submission is
 * merged into the draft (`agentDraftsQuery.withSection`) and saved as a new version, naming the
 * version it was edited from, so a second tab that saved first is told rather than overwritten.
 *
 * **The Procedure step mounts `ProcedureCanvas`**, offering the tools this draft is allowed on this
 * install and nothing else, and turns a drawing into the skill document the server writes. Nothing is
 * kept: a skill enters the library through its review on the Skills page, which this step links to.
 *
 * **Every write is confirmed, and every answer is the API's.** Saving a section, checking, rehearsing,
 * drawing, publishing, approving and sending back each open the kit's `ConfirmDialog` saying what will
 * happen, and a refusal is drawn in the API's own sentence. Whether a publish goes out now or waits
 * for a second person is the API's to say, and the page says it before the press as the check said
 * it. A reader who is the second person sees what the draft adds and the two acts, and no form.
 *
 * **Loaded on demand**: the form library and the canvas are the heaviest things the console mounts,
 * and somebody who never opens a draft does not download them.
 *
 * Task ids: M27.11.6, M27.15.31, M27.16.1, M20.1.2, M20.2.2
 */

import { CheckCircle2, ClipboardCheck, Hammer, PenLine, Send, Workflow } from "lucide-react";
import { useCallback, useId, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ManifestForm } from "../../components/ManifestForm";
import { readManifestForm } from "../../components/manifestSections";
import { ProcedureCanvas } from "../../components/ProcedureCanvas";
import type { DrawingPayload } from "../../components/procedure";
import {
  Advanced,
  Chip,
  ConfirmDialog,
  DetailHeader,
  DetailPage,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  SectionCard,
  UnavailableAction,
  ViewSwitch,
  type DetailView,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";
import { ROSTER_HEADING, agentAddress } from "./AgentsPage";
import {
  ACT_WORDS,
  APPROVE_CONSEQUENCE,
  APPROVE_QUESTION,
  BUILDER_FORM_API_PATH,
  CHECK_CONSEQUENCE,
  CHECK_QUESTION,
  DECLINE_CONSEQUENCE,
  DECLINE_QUESTION,
  DRAFTS_ADDRESS,
  DRAW_CONSEQUENCE,
  DRAW_QUESTION,
  FORM_HINT,
  KEEP_LABEL,
  NOTHING_IS_LIVE,
  PROCEDURE_DESCRIPTION_HINT,
  PROCEDURE_NAME_HINT,
  PUBLISH_CONSEQUENCE,
  PUBLISH_QUESTION,
  REHEARSE_CONSEQUENCE,
  REHEARSE_QUESTION,
  SAVE_CONSEQUENCE,
  SAVE_QUESTION,
  STEPS,
  STEP_LABELS,
  TOOLS_LIST_LABEL,
  TOOLS_SECTION_HEADING,
  draftActApiPath,
  draftAddress,
  draftApiPath,
  kindWords,
  readCheck,
  readDraft,
  readNotChanged,
  readPublished,
  readRehearsal,
  stateWords,
  stepFor,
  withSection,
  type Draft,
  type DraftCheck,
  type DraftPublished,
  type DraftRehearsal,
  type DraftStep,
  type DraftVerb,
} from "./agentDraftsQuery";

export const LOADING_DRAFT = "Loading this draft.";
export const LOADING_FORM = "Loading the form.";
export const STEPS_LABEL = "Draft steps";
export const PROBLEMS_HEADING = "Not whole yet";
export const WRITE_HEADING = "Write the agent";
export const PROCEDURE_HEADING = "Draw a procedure";
export const PROCEDURE_LEDE =
  "Optional. Draw the steps the agent follows, calling only the tools this draft is allowed here, and the server writes it as a skill document.";
export const NO_TOOLS_TO_DRAW =
  `This draft is allowed no tool on this install yet, so a procedure has nothing to call. In the Write step, add one under ${TOOLS_LIST_LABEL} in the ${TOOLS_SECTION_HEADING} section, and save it.`;
export const OPEN_WRITE_STEP = "Open the Write step";
export const ENTER_SKILL_NAME = "Enter the skill name.";
export const ENTER_WHEN_TO_USE = "Enter when to use it.";
export const DRAW_A_STEP_FIRST = "Add a step to the procedure first.";
export const PROCEDURE_NAME = "Skill name";
export const PROCEDURE_DESCRIPTION = "When to use it";
export const DRAW_LABEL = "Write the skill document";
export const SKILL_HEADING = "The skill document";
export const ADD_ON_SKILLS = "Add it on the Skills page";
export const CHECK_HEADING = "Check";
export const CHECK_LEDE = "Whether the latest version can be published, and what it would be on this install.";
export const CHECK_LABEL = "Check this draft";
export const REHEARSE_HEADING = "Rehearse";
export const REHEARSE_LEDE = "What a run through this draft would reach for you, at Shadow. Nothing is carried out.";
export const REHEARSE_LABEL = "Rehearse as me";
export const PUBLISH_HEADING = "Publish";
export const PUBLISH_LABEL = "Publish";
export const APPROVE_LABEL = "Approve and publish";
export const DECLINE_LABEL = "Send back";
export const WHO_CAN_FIND = "Who can find the new agent";
export const ONLY_ME = "Only me";
export const MY_DEPARTMENT = "My department";
export const HISTORY_HEADING = "History";
export const REACHES_FURTHER = "Reaches further than before";
export const SECOND_PERSON = "It will wait for a second person who is not you and whose own access covers all of it.";
export const NO_SECOND_PERSON = "It reaches no further than before, so it can be published on your word.";
export const PASSED = "It passes. It can be published.";
export const NOT_PASSED = "It does not pass yet";
export const MISSING_HEADING = "Missing on this install";
export const MISSING_LEDE = "The agent is published switched off until these are in place.";
export const DETAILS_HEADING = "Company details in it";
export const DETAILS_LEDE = "These stay on this install. They are named because a template made from this agent would carry them.";
export const STARTS_FOR_YOU = "A run would start for you.";
export const DOES_NOT_START_FOR_YOU = "A run would not start for you: nothing you hold is reachable through it.";
export const REACHES_FOR_YOU = "It would reach, for you";
export const QUESTIONS_IT_ASKS = "Test questions it would ask";
export const NOT_YOURS = "Only its author can change this draft.";
export const PUBLISHED_ALREADY = "This draft is published. Start a new draft from the agent to change it again.";
export const OPEN_THE_AGENT = "Open the agent";
export const SOMETHING_DID_NOT_WORK = "Something did not work";
export const NOTHING_CHANGED = "Nothing was changed";
export const SAVE_LABEL = "Save";
export const WHERE_IT_ANSWERS = "Where it answers";
export const WHERE_IT_ANSWERS_HINT =
  "An agent answers only where it is switched on. Chats are switched on from its page by the connector administrator.";
export const ON_THE_WEB_PAGE = "On the web page";

/** One act a person asked for, waiting for its confirmation. */
type Pending =
  | { readonly verb: "revisions"; readonly section: string; readonly heading: string; readonly data: unknown }
  | { readonly verb: "check" | "rehearse" | "publish" | "approve" | "decline" }
  | { readonly verb: "procedure"; readonly drawing: DrawingPayload; readonly name: string; readonly description: string };

interface Refused {
  readonly failure: ApiFailure;
  readonly title: string;
  readonly sentence?: string;
}

function questionFor(pending: Pending, draft: Draft): { question: string; consequence: string; label: string } {
  switch (pending.verb) {
    case "revisions":
      return { question: SAVE_QUESTION(pending.heading), consequence: SAVE_CONSEQUENCE, label: SAVE_LABEL };
    case "check":
      return { question: CHECK_QUESTION, consequence: CHECK_CONSEQUENCE, label: CHECK_LABEL };
    case "rehearse":
      return { question: REHEARSE_QUESTION, consequence: REHEARSE_CONSEQUENCE, label: REHEARSE_LABEL };
    case "procedure":
      return { question: DRAW_QUESTION, consequence: DRAW_CONSEQUENCE, label: DRAW_LABEL };
    case "publish":
      return { question: PUBLISH_QUESTION(draft.name), consequence: PUBLISH_CONSEQUENCE, label: PUBLISH_LABEL };
    case "approve":
      return { question: APPROVE_QUESTION(draft.name), consequence: APPROVE_CONSEQUENCE, label: APPROVE_LABEL };
    case "decline":
      return { question: DECLINE_QUESTION(draft.name), consequence: DECLINE_CONSEQUENCE, label: DECLINE_LABEL };
  }
}

function bodyFor(pending: Pending, draft: Draft, forDepartment: boolean, web: boolean): Record<string, unknown> {
  switch (pending.verb) {
    case "revisions":
      return { document: withSection(draft.document, pending.data), base: draft.revision };
    case "procedure":
      return { drawing: pending.drawing, name: pending.name.trim(), description: pending.description.trim() };
    case "publish":
      return { revision: draft.revision, for_department: forDepartment, web };
    default:
      return { revision: draft.revision };
  }
}

/** One box of the skill's two, with its format said first and a missing answer said under it. */
function SkillField({
  id,
  label,
  hint,
  value,
  problem,
  onChange,
}: {
  readonly id: string;
  readonly label: string;
  readonly hint: string;
  readonly value: string;
  readonly problem: string | null;
  readonly onChange: (value: string) => void;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <p id={`${id}-hint`} className="m-0 text-[12px] text-dim">
        {hint}
      </p>
      <Input
        id={id}
        value={value}
        aria-invalid={problem === null ? undefined : true}
        aria-describedby={problem === null ? `${id}-hint` : `${id}-hint ${id}-problem`}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      {problem === null ? null : (
        <p id={`${id}-problem`} className="m-0 text-[12.5px] font-medium text-ink">
          {problem}
        </p>
      )}
    </div>
  );
}

function Words({ items }: { readonly items: readonly string[] }) {
  return (
    <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-sm text-body">
      {items.map((one) => (
        <li key={one} className="[overflow-wrap:anywhere]">
          {one}
        </li>
      ))}
    </ul>
  );
}

function CheckResult({ check }: { readonly check: DraftCheck }) {
  return (
    <div data-slot="check-result" className="flex min-w-0 flex-col gap-3">
      {check.passed ? (
        <Notice title={PASSED}>
          <p>{check.secondPersonNeeded ? SECOND_PERSON : NO_SECOND_PERSON}</p>
        </Notice>
      ) : (
        <div className="flex flex-col gap-1">
          <p className="m-0 text-sm font-semibold text-ink">{NOT_PASSED}</p>
          <Words items={check.problems} />
        </div>
      )}
      {check.widened.length === 0 ? null : (
        <Fact label={REACHES_FURTHER}>
          <span className="flex flex-wrap gap-1">
            {check.widened.map((one) => (
              <Chip key={one} mono>
                {one}
              </Chip>
            ))}
          </span>
        </Fact>
      )}
      {check.missing.length === 0 ? null : (
        <div className="flex flex-col gap-1">
          <p className="m-0 text-sm font-semibold text-ink">{MISSING_HEADING}</p>
          <p className="m-0 text-[12.5px] text-dim">{MISSING_LEDE}</p>
          <Words items={check.missing} />
        </div>
      )}
      {check.companyDetails.length === 0 ? null : (
        <div className="flex flex-col gap-1">
          <p className="m-0 text-sm font-semibold text-ink">{DETAILS_HEADING}</p>
          <p className="m-0 text-[12.5px] text-dim">{DETAILS_LEDE}</p>
          <Words items={check.companyDetails.map((one) => `${one.text} (${one.kind})`)} />
        </div>
      )}
    </div>
  );
}

function RehearsalResult({ rehearsal }: { readonly rehearsal: DraftRehearsal }) {
  return (
    <div data-slot="rehearsal-result" className="flex min-w-0 flex-col gap-3">
      <p className="m-0 text-sm text-body">{rehearsal.startsForYou ? STARTS_FOR_YOU : DOES_NOT_START_FOR_YOU}</p>
      {rehearsal.reachesForYou.length === 0 ? null : (
        <Fact label={REACHES_FOR_YOU}>
          <span className="flex flex-wrap gap-1">
            {rehearsal.reachesForYou.map((one) => (
              <Chip key={one} mono>
                {one}
              </Chip>
            ))}
          </span>
        </Fact>
      )}
      {rehearsal.questions.length === 0 ? null : (
        <div className="flex flex-col gap-1">
          <p className="m-0 text-sm font-semibold text-ink">{QUESTIONS_IT_ASKS}</p>
          <Words items={rehearsal.questions} />
        </div>
      )}
      <Note kind="not-yet">{rehearsal.notDone}</Note>
    </div>
  );
}

function History({ draft }: { readonly draft: Draft }) {
  if (draft.acts.length === 0) {
    return null;
  }
  return (
    <SectionCard title={HISTORY_HEADING} headingLevel="h3">
      <FactList>
        {draft.acts.map((one) => (
          <Fact key={`${String(one.revision)} ${one.act}`} label={`Version ${String(one.revision)}`}>
            {ACT_WORDS[one.act] ?? one.act}{" "}
            <span className="text-dim">
              {new Date(one.at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
            </span>
          </Fact>
        ))}
      </FactList>
    </SectionCard>
  );
}

function Summary({ draft }: { readonly draft: Draft }) {
  const persona = typeof draft.document["persona"] === "string" ? draft.document["persona"] : "";
  return (
    <SectionCard title={WRITE_HEADING}>
      <Note>{draft.yours ? NOTHING_IS_LIVE : draft.state === "published" ? PUBLISHED_ALREADY : NOT_YOURS}</Note>
      <FactList>
        <Fact label="Name">{draft.name}</Fact>
        <Fact label="Instructions">
          <span className="whitespace-pre-wrap [overflow-wrap:anywhere]">{persona}</span>
        </Fact>
        {draft.widened.length === 0 ? null : (
          <Fact label={REACHES_FURTHER}>
            <span className="flex flex-wrap gap-1">
              {draft.widened.map((one) => (
                <Chip key={one} mono>
                  {one}
                </Chip>
              ))}
            </span>
          </Fact>
        )}
      </FactList>
    </SectionCard>
  );
}

function DraftAnswer({ draftId, step }: { readonly draftId: string; readonly step: DraftStep }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(draftApiPath(draftId), version);
  const draft = useMemo(() => readDraft(answer.data), [answer.data]);
  const writing = step === "write" && draft?.yours === true;
  const form = useResource<unknown>(writing ? BUILDER_FORM_API_PATH : null);
  const sections = useMemo(() => (form.data === null ? [] : readManifestForm(form.data)), [form.data]);

  const [pending, setPending] = useState<Pending | null>(null);
  const [sending, setSending] = useState(false);
  const [refused, setRefused] = useState<Refused | null>(null);
  const [check, setCheck] = useState<DraftCheck | null>(null);
  const [rehearsal, setRehearsal] = useState<DraftRehearsal | null>(null);
  const [skill, setSkill] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<DraftPublished | null>(null);
  const [drawing, setDrawing] = useState<DrawingPayload | null>(null);
  const [skillName, setSkillName] = useState("");
  const [skillWhen, setSkillWhen] = useState("");
  const [tried, setTried] = useState(false);
  const [forDepartment, setForDepartment] = useState(false);
  const [web, setWeb] = useState(true);
  const nameId = useId();
  const whenId = useId();
  const audienceId = useId();
  const channelsId = useId();

  const ask = useCallback((next: Pending) => {
    setRefused(null);
    setPending(next);
  }, []);

  const confirm = () => {
    if (pending === null || draft === null) {
      return;
    }
    const chosen = pending;
    setSending(true);
    void (async () => {
      const verb: DraftVerb = chosen.verb;
      const result = await request<unknown>(draftActApiPath(draftId, verb), {
        method: "POST",
        body: bodyFor(chosen, draft, forDepartment, web),
      });
      setSending(false);
      setPending(null);
      if (!result.ok) {
        const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
        setRefused(
          notChanged === null
            ? { failure: result.failure, title: SOMETHING_DID_NOT_WORK }
            : { failure: result.failure, title: NOTHING_CHANGED, sentence: notChanged.sentence },
        );
        return;
      }
      if (chosen.verb === "check") {
        setCheck(readCheck(result.data));
      } else if (chosen.verb === "rehearse") {
        setRehearsal(readRehearsal(result.data));
      } else if (chosen.verb === "procedure") {
        const text = (result.data as { skill?: unknown } | null)?.skill;
        setSkill(typeof text === "string" ? text : null);
      } else if (chosen.verb === "publish" || chosen.verb === "approve" || chosen.verb === "decline") {
        setOutcome(readPublished(result.data));
      }
      if (chosen.verb !== "rehearse" && chosen.verb !== "procedure") {
        setVersion((count) => count + 1);
      }
    })();
  };

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy || draft === null) {
    return answer.busy ? <LoadingState label={LOADING_DRAFT} /> : null;
  }

  const asked = pending === null ? null : questionFor(pending, draft);
  const views: DetailView[] = STEPS.map((one) => ({ key: one, label: STEP_LABELS[one], to: draftAddress(draftId, one) }));
  const header = (
    <DetailHeader
      name={draft.name}
      headingId={`draft-${draft.draftId}`}
      pills={
        <span data-slot="draft-state" className="inline-block rounded-[2px] bg-sunk px-1.5 py-0.5 font-mono text-[10.5px] text-ink">
          {stateWords(draft.state)}
        </span>
      }
      subline={`${kindWords(draft.kind)} · version ${String(draft.revision)}`}
    />
  );

  let body: ReactNode = null;
  if (step === "write") {
    body = !draft.yours ? (
      <Summary draft={draft} />
    ) : (
      <SectionCard title={WRITE_HEADING} action={<PenLine aria-hidden className="size-4 text-dim" />}>
        <div className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-col gap-1">
            <Note>{NOTHING_IS_LIVE}</Note>
            <Note>{FORM_HINT}</Note>
          </div>
          {draft.problems.length === 0 ? null : (
            <div className="flex flex-col gap-1">
              <p className="m-0 text-sm font-semibold text-ink">{PROBLEMS_HEADING}</p>
              <Words items={draft.problems} />
            </div>
          )}
          {form.failure !== null ? (
            <FailureState failure={form.failure} />
          ) : form.busy ? (
            <LoadingState label={LOADING_FORM} />
          ) : (
            <ManifestForm
              caption={draft.name}
              sections={sections}
              draft={draft.document}
              busy={sending}
              onSubmit={(section, data, heading) => {
                ask({ verb: "revisions", section, heading, data });
              }}
            />
          )}
        </div>
      </SectionCard>
    );
  } else if (step === "procedure") {
    body = !draft.yours ? (
      <Summary draft={draft} />
    ) : (
      <SectionCard title={PROCEDURE_HEADING} lede={PROCEDURE_LEDE} action={<Workflow aria-hidden className="size-4 text-dim" />}>
        {draft.drawableTools.length === 0 ? (
          <div className="flex flex-col gap-2">
            <Note>{NO_TOOLS_TO_DRAW}</Note>
            <Link to={draftAddress(draftId, "write")} className="w-fit text-[12.5px] text-acc-text underline-offset-4 hover:underline">
              {OPEN_WRITE_STEP}
            </Link>
          </div>
        ) : (
          <>
            <ProcedureCanvas
              caption={`A procedure for ${draft.name}`}
              tools={draft.drawableTools}
              onChange={setDrawing}
              skill={skill}
            />
            <div className="[display:grid] min-w-0 gap-3 sm:grid-cols-2">
              <SkillField
                id={nameId}
                label={PROCEDURE_NAME}
                hint={PROCEDURE_NAME_HINT}
                value={skillName}
                problem={tried && skillName.trim() === "" ? ENTER_SKILL_NAME : null}
                onChange={setSkillName}
              />
              <SkillField
                id={whenId}
                label={PROCEDURE_DESCRIPTION}
                hint={PROCEDURE_DESCRIPTION_HINT}
                value={skillWhen}
                problem={tried && skillWhen.trim() === "" ? ENTER_WHEN_TO_USE : null}
                onChange={setSkillWhen}
              />
            </div>
            <div className="flex min-w-0 flex-col gap-1.5">
              <Button
                className="min-h-11 w-fit sm:min-h-9"
                disabled={sending}
                aria-describedby={tried && drawing === null ? `${nameId}-draw` : undefined}
                onClick={() => {
                  // Said beside each box rather than a button that will not press: a disabled button
                  // tells nobody which of three things it is waiting for.
                  setTried(true);
                  if (drawing !== null && skillName.trim() !== "" && skillWhen.trim() !== "") {
                    ask({ verb: "procedure", drawing, name: skillName, description: skillWhen });
                  }
                }}
              >
                {DRAW_LABEL}
              </Button>
              {tried && drawing === null ? (
                <p id={`${nameId}-draw`} className="m-0 text-[12.5px] font-medium text-ink">
                  {DRAW_A_STEP_FIRST}
                </p>
              ) : null}
            </div>
            {skill === null ? null : (
              <div className="flex flex-col gap-1">
                <p className="m-0 text-sm font-semibold text-ink">{SKILL_HEADING}</p>
                <pre className="m-0 max-w-full overflow-x-auto rounded-md border border-line bg-sunk p-3 text-[12px]">{skill}</pre>
                <Link to="/skills" className="w-fit text-[12.5px] text-acc-text underline-offset-4 hover:underline">
                  {ADD_ON_SKILLS}
                </Link>
              </div>
            )}
          </>
        )}
      </SectionCard>
    );
  } else if (step === "check") {
    body = !draft.yours ? (
      <Summary draft={draft} />
    ) : (
      <div className="[display:grid] min-w-0 gap-4 lg:grid-cols-2">
        <SectionCard title={CHECK_HEADING} lede={CHECK_LEDE} action={<ClipboardCheck aria-hidden className="size-4 text-dim" />}>
          <Button
            className="min-h-11 w-fit sm:min-h-9"
            disabled={sending}
            onClick={() => {
              ask({ verb: "check" });
            }}
          >
            {CHECK_LABEL}
          </Button>
          {check === null ? null : <CheckResult check={check} />}
        </SectionCard>
        <SectionCard title={REHEARSE_HEADING} lede={REHEARSE_LEDE} action={<Hammer aria-hidden className="size-4 text-dim" />}>
          <Button
            variant="outline"
            className="min-h-11 w-fit sm:min-h-9"
            disabled={sending}
            onClick={() => {
              ask({ verb: "rehearse" });
            }}
          >
            {REHEARSE_LABEL}
          </Button>
          {rehearsal === null ? null : <RehearsalResult rehearsal={rehearsal} />}
        </SectionCard>
      </div>
    );
  } else {
    body = (
      <div className="flex min-w-0 flex-col gap-4">
        <SectionCard title={PUBLISH_HEADING} action={<Send aria-hidden className="size-4 text-dim" />}>
          {outcome === null ? null : (
            <Notice title={stateWords(outcome.state)}>
              <p>
                {outcome.sentence}
                {outcome.state === "published" ? (
                  <>
                    {" "}
                    <Link to={agentAddress(outcome.agentId)}>{OPEN_THE_AGENT}</Link>
                  </>
                ) : null}
              </p>
            </Notice>
          )}
          {draft.waitingOnYou ? (
            <>
              <Summary draft={draft} />
              <div className="flex flex-wrap gap-2">
                <Button
                  className="min-h-11 sm:min-h-9"
                  disabled={sending}
                  onClick={() => {
                    ask({ verb: "approve" });
                  }}
                >
                  <CheckCircle2 aria-hidden />
                  {APPROVE_LABEL}
                </Button>
                <Button
                  variant="outline"
                  className="min-h-11 sm:min-h-9"
                  disabled={sending}
                  onClick={() => {
                    ask({ verb: "decline" });
                  }}
                >
                  {DECLINE_LABEL}
                </Button>
              </div>
            </>
          ) : !draft.yours ? (
            <Note>{draft.state === "published" ? PUBLISHED_ALREADY : NOT_YOURS}</Note>
          ) : draft.publishUnavailable !== undefined ? (
            <UnavailableAction text={PUBLISH_LABEL} label={PUBLISH_LABEL} reason={draft.publishUnavailable} />
          ) : (
            <>
              <p className="m-0 text-sm text-body">{PUBLISH_CONSEQUENCE}</p>
              {draft.kind !== "new" ? null : (
                <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0" aria-describedby={audienceId}>
                  <legend className="text-sm font-medium text-ink">{WHO_CAN_FIND}</legend>
                  <p id={audienceId} className="m-0 text-[12px] text-dim">
                    Nobody else can find it until it is published to more people.
                  </p>
                  <label className="flex min-h-11 items-center gap-2 text-sm sm:min-h-8">
                    <input
                      type="radio"
                      name="draft-audience"
                      checked={!forDepartment}
                      onChange={() => {
                        setForDepartment(false);
                      }}
                    />
                    {ONLY_ME}
                  </label>
                  <label className="flex min-h-11 items-center gap-2 text-sm sm:min-h-8">
                    <input
                      type="radio"
                      name="draft-audience"
                      checked={forDepartment}
                      onChange={() => {
                        setForDepartment(true);
                      }}
                    />
                    {MY_DEPARTMENT}
                  </label>
                </fieldset>
              )}
              {draft.kind !== "new" ? null : (
                <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0" aria-describedby={channelsId}>
                  <legend className="text-sm font-medium text-ink">{WHERE_IT_ANSWERS}</legend>
                  <p id={channelsId} className="m-0 text-[12px] text-dim">
                    {WHERE_IT_ANSWERS_HINT}
                  </p>
                  <label className="flex min-h-11 items-center gap-2 text-sm sm:min-h-8">
                    <input
                      type="checkbox"
                      name="draft-web"
                      checked={web}
                      onChange={(event) => {
                        setWeb(event.target.checked);
                      }}
                    />
                    {ON_THE_WEB_PAGE}
                  </label>
                </fieldset>
              )}
              <Button
                className="min-h-11 w-fit sm:min-h-9"
                disabled={sending}
                onClick={() => {
                  ask({ verb: "publish" });
                }}
              >
                {PUBLISH_LABEL}
              </Button>
            </>
          )}
        </SectionCard>
        <History draft={draft} />
      </div>
    );
  }

  return (
    <DetailPage
      crumbs={[
        { label: ROSTER_HEADING, to: "/agents" },
        { label: "Drafts", to: DRAFTS_ADDRESS },
        { label: draft.name },
      ]}
      header={header}
      switcher={<ViewSwitch label={STEPS_LABEL} views={views} current={step} />}
    >
      {refused === null ? null : (
        <FailureNotice
          failure={refused.failure}
          title={refused.title}
          {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
        />
      )}
      <ConfirmDialog
        open={pending !== null}
        question={asked?.question ?? ""}
        consequence={asked?.consequence ?? ""}
        confirmLabel={asked?.label ?? ""}
        cancelLabel={KEEP_LABEL}
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setPending(null);
        }}
      />
      {body}
      <Advanced>
        <FactList>
          <Fact label="Agent id">
            <span className="font-mono">{draft.agentId}</span>
          </Fact>
          <Fact label="Draft id">
            <span className="font-mono">{draft.draftId}</span>
          </Fact>
        </FactList>
      </Advanced>
    </DetailPage>
  );
}

export function DraftPage({ draftId, step }: { readonly draftId: string; readonly step: string | undefined }) {
  return (
    <div data-slot="draft-page" className="min-w-0">
      <DraftAnswer key={draftId} draftId={draftId} step={stepFor(step)} />
    </div>
  );
}
