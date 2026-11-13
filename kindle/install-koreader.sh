#!/usr/bin/env bash
# Install KOReader on a jailbroken Kindle through KPM (Kindle Package Manager).
# Usage: KINDLE=kindle ./kindle/install-koreader.sh   (KINDLE = ssh host alias)
set -euo pipefail
KINDLE=${KINDLE:-kindle}
KPM=/var/local/kmc/bin/kpm

if ssh "$KINDLE" "test -x /mnt/us/koreader/koreader.sh"; then
  echo "KOReader já está instalado em /mnt/us/koreader."
  exit 0
fi
if ! ssh "$KINDLE" "test -x $KPM"; then
  echo "KPM não encontrado. Instale o KOReader manualmente: docs/KINDLE.md" >&2
  exit 1
fi
ssh "$KINDLE" "$KPM -y update && $KPM -y install koreader"
ssh "$KINDLE" "ls /mnt/us/koreader/koreader.sh && ls /mnt/us/documents | grep -i koreader || true"
echo "KOReader instalado. Abra-o pela biblioteca do Kindle."
