/**
 * Connect Lark's step for the Wiki: which shared spaces the Brain may answer from, and who on this
 * install may be told each one's pages.
 *
 * **A space is offered from the test, or pasted.** The test lists the spaces Lark shows the app
 * (`LarkUseResultView.spaces`); a space it does not show is added by pasting its settings link.
 * Each gets a reach, the whole company or one department, and a space left at "Not yet" is not
 * sent. The API reads the space's id out of what was pasted and refuses, beside its field, a
 * link naming no space or a department reach naming no department, so a save declares every
 * space it names or none (`brain.ops.lark_wiki_spaces`).
 *
 * **The departments offered are the ones this reader is shown** (`GET /govern/departments`), so
 * the list names no department the reader could not already see.
 *
 * **The declarer is the steward**, which the step says; the declared list names each steward.
 *
 * **An administrator is told how many matched pages were not read**, as one number and the API's
 * note on why, and never which pages: the API sends the count only to a reader who may switch the
 * Wiki on (`skippedPages`), and this shows nothing for none or nought.
 *
 * Task ids: M11.6.4, M11.9.4, M27.11.9
 */

import { Plus } from "lucide-react";
import { useId, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Fact, FactList, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems } from "../../ui/FieldProblems";
import { DEPARTMENTS_API_PATH, readOrganisation } from "../governPeopleQuery";
import {
  LARK_WIKI_SPACES_API_PATH,
  spaceChoices,
  spacesBody,
  type DeclaredSpaces,
  type LarkTested,
  type SpaceChoice,
  type SkippedPages,
  type SpacesDeclared,
  skippedWords,
} from "../larkConnectQuery";

export const DECLARED = "Spaces declared";
export const NOTHING_DECLARED = "No space is declared yet, so the Brain answers from none.";
export const TO_DECLARE = "Spaces to declare";
export const NOT_YET = "Not yet";
export const WHOLE_COMPANY = "The whole company";
export const ONE_DEPARTMENT = "One department";
export const PASTE_A_SPACE = "Paste a space's settings link";
export const PASTE_HINT = "It contains /wiki/space/ and a number. The number on its own works too.";
export const ADD_SPACE = "Add the space";
export const SAVE_SPACES = "Save the spaces";
export const KEEP_UNDECLARED = "Declare nothing";
export const NOT_DECLARED_TITLE = "The spaces were not declared";
export const NONE_SEEN = "Test the connection first to list the spaces Lark shows the app, or paste a space's link below.";
export const STEWARD_NOTE = "You become the steward of each space you declare.";

const FORM = "lark-spaces";

function reachWords(reach: string, department: string, names: Readonly<Record<string, string>>): string {
  return reach === "company" ? WHOLE_COMPANY : `${ONE_DEPARTMENT}: ${names[department] ?? department}`;
}

export const SKIPPED_LABEL = "Pages not read";

export function WikiSpaces({
  tested,
  may,
  skipped = null,
}: {
  readonly tested: LarkTested | null;
  readonly may: boolean;
  /** How many matched pages were not read, for an administrator; null shows nothing. */
  readonly skipped?: SkippedPages | null;
}) {
  const [generation, setGeneration] = useState(0);
  const declaredAnswer = useResource<DeclaredSpaces>(LARK_WIKI_SPACES_API_PATH, generation);
  const departments = readOrganisation(useResource<unknown>(DEPARTMENTS_API_PATH).data).departments;
  const names = Object.fromEntries(departments.map((one) => [one.slug, one.name]));
  const declared = declaredAnswer.data?.spaces ?? [];
  const [pasted, setPasted] = useState<SpaceChoice[]>([]);
  const [reaches, setReaches] = useState<Readonly<Record<string, { reach: string; department: string }>>>({});
  const [link, setLink] = useState("");
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState("");
  const linkId = useId();

  const rows = [...spaceChoices(tested, declared), ...pasted].map((one) => ({ ...one, ...(reaches[one.space] ?? {}) }));
  const sending = rows.filter((one) => one.reach !== "");
  const problems = failure?.problems ?? [];
  // Lark's own names for every space the test saw, declared or not, so the declared list names them.
  const seen = tested?.uses.find((one) => one.name === "knowledge_wiki")?.spaces ?? [];
  const labels: Readonly<Record<string, string>> = Object.fromEntries(
    [...seen.map((one) => [one.space_id, one.name] as const), ...rows.map((one) => [one.space, one.label] as const)].filter(
      ([, name]) => name !== "",
    ),
  );

  function choose(space: string, reach: string, department: string): void {
    setReaches({ ...reaches, [space]: { reach, department } });
  }

  function save(): void {
    setBusy(true);
    void (async () => {
      const result = await request<SpacesDeclared>(LARK_WIKI_SPACES_API_PATH, { method: "POST", body: spacesBody(rows) });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setTold(result.data.told);
      setPasted([]);
      setReaches({});
      setGeneration((one) => one + 1);
    })();
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {skipped === null ? null : (
        <section aria-label={SKIPPED_LABEL} className="flex min-w-0 flex-col gap-1 rounded-md border border-line p-3">
          <p className="m-0 text-[13px] font-medium text-ink">{skippedWords(skipped.count)}</p>
          {skipped.note === "" ? null : <p className="m-0 text-[12.5px] leading-snug text-dim">{skipped.note}</p>}
        </section>
      )}
      <section aria-label={DECLARED} className="flex min-w-0 flex-col gap-1.5">
        <h4 className="m-0 text-[13px] font-semibold text-ink">{DECLARED}</h4>
        {declared.length === 0 ? (
          <p className="m-0 text-[12.5px] text-dim">{NOTHING_DECLARED}</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-1 p-0 text-[12.5px]">
            {declared.map((one) => (
              <li key={one.space_id} className="text-body">
                <span className="font-medium text-ink">{labels[one.space_id] ?? one.space_id}</span>: {reachWords(one.reach, one.department, names)}
                {one.steward === "" ? null : `, stewarded by ${one.steward}`}
              </li>
            ))}
          </ul>
        )}
      </section>
      {told === "" ? null : <Note kind="done">{told}</Note>}
      {!may ? null : (
        <>
          <h4 className="m-0 text-[13px] font-semibold text-ink">{TO_DECLARE}</h4>
          {rows.length === 0 ? <Note>{NONE_SEEN}</Note> : null}
          {failure === null ? null : <FailureNotice failure={failure} title={NOT_DECLARED_TITLE} />}
          <ul aria-label={TO_DECLARE} className="m-0 flex list-none flex-col gap-2 p-0">
            {rows.map((one) => {
              const index = sending.findIndex((sent) => sent.space === one.space);
              const reachId = `${FORM}-${one.space}-reach`;
              return (
                <li key={one.space} className="flex min-w-0 flex-col gap-2 rounded-md border border-line p-3">
                  <Label htmlFor={reachId} className="text-[13px] font-medium text-ink [overflow-wrap:anywhere]">
                    {one.label}
                  </Label>
                  <div className="flex min-w-0 flex-wrap gap-2">
                    <select
                      id={reachId}
                      className="h-11 min-w-0 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink sm:h-9"
                      value={one.reach}
                      disabled={busy}
                      onChange={(event) => {
                        choose(one.space, event.target.value, one.department);
                      }}
                    >
                      <option value="">{NOT_YET}</option>
                      <option value="company">{WHOLE_COMPANY}</option>
                      <option value="department">{ONE_DEPARTMENT}</option>
                    </select>
                    {one.reach !== "department" ? null : (
                      <select
                        aria-label={`Department for ${one.label}`}
                        className="h-11 min-w-0 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink sm:h-9"
                        value={one.department}
                        disabled={busy}
                        onChange={(event) => {
                          choose(one.space, one.reach, event.target.value);
                        }}
                      >
                        <option value="">Choose a department</option>
                        {departments.map((department) => (
                          <option key={department.slug} value={department.slug}>
                            {department.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  {index < 0 ? null : (
                    <FieldProblems
                      problems={problems}
                      form={FORM}
                      names={[`spaces.${String(index)}.space`, `spaces.${String(index)}.reach`, `spaces.${String(index)}.department`]}
                    />
                  )}
                </li>
              );
            })}
          </ul>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor={linkId}>{PASTE_A_SPACE}</Label>
            <div className="flex min-w-0 flex-wrap gap-2">
              <Input
                id={linkId}
                value={link}
                autoComplete="off"
                spellCheck={false}
                aria-describedby={`${linkId}-hint`}
                className="min-w-0 flex-1"
                disabled={busy}
                onChange={(event) => {
                  setLink(event.target.value);
                }}
              />
              <Button
                type="button"
                variant="outline"
                className="min-h-11 sm:min-h-9"
                disabled={busy || link.trim() === "" || rows.some((one) => one.space === link.trim())}
                onClick={() => {
                  setPasted([...pasted, { space: link.trim(), label: link.trim(), reach: "", department: "" }]);
                  setLink("");
                }}
              >
                <Plus aria-hidden />
                {ADD_SPACE}
              </Button>
            </div>
            <p id={`${linkId}-hint`} className="m-0 text-[12.5px] text-dim">
              {PASTE_HINT}
            </p>
          </div>
          <p className="m-0 text-[12.5px] text-dim">{STEWARD_NOTE}</p>
          <Button
            type="button"
            className="min-h-11 self-start sm:min-h-9"
            disabled={busy || sending.length === 0 || sending.some((one) => one.reach === "department" && one.department === "")}
            onClick={() => {
              setPending(true);
            }}
          >
            {SAVE_SPACES}
          </Button>
        </>
      )}
      <ConfirmDialog
        open={pending}
        question={`${SAVE_SPACES}?`}
        consequence={`${declaredAnswer.data?.told ?? ""} ${STEWARD_NOTE}`}
        details={
          <FactList>
            {sending.map((one) => (
              <Fact key={one.space} label={one.label}>
                {reachWords(one.reach, one.department, names)}
              </Fact>
            ))}
          </FactList>
        }
        confirmLabel={SAVE_SPACES}
        cancelLabel={KEEP_UNDECLARED}
        busy={busy}
        danger={false}
        onConfirm={save}
        onCancel={() => {
          setPending(false);
        }}
      />
    </div>
  );
}
