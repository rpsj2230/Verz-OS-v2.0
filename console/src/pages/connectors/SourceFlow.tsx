/**
 * Connecting any source other than Lark, one screen at a time, on the kit's `ConnectFlow`: the
 * vendor's steps with a picture each, then the source's own form on the last screen.
 *
 * **The steps are each connector's own**, declared beside its form in its module (`guide` on
 * `brain.connectors.declaration.ConnectorDeclaration`) and served with the form by
 * `GET /api/v1/connectors`, so this page holds no vendor's words. A console source's last step
 * asks for exactly its form's settings and its key, and that step draws `components/
 * ConnectSource.tsx`, the same form, confirmation and refusals first run uses.
 *
 * **Since 2026-09-30 no source is connected at the server (M11.7.7).** Google Drive's last step
 * takes its folder, department, answerable person and a key file chosen as a file, and the Laravel
 * views' takes each view's rule and a database user as a name and a password, through
 * `components/CredentialField.tsx`. A source the API still lists as not connectable here gets its
 * flow with no form, and today that is none but Lark's, which has its own.
 *
 * **Opened with no source, it asks which first**, listing the sources this reader may connect and
 * the ones prepared here for the server. Lark is not among them: it has its own flow and button.
 *
 * **Closing keeps the step and the settings typed, never the key.** `kit/flowMemory.ts` holds them
 * per source for as long as the tab is open, and a connection made forgets them.
 *
 * Task ids: M27.11.9, M42.6.5, M11.9.4
 */

import { ArrowRight } from "lucide-react";
import { useCallback, useState } from "react";
import { ConnectSource } from "../../components/ConnectSource";
import { ConnectFlow, FlowDialog, forgetFlow, indexOf, Note, recallFlow, rememberFlow, type FlowStep } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { offered, type Connectable, type Connectors as ConnectorsBody, type NotConnectable } from "../connectorsQuery";

export const CHOOSE_TITLE = "Connect a source";
export const CHOOSE_DESCRIPTION = "Choose the source. Each is connected one screen at a time, with a picture of every step.";
export const FLOW_DESCRIPTION =
  "One screen at a time. Close it whenever you need to: it keeps your place and the settings, never the key.";
export const SERVER_DESCRIPTION = "Prepared here one screen at a time, and finished at the server.";
export const FROM_HERE = "Connected from this screen";
export const AT_THE_SERVER = "Prepared here, finished at the server";
export const START = "Start";
export const OTHER_SOURCE = "Choose another source";
export const NOTHING_TO_CONNECT = "There is no source here you may connect. Connecting one needs the connector installation grant over it.";

/** The memory key a source's flow keeps its place under. */
export function flowKey(name: string): string {
  return `source:${name}`;
}

/** Where a source's flow was left: the step and the settings typed, never the key. */
export interface SourcePlace {
  readonly at: string;
  readonly settings: Readonly<Record<string, string>>;
}

/** A source the flow can be opened on: one this reader may connect, or one finished at the server. */
type Openable = { readonly kind: "form"; readonly source: Connectable } | { readonly kind: "server"; readonly source: NotConnectable };

function openable(page: ConnectorsBody): readonly Openable[] {
  return [
    ...offered(page.connectable)
      .filter((one) => one.steps.length > 0)
      .map((source): Openable => ({ kind: "form", source })),
    ...page.not_connectable.filter((one) => one.steps.length > 0).map((source): Openable => ({ kind: "server", source })),
  ];
}

function Chooser({ sources, onChoose }: { readonly sources: readonly Openable[]; readonly onChoose: (name: string) => void }) {
  if (sources.length === 0) {
    return <Note>{NOTHING_TO_CONNECT}</Note>;
  }
  return (
    <ul aria-label="Sources" className="m-0 flex list-none flex-col gap-2 p-0">
      {sources.map((one) => (
        <li key={one.source.name} className="flex min-w-0 items-center justify-between gap-3 rounded-md border border-line p-3">
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-[13px] font-medium text-ink">{one.source.label}</span>
            <span className="text-[12px] text-dim">
              {one.kind === "form" ? FROM_HERE : AT_THE_SERVER} · {one.source.steps.length} steps
            </span>
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="min-h-11 shrink-0 sm:min-h-8"
            aria-label={`${START}: ${one.source.label}`}
            onClick={() => {
              onChoose(one.source.name);
            }}
          >
            {START}
            <ArrowRight aria-hidden />
          </Button>
        </li>
      ))}
    </ul>
  );
}

function Flow({ page, chosen, onConnected }: { readonly page: ConnectorsBody; readonly chosen: Openable; readonly onConnected: (told: string) => void }) {
  const name = chosen.source.name;
  const steps: readonly FlowStep[] = chosen.source.steps;
  const [place, setPlace] = useState<SourcePlace>(() => recallFlow<SourcePlace>(flowKey(name)) ?? { at: steps[0]?.key ?? "", settings: {} });
  const move = useCallback(
    (next: SourcePlace) => {
      setPlace(next);
      rememberFlow<SourcePlace>(flowKey(name), next);
    },
    [name],
  );
  const last = steps[steps.length - 1];
  const panels =
    chosen.kind === "form" && last !== undefined
      ? {
          [last.key]: (
            <ConnectSource
              source={chosen.source}
              confirmation={page.confirm_connect}
              keyMaxChars={page.key_max_chars}
              keyBlank={page.key_blank}
              startSettings={place.settings}
              onSettingsChange={(settings) => {
                move({ ...place, settings });
              }}
              onConnected={(told) => {
                forgetFlow(flowKey(name));
                onConnected(told);
              }}
            />
          ),
        }
      : {};
  return (
    <ConnectFlow
      steps={steps}
      at={indexOf(steps, place.at)}
      onAt={(index) => {
        const next = steps[index];
        if (next !== undefined) {
          move({ ...place, at: next.key });
        }
      }}
      panels={panels}
      shared={page.vault_told === "" || chosen.kind !== "form" ? undefined : <Note kind="not-yet">{page.vault_told}</Note>}
    />
  );
}

export function SourceFlow({
  page,
  source,
  onClose,
  onDone,
}: {
  readonly page: ConnectorsBody;
  /** The source to open on, or null to ask which first. */
  readonly source: string | null;
  readonly onClose: () => void;
  /** Told the API's sentence once the source is connected. */
  readonly onDone: (told: string) => void;
}) {
  const sources = openable(page);
  const [picked, setPicked] = useState<string | null>(source);
  const chosen = sources.find((one) => one.source.name === picked);
  if (chosen === undefined) {
    return (
      <FlowDialog title={CHOOSE_TITLE} description={CHOOSE_DESCRIPTION} onClose={onClose}>
        <Chooser sources={sources} onChoose={setPicked} />
      </FlowDialog>
    );
  }
  return (
    <FlowDialog
      title={chosen.kind === "form" ? `Connect ${chosen.source.label}` : `How ${chosen.source.label} is connected`}
      description={chosen.kind === "form" ? FLOW_DESCRIPTION : SERVER_DESCRIPTION}
      onClose={onClose}
    >
      {source === null ? (
        <Button
          type="button"
          variant="link"
          className="min-h-11 self-start px-0 sm:min-h-8"
          onClick={() => {
            setPicked(null);
          }}
        >
          {OTHER_SOURCE}
        </Button>
      ) : null}
      <Flow key={chosen.source.name} page={page} chosen={chosen} onConnected={onDone} />
    </FlowDialog>
  );
}
