/**
 * Websites for agents' browsers on the Features page: the websites an administrator declared, the
 * exceptions and exemptions signed for them, and the three forms that declare a website and sign
 * either permission.
 *
 * **Nothing here decides who may.** The route asks for `admin:browser` over everything and refuses
 * everybody else before it reads anything, and a refusal is shown as the API wrote it. Each website
 * and permission the API sends is drawn; none is named here.
 *
 * **A write is followed by a fresh read**, so the page shows what the database holds. Retiring a
 * website and revoking a permission are always offered, because the switch that opens a permission
 * does not close the way back.
 *
 * Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
 */

import { useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  EmptyList,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import {
  BROWSER_API_PATH,
  BROWSER_TITLE,
  DECLARATION_LABEL,
  DECLARE,
  EXCEPTIONS_API_PATH,
  EXEMPTIONS_API_PATH,
  grantSentence,
  NO_GRANTS,
  NO_GRANTS_TITLE,
  NO_TARGETS,
  NO_TARGETS_TITLE,
  NOT_CHANGED,
  NOT_JSON,
  OPENS_NO_BROWSER,
  READING_BROWSER,
  readBrowser,
  readDays,
  readDeclaration,
  retirePath,
  revokePath,
  SIGN_EXCEPTION,
  SIGN_EXEMPTION,
  SWITCHED_OFF,
  TARGETS_API_PATH,
  UNREADABLE_BROWSER,
  UNREADABLE_HEADING,
  type BrowserBody,
  type GrantRow,
  type TargetRow,
} from "../browserQuery";

function TargetCard({
  row,
  busy,
  onRetire,
}: {
  readonly row: TargetRow;
  readonly busy: boolean;
  readonly onRetire: (row: TargetRow) => void;
}) {
  return (
    <SectionCard
      title={row.name}
      headingLevel="h3"
      action={
        <Button
          size="sm"
          variant="outline"
          className="min-h-11 sm:min-h-8"
          disabled={busy}
          aria-label={`Retire: ${row.name}`}
          onClick={() => {
            onRetire(row);
          }}
        >
          Retire
        </Button>
      }
    >
      <p className="m-0 text-[13px] text-body">Opens only {row.origins.join(", ")}.</p>
      {row.surfaces.map((one) => (
        <p key={one.name} className="m-0 mt-1 text-[12.5px] text-dim">
          {one.name}: {one.path} ({one.verbs.join(", ")})
          {one.reads.length === 0 ? "" : `, reads ${one.reads.join(", ")}`}
          {one.controls.length === 0 ? "" : `; ${one.controls.join("; ")}`}
        </p>
      ))}
      {row.bindings.map((one) => (
        <p key={one.placeholder} className="m-0 mt-1 text-[12.5px] text-dim">
          Signs in with {one.placeholder} ({one.kind}) on {one.origin}.
        </p>
      ))}
      {row.api_tools.length === 0 ? null : (
        <p className="m-0 mt-1 text-[12.5px] text-dim">
          Already has an API: {row.api_tools.join(", ")}.
        </p>
      )}
      <p className="m-0 mt-1 text-[12px] text-dim">Declared by {row.declared_by}.</p>
    </SectionCard>
  );
}

function GrantCard({
  row,
  busy,
  onRevoke,
}: {
  readonly row: GrantRow;
  readonly busy: boolean;
  readonly onRevoke: (row: GrantRow) => void;
}) {
  return (
    <SectionCard
      title={grantSentence(row)}
      headingLevel="h3"
      action={
        <>
          <Chip>{row.kind}</Chip>
          <Button
            size="sm"
            variant="outline"
            className="min-h-11 sm:min-h-8"
            disabled={busy}
            aria-label={`Revoke: ${row.kind} ${row.what}`}
            onClick={() => {
              onRevoke(row);
            }}
          >
            Revoke
          </Button>
        </>
      }
    >
      <p className="m-0 text-[13px] text-body">{row.reason}</p>
      <p className="m-0 mt-1 text-[12px] text-dim">
        Signed by {row.signed_by}; ends {new Date(row.expires_at).toLocaleDateString("en-GB")}.
      </p>
    </SectionCard>
  );
}

function Form({
  title,
  busyLabel,
  fields,
  onSend,
}: {
  readonly title: string;
  readonly busyLabel: string;
  readonly fields: readonly { readonly id: string; readonly label: string; readonly area?: boolean }[];
  readonly onSend: (values: Record<string, string>) => Promise<ApiFailure | string | null>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  function send(): void {
    setBusy(true);
    void (async () => {
      const outcome = await onSend(values);
      setBusy(false);
      if (outcome === null) {
        setFailure(null);
        setProblem(null);
        setValues({});
      } else if (typeof outcome === "string") {
        setProblem(outcome);
      } else {
        setProblem(null);
        setFailure(outcome);
      }
    })();
  }

  return (
    <SectionCard title={title} headingLevel="h3">
      {fields.map((one) => (
        <div key={one.id} className="mb-2">
          <label className="m-0 block text-[13px] text-body" htmlFor={`browser-${one.id}`}>
            {one.label}
          </label>
          {one.area ? (
            <Textarea
              id={`browser-${one.id}`}
              value={values[one.id] ?? ""}
              rows={8}
              className="mt-1 font-mono text-[12px]"
              onChange={(event) => {
                setValues({ ...values, [one.id]: event.target.value });
              }}
            />
          ) : (
            <Input
              id={`browser-${one.id}`}
              value={values[one.id] ?? ""}
              className="mt-1"
              onChange={(event) => {
                setValues({ ...values, [one.id]: event.target.value });
              }}
            />
          )}
        </div>
      ))}
      {problem === null ? null : <Note>{problem}</Note>}
      {failure === null ? null : <FailureState failure={failure} title={NOT_CHANGED} />}
      <Button
        size="sm"
        className="min-h-11 sm:min-h-8"
        disabled={busy || fields.some((one) => (values[one.id] ?? "").trim() === "")}
        onClick={send}
      >
        {busy ? busyLabel : title}
      </Button>
    </SectionCard>
  );
}

function Panel({ body, onChanged }: { readonly body: BrowserBody; readonly onChanged: (told: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function ended(done: Promise<{ ok: true } | { ok: false; failure: ApiFailure }>, told: string): void {
    setBusy(true);
    void (async () => {
      const result = await done;
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onChanged(told);
    })();
  }

  function retire(row: TargetRow): void {
    ended(request<unknown>(retirePath(row.name), { method: "POST" }), `"${row.name}" is retired.`);
  }

  function revoke(row: GrantRow): void {
    ended(request<unknown>(revokePath(row.seq), { method: "POST" }), `The ${row.kind} for ${row.what} is revoked.`);
  }

  async function signed(
    done: Promise<{ ok: true } | { ok: false; failure: ApiFailure }>,
    told: string,
  ): Promise<ApiFailure | null> {
    const result = await done;
    if (!result.ok) {
      return result.failure;
    }
    onChanged(told);
    return null;
  }

  return (
    <>
      <Note>{OPENS_NO_BROWSER}</Note>
      {body.declarations_are_on ? null : <Note>{SWITCHED_OFF}</Note>}
      {body.targets.length === 0 ? (
        <EmptyList
          title={NO_TARGETS_TITLE}
          description={NO_TARGETS}
          adds="Declare a website with the form on this screen."
          by={["super_admin"]}
        />
      ) : null}
      {body.targets.map((row) => (
        <TargetCard
          key={row.name}
          row={row}
          busy={busy}
          onRetire={retire}
        />
      ))}
      {body.unreadable.length === 0 ? null : (
        <Note>
          {UNREADABLE_HEADING}: {body.unreadable.join(", ")}. They are not declared; declare them again.
        </Note>
      )}
      {body.grants.length === 0 ? (
        <EmptyList
          title={NO_GRANTS_TITLE}
          description={NO_GRANTS}
          adds="Sign an exception or an exemption with the forms on this screen."
          by={["super_admin"]}
        />
      ) : null}
      {body.grants.map((row) => (
        <GrantCard
          key={row.seq}
          row={row}
          busy={busy}
          onRevoke={revoke}
        />
      ))}
      {failure === null ? null : <FailureState failure={failure} title={NOT_CHANGED} />}
      {body.declarations_are_on ? (
        <>
          <Form
            title={DECLARE}
            busyLabel="Declaring"
            fields={[{ id: "declaration", label: DECLARATION_LABEL, area: true }]}
            onSend={async (values) => {
              const declaration = readDeclaration(values["declaration"] ?? "");
              if (declaration === null) {
                return NOT_JSON;
              }
              return signed(
                request<unknown>(TARGETS_API_PATH, { method: "POST", body: { declaration } }),
                "The website is declared.",
              );
            }}
          />
          <Form
            title={SIGN_EXCEPTION}
            busyLabel="Signing"
            fields={[
              { id: "exception-target", label: "Website" },
              { id: "exception-surface", label: "Page" },
              { id: "exception-days", label: `Days (1 to ${String(body.most_days)})` },
              { id: "exception-reason", label: "Why" },
            ]}
            onSend={async (values) => {
              const days = readDays(values["exception-days"] ?? "", body.most_days);
              if (days === null) {
                return `Days is a whole number from 1 to ${String(body.most_days)}.`;
              }
              return signed(
                request<unknown>(EXCEPTIONS_API_PATH, {
                  method: "POST",
                  body: {
                    target: values["exception-target"],
                    surface: values["exception-surface"],
                    days,
                    reason: values["exception-reason"],
                  },
                }),
                "The exception is signed.",
              );
            }}
          />
          <Form
            title={SIGN_EXEMPTION}
            busyLabel="Signing"
            fields={[
              { id: "exemption-skill", label: "Skill" },
              { id: "exemption-target", label: "Website" },
              { id: "exemption-days", label: `Days (1 to ${String(body.most_days)})` },
              { id: "exemption-reason", label: "Why" },
            ]}
            onSend={async (values) => {
              const days = readDays(values["exemption-days"] ?? "", body.most_days);
              if (days === null) {
                return `Days is a whole number from 1 to ${String(body.most_days)}.`;
              }
              return signed(
                request<unknown>(EXEMPTIONS_API_PATH, {
                  method: "POST",
                  body: {
                    skill: values["exemption-skill"],
                    target: values["exemption-target"],
                    days,
                    reason: values["exemption-reason"],
                  },
                }),
                "The exemption is signed.",
              );
            }}
          />
        </>
      ) : null}
      <Advanced>
        <FactList>
          {body.targets.map((one) => (
            <Fact key={one.name} label={one.name}>
              <span className="block text-[12px] text-dim">
                {one.bindings.map((binding) => `${binding.placeholder} -> ${binding.path}`).join("; ") ||
                  "no credential bound"}
              </span>
            </Fact>
          ))}
        </FactList>
      </Advanced>
    </>
  );
}

export function BrowserPanel() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<unknown>(BROWSER_API_PATH, version);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_BROWSER} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readBrowser(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_BROWSER}</Note>
      ) : (
        <Panel
          body={body}
          onChanged={(sentence) => {
            setTold(sentence);
            setVersion((count) => count + 1);
          }}
        />
      );
  }
  return (
    <section data-slot="browser-panel" aria-label={BROWSER_TITLE} className="flex min-w-0 flex-col gap-3">
      <h2 className="m-0 text-[15px] font-semibold">{BROWSER_TITLE}</h2>
      {told === null ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      {content}
    </section>
  );
}
