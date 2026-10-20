#!/bin/zsh
# Hand mutation of console guards, in the throwaway worktree only. Each row: file, before, after,
# test files. Restores byte-identically and checks the md5.
export PATH=/opt/homebrew/bin:$PATH NODE_OPTIONS=--no-experimental-webstorage
MUT=/Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/wp-adoption-mut/console
cd "$MUT" || exit 1

run() {
  local label="$1" file="$2" before="$3" after="$4"; shift 4
  local sum_before=$(md5 -q "$file")
  cp "$file" $MUT/../.mut-backup
  python3 - "$file" "$before" "$after" <<'PY'
import sys
path, before, after = sys.argv[1:4]
s = open(path).read()
assert s.count(before) == 1, f"{before!r} matches {s.count(before)} places"
open(path, "w", newline="\n").write(s.replace(before, after))
PY
  local out
  out=$(npx vitest run "$@" --testTimeout=120000 2>&1)
  local failed=$(echo "$out" | grep -E "^ *(FAIL|×)" | head -3 | tr '\n' ';')
  cp $MUT/../.mut-backup "$file"
  local sum_after=$(md5 -q "$file")
  [[ "$sum_before" == "$sum_after" ]] && restored=restored || restored=NOT-RESTORED
  if [[ -n "$failed" ]]; then echo "CAUGHT   | $label | $failed | $restored"; else echo "SURVIVED | $label | $restored"; fi
}

run "the suggestion is asked for even once something is connected" src/pages/connectors/ConnectorStart.tsx 'useResource<unknown>(connectedAny ? null : START_API_PATH)' 'useResource<unknown>(START_API_PATH)' tests/connector-start.test.tsx
run "the suggestion is drawn once something is connected" src/pages/connectors/ConnectorStart.tsx 'if (connectedAny || answer.busy' 'if (answer.busy' tests/connector-start.test.tsx
run "a body that names no source still draws a card" src/pages/adoptionCoverageQuery.ts 'return source === undefined ? undefined : { source, label: text(payload["label"]) ?? source };' 'return { source: source ?? "", label: text(payload["label"]) ?? source ?? "" };' tests/connector-start.test.tsx
run "a question with no system to check it in is drawn" src/pages/adoptionCoverageQuery.ts 'if (question !== undefined && checkIn !== undefined) {' 'if (question !== undefined) {' tests/ask-welcome.test.tsx
run "the fixed questions wait for the questions from data" src/pages/AskWelcome.tsx 'if (questions.length === 0 && fromData.length === 0) {' 'if (fromData.length === 0) {' tests/ask-welcome.test.tsx
run "the coverage section is drawn while the install has it off" src/pages/reports/AdoptionCoverage.tsx 'if (coverage === null || !coverage.switchedOn) {' 'if (coverage === null) {' tests/report-dashboards.test.tsx -t Adoption
run "a connected department with no count reads as nought" src/pages/reports/AdoptionCoverage.tsx 'return row.records === undefined ? NOT_READ_YET : (countWords(row.records) ?? NOT_READ_YET);' 'return countWords(row.records ?? 0) ?? NOT_READ_YET;' tests/report-dashboards.test.tsx -t Adoption
run "a not-connected department is left out of the table" src/pages/adoptionCoverageQuery.ts 'if (department === undefined || state === undefined || stateWords === undefined) {' 'if (department === undefined || state === undefined || stateWords === undefined || state === "not_connected") {' tests/report-dashboards.test.tsx -t Adoption
