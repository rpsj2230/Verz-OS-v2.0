/**
 * The Packs tab of Roles and permissions: the named bundles of capabilities a person can be given in
 * one assignment, and the acts that create, version, copy and retire one (M27.15.24).
 *
 * **A version changes the pack in place, so every holder moves with it**, and the API says so in its
 * own sentence (`versioning`), which the confirmation carries: a new version is an update of the one
 * row, recorded in the audit trail with its number, and nothing is re-granted person by person. That
 * is why versioning asks first and creating and copying do not. The writer must hold every capability
 * in the pack over the whole company, because nobody bundles what they could not grant alone; the API
 * judges that, and refuses a capability nobody declared in a sentence naming what was typed.
 *
 * **A pack somebody still holds is not retired**, because retiring it would silently take access away
 * from its holders; the API refuses in one sentence that names nobody and no figure (`retiring`).
 *
 * **Assigning a pack widens a person by exactly that pack**, and it is done from the person's Grants
 * view, where the scope it is bounded by is chosen.
 *
 * **The catalogue is whole or empty**: the Capabilities screen's read decides, because a pack's
 * contents are capability names. There is no count of anything.
 *
 * Task ids: M27.15.24, M27.11.3, M27.16.1
 */

import { Copy, MoreHorizontal, Package, Plus } from "lucide-react";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Chip,
  ConfirmDialog,
  Drawer,
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  PageHeader,
  SectionCard,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import {
  CAPABILITY_PATTERN,
  Field,
  FormProblem,
  SHORT_NAME_HINT,
  shortNameProblem,
  suggestedShortName,
} from "../access/formParts";
import { ROLES_HEADING } from "./RolesPage";

export const PACKS_API_PATH = "/govern/packs";
export const PACK_VERSION_API_PATH = "/govern/packs/version";
export const PACK_COPY_API_PATH = "/govern/packs/copy";
export const PACK_RETIREMENT_API_PATH = "/govern/packs/retirement";

export const PACKS_CRUMB = "Packs";
export const PACKS_LEDE = "Named bundles of capabilities, given to a person in one assignment over one scope.";
export const NO_PACKS = "No packs to show";
export const NO_PACKS_DESCRIPTION =
  "A pack appears here once somebody who may grant over the whole company creates one, and is shown to a reader who may name capabilities.";
export const NEW_PACK = "New pack";

export const VERSIONING_FALLBACK =
  "A new version changes what every holder of the pack holds, at once, and is recorded in the audit trail with its number.";
export const RETIRING_FALLBACK = "A pack somebody still holds is not retired; take it away from them first.";

/** One pack, as the catalogue sends it. */
export interface PackLine {
  readonly slug: string;
  readonly label: string;
  readonly capabilities: readonly string[];
  readonly version?: number;
}

export interface PackCatalogue {
  readonly packs: readonly PackLine[];
  readonly mayWrite: boolean;
  readonly versioning?: string;
  readonly retiring?: string;
}

export function readPackCatalogue(payload: unknown): PackCatalogue {
  if (typeof payload !== "object" || payload === null) {
    return { packs: [], mayWrite: false };
  }
  const body = payload as Record<string, unknown>;
  const packs = (Array.isArray(body["packs"]) ? (body["packs"] as readonly unknown[]) : []).flatMap((item) => {
    const row = item as Record<string, unknown>;
    if (typeof row["slug"] !== "string") {
      return [];
    }
    const capabilities = Array.isArray(row["capabilities"]) ? (row["capabilities"] as readonly unknown[]).filter((one): one is string => typeof one === "string") : [];
    return [
      {
        slug: row["slug"],
        label: typeof row["label"] === "string" ? row["label"] : row["slug"],
        capabilities,
        ...(typeof row["version"] === "number" ? { version: row["version"] } : {}),
      },
    ];
  });
  return {
    packs,
    mayWrite: body["may_write"] === true,
    ...(typeof body["versioning"] === "string" ? { versioning: body["versioning"] } : {}),
    ...(typeof body["retiring"] === "string" ? { retiring: body["retiring"] } : {}),
  };
}

/** The capabilities typed one per line, each once, in the order typed. */
export function capabilitiesTyped(text: string): readonly string[] {
  const seen = new Set<string>();
  for (const line of text.split(/[\n,]+/)) {
    const one = line.trim();
    if (one !== "") {
      seen.add(one);
    }
  }
  return [...seen];
}

/** What is wrong with the capabilities typed, or null. Names the value the person typed. */
export function capabilitiesProblem(text: string): string | null {
  const typed = capabilitiesTyped(text);
  if (typed.length === 0) {
    return "Give at least one capability, one per line.";
  }
  const wrong = typed.find((one) => !CAPABILITY_PATTERN.test(one));
  return wrong === undefined ? null : `${wrong} is not written as a capability: a verb, a colon and what it reaches, such as read:ticket.*.`;
}

const CAPABILITIES_HINT =
  "One per line, each a verb, a colon and what it reaches, such as read:ticket.* or invoke:quote_helper. You must hold each one over the whole company.";

type Editing =
  | { readonly kind: "create" }
  | { readonly kind: "version"; readonly pack: PackLine }
  | { readonly kind: "copy"; readonly pack: PackLine };

/** The drawer a pack is created, versioned or copied through. */
function PackDrawer({
  editing,
  versioning,
  onClose,
  onWritten,
}: {
  readonly editing: Editing | null;
  readonly versioning: string;
  readonly onClose: () => void;
  readonly onWritten: () => void;
}) {
  const source = editing === null || editing.kind === "create" ? null : editing.pack;
  const [label, setLabel] = useState(source === null ? "" : editing?.kind === "copy" ? `Copy of ${source.label}` : source.label);
  const [slug, setSlug] = useState(source === null ? "" : editing?.kind === "copy" ? suggestedShortName(`${source.slug} copy`) : source.slug);
  const [edited, setEdited] = useState(false);
  const [capabilities, setCapabilities] = useState(source === null ? "" : source.capabilities.join("\n"));
  const [problems, setProblems] = useState<Partial<Record<"label" | "slug" | "capabilities", string>>>({});
  const [pending, setPending] = useState<{ readonly label: string; readonly capabilities: readonly string[] } | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const done = () => {
    setFailure(null);
    onClose();
    onWritten();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (editing === null) {
      return;
    }
    const found: Partial<Record<"label" | "slug" | "capabilities", string>> = {};
    if (label.trim() === "") {
      found.label = "Give the pack a name people will read.";
    }
    if (editing.kind !== "version") {
      const shape = shortNameProblem(slug);
      if (shape !== null) {
        found.slug = shape;
      }
    }
    if (editing.kind !== "copy") {
      const wrong = capabilitiesProblem(capabilities);
      if (wrong !== null) {
        found.capabilities = wrong;
      }
    }
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    if (editing.kind === "version") {
      // A version changes what every holder holds, so it is asked first; see `send` below.
      setFailure(null);
      setPending({ label: label.trim(), capabilities: capabilitiesTyped(capabilities) });
      return;
    }
    setBusy(true);
    void (async () => {
      const result =
        editing.kind === "create"
          ? await request<unknown>(PACKS_API_PATH, {
              method: "POST",
              body: { slug: slug.trim(), label: label.trim(), capabilities: capabilitiesTyped(capabilities) },
            })
          : await request<unknown>(PACK_COPY_API_PATH, {
              method: "POST",
              body: { slug: editing.pack.slug, new_slug: slug.trim(), label: label.trim() },
            });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      done();
    })();
  };

  const send = useCallback(() => {
    if (pending === null || editing?.kind !== "version") {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(PACK_VERSION_API_PATH, {
        method: "POST",
        body: {
          slug: editing.pack.slug,
          expected_version: editing.pack.version ?? 1,
          label: pending.label,
          capabilities: [...pending.capabilities],
        },
      });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onClose();
      onWritten();
    })();
  }, [pending, editing, onClose, onWritten]);

  const title = editing === null ? "" : editing.kind === "create" ? NEW_PACK : editing.kind === "version" ? `New version of ${editing.pack.label}` : `Copy ${editing.pack.label}`;
  const description =
    editing?.kind === "version"
      ? versioning
      : editing?.kind === "copy"
        ? "A new pack with the same capabilities, at version 1. Nobody holds it until it is assigned."
        : "A new pack at version 1. Nobody holds it until it is assigned.";
  const verb = editing?.kind === "version" ? "Review the new version" : editing?.kind === "copy" ? "Copy the pack" : "Create the pack";

  return (
    <>
      <Drawer
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) {
            onClose();
          }
        }}
        title={title}
        description={description}
        footer={
          <>
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" form="pack-form" disabled={busy || pending !== null}>
              {verb}
            </Button>
          </>
        }
      >
        <form id="pack-form" noValidate className="flex flex-col gap-4" onSubmit={submit}>
          <Field label="Name" hint="What people read, up to 120 characters." problem={problems.label} apiProblems={failure?.problems ?? []} names={["label"]}>
            {({ id, describedBy, invalid }) => (
              <Input
                id={id}
                aria-describedby={describedBy}
                aria-invalid={invalid ? true : undefined}
                className="h-11 sm:h-9"
                maxLength={120}
                value={label}
                onChange={(event) => {
                  setLabel(event.target.value);
                  if (!edited && editing?.kind === "create") {
                    setSlug(suggestedShortName(event.target.value));
                  }
                }}
              />
            )}
          </Field>
          {editing?.kind === "version" ? null : (
            <Field label="Short name" hint={`${SHORT_NAME_HINT} It cannot be changed later.`} problem={problems.slug} apiProblems={failure?.problems ?? []} names={["slug", "new_slug"]}>
              {({ id, describedBy, invalid }) => (
                <Input
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={invalid ? true : undefined}
                  autoComplete="off"
                  spellCheck={false}
                  className="h-11 font-mono sm:h-9"
                  maxLength={60}
                  value={slug}
                  onChange={(event) => {
                    setEdited(true);
                    setSlug(event.target.value);
                  }}
                />
              )}
            </Field>
          )}
          {editing?.kind === "copy" ? (
            <p className="m-0 font-mono text-[11.5px] leading-relaxed text-dim [overflow-wrap:anywhere]">{editing.pack.capabilities.join(", ")}</p>
          ) : (
            <Field label="Capabilities" hint={CAPABILITIES_HINT} problem={problems.capabilities} apiProblems={failure?.problems ?? []} names={["capabilities"]}>
              {({ id, describedBy, invalid }) => (
                <Textarea
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={invalid ? true : undefined}
                  spellCheck={false}
                  className="min-h-32 font-mono"
                  value={capabilities}
                  onChange={(event) => {
                    setCapabilities(event.target.value);
                  }}
                />
              )}
            </Field>
          )}
          {Object.keys(problems).length > 0 ? <FormProblem>Nothing has been sent: correct the fields marked above.</FormProblem> : null}
          {failure === null ? null : <FailureState failure={failure} />}
        </form>
      </Drawer>
      <ConfirmDialog
        open={pending !== null}
        question={editing?.kind === "version" ? `Make version ${String((editing.pack.version ?? 1) + 1)} of ${editing.pack.label}?` : ""}
        consequence={versioning}
        details={pending === null ? undefined : <p className="m-0 font-mono text-[12px] [overflow-wrap:anywhere]">{pending.capabilities.join(", ")}</p>}
        confirmLabel="Make the new version"
        cancelLabel="Leave it"
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setPending(null);
        }}
      />
    </>
  );
}

/** A pack retired, confirmed, in the API's words. */
function RetirePack({ pack, retiring, onClose, onWritten }: { readonly pack: PackLine | null; readonly retiring: string; readonly onClose: () => void; readonly onWritten: () => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const go = useCallback(() => {
    if (pack === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(PACK_RETIREMENT_API_PATH, {
        method: "POST",
        body: { slug: pack.slug, expected_version: pack.version ?? 1 },
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onClose();
      onWritten();
    })();
  }, [pack, onClose, onWritten]);
  return (
    <ConfirmDialog
      open={pack !== null}
      question={pack === null ? "" : `Retire the pack ${pack.label}?`}
      consequence={`${retiring} It is kept on record and can no longer be assigned.`}
      details={failure === null ? undefined : <FailureState failure={failure} />}
      confirmLabel="Retire the pack"
      cancelLabel="Keep it"
      busy={busy}
      onConfirm={go}
      onCancel={() => {
        setFailure(null);
        onClose();
      }}
    />
  );
}

export function PacksPage() {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(PACKS_API_PATH, version);
  const catalogue = useMemo(() => readPackCatalogue(answer.data), [answer.data]);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [retiring, setRetiring] = useState<PackLine | null>(null);
  const written = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);

  const columns: readonly EntityColumn<PackLine>[] = [
    { id: "label", header: "Pack", hideable: false, cell: (row) => <span className="font-medium text-ink">{row.label}</span>, text: (row) => row.label },
    {
      id: "capabilities",
      header: "Capabilities",
      cell: (row) => (
        <span className="flex max-w-[28rem] flex-wrap gap-1">
          {row.capabilities.map((one) => (
            <Chip key={one} mono>
              {one}
            </Chip>
          ))}
        </span>
      ),
      text: (row) => row.capabilities.join("; "),
    },
    {
      id: "version",
      header: "Version",
      align: "end",
      cell: (row) => (row.version === undefined ? null : <span className="font-mono tabular-nums">{row.version}</span>),
      text: (row) => (row.version === undefined ? "" : String(row.version)),
    },
    { id: "slug", header: "Short name", hidden: true, cell: (row) => <code className="font-mono text-[12px]">{row.slug}</code>, text: (row) => row.slug },
  ];

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label="Loading packs." />;
  } else if (catalogue.packs.length === 0) {
    body = <EmptyState title={NO_PACKS} description={NO_PACKS_DESCRIPTION} icon={<Package aria-hidden />} />;
  } else {
    body = (
      <EntityTable
        caption="Every pack"
        columns={columns}
        rows={catalogue.packs}
        rowId={(row) => row.slug}
        rowLabel={(row) => row.label}
        exportName="packs"
        rowActions={
          catalogue.mayWrite
            ? (row) => (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${row.label}`}>
                      <MoreHorizontal aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48">
                    <DropdownMenuItem
                      onSelect={() => {
                        setEditing({ kind: "version", pack: row });
                      }}
                    >
                      New version
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => {
                        setEditing({ kind: "copy", pack: row });
                      }}
                    >
                      <Copy aria-hidden /> Copy
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => {
                        setRetiring(row);
                      }}
                    >
                      Retire
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )
            : undefined
        }
      />
    );
  }

  return (
    <div data-slot="packs-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: ROLES_HEADING }, { label: PACKS_CRUMB }]}
        title={PACKS_CRUMB}
        lede={PACKS_LEDE}
        primary={
          catalogue.mayWrite ? (
            <Button
              className="min-h-11 sm:min-h-9"
              onClick={() => {
                setEditing({ kind: "create" });
              }}
            >
              <Plus aria-hidden /> {NEW_PACK}
            </Button>
          ) : undefined
        }
      />
      <SectionCard title="Packs" lede="Assign a pack from a person's Grants view, where the scope it is bounded by is chosen.">
        {body}
      </SectionCard>
      {editing === null ? null : (
        <PackDrawer
          key={editing.kind === "create" ? "create" : `${editing.kind}:${editing.pack.slug}`}
          editing={editing}
          versioning={catalogue.versioning ?? VERSIONING_FALLBACK}
          onClose={() => {
            setEditing(null);
          }}
          onWritten={written}
        />
      )}
      <RetirePack
        pack={retiring}
        retiring={catalogue.retiring ?? RETIRING_FALLBACK}
        onClose={() => {
          setRetiring(null);
        }}
        onWritten={written}
      />
    </div>
  );
}
