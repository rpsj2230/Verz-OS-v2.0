/**
 * Loading, empty and failed: the three states every list and every detail page passes through,
 * drawn once so each module says them the same way.
 *
 * **Four different sentences, always.** `tests/screen-states.test.tsx` mounts every registered page
 * loading, unreachable, failed, answered and emptied, and holds each to a sentence the others do not
 * say. So the loading state carries words and not only a skeleton, the empty state says what would
 * put a row here, and a failure is `ui/FailureNotice`, which already tells an unreachable Brain from
 * a refusal and shows the reference a person needs to follow one up.
 *
 * **The empty state is one sentence for every reason a list is empty.** A company with none and a
 * reader whose reach covers none are one event to this browser and must look the same, because the
 * difference is a fact about rows the reader may not see. What the sentence may say is who could
 * put a row here and how, which is true for every reader.
 *
 * Task ids: M27.10.2
 */

import type { ReactNode } from "react";
import type { ApiFailure } from "../../api/errors";
import { cn } from "../../lib/utils";
import { FailureNotice } from "../../ui/FailureNotice";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "../ui/empty";
import { Skeleton } from "../ui/skeleton";
import { ROLE_WORDS, type PlatformRole } from "./roles";

/** A page or a block whose answer has not come yet. The words are what a screen reader hears. */
export function LoadingState({
  label,
  rows = 4,
  className,
}: {
  /** "Loading agents." Said, and drawn under the placeholder bars. */
  readonly label: string;
  readonly rows?: number | undefined;
  readonly className?: string | undefined;
}) {
  return (
    <div data-slot="loading-state" role="status" className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} aria-hidden className="h-9 w-full" />
      ))}
      <p className="m-0 text-[12.5px] text-dim">{label}</p>
    </div>
  );
}

/** Nothing to show: what the list is, and what would put a row on it. */
export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
}: {
  readonly title: string;
  readonly description: ReactNode;
  readonly action?: ReactNode | undefined;
  readonly icon?: ReactNode | undefined;
  readonly className?: string | undefined;
}) {
  return (
    <Empty data-slot="empty-state" className={cn("border border-dashed border-line", className)}>
      <EmptyHeader>
        {icon === undefined ? null : <EmptyMedia variant="icon">{icon}</EmptyMedia>}
        <EmptyTitle as="h3">{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      {action === undefined ? null : <EmptyContent>{action}</EmptyContent>}
    </Empty>
  );
}

/** Said when no role adds a row of this list: the install records its rows itself. */
export const THE_INSTALL_RECORDS_THESE = "The install records these itself, and no role adds one by hand.";

/** The `by` of a list that fills itself. */
export const BY_THE_INSTALL = "install" as const;

/** Who adds a row to an empty list: the roles the screen is designed for, or the install itself. */
export type EmptyBy = readonly PlatformRole[] | typeof BY_THE_INSTALL;

/** "a Super Admin", "an Auditor": a role with the article a person would say it with. */
function withArticle(role: PlatformRole): string {
  const word = ROLE_WORDS[role];
  return `${/^[AEIOU]/u.test(word) ? "an" : "a"} ${word}`;
}

/**
 * The sentence for who adds a row, the same for every reader.
 *
 * Roles, in the order given, joined as a person would say them. A role is named as who the screen
 * is designed for and never as what lets somebody press the button: a role grants no capability,
 * and the grant decides, so the sentence says who does it and leaves out who may.
 */
export function whoAdds(by: EmptyBy): string {
  if (by === BY_THE_INSTALL) {
    return THE_INSTALL_RECORDS_THESE;
  }
  const named = by.map(withArticle);
  const last = named[named.length - 1] ?? "";
  const joined = named.length < 2 ? last : `${named.slice(0, -1).join(", ")} or ${last}`;
  return `${joined.charAt(0).toUpperCase()}${joined.slice(1)} adds one.`;
}

/**
 * A list with nothing in it, saying what is there for, what would put a row on it and who does that.
 *
 * **Three sentences, and the second and third are required by the type.** `adds` is the act that
 * makes a row, in a sentence, and `by` is who does it, from the platform's six roles or the install
 * itself. A page cannot draw an empty list without both, which is `docs/admin-console-architecture.md`
 * 5.2 and M27.15.69: an empty list that says only "No agents" sends a person to ask somebody what
 * they would have to do.
 *
 * **The same words for every reader and every reason**, as `EmptyState` is: a company with none and
 * a reader whose reach covers none are one event to this browser. Nothing here takes a count, a
 * reason or a flag that varies with what the reader may see, and `tests/empty-lists.test.tsx` holds
 * the words to naming no cause.
 */
export function EmptyList({
  title,
  description,
  adds,
  by,
  action,
  icon,
  className,
}: {
  readonly title: string;
  /** What the list is for, said once. */
  readonly description: ReactNode;
  /** The act that puts a row on the list, as one sentence. */
  readonly adds: string;
  /** Who does it. */
  readonly by: EmptyBy;
  readonly action?: ReactNode | undefined;
  readonly icon?: ReactNode | undefined;
  readonly className?: string | undefined;
}) {
  return (
    <div data-slot="empty-list" className="min-w-0">
      <EmptyState
        title={title}
        description={
          <>
            <span data-slot="empty-what">{description}</span>{" "}
            <span data-slot="empty-adds">{adds}</span>{" "}
            <span data-slot="empty-by">{whoAdds(by)}</span>
          </>
        }
        action={action}
        icon={icon}
        className={className}
      />
    </div>
  );
}

/**
 * A request that did not come back as an answer, in the API's own words with its reference.
 *
 * A thin frame around `FailureNotice` rather than a second failure component: the notice is where
 * the unreachable, second-factor and no-reference cases are decided, and a copy of it is the copy
 * that forgets one of them.
 */
export function FailureState({
  failure,
  title,
  children,
}: {
  readonly failure: ApiFailure;
  /** The heading over a failure the API answered, when the block has its own. */
  readonly title?: string | undefined;
  readonly children?: ReactNode | undefined;
}) {
  return (
    <div data-slot="failure-state" className="min-w-0">
      <FailureNotice failure={failure} {...(title === undefined ? {} : { title })}>
        {children}
      </FailureNotice>
    </div>
  );
}
