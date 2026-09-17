/**
 * Settings: every installation value with where it came from, and the branding fields saved here.
 *
 * One card per group in the API's order. Each row shows the value as the API sent it, where it came
 * from, when a change takes effect and which modules read it. Branding rows carry a field and a Save
 * button; every other group says, in the API's words, where it is changed instead.
 *
 * **Nothing here decides who may read or save.** The route asks for `admin:install_setting` over
 * everything and refuses everybody else before it reads anything, so a reader who may not configure
 * the install sees the API's refusal and never the values.
 *
 * **A save answers with the whole screen as the database now holds it**, and that answer replaces
 * the page, so what is drawn after a save is what was stored rather than what was typed.
 *
 * **Leaving is shown and never run from here.** The last card lists what a handover exports and
 * removes, who removes each part and the command that does it on the server, as the API sends it.
 * There is no button: dropping every schema is not a click.
 *
 * Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1
 */

import { useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Chip } from "../ui/Chip";
import { FailureNotice } from "../ui/FailureNotice";
import {
  FINDINGS_HEADING,
  LEAVING_HEADING,
  READING_SETTINGS,
  SAVE,
  SAVED,
  SETTINGS_API_PATH,
  SETTINGS_CRUMB,
  SETTINGS_LABEL,
  SETTINGS_LEDE,
  STARTER_HEADING,
  UNREADABLE_SETTINGS,
  byWords,
  readSettings,
  savePath,
  sourceWords,
  type SettingRow,
  type SettingsBody,
} from "./settingsQuery";

function EditableValue({
  row,
  onSaved,
}: {
  readonly row: SettingRow;
  readonly onSaved: (body: SettingsBody) => void;
}) {
  const [value, setValue] = useState(row.value);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const id = `setting-${row.name}`;

  return (
    <form
      className="form-actions"
      onSubmit={(event) => {
        event.preventDefault();
        setBusy(true);
        void (async () => {
          const result = await request<unknown>(savePath(row.name), { method: "PUT", body: { value } });
          setBusy(false);
          if (!result.ok) {
            setFailure(result.failure);
            return;
          }
          setFailure(null);
          const body = readSettings(result.data);
          if (body !== null) {
            onSaved(body);
          }
        })();
      }}
    >
      <label htmlFor={id} className="visually-hidden">
        {row.name}
      </label>
      <input
        id={id}
        name={row.name}
        className="form-control"
        type="text"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
        }}
      />
      <button type="submit" className="button" disabled={busy} aria-label={`${SAVE}: ${row.name}`}>
        {SAVE}
      </button>
      {failure === null ? null : <FailureNotice failure={failure} />}
    </form>
  );
}

function SettingsView({ body, onSaved }: { readonly body: SettingsBody; readonly onSaved: (body: SettingsBody) => void }) {
  return (
    <>
      {body.findings.length === 0 ? null : (
        <section className="card" aria-labelledby="settings-findings">
          <h2 id="settings-findings">{FINDINGS_HEADING}</h2>
          {body.findings.map((one) => (
            <p key={one}>{one}</p>
          ))}
        </section>
      )}
      {body.groups.map((group) => (
        <section className="card" key={group.group} aria-labelledby={`settings-${group.group}`}>
          <h2 id={`settings-${group.group}`}>{group.title}</h2>
          {group.editable ? null : <p className="note">{group.changed_elsewhere}</p>}
          {group.group === "models" ? <p>{body.profile}</p> : null}
          {group.settings.map((row) => (
            <div key={row.name} className="setting-row">
              <h3>
                <code>{row.name}</code> <Chip label={sourceWords(row.source)} />
              </h3>
              {row.editable ? (
                <EditableValue key={row.value} row={row} onSaved={onSaved} />
              ) : (
                <p>
                  <code>{row.value === "" ? sourceWords(row.source) : row.value}</code>
                </p>
              )}
              <p className="note">{row.meaning}</p>
              <p className="note">{row.applies}</p>
              <p className="note">
                Read by{" "}
                {row.read_by.map((reader, index) => (
                  <span key={reader}>
                    {index === 0 ? "" : ", "}
                    <code>{reader}</code>
                  </span>
                ))}
              </p>
            </div>
          ))}
        </section>
      ))}
      <section className="card" aria-labelledby="settings-starter">
        <h2 id="settings-starter">{STARTER_HEADING}</h2>
        <p>
          Roles: {body.starter.roles.join(", ")}. Permission sets: {body.starter.packs.join(", ")}. Scopes:{" "}
          {body.starter.scopes.join(", ")}.
        </p>
        <p className="note">
          {body.starter.furnished === null
            ? "Whether it was furnished could not be read, because this process has no database."
            : body.starter.furnished
              ? "Furnished: the record of it is in the database."
              : "Not furnished yet: the application furnishes it when it next starts."}
        </p>
        <p>{body.starter.agents_told}</p>
        <p className="note">Agent templates the catalogue ships: {body.starter.agent_templates.join(", ")}.</p>
      </section>
      <section className="card" aria-labelledby="settings-leaving">
        <h2 id="settings-leaving">{LEAVING_HEADING}</h2>
        <p>{body.leaving.told}</p>
        <div className="grid">
          <div className="grid__scroll">
            <table className="grid__table">
              <thead>
                <tr>
                  <th scope="col">Store or part</th>
                  <th scope="col">Removed by</th>
                  <th scope="col">How</th>
                </tr>
              </thead>
              <tbody>
                {body.leaving.steps.map((step) => (
                  <tr key={step.what}>
                    <td>
                      <code>{step.what}</code>
                      {step.holds === "" ? null : <p className="note">{step.holds}</p>}
                    </td>
                    <td>{byWords(step.by)}</td>
                    <td>{step.how}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <p className="note">
          The certificate names the day the last backup expires: {body.leaving.backup_retention_days} days after
          the last part is removed.
        </p>
        <p className="note">
          Procedure: <code>{body.leaving.procedure}</code>
        </p>
        <ol>
          {body.leaving.commands.map((command) => (
            <li key={command}>
              <code>{command}</code>
            </li>
          ))}
        </ol>
      </section>
      <p className="note">{body.credentials}</p>
      <p className="note">{body.editable_because}</p>
    </>
  );
}

function SettingsBodyLoader({ onSaved }: { readonly onSaved: (body: SettingsBody) => void }) {
  const answer = useResource<unknown>(SETTINGS_API_PATH);
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_SETTINGS}
      </p>
    );
  }
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  const body = readSettings(answer.data);
  if (body === null) {
    return <p className="note">{UNREADABLE_SETTINGS}</p>;
  }
  return <SettingsView body={body} onSaved={onSaved} />;
}

export function Settings() {
  const [saved, setSaved] = useState<SettingsBody | null>(null);

  return (
    <article className="page">
      <p className="note">{SETTINGS_CRUMB}</p>
      <h1>{SETTINGS_LABEL}</h1>
      <p className="lede">{SETTINGS_LEDE}</p>
      {saved === null ? (
        <SettingsBodyLoader onSaved={setSaved} />
      ) : (
        <>
          <p className="note" role="status">
            {SAVED}
          </p>
          <SettingsView body={saved} onSaved={setSaved} />
        </>
      )}
    </article>
  );
}
