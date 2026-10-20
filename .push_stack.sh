#!/bin/zsh
export PATH=/opt/homebrew/bin:$PATH
SP=/private/tmp/claude-501/-Users-rupash-Claude-Verz-OS-v2-0-brain--scratch-wt-cg-governance/0c352820-7ea6-4c17-be4f-1f3d73ae9161/scratchpad
cd /Users/rupash/Claude/Verz-OS-v2.0/brain/.scratch/wt-cg-governance/trial/wk-model-merge || exit 1
rm -f $SP/push_done.txt
{
  for pair in "9dbee327 M7/model-server-frame" "f0410a9d M7/model-server-document-parts" "eb7b165d M7/model-server-embedding" "dfe7f8e8 M7/model-server-provenance" "1e478e73 M7/model-server-entities"; do
    set -- ${=pair}
    echo "== pushing $2 ($1)"
    git push origin "${1}:refs/heads/${2}" 2>&1 | tail -15
    echo "exit: ${pipestatus[1]}"
  done
} > $SP/push.txt 2>&1
echo done > $SP/push_done.txt
