/**
 * Plugins on the Features page: the plugins this install has recorded and their state, a place to
 * record one by its manifest, and the points a plugin may plug into in Advanced.
 *
 * **Nothing here decides who may.** The route asks for `admin:plugin` over everything and refuses
 * everybody else before it reads anything, and a refusal is shown as the API wrote it. Each plugin
 * and point the API sends is drawn; none is named here.
 *
 * **A write is followed by a fresh read**, so the page shows what the database holds, and the
 * acts offered are the ones the plugin's state allows (`verbsFor`), which are the lifecycle's own
 * edges.
 *
 * Task ids: M29.2.1, M29.2.2, M29.2.3
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
import { Textarea } from "../../components/ui/textarea";
import {
  MANIFEST_LABEL,
  movedSentence,
  NO_PLUGINS,
  NO_PLUGINS_TITLE,
  NOT_CHANGED,
  NOT_JSON,
  NOT_LOADED,
  PLUGINS_API_PATH,
  PLUGINS_TITLE,
  POINTS_HEADING,
  READING_PLUGINS,
  readManifest,
  readPlugins,
  RECORD,
  SWITCHED_OFF,
  UNREADABLE_PLUGINS,
  verbPath,
  verbsFor,
  VERB_LABEL,
  type PluginRow,
  type PluginsBody,
  type Verb,
} from "../pluginsQuery";

function PluginCard({
  row,
  busy,
  onAct,
}: {
  readonly row: PluginRow;
  readonly busy: boolean;
  readonly onAct: (row: PluginRow, verb: Verb) => void;
}) {
  return (
    <SectionCard
      title={`${row.plugin_id} ${row.version}`}
      headingLevel="h3"
      action={
        <>
          <Chip>{row.state}</Chip>
          {verbsFor(row.state).map((verb) => (
            <Button
              key={verb}
              size="sm"
              variant={verb === "enable" ? "default" : "outline"}
              className="min-h-11 sm:min-h-8"
              disabled={busy}
              aria-label={`${VERB_LABEL[verb]}: ${row.plugin_id}`}
              onClick={() => {
                onAct(row, verb);
              }}
            >
              {VERB_LABEL[verb]}
            </Button>
          ))}
        </>
      }
    >
      <p className="m-0 text-[13px] text-body">Plugs in at {row.point}.</p>
      {row.requires.length === 0 ? null : (
        <p className="m-0 mt-2 text-[12.5px] text-dim">Needs its caller to hold {row.requires.join(", ")}.</p>
      )}
      {row.config.map((one) => (
        <p key={one.name} className="m-0 mt-1 text-[12.5px] text-dim">
          {one.name}: {one.meaning}
          {one.required ? " (required)" : ""}
        </p>
      ))}
    </SectionCard>
  );
}

function Recorder({ onRecorded }: { readonly onRecorded: (told: string) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function record(): void {
    const manifest = readManifest(text);
    if (manifest === null) {
      setProblem(NOT_JSON);
      return;
    }
    setProblem(null);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(PLUGINS_API_PATH, { method: "POST", body: { manifest } });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setText("");
      const made = result.data as { plugin_id?: unknown };
      onRecorded(`"${typeof made.plugin_id === "string" ? made.plugin_id : "The plugin"}" is recorded, switched off.`);
    })();
  }

  return (
    <SectionCard title={RECORD} headingLevel="h3">
      <label className="m-0 block text-[13px] text-body" htmlFor="plugin-manifest">
        {MANIFEST_LABEL}
      </label>
      <Textarea
        id="plugin-manifest"
        value={text}
        rows={8}
        className="mt-1 font-mono text-[12px]"
        onChange={(event) => {
          setText(event.target.value);
        }}
      />
      {problem === null ? null : <Note>{problem}</Note>}
      {failure === null ? null : <FailureState failure={failure} title={NOT_CHANGED} />}
      <div className="mt-2">
        <Button size="sm" className="min-h-11 sm:min-h-8" disabled={busy || text.trim() === ""} onClick={record}>
          {RECORD}
        </Button>
      </div>
    </SectionCard>
  );
}

function PluginList({ body, onChanged }: { readonly body: PluginsBody; readonly onChanged: (told: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function act(row: PluginRow, verb: Verb): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(verbPath(row.plugin_id, verb), { method: "POST" });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onChanged(movedSentence(row.plugin_id, verb));
    })();
  }

  return (
    <>
      {body.no_plugin_is_loaded ? <Note>{NOT_LOADED}</Note> : null}
      {body.registry_is_on ? null : <Note>{SWITCHED_OFF}</Note>}
      {body.plugins.length === 0 ? (
        <EmptyList
          title={NO_PLUGINS_TITLE}
          description={NO_PLUGINS}
          adds="Record a plugin's manifest with the form on this screen; it arrives switched off."
          by={["super_admin"]}
        />
      ) : null}
      {body.plugins.map((row) => (
        <PluginCard key={row.plugin_id} row={row} busy={busy} onAct={act} />
      ))}
      {failure === null ? null : <FailureState failure={failure} title={NOT_CHANGED} />}
      {body.registry_is_on ? <Recorder onRecorded={onChanged} /> : null}
      <Advanced>
        <h4 className="m-0 mb-2 text-[12.5px] font-semibold">{POINTS_HEADING}</h4>
        <FactList>
          {body.points.map((one) => (
            <Fact key={one.name} label={one.name}>
              <span className="font-mono text-[11.5px]">{one.leaf}</span>
              <span className="block text-[12px] text-dim">
                {one.answer === "plugin" ? `A plugin runs in a ${one.tier ?? ""} (${one.contract})` : `Answered by ${one.answer}`}
              </span>
            </Fact>
          ))}
        </FactList>
      </Advanced>
    </>
  );
}

export function PluginsPanel() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<string | null>(null);
  const answer = useResource<unknown>(PLUGINS_API_PATH, version);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_PLUGINS} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readPlugins(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_PLUGINS}</Note>
      ) : (
        <PluginList
          body={body}
          onChanged={(sentence) => {
            setTold(sentence);
            setVersion((count) => count + 1);
          }}
        />
      );
  }
  return (
    <section data-slot="plugins-panel" aria-label={PLUGINS_TITLE} className="flex min-w-0 flex-col gap-3">
      <h2 className="m-0 text-[15px] font-semibold">{PLUGINS_TITLE}</h2>
      {told === null ? null : (
        <div role="status">
          <Note kind="done">{told}</Note>
        </div>
      )}
      {content}
    </section>
  );
}
