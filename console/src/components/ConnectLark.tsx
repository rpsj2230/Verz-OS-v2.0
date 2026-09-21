/**
 * Connect Lark: from no Lark app at all to each chosen use switched on, on the Connectors screen.
 *
 * Four parts, in the order somebody does them: choose what the app is for, follow the steps in
 * Lark's developer console (built by the API for exactly those uses), paste the App ID and App
 * Secret and test, then save. Each use's standing is drawn above them, so the same card is the
 * status afterwards.
 *
 * **The steps and the scopes are the API's.** Choosing a use reads the guide again, so the scope
 * list shown is the one the test checks. See `pages/larkConnectQuery.ts`.
 *
 * **Testing reads and writes nothing; saving keeps the secret in the vault and switches the uses
 * on, and it is confirmed first**, because switching the staff list on replaces whichever staff
 * source the install had. The confirmation names the uses and says the secret is supplied, never
 * what it is.
 *
 * **The staff list is handed to the Staff sources screen afterwards**, which is where its runs, a
 * dry run and the leavers are, and the card links there.
 *
 * Task ids: M11.9.4
 */

import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import {
  allWorking,
  guidePath,
  LARK_API_PATH,
  LARK_TEST_API_PATH,
  larkBody,
  toggled,
  verdictWords,
  type LarkGuide,
  type LarkSaved,
  type LarkTested,
} from "../pages/larkConnectQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import { ConfirmAction } from "./ConfirmAction";

export const CONNECT_LARK = "Connect Lark";
export const WHAT_FOR = "What the Lark app is for";
export const STEPS_IN_LARK = "In Lark's developer console";
export const SCOPES_TO_ADD = "Scopes to add";
export const PASTE_AND_TEST = "Paste the App ID and App Secret, then test";
export const TEST_CONNECTION = "Test connection";
export const SAVE_LARK = "Save and switch on";
export const KEEP_AS_IS = "Change nothing";
export const NOT_SAVED = "Lark was not connected";
export const NOT_TESTED = "The test did not run";
export const SECRET_SUPPLIED = "Supplied, and never shown again";
export const STAFF_SOURCES_LINK = "Open Staff sources";

const FORM = "connect-lark";
const FIELDS = ["app_id", "app_secret", "uses", "platform", "base_link"];

function Standing({ guide }: { readonly guide: LarkGuide }) {
  return (
    <dl className="fields" aria-label="Where each Lark use stands">
      {guide.uses.map((one) => (
        <div className="fields__row" key={one.name}>
          <dt>{one.label}</dt>
          <dd>
            <span>{one.status}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Results({ tested }: { readonly tested: LarkTested }) {
  return (
    <section aria-label="Test results">
      <p className={tested.accepted ? undefined : "note"}>{tested.told}</p>
      {tested.uses.length === 0 ? null : (
        <dl className="fields" aria-label="What the test found for each use">
          {tested.uses.map((one) => (
            <div className="fields__row" key={one.name}>
              <dt>{one.label}</dt>
              <dd>
                <strong>{verdictWords(one.verdict)}</strong>
                <p className="note">{one.told}</p>
                {one.missing.length === 0 ? null : (
                  <ul aria-label={`Scopes to add for ${one.label}`}>
                    {one.missing.map((scope) => (
                      <li key={scope}>
                        <code>{scope}</code>
                      </li>
                    ))}
                  </ul>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function Wizard({ guide, onChoose, onSaved }: {
  readonly guide: LarkGuide;
  readonly onChoose: (uses: string[], platform: string) => void;
  readonly onSaved: (told: string) => void;
}) {
  const [appId, setAppId] = useState("");
  const [secret, setSecret] = useState("");
  const [baseLink, setBaseLink] = useState(guide.base);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState(false);
  const [tested, setTested] = useState<LarkTested | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [saved, setSaved] = useState<LarkSaved | null>(null);
  const chosen = guide.chosen;
  const mayAll = chosen.length > 0 && guide.uses.filter((one) => chosen.includes(one.name)).every((one) => one.may_switch_on);
  const problems = failure?.problems ?? [];
  // Nothing is sent from a blank form: both buttons wait for an App ID and an App Secret.
  const typed = appId.trim() !== "" && secret.trim() !== "";

  function test(event: FormEvent<HTMLFormElement>): void {
    // Never a native submission: a GET with the secret in the query string.
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    setTested(null);
    void (async () => {
      const result = await request<LarkTested>(LARK_TEST_API_PATH, {
        method: "POST",
        body: larkBody(appId, secret, chosen, guide.platform, baseLink),
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setTested(result.data);
    })();
  }

  function save(): void {
    const body = larkBody(appId, secret, chosen, guide.platform, baseLink);
    setBusy(true);
    // The secret leaves the field before the request does. See `THE_SECRET_STAYS_IN_ITS_FIELD`.
    setSecret("");
    void (async () => {
      const result = await request<LarkSaved>(LARK_API_PATH, { method: "POST", body });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setSaved(result.data);
      onSaved(result.data.told);
    })();
  }

  return (
    <>
      <h3>{WHAT_FOR}</h3>
      <fieldset className="form" aria-label={WHAT_FOR}>
        {guide.uses.map((one) => (
          <div className="rjsf-field" key={one.name}>
            <label>
              <input
                type="checkbox"
                name="uses"
                checked={chosen.includes(one.name)}
                disabled={busy || !one.may_switch_on}
                onChange={(event) => {
                  setTested(null);
                  onChoose(toggled(guide.uses, chosen, one.name, event.target.checked), guide.platform);
                }}
              />{" "}
              {one.label}
            </label>
            <p className="field-description">{one.what}</p>
          </div>
        ))}
        <label className="control-label" htmlFor={`${FORM}-platform`}>
          Lark platform
        </label>
        <select
          id={`${FORM}-platform`}
          className="form-control"
          value={guide.platform}
          disabled={busy}
          onChange={(event) => {
            onChoose(chosen, event.target.value);
          }}
        >
          {guide.platforms.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
      </fieldset>

      <h3>{STEPS_IN_LARK}</h3>
      <ol aria-label={STEPS_IN_LARK}>
        {guide.steps.map((one) => (
          <li key={one.title}>
            <strong>{one.title}.</strong> {one.text}
          </li>
        ))}
      </ol>
      {guide.scopes.length === 0 ? null : (
        <>
          <h3>{SCOPES_TO_ADD}</h3>
          <ul aria-label={SCOPES_TO_ADD}>
            {guide.scopes.map((one) => (
              <li key={one.name}>
                <code>{one.name}</code> {one.read_only ? "(read-only)" : "(the one write)"}: {one.what}
              </li>
            ))}
          </ul>
        </>
      )}
      {chosen.includes("chat_channel") ? (
        <p className="note">
          {guide.channel_note}
          {guide.events_address === "" ? null : (
            <>
              {" "}
              <code>{guide.events_address}</code>
            </>
          )}
        </p>
      ) : null}

      <h3>{PASTE_AND_TEST}</h3>
      <p className="note">{guide.test_note}</p>
      {guide.vault_told === "" ? null : <p className="note">{guide.vault_told}</p>}
      {failure === null ? null : (
        <FailureNotice failure={failure} title={tested === null && !pending ? NOT_TESTED : NOT_SAVED} fields={FIELDS} />
      )}
      <FieldProblems problems={problems} form={FORM} names="uses" />
      <form className="form" noValidate autoComplete="off" onSubmit={test}>
        <div className="rjsf-field">
          <label className="control-label" htmlFor={`${FORM}-app_id`}>
            App ID
          </label>
          <input
            id={`${FORM}-app_id`}
            className="form-control"
            type="text"
            name="app_id"
            value={appId}
            autoComplete="off"
            spellCheck={false}
            {...problemAttributes(problems, FORM, "app_id")}
            disabled={busy}
            onChange={(event) => {
              setAppId(event.target.value);
            }}
          />
          <FieldProblems problems={problems} form={FORM} names="app_id" />
        </div>
        <div className="rjsf-field">
          <label className="control-label" htmlFor={`${FORM}-app_secret`}>
            App Secret
          </label>
          <input
            id={`${FORM}-app_secret`}
            className="form-control"
            type="text"
            name="app_secret"
            value={secret}
            autoComplete="off"
            spellCheck={false}
            {...problemAttributes(problems, FORM, "app_secret")}
            disabled={busy}
            onChange={(event) => {
              setSecret(event.target.value);
            }}
          />
          <p className="field-description">Kept in the vault when you save, and never shown again.</p>
          <FieldProblems problems={problems} form={FORM} names="app_secret" />
        </div>
        {chosen.includes("knowledge_base") ? (
          <div className="rjsf-field">
            <label className="control-label" htmlFor={`${FORM}-base_link`}>
              Link of the Base to read
            </label>
            <input
              id={`${FORM}-base_link`}
              className="form-control"
              type="text"
              name="base_link"
              value={baseLink}
              autoComplete="off"
              spellCheck={false}
              {...problemAttributes(problems, FORM, "base_link")}
              disabled={busy}
              onChange={(event) => {
                setBaseLink(event.target.value);
              }}
            />
            <FieldProblems problems={problems} form={FORM} names="base_link" />
          </div>
        ) : null}
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy || !mayAll || !typed}>
            {TEST_CONNECTION}
          </button>
          <button
            type="button"
            className="button"
            disabled={busy || !mayAll || !typed || (tested !== null && !tested.accepted)}
            onClick={() => {
              setPending(true);
            }}
          >
            {SAVE_LARK}
          </button>
        </div>
      </form>
      {tested === null ? null : <Results tested={tested} />}
      {tested !== null && !allWorking(tested) ? (
        <p className="note">Fix what the test found in Lark, then test again before saving.</p>
      ) : null}
      {!pending ? null : (
        <ConfirmAction
          question={`${SAVE_LARK}?`}
          consequence={
            "The App Secret is kept in the vault for each use below and the uses are switched on. " +
            "Switching the staff list on makes Lark this install's staff source. " +
            guide.knowledge_note
          }
          details={
            <dl className="fields" aria-label="What will be switched on">
              {guide.uses
                .filter((one) => chosen.includes(one.name))
                .map((one) => (
                  <div className="fields__row" key={one.name}>
                    <dt>{one.label}</dt>
                    <dd>Switched on</dd>
                  </div>
                ))}
              <div className="fields__row">
                <dt>App Secret</dt>
                <dd>{SECRET_SUPPLIED}</dd>
              </div>
            </dl>
          }
          confirmLabel={SAVE_LARK}
          cancelLabel={KEEP_AS_IS}
          busy={busy}
          onConfirm={save}
          onCancel={() => {
            setPending(false);
          }}
        />
      )}
      {saved !== null && saved.switched_on.includes("staff_list") ? (
        <p>
          <Link to={saved.staff_sources_screen}>{STAFF_SOURCES_LINK}</Link> to run a dry run of the staff
          list and see who would join and leave.
        </p>
      ) : null}
    </>
  );
}

export function ConnectLark() {
  const [uses, setUses] = useState<string[] | null>(null);
  const [platform, setPlatform] = useState("");
  const [generation, setGeneration] = useState(0);
  const answer = useResource<LarkGuide>(guidePath(uses, platform), generation);
  // The last guide read stays drawn while the next one is asked for, so choosing a use does not
  // unmount the form and lose what was typed into it.
  const [guide, setGuide] = useState<LarkGuide | null>(null);
  useEffect(() => {
    if (answer.data !== null) {
      setGuide(answer.data);
    }
  }, [answer.data]);
  return (
    <section className="card" aria-label={CONNECT_LARK}>
      <h2>{CONNECT_LARK}</h2>
      {answer.failure ? <FailureNotice failure={answer.failure} /> : null}
      {guide === null ? (
        answer.failure ? null : (
          <p className="note" role="status">
            Reading how Lark is connected.
          </p>
        )
      ) : (
        <>
          <Standing guide={guide} />
          <Wizard
            guide={guide}
            onChoose={(next, where) => {
              setUses(next);
              setPlatform(where);
            }}
            onSaved={() => {
              setUses(null);
              setGeneration((current) => current + 1);
            }}
          />
        </>
      )}
    </section>
  );
}
