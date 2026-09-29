/**
 * Learning, rebuilt on the page kit in `learning/LearningPage.tsx`. This module keeps the name the
 * route file imports and reads the view out of the address.
 *
 * Task ids: M27.7.21, M27.16.1
 */

import { useParams } from "react-router-dom";
import { learningViewNamed } from "./learningQuery";
import { LearningPage } from "./learning/LearningPage";

export function Learning() {
  const { view } = useParams();
  return <LearningPage view={learningViewNamed(view)} />;
}
