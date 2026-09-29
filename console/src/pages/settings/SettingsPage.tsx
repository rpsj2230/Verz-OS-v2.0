/**
 * Settings on the shared page kit: every installation value, grouped by what it is for, the
 * editable ones changed and returned to their default here, and each of the others with the one
 * sentence saying where it is changed.
 *
 * **Nothing here decides who may read or change.** The route asks for `admin:install_setting` over
 * everything before it reads anything, and a refused reader sees the API's refusal and no value.
 *
 * **A write answers with the whole screen as the database now holds it**, and that answer replaces
 * the page, so what is drawn after a save or a return to default is what was stored.
 *
 * **What was removed, and why.** The variable names and the modules that read each value were on
 * every row; they are for somebody editing the environment file, so they sit in one Advanced table.
 * The roles, packs and scopes the install was furnished with are identifiers and moved there too.
 * The two paragraphs the API sends about credentials and about what is edited here repeated the
 * lede and every row's own reason, and the handover's commands are a server procedure, so the
 * Leaving card shows what is removed and by whom and keeps the commands in Advanced.
 *
 * Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1, M27.12.7, M27.16.1
 */

import { useId, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  ConfirmDialog,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import {
  byWords,
  CHOICES,
  defaultConsequence,
  defaultPath,
  defaultQuestion,
  FINDINGS_HEADING,
  formatOf,
  FURNISHED_HEADING,
  KEEP_SAVED,
  KEEP_SETTING,
  knownTimeZones,
  LEAVING_HEADING,
  mayReturnToDefault,
  NOT_RETURNED,
  NOT_SAVED,
  READING_SETTINGS,
  readSettings,
  RETURN_TO_DEFAULT,
  RETURNED,
  SAVE,
  SAVE_CHANGE,
  SAVED,
  saveConsequence,
  savePath,
  saveQuestion,
  SETTINGS_API_PATH,
  SETTINGS_LABEL,
  SETTINGS_LEDE,
  shownValue,
  sourceWords,
  startingValue,
  TIME_ZONE_SETTING,
  UNREADABLE_SETTINGS,
  VARIABLES_LABEL,
  type SettingRow,
  type SettingsBody,
} from "../settingsQuery";

export const NO_SETTINGS = "No settings to show";
export const NO_SETTINGS_DESCRIPTION = "The answer carried no group of settings, so there is nothing to change here.";

/** Whether the starter set's record was read, in words. */
function furnishedWords(furnished: boolean | null | undefined): string {
  if (furnished === null || furnished === undefined) {
    return "Not known: this process has no database to read the record from.";
  }
  return furnished ? "Furnished." : "Not furnished yet: it is furnished when the application next starts.";
}

/** One editable value: its field, what it accepts, Save, and Return to default when one is saved. */
function EditableSetting({
  row,
  onSaved,
}: {
  readonly row: SettingRow;
  readonly onSaved: (body: SettingsBody, told: string) => void;
}) {
  const [value, setValue] = useState(startingValue(row));
  const [asking, setAsking] = useState<"save" | "default" | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const id = useId();
  const hint = `${id}-hint`;
  const suggestions = `${id}-zones`;
  const choices = CHOICES[row.name];
  const zones = row.name === TIME_ZONE_SETTING ? knownTimeZones() : [];

  const save = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(savePath(row.name), { method: "PUT", body: { value } });
      setBusy(false);
      setAsking(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      const body = readSettings(result.data);
      if (body !== null) {
        onSaved(body, SAVED);
      }
    })();
  };

  const returnToDefault = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(defaultPath(row.name), { method: "POST" });
      setBusy(false);
      setAsking(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      const body = readSettings(result.data);
      if (body !== null) {
        onSaved(body, RETURNED);
      }
    })();
  };

  return (
    <form
      className="flex min-w-0 flex-col gap-2"
      noValidate
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setFailure(null);
        setAsking("save");
      }}
    >
      <Label htmlFor={id} className="sr-only">
        {row.label}
      </Label>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
        {choices === undefined ? (
          <Input
            id={id}
            name={row.name}
            value={value}
            aria-describedby={hint}
            list={zones.length === 0 ? undefined : suggestions}
            autoComplete="off"
            className="sm:max-w-md"
            onChange={(event) => {
              setValue(event.target.value);
            }}
          />
        ) : (
          <select
            id={id}
            name={row.name}
            aria-describedby={hint}
            className="h-9 rounded-md border border-input bg-transparent px-2.5 text-sm text-ink sm:max-w-md"
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
            }}
          >
            {choices.map((one) => (
              <option key={one.value} value={one.value}>
                {one.label}
              </option>
            ))}
          </select>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="sm" className="min-h-11 sm:min-h-8" disabled={busy} aria-label={`${SAVE}: ${row.label}`}>
            {SAVE}
          </Button>
          {mayReturnToDefault(row) ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-h-11 sm:min-h-8"
              disabled={busy}
              aria-label={`${RETURN_TO_DEFAULT}: ${row.label}`}
              onClick={() => {
                setFailure(null);
                setAsking("default");
              }}
            >
              {RETURN_TO_DEFAULT}
            </Button>
          ) : null}
        </div>
      </div>
      {zones.length === 0 ? null : (
        <datalist id={suggestions}>
          {zones.map((one) => (
            <option key={one} value={one} />
          ))}
        </datalist>
      )}
      <p id={hint} className="m-0 text-[12.5px] leading-snug text-dim">
        {formatOf(row.name)}
      </p>
      {failure === null ? null : <FailureState failure={failure} title={asking === "default" ? NOT_RETURNED : NOT_SAVED} />}
      <ConfirmDialog
        open={asking === "save"}
        question={saveQuestion(row)}
        consequence={saveConsequence(row, value)}
        confirmLabel={SAVE_CHANGE}
        cancelLabel={KEEP_SETTING}
        busy={busy}
        onConfirm={save}
        onCancel={() => {
          setAsking(null);
        }}
      />
      <ConfirmDialog
        open={asking === "default"}
        question={defaultQuestion(row)}
        consequence={defaultConsequence(row)}
        confirmLabel={RETURN_TO_DEFAULT}
        cancelLabel={KEEP_SAVED}
        busy={busy}
        onConfirm={returnToDefault}
        onCancel={() => {
          setAsking(null);
        }}
      />
    </form>
  );
}

/** One setting's row: its name and where the value came from, then its field or its reason. */
function SettingLine({
  row,
  onSaved,
}: {
  readonly row: SettingRow;
  readonly onSaved: (body: SettingsBody, told: string) => void;
}) {
  return (
    <div data-slot="setting" className="flex min-w-0 flex-col gap-2 border-b border-line py-3 first:pt-0 last:border-b-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="m-0 text-[13.5px] font-medium text-ink">{row.label}</h3>
        <Chip>{sourceWords(row.source)}</Chip>
      </div>
      {row.editable ? (
        <EditableSetting key={`${row.value} ${row.source}`} row={row} onSaved={onSaved} />
      ) : (
        <>
          <p className="m-0 font-mono text-[12.5px] text-ink [overflow-wrap:anywhere]">{shownValue(row)}</p>
          <p className="m-0 text-[12.5px] leading-snug text-dim">{row.read_only_because}</p>
        </>
      )}
    </div>
  );
}

function SettingsView({
  body,
  onSaved,
}: {
  readonly body: SettingsBody;
  readonly onSaved: (body: SettingsBody, told: string) => void;
}) {
  const everyRow = body.groups.flatMap((group) => group.settings);
  return (
    <>
      {body.findings.length === 0 ? null : (
        <SectionCard title={FINDINGS_HEADING}>
          <div className="flex flex-col gap-1.5">
            {body.findings.map((one) => (
              <Note key={one} kind="not-yet">
                {one}
              </Note>
            ))}
          </div>
        </SectionCard>
      )}
      {body.groups.length === 0 ? (
        <EmptyState title={NO_SETTINGS} description={NO_SETTINGS_DESCRIPTION} />
      ) : null}
      {body.groups.map((group) => (
        <SectionCard key={group.group} title={group.title} lede={group.group === "models" ? body.profile : undefined}>
          {group.settings.map((row) => (
            <SettingLine key={row.name} row={row} onSaved={onSaved} />
          ))}
        </SectionCard>
      ))}
      <SectionCard title={FURNISHED_HEADING}>
        <FactList>
          <Fact label="Roles, packs and scope">{furnishedWords(body.starter.furnished)}</Fact>
          <Fact label="Standard agents">{body.starter.agents_told}</Fact>
        </FactList>
      </SectionCard>
      <SectionCard title={LEAVING_HEADING} lede={body.leaving.told}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>What</TableHead>
              <TableHead>Removed by</TableHead>
              <TableHead>How</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {body.leaving.steps.map((step) => (
              <TableRow key={step.what}>
                <TableCell className="align-top whitespace-normal [overflow-wrap:anywhere]">
                  <span className="font-mono text-[12px]">{step.what}</span>
                  {step.holds === "" ? null : <span className="block text-[12px] text-dim">{step.holds}</span>}
                </TableCell>
                <TableCell className="align-top whitespace-normal">{byWords(step.by)}</TableCell>
                <TableCell className="align-top whitespace-normal [overflow-wrap:anywhere]">{step.how}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className="m-0 mt-2 text-[12.5px] text-dim">
          The certificate names the day the last backup expires: {body.leaving.backup_retention_days} days after the last
          part is removed.
        </p>
      </SectionCard>
      <Advanced>
        <p className="m-0 text-[12.5px] text-dim">{VARIABLES_LABEL}</p>
        <FactList>
          {everyRow.map((row) => (
            <Fact key={row.name} label={row.label}>
              <span className="font-mono text-[11.5px]">{row.name}</span>
              {row.read_by.length === 0 ? null : (
                <span className="block font-mono text-[11px] text-dim">{row.read_by.join(", ")}</span>
              )}
            </Fact>
          ))}
          <Fact label="Roles">{body.starter.roles.join(", ")}</Fact>
          <Fact label="Permission packs">{body.starter.packs.join(", ")}</Fact>
          <Fact label="Scopes">{body.starter.scopes.join(", ")}</Fact>
          <Fact label="Handover procedure">
            <span className="font-mono text-[11.5px]">{body.leaving.procedure}</span>
            {body.leaving.commands.map((command) => (
              <span key={command} className="block font-mono text-[11px] text-dim">
                {command}
              </span>
            ))}
          </Fact>
        </FactList>
      </Advanced>
    </>
  );
}

export function SettingsPage() {
  const answer = useResource<unknown>(SETTINGS_API_PATH);
  const [written, setWritten] = useState<{ readonly body: SettingsBody; readonly told: string } | null>(null);
  const onSaved = (body: SettingsBody, told: string) => {
    setWritten({ body, told });
  };

  let content;
  if (written !== null) {
    content = (
      <>
        <div role="status">
          <Note kind="done">{written.told}</Note>
        </div>
        <SettingsView body={written.body} onSaved={onSaved} />
      </>
    );
  } else if (answer.busy) {
    content = <LoadingState label={READING_SETTINGS} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readSettings(answer.data);
    content = body === null ? <Note>{UNREADABLE_SETTINGS}</Note> : <SettingsView body={body} onSaved={onSaved} />;
  }

  return (
    <div data-slot="settings-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: SETTINGS_LABEL }]} title={SETTINGS_LABEL} lede={SETTINGS_LEDE} />
      {content}
    </div>
  );
}
