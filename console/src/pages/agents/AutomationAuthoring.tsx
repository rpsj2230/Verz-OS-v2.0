/**
 * New automation on an agent's Automations tab: start from a named outcome or from words, choose
 * when it runs and whether something must be true first, name what the agent may use, read what it
 * would have done at its last few triggers, and save it paused (M39.9.2.1 to M39.9.2.4).
 *
 * **Never a blank canvas of steps.** The form has four choices and one piece of writing: the
 * trigger (a schedule, a change in a connected source, a call from outside), at most one condition
 * from a short list, the tools the agent may use, and what it is told to do. What it offers is the
 * API's, for this agent and this install, and a field or a tool the agent could not use is not in
 * the lists.
 *
 * **Two presses, and the second is the confirmation.** "Review" asks the API what saving would
 * store and shows it with the rehearsal: the last few times it would have run and what it would
 * have been told at each, writing and sending nothing. Only "Save it paused" writes, and it sends
 * back the digest the API computed, which the route recomputes. A refusal of what was written is a
 * list of sentences under the form, all of them at once, because a form is edited and not debugged.
 *
 * **The button is drawn only when the install has switched New automation on.** The API answers
 * `enabled: false` with nothing else and this draws nothing, so an install that has not switched it
 * on shows no control that would be refused.
 *
 * **Nothing here decides anything.** The trigger kinds that nothing fires yet are chosen and kept,
 * and the preview says in words that they cannot be started.
 *
 * Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.3, M39.9.2.4, M17.4.1, M17.4.2
 */

import { Plus } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";
import { FORM, Field, SELECT, Status, Submit } from "../knowledge/formParts";
import { ConfirmAction } from "../../components/ConfirmAction";
import {
  authoringCreateApiPath,
  authoringOptionsApiPath,
  authoringPreviewApiPath,
  createBody,
  draftBody,
  readAuthored,
  readAuthoringOptions,
  readAuthoringPreview,
  readNotWritten,
  readRefusal,
  startDraft,
  type AuthoringOptions,
  type AuthoringPreview,
  type Draft,
  type Every,
  type TriggerKind,
} from "../automationAuthoringQuery";

export const NEW_AUTOMATION = "New automation";
export const NEW_HEADING = "New automation";
export const NEW_LEDE =
  "Start from an outcome or write it in words. It runs as you, starts paused, and somebody else has to start it.";
export const READING_OPTIONS = "Reading what a new automation may be.";
export const REVIEW = "Review and rehearse";
export const REVIEWING = "Working out what it would have done.";
export const SAVE = "Save it paused";
export const KEEP_LABEL = "Not now";
export const SAVED_TITLE = "Saved";
export const NOT_SAVED = "Nothing was saved";
export const FROM_WORDS = "From my own words";
export const NO_CONDITION = "No condition: it runs every time";
export const NOTHING_FIRES_HERE = "Starting on a change is switched off on this install, so it is saved and cannot be started until an administrator switches it on.";
export const NO_CONNECTORS = "No connected source is bound to this agent, so there is nothing to listen to.";
export const NO_TOOLS = "This agent's ceiling allows no tools, so this automation can use none.";
export const NO_SKILLS = "This agent has no approved skill attached that an automation of yours would be offered.";
export const SKILLS_LABEL = "Skills it would be offered";
export const PREVIEW_UNREADABLE =
  "The API's answer about this automation could not be read, so nothing can be confirmed. Nothing was saved.";
export const SOMETHING_DID_NOT_WORK = "Something did not work";
export const CANNOT_BE_AN_AUTOMATION = "What you wrote cannot be an automation yet";

export const START_FROM_LABEL = "Start from";
export const NAME_LABEL = "What it does, as an outcome starting with I";
export const INSTRUCTION_LABEL = "What the agent is told to do each time";
export const GUARDS_LABEL = "What goes wrong if it does not run";
export const TRIGGER_LABEL = "When it runs";
export const SOURCE_LABEL = "Which connected source";
export const ENDPOINT_LABEL = "Name of the call that starts it";
export const CADENCE_LABEL = "How often";
export const HOUR_LABEL = "At what hour (UTC)";
export const DAY_LABEL = "On which day";
export const CONDITION_LABEL = "Only when";
export const COMPARISON_LABEL = "Comparison";
export const VALUE_LABEL = "Value";
export const DAYS_VALUE_LABEL = "Number of days";
export const TOOLS_LABEL = "What it may use";

const EVERIES: ReadonlyArray<{ readonly value: Every; readonly label: string }> = [
  { value: "day", label: "Every day" },
  { value: "weekday", label: "Every weekday" },
  { value: "week", label: "Once a week" },
];
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

interface Refused {
  readonly failure: ApiFailure;
  readonly title?: string;
  readonly sentences?: readonly string[];
}

function TriggerFields({
  options,
  draft,
  onChange,
}: {
  readonly options: AuthoringOptions;
  readonly draft: Draft;
  readonly onChange: (next: Draft) => void;
}) {
  return (
    <>
      <Field label={TRIGGER_LABEL}>
        {(id) => (
          <select
            id={id}
            name="trigger"
            className={SELECT}
            value={draft.kind}
            onChange={(event) => {
              onChange({ ...draft, kind: event.target.value as TriggerKind });
            }}
          >
            {options.triggers.map((one) => (
              <option key={one.kind} value={one.kind} disabled={one.notOffered !== null}>
                {one.notOffered === null ? one.label : `${one.label} (not offered)`}
              </option>
            ))}
          </select>
        )}
      </Field>
      {draft.kind === "schedule" ? (
        <>
          <Field label={CADENCE_LABEL}>
            {(id) => (
              <select
                id={id}
                name="every"
                className={SELECT}
                value={draft.every}
                onChange={(event) => {
                  onChange({ ...draft, every: event.target.value as Every });
                }}
              >
                {EVERIES.map((one) => (
                  <option key={one.value} value={one.value}>
                    {one.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {draft.every === "week" ? (
            <Field label={DAY_LABEL}>
              {(id) => (
                <select
                  id={id}
                  name="weekday"
                  className={SELECT}
                  value={draft.weekday}
                  onChange={(event) => {
                    onChange({ ...draft, weekday: Number(event.target.value) });
                  }}
                >
                  {DAYS.map((name, index) => (
                    <option key={name} value={index}>
                      {name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          ) : null}
          <Field label={HOUR_LABEL}>
            {(id) => (
              <select
                id={id}
                name="hour"
                className={SELECT}
                value={draft.hourUtc}
                onChange={(event) => {
                  onChange({ ...draft, hourUtc: Number(event.target.value) });
                }}
              >
                {Array.from({ length: 24 }, (_, hour) => (
                  <option key={hour} value={hour}>
                    {`${String(hour).padStart(2, "0")}:00`}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </>
      ) : draft.kind === "connector_event" ? (
        options.connectors.length === 0 ? (
          <Status>{NO_CONNECTORS}</Status>
        ) : (
          <Field label={SOURCE_LABEL}>
            {(id) => (
              <select
                id={id}
                name="source"
                className={SELECT}
                value={draft.source}
                onChange={(event) => {
                  onChange({ ...draft, source: event.target.value });
                }}
              >
                <option value="">Choose one</option>
                {options.connectors.map((one) => (
                  <option key={one} value={one}>
                    {one}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )
      ) : (
        <Field label={ENDPOINT_LABEL} hint="Lower case letters, digits and underscores.">
          {(id, describedBy) => (
            <Input
              id={id}
              name="endpoint"
              aria-describedby={describedBy}
              value={draft.source}
              onChange={(event) => {
                onChange({ ...draft, source: event.target.value });
              }}
            />
          )}
        </Field>
      )}
      {options.triggers.find((one) => one.kind === draft.kind)?.notOffered ? (
        <Status>{options.triggers.find((one) => one.kind === draft.kind)?.notOffered}</Status>
      ) : options.triggers.find((one) => one.kind === draft.kind)?.fires === false ? (
        <Status>{NOTHING_FIRES_HERE}</Status>
      ) : null}
    </>
  );
}

function ConditionFields({
  options,
  draft,
  onChange,
}: {
  readonly options: AuthoringOptions;
  readonly draft: Draft;
  readonly onChange: (next: Draft) => void;
}) {
  const field = options.fields.find((one) => one.key === draft.conditionField);
  const op = field?.ops.find((one) => one.op === draft.conditionOp);
  return (
    <>
      <Field label={CONDITION_LABEL}>
        {(id) => (
          <select
            id={id}
            name="condition-field"
            className={SELECT}
            value={draft.conditionField}
            onChange={(event) => {
              const next = options.fields.find((one) => one.key === event.target.value);
              onChange({
                ...draft,
                conditionField: event.target.value,
                conditionOp: next?.ops[0]?.op ?? "",
                conditionValue: "",
              });
            }}
          >
            <option value="">{NO_CONDITION}</option>
            {options.fields.map((one) => (
              <option key={one.key} value={one.key}>
                {one.label}
              </option>
            ))}
          </select>
        )}
      </Field>
      {field === undefined ? null : (
        <>
          <Field label={COMPARISON_LABEL}>
            {(id) => (
              <select
                id={id}
                name="condition-op"
                className={SELECT}
                value={draft.conditionOp}
                onChange={(event) => {
                  onChange({ ...draft, conditionOp: event.target.value });
                }}
              >
                {field.ops.map((one) => (
                  <option key={one.op} value={one.op}>
                    {one.label}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={op?.inDays === true ? DAYS_VALUE_LABEL : VALUE_LABEL}>
            {(id) => (
              <Input
                id={id}
                name="condition-value"
                inputMode={op?.inDays === true ? "numeric" : "text"}
                value={draft.conditionValue}
                onChange={(event) => {
                  onChange({ ...draft, conditionValue: event.target.value });
                }}
              />
            )}
          </Field>
        </>
      )}
    </>
  );
}

function Review({ shown }: { readonly shown: AuthoringPreview }) {
  return (
    <div data-slot="authoring-review" className="flex min-w-0 flex-col gap-3">
      <dl className="fields" aria-label="What saving it would do">
        <div className="fields__row">
          <dt>Name</dt>
          <dd>{shown.name}</dd>
        </div>
        <div className="fields__row">
          <dt>Runs as</dt>
          <dd>
            {shown.runsAsName} <code>{shown.runsAs}</code>
          </dd>
        </div>
        <div className="fields__row">
          <dt>When</dt>
          <dd>{shown.trigger}</dd>
        </div>
        <div className="fields__row">
          <dt>Only when</dt>
          <dd>{shown.condition ?? "It runs every time."}</dd>
        </div>
        <div className="fields__row">
          <dt>Told to</dt>
          <dd>{shown.instruction}</dd>
        </div>
        <div className="fields__row">
          <dt>May use</dt>
          <dd>{shown.tools.length === 0 ? NO_TOOLS : shown.tools.join(", ")}</dd>
        </div>
        <div className="fields__row">
          <dt>Skills</dt>
          <dd>{shown.skills.length === 0 ? NO_SKILLS : shown.skills.join(", ")}</dd>
        </div>
        <div className="fields__row">
          <dt>What it can reach</dt>
          <dd>{shown.reach.length === 0 ? "Nothing: your access and this agent's ceiling have no read in common." : shown.reach.join(", ")}</dd>
        </div>
        <div className="fields__row">
          <dt>What breaks without it</dt>
          <dd>{shown.guards}</dd>
        </div>
      </dl>
      {shown.nothingFires === undefined ? null : <Status>{shown.nothingFires}</Status>}
      {shown.cannotRun === undefined ? null : <Status>{shown.cannotRun}</Status>}
      <p className="m-0 text-[12.5px] text-body">{shown.writesWait}</p>
      <p className="m-0 text-[12px] text-dim">{shown.skillsRule}</p>
      <section aria-label="Rehearsal" data-slot="authoring-rehearsal" className="flex flex-col gap-2">
        <h4 className="m-0 text-[13px] font-medium text-ink">What it would have done</h4>
        <p className="m-0 text-[12px] text-dim">{shown.rehearsalRule}</p>
        <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px]">
          {shown.rehearsal.map((one, index) => (
            <li key={`${one.at ?? "none"}-${String(index)}`} className="rounded-md border border-line p-2.5">
              {one.at === undefined ? null : <p className="m-0 text-[11.5px] text-dim">{one.at}</p>}
              <p className="m-0">{one.says}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Form({
  agentId,
  options,
  onSaved,
  onClose,
}: {
  readonly agentId: string;
  readonly options: AuthoringOptions;
  readonly onSaved: (name: string) => void;
  readonly onClose: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => startDraft(undefined));
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState<AuthoringPreview | null>(null);
  const [failure, setFailure] = useState<Refused | null>(null);
  const [unreadable, setUnreadable] = useState(false);

  const review = useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      setBusy(true);
      setFailure(null);
      setUnreadable(false);
      void (async () => {
        const result = await request<unknown>(authoringPreviewApiPath(agentId), { method: "POST", body: draftBody(draft) });
        setBusy(false);
        if (!result.ok) {
          const sentences = result.failure.status === 422 ? readRefusal(result.body) : null;
          setFailure(sentences === null ? { failure: result.failure } : { failure: result.failure, title: CANNOT_BE_AN_AUTOMATION, sentences });
          return;
        }
        const preview = readAuthoringPreview(result.data);
        if (preview === null) {
          setUnreadable(true);
          return;
        }
        setShown(preview);
      })();
    },
    [agentId, draft],
  );

  const save = useCallback(
    (preview: AuthoringPreview) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(authoringCreateApiPath(agentId), { method: "POST", body: createBody(draft, preview) });
        setBusy(false);
        setShown(null);
        if (result.ok) {
          onSaved(readAuthored(result.data)?.name ?? preview.name);
          return;
        }
        const told = result.failure.status === 409 ? readNotWritten(result.body) : null;
        const sentences = result.failure.status === 422 ? readRefusal(result.body) : null;
        setFailure({
          failure: result.failure,
          ...(told === null ? {} : { title: NOT_SAVED, sentences: [told] }),
          ...(sentences === null ? {} : { title: CANNOT_BE_AN_AUTOMATION, sentences }),
        });
      })();
    },
    [agentId, draft, onSaved],
  );

  const chooseStart = (templateId: string): void => {
    setDraft(startDraft(options.templates.find((one) => one.templateId === templateId)));
  };
  const toggleTool = (tool: string): void => {
    setDraft({ ...draft, tools: draft.tools.includes(tool) ? draft.tools.filter((one) => one !== tool) : [...draft.tools, tool] });
  };

  return (
    <div data-slot="authoring" className="flex min-w-0 max-w-xl flex-col gap-4">
      {failure === null ? null : (
        <div className="flex flex-col gap-2">
          <FailureNotice failure={failure.failure} title={failure.title ?? SOMETHING_DID_NOT_WORK} />
          {failure.sentences === undefined ? null : (
            <ul data-slot="authoring-findings" className="m-0 flex list-disc flex-col gap-1 pl-5 text-[13px] text-ink">
              {failure.sentences.map((one) => (
                <li key={one}>{one}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {unreadable ? (
        <Notice title={NOT_SAVED}>
          <p>{PREVIEW_UNREADABLE}</p>
        </Notice>
      ) : null}
      {shown === null ? null : (
        <ConfirmAction
          question={`Save "${shown.name}" on this agent?`}
          consequence={shown.startsPaused}
          details={<Review shown={shown} />}
          confirmLabel={SAVE}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            save(shown);
          }}
          onCancel={() => {
            setShown(null);
          }}
        />
      )}
      {shown !== null ? null : (
        <form className={FORM} onSubmit={review} aria-label={NEW_HEADING}>
          <Field label={START_FROM_LABEL}>
            {(id) => (
              <select
                id={id}
                name="start"
                className={SELECT}
                value={draft.templateId}
                onChange={(event) => {
                  chooseStart(event.target.value);
                }}
              >
                <option value="">{FROM_WORDS}</option>
                {options.templates.map((one) => (
                  <option key={one.templateId} value={one.templateId}>
                    {one.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={NAME_LABEL}>
            {(id) => (
              <Input
                id={id}
                name="name"
                value={draft.name}
                onChange={(event) => {
                  setDraft({ ...draft, name: event.target.value });
                }}
              />
            )}
          </Field>
          <Field label={INSTRUCTION_LABEL} hint="In plain words, as you would ask a colleague. It is never run as code.">
            {(id, describedBy) => (
              <Textarea
                id={id}
                name="instruction"
                aria-describedby={describedBy}
                rows={4}
                value={draft.instruction}
                onChange={(event) => {
                  setDraft({ ...draft, instruction: event.target.value });
                }}
              />
            )}
          </Field>
          <Field label={GUARDS_LABEL}>
            {(id) => (
              <Textarea
                id={id}
                name="guards"
                rows={2}
                value={draft.guards}
                onChange={(event) => {
                  setDraft({ ...draft, guards: event.target.value });
                }}
              />
            )}
          </Field>
          <TriggerFields options={options} draft={draft} onChange={setDraft} />
          <ConditionFields options={options} draft={draft} onChange={setDraft} />
          <fieldset className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
            <legend className="mb-1 text-[13px] font-medium text-ink">{TOOLS_LABEL}</legend>
            {options.tools.length === 0 ? (
              <Status>{NO_TOOLS}</Status>
            ) : (
              options.tools.map((tool) => (
                <label key={tool} className="flex min-h-11 items-center gap-2 text-[13px] sm:min-h-8">
                  <input
                    type="checkbox"
                    checked={draft.tools.includes(tool)}
                    onChange={() => {
                      toggleTool(tool);
                    }}
                  />
                  {tool}
                </label>
              ))
            )}
            <p className="m-0 text-[12px] text-dim">{options.mayUse}</p>
            <p className="m-0 text-[12px] text-dim">{options.writesWait}</p>
          </fieldset>
          <section aria-label={SKILLS_LABEL} data-slot="authoring-skills" className="flex min-w-0 flex-col gap-1">
            <h4 className="m-0 text-[13px] font-medium text-ink">{SKILLS_LABEL}</h4>
            {options.skills.length === 0 ? (
              <Status>{NO_SKILLS}</Status>
            ) : (
              <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[13px]">
                {options.skills.map((one) => (
                  <li key={one.name}>
                    <span className="font-medium text-ink">{one.name}</span>
                    <span className="text-dim">{` ${one.version}, ${one.description}`}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="m-0 text-[12px] text-dim">{options.skillsRule}</p>
          </section>
          {busy ? <Status>{REVIEWING}</Status> : null}
          <div className="flex items-center justify-end gap-3">
            <Button type="button" variant="ghost" className="min-h-11 sm:min-h-9" onClick={onClose}>
              {KEEP_LABEL}
            </Button>
            <Submit label={REVIEW} busy={busy} />
          </div>
        </form>
      )}
    </div>
  );
}

export function AutomationAuthoring({ agentId, onSaved }: { readonly agentId: string; readonly onSaved: () => void }) {
  const found = useResource<unknown>(authoringOptionsApiPath(agentId));
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  if (found.failure !== null || found.busy) {
    // A refusal of the options is the one answer for an agent this reader may not write on, so
    // there is no control to draw. The reading is brief and says nothing while it is.
    return null;
  }
  const options = readAuthoringOptions(found.data);
  if (options === null || !options.enabled) {
    return null;
  }
  return (
    <section aria-label={NEW_HEADING} data-slot="new-automation" className="flex min-w-0 flex-col gap-3">
      {saved === null ? null : (
        <Notice title={SAVED_TITLE}>
          <p>{`"${saved}" is saved and paused. ${options.startsPaused}`}</p>
        </Notice>
      )}
      {open ? (
        <>
          <h3>{NEW_HEADING}</h3>
          <p className="note">{NEW_LEDE}</p>
          <Form
            agentId={agentId}
            options={options}
            onClose={() => {
              setOpen(false);
            }}
            onSaved={(name) => {
              setSaved(name);
              setOpen(false);
              onSaved();
            }}
          />
        </>
      ) : (
        <div>
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 sm:min-h-8"
            onClick={() => {
              setSaved(null);
              setOpen(true);
            }}
          >
            <Plus aria-hidden />
            {NEW_AUTOMATION}
          </Button>
        </div>
      )}
    </section>
  );
}
