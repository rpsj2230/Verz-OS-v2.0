/**
 * Memory, rebuilt on the page kit: `memory/MemoryPage.tsx` at the bare address, where a person is
 * chosen by name, and `memory/MemoryDetailPage.tsx` for one person's memory and its views. This
 * module keeps the name the route file imports and reads the address.
 *
 * Task ids: M27.7.22, M27.16.1
 */

import { useParams } from "react-router-dom";
import { memoryViewNamed, referenceProblem } from "./memoryQuery";
import { MemoryDetailPage } from "./memory/MemoryDetailPage";
import { MemoryPage } from "./memory/MemoryPage";

export function Memory() {
  const { subject, view } = useParams();
  if (subject === undefined) {
    return <MemoryPage />;
  }
  // A reference the route would refuse is said in words here and never asked about.
  const problem = referenceProblem(subject);
  return problem === null ? <MemoryDetailPage subject={subject} view={memoryViewNamed(view)} /> : <MemoryPage problem={problem} />;
}
