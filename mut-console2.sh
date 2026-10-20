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

run "a connected department with no count reads as nought" src/pages/reports/AdoptionCoverage.tsx 'return row.records === undefined ? NOT_READ_YET : (countWords(row.records) ?? NOT_READ_YET);' 'return countWords(row.records ?? 0) ?? NOT_READ_YET;' tests/report-dashboards.test.tsx -t Adoption
