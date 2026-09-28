/**
 * The providers list, on the shared page kit: every AI provider this install can use, switched on
 * or off, whether a key is held, its last test, and the models its steps use.
 *
 * **This is the owner's list and nothing more** (2026-09-22: the screen was "very complicated").
 * The old Models and health page drew about ten tables; the failover matrix is now the Routing
 * page's, a provider's terms, figures and history are its own page's, and the tier numbers and
 * residency rules are under the Routing page's Advanced section. What stayed here is what an
 * administrator does every day: turn a provider on or off, test it, open it to add its key.
 *
 * **The list is the route's**, `GET /models/providers` under the list contract
 * (`brain.provider_routes.PROVIDERS`), so the search and the two filters are requests and the order
 * is the product's. The steps and the profile come on the same answer, so the status and the models
 * in use are the plan the next call makes.
 *
 * **Where answers are made sits above the list, because it decides whether any of them is used.**
 * It is the install's profile, shown to every reader and changed from a confirmation by a reader the
 * API says may.
 *
 * **The prices sit under the list, because they are what a provider's calls are costed at**
 * (M27.12.5): `components/ModelPrices.tsx`, each model a step names with its price per million
 * tokens and whether its calls are costed, set from its row by a reader who may switch a provider.
 *
 * **Every act is confirmed, and drawn only for a reader the API says may use it.** A switch moves
 * every department's questions, a test spends tokens under the presser's name
 * (`modelsQuery.A_CHECK_SPENDS_TOKENS_SO_IT_IS_CONFIRMED`), and a new provider is somewhere questions
 * may be sent. `editable` decides whether a control is drawn and decides nothing else.
 *
 * Task ids: M27.16.1, M27.8.8, M5.7.1, M5.7.2, M5.6.4, M27.12.5
 */

import { Download, MoreHorizontal, Plus, Route } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { Chip, ConfirmDialog, FailureState, ListPage, Note, type EntityColumn } from "../../components/kit";
import { ModelPrices } from "../../components/ModelPrices";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import {
  checkConsequence,
  checkQuestion,
  chooseProfileLabel,
  keyAction,
  keyHeldWords,
  KEEP_IT_AS_IT_IS,
  DO_NOT_TEST,
  MODELS_LABEL,
  otherProfile,
  PROFILE_API_PATH,
  PROFILE_WORDS,
  profileBody,
  profileChosenSentence,
  profileConsequence,
  profileNowSentence,
  profileQuestion,
  providerCheckApiPath,
  providerName,
  providerStatus,
  providerSwitchApiPath,
  PROVIDERS_API_PATH,
  readCheck,
  readProviders,
  SEND_THE_TEST,
  switchBody,
  switchConsequence,
  switchedSentence,
  switchQuestion,
  TEST,
  TURN_OFF,
  TURN_ON,
  WHERE_ANSWERS_ARE_MADE,
  type ProviderStateRow,
  type ProvidersBody,
} from "../modelsQuery";
import { readRegisterDocument, REGISTER_API_PATH, REGISTER_HEADING } from "../providerRegisterQuery";
import { AddProvider } from "./AddProvider";
import { MODULE_LABEL, providerAddress, saveText, WORKS_AT } from "./modelsActions";
import { OnOffPill, StatusPill } from "./pills";
import { lastTestWords, modelsInUse } from "./providerWords";

export const PROVIDERS_LEDE =
  "The AI providers this install can use: switched on or off, whether a key is held, the last test, and the models in use.";
export const LOADING_PROVIDERS = "Loading the providers.";
export const NO_PROVIDERS = "No providers to show";
export const NO_PROVIDERS_DESCRIPTION = "A provider appears here once it is built in or added by an administrator.";
export const PROVIDERS_CAPTION = "AI providers";
export const FILTERS_LABEL = "Narrow the providers";
export const SEARCH_HINT = "Search providers";
export const ADD_A_PROVIDER = "Add a provider";
export const ROUTING_LINK = "Routing";
export const NONE_IN_USE = "None in use";

export const PROVIDER_COLUMN = "Provider";
export const ON_COLUMN = "On or off";
export const KEY_COLUMN = "Key";
export const LAST_TEST_COLUMN = "Last test";
export const MODELS_COLUMN = "Models in use";

/** The two filters the route declares that this page offers. */
export const PROVIDER_FILTERS: readonly FilterChoice<ProviderStateRow>[] = [
  {
    column: "switched_on",
    label: ON_COLUMN,
    everything: "On or off",
    read: (row) => row.switched_on,
    describe: (value) => (value === "true" ? "On" : "Off"),
  },
  {
    column: "key_held",
    label: KEY_COLUMN,
    everything: "Any key",
    read: (row) => row.key_held ?? undefined,
    describe: (value) => (value === "true" ? "Held" : "Not held"),
  },
];

/** The orders the route declares: the product's own, and by name. */
export const PROVIDER_SORTS: readonly SortChoice[] = [
  { value: "", label: "Built in first" },
  { value: "provider", label: "Name" },
];

/** A write this page is about to send, held while its confirmation is open. */
type Ask =
  | { readonly kind: "switch"; readonly provider: string; readonly name: string; readonly on: boolean }
  | { readonly kind: "check"; readonly provider: string; readonly name: string }
  | { readonly kind: "profile"; readonly profile: string };

/** The rows out of the list's body: a provider only with its slug, once each, in the order sent. */
export function readProviderRows(payload: unknown): readonly ProviderStateRow[] {
  const body = readProviders(payload);
  if (body === null) {
    return [];
  }
  const seen = new Set<string>();
  return body.providers.filter((one) => {
    if (typeof one.provider !== "string" || one.provider === "" || seen.has(one.provider)) {
      return false;
    }
    seen.add(one.provider);
    return true;
  });
}

function askQuestion(ask: Ask): string {
  if (ask.kind === "switch") {
    return switchQuestion(ask.name, ask.on);
  }
  return ask.kind === "check" ? checkQuestion(ask.name) : profileQuestion(ask.profile);
}

function askConsequence(ask: Ask): string {
  if (ask.kind === "switch") {
    return switchConsequence(ask.name, ask.on);
  }
  return ask.kind === "check" ? checkConsequence(ask.name) : profileConsequence(ask.profile);
}

function askLabel(ask: Ask): string {
  if (ask.kind === "switch") {
    return ask.on ? TURN_ON : TURN_OFF;
  }
  return ask.kind === "check" ? SEND_THE_TEST : chooseProfileLabel(ask.profile);
}

function RowMenu({
  row,
  name,
  editable,
  onAsk,
}: {
  readonly row: ProviderStateRow;
  readonly name: string;
  readonly editable: boolean;
  readonly onAsk: (ask: Ask) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${name}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuItem asChild>
          <Link to={providerAddress(row.provider)}>Open</Link>
        </DropdownMenuItem>
        {row.credential === null ? null : (
          <DropdownMenuItem asChild>
            <Link to={providerAddress(row.provider, "profile")}>{keyAction(row)}</Link>
          </DropdownMenuItem>
        )}
        {editable ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                onAsk({ kind: "check", provider: row.provider, name });
              }}
            >
              {TEST}
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                onAsk({ kind: "switch", provider: row.provider, name, on: !row.switched_on });
              }}
            >
              {row.switched_on ? TURN_OFF : TURN_ON}
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Where answers are made, and the one control that changes it. */
function WhereAnswersAreMade({ body, onAsk }: { readonly body: ProvidersBody; readonly onAsk: (ask: Ask) => void }) {
  const target = otherProfile(body.profile);
  return (
    <section
      aria-label={WHERE_ANSWERS_ARE_MADE}
      className="flex flex-col gap-2 rounded-md border border-line bg-panel px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="m-0 text-[13px] text-body">
        <span className="font-semibold text-ink">{WHERE_ANSWERS_ARE_MADE}: </span>
        {PROFILE_WORDS[body.profile] ?? body.profile}. {profileNowSentence(body.profile)}
      </p>
      {body.profile_editable === true ? (
        <Button
          variant="outline"
          size="sm"
          className="min-h-11 shrink-0 sm:min-h-8"
          onClick={() => {
            onAsk({ kind: "profile", profile: target });
          }}
        >
          {chooseProfileLabel(target)}
        </Button>
      ) : null}
    </section>
  );
}

export function ProvidersPage() {
  const [version, setVersion] = useState(0);
  const listing = useListing<ProviderStateRow>(PROVIDERS_API_PATH, {
    listKey: "providers",
    choices: PROVIDER_FILTERS,
    version,
  });
  const rows = useMemo(() => readProviderRows(listing.body), [listing.body]);
  const body = useMemo(() => readProviders(listing.body), [listing.body]);
  const [asked, setAsked] = useState<Ask | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const send = useCallback((pending: Ask) => {
    setBusy(true);
    void (async () => {
      const result =
        pending.kind === "switch"
          ? await request<unknown>(providerSwitchApiPath(pending.provider), { method: "PUT", body: switchBody(pending.on) })
          : pending.kind === "check"
            ? await request<unknown>(providerCheckApiPath(pending.provider), { method: "POST" })
            : await request<unknown>(PROFILE_API_PATH, { method: "PUT", body: profileBody(pending.profile) });
      setBusy(false);
      setAsked(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      if (pending.kind === "switch") {
        setTold(switchedSentence(pending.name, pending.on));
      } else if (pending.kind === "check") {
        const check = readCheck(result.data);
        setTold(check === null ? null : `${pending.name}: ${check.told}`);
      } else {
        setTold(profileChosenSentence(pending.profile));
      }
      setVersion((count) => count + 1);
    })();
  }, []);

  const downloadRegister = useCallback(() => {
    void (async () => {
      const result = await request<unknown>(REGISTER_API_PATH);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const register = readRegisterDocument(result.data);
      if (register !== null) {
        saveText(register.filename, register.document, "text/markdown;charset=utf-8");
      }
    })();
  }, []);

  const providers = body?.providers ?? [];
  const steps = body?.rungs ?? [];
  const editable = body?.editable === true;
  // Adding writes a key as well as a provider, so it is offered to a reader the API sent the vault's
  // column to, who may manage credentials, and who may also switch.
  const mayAdd = editable && providers.some((one) => one.credential !== null);
  const onAsk = (ask: Ask) => {
    setFailure(null);
    setTold(null);
    setAsked(ask);
  };

  const columns: readonly EntityColumn<ProviderStateRow>[] = [
    {
      id: "provider",
      header: PROVIDER_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[11rem] flex-col gap-1">
          <Link
            to={providerAddress(row.provider)}
            className="font-medium text-ink underline-offset-4 [overflow-wrap:anywhere] hover:text-acc-text hover:underline"
          >
            {providerName(row.provider, providers)}
          </Link>
          <span>
            <StatusPill status={providerStatus(row, steps, body?.profile)} />
          </span>
        </span>
      ),
      text: (row) => providerName(row.provider, providers),
    },
    {
      id: "switched_on",
      header: ON_COLUMN,
      cell: (row) => <OnOffPill on={row.switched_on} />,
      text: (row) => (row.switched_on ? "On" : "Off"),
    },
    {
      id: "key",
      header: KEY_COLUMN,
      cell: (row) => <span className="text-body">{keyHeldWords(row.key_held)}</span>,
      text: (row) => keyHeldWords(row.key_held),
    },
    {
      id: "last_test",
      header: LAST_TEST_COLUMN,
      cell: (row) => <span className="text-body">{lastTestWords(row.last_check)}</span>,
      text: (row) => lastTestWords(row.last_check),
    },
    {
      id: "models",
      header: MODELS_COLUMN,
      cell: (row) => {
        const models = modelsInUse(row.provider, steps);
        return models.length === 0 ? (
          <span className="text-[12.5px] text-dim">{NONE_IN_USE}</span>
        ) : (
          <span className="flex flex-wrap gap-1">
            {models.map((one) => (
              <Chip key={one} mono>
                {one}
              </Chip>
            ))}
          </span>
        );
      },
      text: (row) => modelsInUse(row.provider, steps).join("; "),
    },
  ];

  return (
    <>
      <ListPage
        crumbs={[{ label: MODULE_LABEL }, { label: MODELS_LABEL }]}
        title={MODELS_LABEL}
        lede={PROVIDERS_LEDE}
        primary={
          mayAdd ? (
            <Button
              className="min-h-11 sm:min-h-8"
              aria-expanded={adding}
              onClick={() => {
                setAdding((open) => !open);
              }}
            >
              <Plus aria-hidden />
              {ADD_A_PROVIDER}
            </Button>
          ) : undefined
        }
        actions={
          <>
            <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
              <Link to={WORKS_AT.routing}>
                <Route aria-hidden /> {ROUTING_LINK}
              </Link>
            </Button>
            {body === null ? null : (
              <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" onClick={downloadRegister}>
                <Download aria-hidden /> {REGISTER_HEADING}
              </Button>
            )}
          </>
        }
        notice={
          <>
            {body === null ? null : <WhereAnswersAreMade body={body} onAsk={onAsk} />}
            {adding && mayAdd ? (
              <AddProvider
                onAdded={(name) => {
                  setAdding(false);
                  setTold(`${name} was added. Add a step for one of its models on the Routing page to use it.`);
                  setVersion((count) => count + 1);
                }}
                onClose={() => {
                  setAdding(false);
                }}
              />
            ) : null}
            {told === null ? null : (
              <div role="status">
                <Note kind="works">{told}</Note>
              </div>
            )}
            {failure === null ? null : <FailureState failure={failure} />}
          </>
        }
        listing={listing}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={PROVIDER_FILTERS}
        sorts={PROVIDER_SORTS}
        searchHint={SEARCH_HINT}
        caption={PROVIDERS_CAPTION}
        columns={columns}
        rowId={(row) => row.provider}
        rowLabel={(row) => providerName(row.provider, providers)}
        rowActions={(row) => (
          <RowMenu row={row} name={providerName(row.provider, providers)} editable={editable} onAsk={onAsk} />
        )}
        exportName="providers"
        loading={LOADING_PROVIDERS}
        emptyTitle={NO_PROVIDERS}
        emptyDescription={NO_PROVIDERS_DESCRIPTION}
        footer={body === null ? undefined : <ModelPrices editable={editable} />}
      />
      <ConfirmDialog
        open={asked !== null}
        question={asked === null ? "" : askQuestion(asked)}
        consequence={asked === null ? "" : askConsequence(asked)}
        confirmLabel={asked === null ? "" : askLabel(asked)}
        cancelLabel={asked?.kind === "check" ? DO_NOT_TEST : KEEP_IT_AS_IT_IS}
        busy={busy}
        onConfirm={() => {
          if (asked !== null) {
            send(asked);
          }
        }}
        onCancel={() => {
          setAsked(null);
        }}
      />
    </>
  );
}
