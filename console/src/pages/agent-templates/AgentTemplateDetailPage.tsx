/**
 * One template on the shared page kit: what it is for, what an install of it would ask for, its
 * starting leash and instructions, and the install itself where a published version can be.
 *
 * **What it asks for is a request and never a grant.** Skills, connectors, tools and capabilities
 * are the manifest's; installing gives the new agent no reach its callers lack, which the page says
 * once beside them.
 *
 * **Install is live only for a version this install can install.** The version route answers the
 * digest the install must name and, when it cannot be installed here, the sentence why; a built-in
 * template has no published version, and a reader without the install authority is refused, and
 * both read as the one sentence `NO_INSTALLABLE_VERSION`, because the page cannot tell them apart
 * and must not try. A new agent starts disabled and at Shadow, which the confirmation says in the
 * API's words, and the page then opens it.
 *
 * **Withdraw has no route**, so it is `kit/UnavailableAction` with `templateActions.ts`' sentence.
 *
 * Task ids: M27.11.7, M27.16.1
 */

import { useId, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import type { components } from "../../api/schema";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  Chip,
  ConfirmDialog,
  DetailHeader,
  DetailPage,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  LoadingState,
  Note,
  SectionCard,
  StatCard,
  UnavailableAction,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { TEMPLATES_API_PATH } from "../agentTemplatesQuery";
import { agentAddress } from "../agents/AgentsPage";
import { ACT_LABELS, originWords, rungWords, UNAVAILABLE } from "./templateActions";
import { TEMPLATES_HEADING } from "./AgentTemplatesPage";

export type TemplateDetail = components["schemas"]["TemplateDetailView"];
export type TemplateVersion = components["schemas"]["TemplateVersionView"];

export const READING_TEMPLATE = "Reading this template.";
export const UNREADABLE_TEMPLATE = "The answer could not be read as a template.";
export const INSTALL_HEADING = "Install as a new agent";
export const NO_INSTALLABLE_VERSION =
  "No version of this template can be installed from here. A template is installed from a version this install has published.";
export const INSTALLING_NEVER_WIDENS =
  "Installing never widens anyone. What a template asks for is checked against whoever calls the agent, every time.";
export const NAME_HINT = "Up to 120 characters. Leave it as it is to use the template's own name.";
export const DEPARTMENT_HINT = "Ticked, only people in your department can find it; otherwise only you can, until it is published.";
export const NOT_INSTALLED = "The template was not installed";
export const CANCEL = "Change nothing";
export const NOTHING_LISTED = "Nothing";

export function templateApiPath(templateId: string): string {
  return `${TEMPLATES_API_PATH}/${encodeURIComponent(templateId)}`;
}

export function versionApiPath(templateId: string, version: number): string {
  return `${templateApiPath(templateId)}/versions/${String(version)}`;
}

export function installApiPath(templateId: string, version: number): string {
  return `${versionApiPath(templateId, version)}/install`;
}

/** Read `TemplateDetailView`, or null for any other body. */
export function readTemplate(payload: unknown): TemplateDetail | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<TemplateDetail>;
  return typeof body.entry === "object" && body.entry !== null && Array.isArray(body.skills) ? (payload as TemplateDetail) : null;
}

function Chips({ values }: { readonly values: readonly string[] }) {
  if (values.length === 0) {
    return <span className="text-[12.5px] text-dim">{NOTHING_LISTED}</span>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {values.map((one) => (
        <Chip key={one} mono>
          {one}
        </Chip>
      ))}
    </span>
  );
}

function InstallCard({ template }: { readonly template: TemplateDetail }) {
  const navigate = useNavigate();
  const { entry } = template;
  const version = useResource<TemplateVersion>(versionApiPath(entry.template_id, entry.version));
  const [name, setName] = useState(entry.display_name);
  const [forDepartment, setForDepartment] = useState(false);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const nameId = useId();
  const departmentId = useId();

  if (version.busy) {
    return (
      <SectionCard title={INSTALL_HEADING}>
        <LoadingState label="Reading whether this version can be installed." rows={1} />
      </SectionCard>
    );
  }
  const found = version.failure === null ? version.data : null;
  if (found === null || found === undefined) {
    return (
      <SectionCard title={INSTALL_HEADING}>
        <Note>{NO_INSTALLABLE_VERSION}</Note>
      </SectionCard>
    );
  }
  if (found.unavailable !== null && found.unavailable !== undefined) {
    return (
      <SectionCard title={INSTALL_HEADING}>
        <Note kind="not-yet">{found.unavailable}</Note>
      </SectionCard>
    );
  }

  function send(digest: string): void {
    setBusy(true);
    void (async () => {
      const trimmed = name.trim();
      const body = {
        expected_digest: digest,
        for_department: forDepartment,
        ...(trimmed === "" || trimmed === entry.display_name ? {} : { display_name: trimmed }),
      };
      const result = await request<unknown>(installApiPath(entry.template_id, entry.version), { method: "POST", body });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const agentId = (result.data as { agent?: { agent_id?: unknown } } | null)?.agent?.agent_id;
      setPending(false);
      if (typeof agentId === "string") {
        navigate(agentAddress(agentId));
      }
    })();
  }

  return (
    <SectionCard title={INSTALL_HEADING} lede={found.starts}>
      <form
        className="flex min-w-0 flex-col gap-4"
        noValidate
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          setFailure(null);
          setPending(true);
        }}
      >
        <div className="flex flex-col gap-2">
          <Label htmlFor={nameId}>Name of the new agent</Label>
          <Input
            id={nameId}
            name="display_name"
            value={name}
            maxLength={120}
            aria-describedby={`${nameId}-hint`}
            className="sm:max-w-md"
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
          <p id={`${nameId}-hint`} className="m-0 text-[12.5px] leading-snug text-dim">
            {NAME_HINT}
          </p>
        </div>
        <div className="flex items-start gap-2">
          <input
            id={departmentId}
            type="checkbox"
            name="for_department"
            className="mt-1 size-4"
            checked={forDepartment}
            aria-describedby={`${departmentId}-hint`}
            onChange={(event) => {
              setForDepartment(event.target.checked);
            }}
          />
          <div className="flex flex-col gap-1">
            <Label htmlFor={departmentId}>For my department</Label>
            <p id={`${departmentId}-hint`} className="m-0 text-[12.5px] leading-snug text-dim">
              {DEPARTMENT_HINT}
            </p>
          </div>
        </div>
        {failure === null ? null : <FailureState failure={failure} title={NOT_INSTALLED} />}
        <div>
          <Button type="submit" disabled={busy} className="min-h-11 sm:min-h-9">
            {ACT_LABELS.install}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={pending}
        question={`Install ${name.trim() === "" ? entry.display_name : name.trim()} from ${entry.display_name}, version ${String(entry.version)}?`}
        consequence={found.starts}
        details={failure === null ? undefined : <FailureState failure={failure} title={NOT_INSTALLED} />}
        confirmLabel={ACT_LABELS.install}
        cancelLabel={CANCEL}
        busy={busy}
        onConfirm={() => {
          send(found.content_digest);
        }}
        onCancel={() => {
          setPending(false);
        }}
      />
    </SectionCard>
  );
}

function TemplateView({ template }: { readonly template: TemplateDetail }) {
  const { entry } = template;
  return (
    <DetailPage
      crumbs={[{ label: TEMPLATES_HEADING, to: "/agent-templates" }, { label: entry.display_name }]}
      header={
        <DetailHeader
          name={entry.display_name}
          headingId="agent-template-heading"
          pills={
            <>
              <Chip>{originWords(entry.origin)}</Chip>
              <Chip>{`Version ${String(entry.version)}`}</Chip>
            </>
          }
          actions={
            <UnavailableAction label={ACT_LABELS.withdraw} text={ACT_LABELS.withdraw} reason={UNAVAILABLE.withdraw.reason} />
          }
          figures={
            <KpiStrip label="What this template asks for" count={4}>
              <StatCard label="Skills" value={String(template.skills.length)} />
              <StatCard label="Connectors" value={String(template.connectors.length)} />
              <StatCard label="Tools" value={String(template.tools.length)} />
              <StatCard label="Checked questions" value={String(template.golden_cases)} sub="asked before a change ships" />
            </KpiStrip>
          }
        />
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        {entry.summary === null || entry.summary === undefined ? null : <p className="m-0 max-w-[68ch] text-sm text-body">{entry.summary}</p>}
        <InstallCard template={template} />
        <SectionCard title="What it asks for" footer={<Note>{INSTALLING_NEVER_WIDENS}</Note>}>
          <FactList>
            <Fact label="Model size">{template.tier}</Fact>
            <Fact label="Skills">
              <Chips values={template.skills} />
            </Fact>
            <Fact label="Connectors">
              <Chips values={template.connectors} />
            </Fact>
            <Fact label="Tools">
              <Chips values={template.tools} />
            </Fact>
            <Fact label="Capabilities">
              <Chips values={template.capabilities} />
            </Fact>
            <Fact label="Most it may do">{template.max_side_effect}</Fact>
          </FactList>
        </SectionCard>
        <SectionCard title="Starting leash" lede="Where a person is involved before it acts. An action it names nowhere is Shadow.">
          {template.leash.length === 0 ? (
            <Note>Shadow on every action: it only practises until somebody raises it.</Note>
          ) : (
            <FactList>
              {template.leash.map((one) => (
                <Fact key={`${one.target} ${one.rung}`} label={one.target}>
                  {rungWords(one.rung)}
                </Fact>
              ))}
            </FactList>
          )}
        </SectionCard>
        {template.persona === "" ? null : (
          <SectionCard title="Instructions">
            <p className="m-0 max-h-80 overflow-y-auto whitespace-pre-wrap rounded-md bg-sunk p-3 text-[13px] leading-relaxed text-ink [overflow-wrap:anywhere]">
              {template.persona}
            </p>
          </SectionCard>
        )}
        <Advanced>
          <FactList>
            <Fact label="Template ID">
              <span className="font-mono text-[12px]">{entry.template_id}</span>
            </Fact>
            <Fact label="Published by">
              <span className="font-mono text-[12px]">{entry.published_by}</span>
            </Fact>
          </FactList>
        </Advanced>
      </div>
    </DetailPage>
  );
}

export function AgentTemplateDetailPage({ templateId }: { readonly templateId: string }) {
  const answer = useResource<unknown>(templateApiPath(templateId));
  if (answer.busy) {
    return <LoadingState label={READING_TEMPLATE} />;
  }
  if (answer.failure !== null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <h1 className="m-0 font-heading text-[22px] font-semibold text-ink">{TEMPLATES_HEADING}</h1>
        <FailureState failure={answer.failure} />
      </div>
    );
  }
  const template = readTemplate(answer.data);
  if (template === null) {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <h1 className="m-0 font-heading text-[22px] font-semibold text-ink">{TEMPLATES_HEADING}</h1>
        <Note>{UNREADABLE_TEMPLATE}</Note>
      </div>
    );
  }
  return <TemplateView template={template} />;
}
