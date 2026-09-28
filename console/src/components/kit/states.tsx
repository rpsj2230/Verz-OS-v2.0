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
