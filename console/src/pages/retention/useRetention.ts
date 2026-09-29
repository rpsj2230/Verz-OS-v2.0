/**
 * The three answers every Retention view reads: the newest sweep report, the controls this reader
 * may be shown with the sentences each act confirms with, and the erasure queue. Asked again under a
 * new version after any write, so what is drawn is what is stored rather than what was sent.
 *
 * Task ids: M27.7.24, M27.16.1
 */

import { useCallback, useMemo, useState } from "react";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  CONTROLS_API_PATH,
  ERASURES_API_PATH,
  reportOf,
  RETENTION_API_PATH,
  type Controls,
  type ErasureQueue,
  type Report,
  type RetentionAnswer,
} from "../retentionQuery";
import { peopleIn } from "../review/parts";

export interface Retention {
  readonly report: Report | null;
  readonly controls: Controls | null;
  readonly queue: ErasureQueue | null;
  /** The names of who filed each erasure request. */
  readonly filers: Readonly<Record<string, string>>;
  readonly failure: ApiFailure | null;
  readonly busy: boolean;
  readonly version: number;
  readonly again: () => void;
}

export function useRetention(): Retention {
  const [version, setVersion] = useState(0);
  const answer = useResource<RetentionAnswer>(RETENTION_API_PATH, version);
  const controls = useResource<Controls>(CONTROLS_API_PATH, version);
  const queue = useResource<ErasureQueue>(ERASURES_API_PATH, version);
  const again = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const filers = useMemo(() => peopleIn(queue.data), [queue.data]);
  return {
    report: reportOf(answer.data),
    controls: controls.data,
    queue: queue.data,
    filers,
    failure: answer.failure ?? controls.failure ?? queue.failure,
    busy: (answer.busy && answer.data === null) || (controls.busy && controls.data === null) || (queue.busy && queue.data === null),
    version,
    again,
  };
}
