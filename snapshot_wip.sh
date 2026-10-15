#!/bin/bash
# Snapshot every worktree that has unpushed commits or uncommitted work to wip/1015/<name>
# without touching the worktree, its index or its branch (temporary index, commit-tree, push by sha).
set -u
ROOT=/Users/rupash/Claude/Verz-OS-v2.0/brain
cd "$ROOT"
git fetch -q origin 2>/dev/null
git worktree list --porcelain | awk '/^worktree /{print $2}' | while read -r wt; do
  [ -d "$wt" ] || continue
  name=$(basename "$wt")
  case "$name" in brain) continue;; esac
  cd "$wt" || continue
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null) || continue
  [ "$branch" = HEAD ] && continue
  ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
  dirty=$(git status --porcelain 2>/dev/null | grep -v node_modules | grep -c .)
  remote=$(git rev-parse --verify -q "origin/$branch" || true)
  head=$(git rev-parse HEAD)
  if [ -n "$remote" ] && [ "$remote" = "$head" ] && [ "$dirty" = 0 ]; then continue; fi
  if [ "$ahead" = 0 ] && [ "$dirty" = 0 ]; then continue; fi
  idx=$(mktemp -u /private/tmp/claude-501/wipidx.XXXXXX)
  GIT_INDEX_FILE=$idx git read-tree HEAD 2>/dev/null
  GIT_INDEX_FILE=$idx git add -A -- . ':!console/node_modules' ':!node_modules' ':!.venv' 2>/dev/null
  tree=$(GIT_INDEX_FILE=$idx git write-tree)
  commit=$(git commit-tree "$tree" -p HEAD -m "WIP snapshot of $branch from $name (2026-10-15, limit stop)")
  rm -f "$idx"
  if git push -q --no-verify origin "$commit:refs/heads/wip/1015/$name" 2>/dev/null; then
    echo "pushed $name ($branch) ahead=$ahead dirty=$dirty -> wip/1015/$name"
  else
    echo "FAILED $name ($branch)"
  fi
done
