/**
 * Fields and records, at the name the route file loads and the tests import. The page is
 * `classification/ClassificationPage.tsx`, built on the shared page kit.
 *
 * Task ids: M7.5.3, M7.7.3, M27.16.1
 */

import { useParams } from "react-router-dom";
import { ClassificationPage } from "./classification/ClassificationPage";

export {
  AN_UPLOAD_NEEDS,
  CLASSIFICATION_HEADING,
  IT_DOES_NOT_WIDEN,
  IT_WAS_APPLIED,
  IT_WAS_NOT_APPLIED,
  IT_WAS_NOT_UPLOADED,
  IT_WIDENS,
  IT_WOULD_NOT_LOAD,
  NOTHING_ASKED_FOR,
  NOTHING_WOULD_CHANGE,
  NO_SUCH_COLUMN,
  REVIEW_BEFORE_APPLYING,
  THERE_IS_NO_SAVE,
  UPLOAD_HEADING,
  UPLOAD_LEDE,
  WHAT_A_WIDENING_MEANS,
  WHAT_THE_EPOCH_IS,
} from "./classification/ClassificationPage";

export function Classification() {
  const { entity, column } = useParams();
  return <ClassificationPage entity={entity} column={column} />;
}
