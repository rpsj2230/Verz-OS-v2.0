/**
 * Connect or switch the staff source: choose the kind, follow its steps, test, save, then run and
 * apply the first sync. A drawer, so the status page stays in view behind it.
 *
 * Every sentence of the steps is the API's guide, so a vendor renaming a menu is fixed once, on the
 * server. The four presses go in the order they are safe: a test and the first sync's preview keep
 * nothing and are not confirmed; saving the connection and applying the first sync change what the
 * install reads and who is on its staff list, so each opens the kit's `ConfirmDialog`. Save is
 * offered only once a test of exactly the values in the boxes has read the directory.
 *
 * The typed values stay in this drawer until the first sync is applied, because the preview and the
 * apply are sent them again and the vault is never read back; they are cleared then. A reader who
 * may not connect is shown the steps and no form, and the API refuses every write whatever this drew.
 *
 * Task ids: M27.7.2, M1.8.6, M27.16.1
 */

import { useCallback, useId, useState, type FormEvent, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Drawer, Fact, FactList, FailureState, LoadingState, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  APPLY_FIRST_SYNC_API_PATH,
  blankValues,
  CONNECT_API_PATH,
  connectBody,
  CONNECTION_TEST_API_PATH,
  FIRST_SYNC_API_PATH,
  GUIDES_API_PATH,
  heldBoxes,
  readConnectionTest,
  readFirstSync,
  readGuides,
  startingGuide,
  type ConnectionTest,
  type FirstSync,
  type Guide,
  type GuideField,
} from "../staffSourcesQuery";
import { Names, Problem } from "./parts";

export const CONNECT_TITLE = "Connect a staff source";
export const CONNECT_DESCRIPTION =
  "Choose where your staff list lives, follow its steps and test the connection. Nothing is saved until you save it.";
export const STEPS_TITLE = "How to connect a staff source";
export const STEPS_DESCRIPTION = "The steps for each kind of source, so you know what connecting one will take.";
export const STEPS_ONLY =
  "Connecting a source needs the install settings and credentials authorities over the whole company.";
export const LOADING_STEPS = "Loading the steps.";
export const WHICH_SOURCE = "Kind of source";
export const WHICH_SOURCE_HINT = "Where your company keeps its list of staff.";
export const WHERE = "Where";
export const STEPS_LABEL = "Steps";
export const FOR_EXAMPLE = "For example";
export const SECRET_HINT = "Pasted once and never shown again.";
export const TEST_CONNECTION = "Test connection";
export const WORKING = "Asking the directory.";
export const SAVE_AND_CONNECT = "Save and connect";
export const KEEP_AS_IT_IS = "Keep the current source";
export const SAVE_CONSEQUENCE =
  "The credential is kept in the vault and replaces any kept before, and the nightly staff sync " +
  "reads this source from now on. Nobody is added until you apply the first sync.";
export const TEST_FIRST = "Save is offered once a test of these values has read the directory.";
export const NOT_CONNECTED = "The source was not connected";
export const SUPPLIED = "Supplied, and never shown again";
export const FIRST_SYNC_HEADING = "First sync";
export const SHOW_FIRST_SYNC = "Show what the first sync would do";
export const APPLY_FIRST_SYNC = "Apply the first sync";
export const LEAVE_UNAPPLIED = "Not yet";
export const APPLY_QUESTION = "Apply the first sync now?";
export const APPLY_CONSEQUENCE =
  "The people listed are added to the staff list and anybody marked as having left is marked. Nobody " +
  "is given a sign-in, and a leaver's agents stop until a new owner takes them on.";
export const WOULD_ADD = "People it would add";
export const WOULD_MARK_LEFT = "People it would mark as having left";
export const WOULD_RENAME = "People whose address it would move";
export const HELD_BACK = "What it would hold back";
export const REFUSED = "Why it would not apply";
export const CLOSE = "Close";

/** What a box left empty is told, beside it, before anything is sent. */
export function fillInBox(label: string): string {
  return `Fill in ${label} before going on.`;
}

/** Every name the API may give a box's problem: its own key, and its place in the body. */
function boxNames(key: string): readonly string[] {
  return [key, `values.${key}`];
}

/** The plan a preview returned: the API's sentence, then names. */
function Plan({ plan }: { readonly plan: FirstSync }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Note>{plan.told}</Note>
      <Names label={REFUSED} names={plan.refusals} />
      <Names label={WOULD_ADD} names={plan.added} />
      <Names label={WOULD_MARK_LEFT} names={plan.marked_left} />
      <Names label={WOULD_RENAME} names={plan.renamed} />
      <Names label={HELD_BACK} names={plan.withheld} />
    </div>
  );
}

/** One box: its label, the field, what it accepts, and the API's problems with it. */
function Box({
  box,
  prefix,
  value,
  problems,
  disabled,
  onChange,
}: {
  readonly box: GuideField;
  readonly prefix: string;
  readonly value: string;
  readonly problems: readonly FieldProblem[];
  readonly disabled: boolean;
  readonly onChange: (value: string) => void;
}) {
  const id = `${prefix}-${box.key}`;
  const hint = `${id}-hint`;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label htmlFor={id}>{box.label}</Label>
      <Input
        id={id}
        name={box.key}
        value={value}
        autoComplete="off"
        autoCapitalize="off"
        spellCheck={false}
        disabled={disabled}
        {...problemAttributes(problems, prefix, boxNames(box.key), hint)}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <p id={hint} className="m-0 text-[12.5px] leading-snug text-dim">
        {box.help}
        {box.secret ? ` ${SECRET_HINT}` : box.example === "" ? null : ` ${FOR_EXAMPLE}: ${box.example}`}
      </p>
      <FieldProblems problems={problems} form={prefix} names={boxNames(box.key)} />
    </div>
  );
}

/** The form for one guide: its boxes, the test, the save, and the first sync after it. */
function ConnectForm({ guide, onConnected }: { readonly guide: Guide; readonly onConnected: (told: string) => void }) {
  const prefix = `staff-source-${guide.source}`;
  const [values, setValues] = useState<Record<string, string>>(() => blankValues(guide));
  // Start on the credential the vault already holds when there is one, so it is not pasted twice.
  const [useHeld, setUseHeld] = useState((guide.held ?? "") !== "");
  const boxes = useHeld ? heldBoxes(guide) : guide.fields;
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [busy, setBusy] = useState(false);
  const [tested, setTested] = useState<ConnectionTest | null>(null);
  // The values the last test read with, so an edit after it asks for a new test.
  const [testedWith, setTestedWith] = useState("");
  const [savePending, setSavePending] = useState(false);
  const [connected, setConnected] = useState("");
  const [plan, setPlan] = useState<FirstSync | null>(null);
  const [applyPending, setApplyPending] = useState(false);
  const [applied, setApplied] = useState<FirstSync | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];

  const snapshot = JSON.stringify(connectBody(guide, values));
  const readable = tested?.read === true && testedWith === snapshot;

  /** Settles one answer: clears the busy flag, and keeps the failure or hands back the data. */
  const settle = useCallback((result: Awaited<ReturnType<typeof request<unknown>>>): unknown => {
    setBusy(false);
    if (!result.ok) {
      setFailure(result.failure);
      return null;
    }
    setFailure(null);
    return result.data;
  }, []);

  /** The two writes that keep nothing: the connection test and the first sync's preview. */
  const look = useCallback(
    async (path: string): Promise<unknown> => {
      setBusy(true);
      return settle(await request<unknown>(path, { method: "POST", body: connectBody(guide, values) }));
    },
    [guide, values, settle],
  );

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFailure(null);
    // Empty boxes are said beside them, and nothing is sent or confirmed.
    const empty = boxes
      .filter((one) => (values[one.key] ?? "").trim() === "")
      .map((one) => ({ field: one.key, code: "blank", message: fillInBox(one.label) }));
    setBlank(empty);
    if (empty.length > 0) {
      return;
    }
    if (useHeld) {
      // Nothing to test: the application never reads a kept secret. Straight to the confirmation.
      setSavePending(true);
      return;
    }
    const sent = snapshot;
    void (async () => {
      const found = readConnectionTest(await look(CONNECTION_TEST_API_PATH));
      setTested(found);
      setTestedWith(found?.read === true ? sent : "");
    })();
  }

  // Saving and applying each have their own request, reached only from their confirmations.
  const save = useCallback(() => {
    setBusy(true);
    void (async () => {
      const data = settle(
        await request<unknown>(CONNECT_API_PATH, { method: "POST", body: connectBody(guide, values, useHeld) }),
      );
      setSavePending(false);
      if (data === null) {
        return;
      }
      const told = (data as { told?: unknown }).told;
      const sentence = typeof told === "string" ? told : SAVE_AND_CONNECT;
      setConnected(sentence);
      onConnected(sentence);
    })();
  }, [guide, values, useHeld, settle, onConnected]);

  const apply = useCallback(() => {
    setBusy(true);
    void (async () => {
      const done = readFirstSync(
        settle(await request<unknown>(APPLY_FIRST_SYNC_API_PATH, { method: "POST", body: connectBody(guide, values) })),
      );
      setApplyPending(false);
      setApplied(done);
      if (done !== null) {
        // The first sync is done; nothing needs the typed values any longer.
        setValues(blankValues(guide));
        onConnected(done.told);
      }
    })();
  }, [guide, values, settle, onConnected]);

  return (
    <div className="flex min-w-0 flex-col gap-4" role="group" aria-label={`${CONNECT_TITLE}: ${guide.title}`}>
      {failure === null ? null : (
        <FailureNotice failure={failure} title={NOT_CONNECTED} fields={guide.fields.flatMap((one) => boxNames(one.key))} />
      )}
      {(guide.held ?? "") === "" || connected !== "" ? null : (
        <label className="flex items-start gap-2 text-[13px] text-ink">
          <input
            type="checkbox"
            name="use_held"
            className="mt-0.5"
            checked={useHeld}
            disabled={busy}
            onChange={(event) => {
              setUseHeld(event.target.checked);
              setBlank([]);
            }}
          />
          <span>{guide.held}</span>
        </label>
      )}
      <form id={prefix} className="flex min-w-0 flex-col gap-4" noValidate autoComplete="off" onSubmit={submit}>
        {boxes.map((box) => (
          <Box
            key={box.key}
            box={box}
            prefix={prefix}
            value={values[box.key] ?? ""}
            problems={problems}
            disabled={busy || connected !== ""}
            onChange={(value) => {
              setValues({ ...values, [box.key]: value });
            }}
          />
        ))}
        {connected !== "" ? null : (
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant={useHeld ? "default" : "outline"} className="min-h-11 sm:min-h-8" disabled={busy}>
              {useHeld ? SAVE_AND_CONNECT : TEST_CONNECTION}
            </Button>
            {useHeld ? null : (
              <Button
                type="button"
                className="min-h-11 sm:min-h-8"
                disabled={busy || !readable}
                onClick={() => {
                  setSavePending(true);
                }}
              >
                {SAVE_AND_CONNECT}
              </Button>
            )}
          </div>
        )}
      </form>
      {busy ? (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {WORKING}
        </p>
      ) : null}
      {tested === null || connected !== "" ? null : tested.read ? (
        <Note kind="works">{tested.told}</Note>
      ) : (
        <Problem>{tested.told}</Problem>
      )}
      {connected !== "" || readable || tested === null || useHeld ? null : <Note>{TEST_FIRST}</Note>}
      {connected === "" ? null : <Note kind="works">{connected}</Note>}
      {connected === "" || useHeld ? null : (
        <section className="flex min-w-0 flex-col gap-3 border-t border-line pt-3" aria-label={FIRST_SYNC_HEADING}>
          <h3 className="m-0 text-sm font-semibold text-ink">{FIRST_SYNC_HEADING}</h3>
          {applied !== null ? (
            <Note kind="works">{applied.told}</Note>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" className="min-h-11 sm:min-h-8" disabled={busy} onClick={() => {
                  void (async () => {
                    setPlan(readFirstSync(await look(FIRST_SYNC_API_PATH)));
                  })();
                }}>
                  {SHOW_FIRST_SYNC}
                </Button>
                <Button
                  type="button"
                  className="min-h-11 sm:min-h-8"
                  disabled={busy || plan === null || !plan.safe_to_apply}
                  onClick={() => {
                    setApplyPending(true);
                  }}
                >
                  {APPLY_FIRST_SYNC}
                </Button>
              </div>
              {plan === null ? null : <Plan plan={plan} />}
            </>
          )}
        </section>
      )}
      <ConfirmDialog
        open={savePending}
        question={`Connect ${guide.title}?`}
        consequence={SAVE_CONSEQUENCE}
        details={
          <FactList>
            {boxes.map((box) => (
              <Fact key={box.key} label={box.label}>
                {box.secret ? SUPPLIED : (values[box.key] ?? "")}
              </Fact>
            ))}
          </FactList>
        }
        confirmLabel={SAVE_AND_CONNECT}
        cancelLabel={KEEP_AS_IT_IS}
        busy={busy}
        onConfirm={save}
        onCancel={() => {
          setSavePending(false);
        }}
      />
      <ConfirmDialog
        open={applyPending}
        question={APPLY_QUESTION}
        consequence={APPLY_CONSEQUENCE}
        confirmLabel={APPLY_FIRST_SYNC}
        cancelLabel={LEAVE_UNAPPLIED}
        busy={busy}
        onConfirm={apply}
        onCancel={() => {
          setApplyPending(false);
        }}
      />
    </div>
  );
}

/** The drawer. It reads the guides each time it opens, so a credential kept since is offered. */
export function ConnectDrawer({
  onClose,
  onConnected,
}: {
  readonly onClose: () => void;
  /** Told what the API said after a save or an apply, so the page can say it and read again. */
  readonly onConnected: (told: string) => void;
}) {
  const answer = useResource<unknown>(GUIDES_API_PATH);
  const guides = readGuides(answer.data);
  const [picked, setPicked] = useState<string | null>(null);
  const selectId = useId();
  const guide = guides === null ? null : (guides.guides.find((one) => one.source === picked) ?? startingGuide(guides.guides));
  const mayConnect = guides?.may_connect ?? false;

  let body: ReactNode;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.busy || guides === null) {
    body = <LoadingState label={LOADING_STEPS} rows={3} />;
  } else if (guide === null) {
    body = <Note>{STEPS_ONLY}</Note>;
  } else {
    body = (
      <div className="flex min-w-0 flex-col gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <Label htmlFor={selectId}>{WHICH_SOURCE}</Label>
          <select
            id={selectId}
            className="h-11 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink sm:h-9"
            aria-describedby={`${selectId}-hint`}
            value={guide.source}
            onChange={(event) => {
              setPicked(event.target.value);
            }}
          >
            {guides.guides.map((one) => (
              <option key={one.source} value={one.source}>
                {one.title}
              </option>
            ))}
          </select>
          <p id={`${selectId}-hint`} className="m-0 text-[12.5px] leading-snug text-dim">
            {WHICH_SOURCE_HINT}
          </p>
        </div>
        <FactList>
          <Fact label={WHERE}>{guide.where}</Fact>
        </FactList>
        <ol aria-label={`${STEPS_LABEL}: ${guide.title}`} className="m-0 flex min-w-0 list-decimal flex-col gap-1.5 pl-5 text-[13px] text-ink">
          {guide.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        {guide.connectable ? null : <Note kind="not-yet">{guide.unavailable}</Note>}
        {!mayConnect ? (
          <Note>{STEPS_ONLY}</Note>
        ) : guide.connectable ? (
          <ConnectForm key={guide.source} guide={guide} onConnected={onConnected} />
        ) : null}
        {guides.schedule === "" ? null : <Note>{guides.schedule}</Note>}
      </div>
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
      title={mayConnect || guides === null ? CONNECT_TITLE : STEPS_TITLE}
      description={mayConnect || guides === null ? CONNECT_DESCRIPTION : STEPS_DESCRIPTION}
      footer={
        <Button variant="outline" className="min-h-11 sm:min-h-8" onClick={onClose}>
          {CLOSE}
        </Button>
      }
    >
      {body}
    </Drawer>
  );
}
