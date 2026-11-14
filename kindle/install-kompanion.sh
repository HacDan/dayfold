#!/usr/bin/env bash
# Show EPUB editions in the stock Kindle library (cover + title) and open them in KOReader.
# Installs KOmpanion through KPM. It registers an EPUB metadata extractor and a launcher in
# /var/local/appreg.db; a backup of that database is kept in /mnt/us first.
# Usage: KINDLE=kindle ./kindle/install-kompanion.sh   (undo: kpm uninstall kompanion)
set -euo pipefail
KINDLE=${KINDLE:-kindle}
KPM=/var/local/kmc/bin/kpm
ssh "$KINDLE" "test -x $KPM" || { echo "KPM não encontrado no Kindle." >&2; exit 1; }
ssh "$KINDLE" "test -f /mnt/us/appreg.db.backup-dayfold || cp /var/local/appreg.db /mnt/us/appreg.db.backup-dayfold"
ssh "$KINDLE" "$KPM -y update >/dev/null; $KPM -y install kompanion"
ssh "$KINDLE" "sqlite3 /var/local/appreg.db \"select count(*) from associations where handlerId like 'com.notmarek.kompanion%';\""
echo "KOmpanion instalado: as edições em documents/Dayfold aparecem na biblioteca do Kindle."
