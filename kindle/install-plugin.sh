#!/usr/bin/env bash
# Copy the Dayfold KOReader plugin to the Kindle and point it to this server.
# Usage: KINDLE=kindle SERVER=http://192.168.0.10:8422 [TOKEN=...] ./kindle/install-plugin.sh
set -euo pipefail
cd "$(dirname "$0")/.."
KINDLE=${KINDLE:-kindle}
SERVER=${SERVER:?defina SERVER, ex.: http://192.168.0.10:8422}
SERVER=${SERVER%/}
if [ -z "${TOKEN:-}" ]; then
  # The first reader's token; set TOKEN=... for another reader or a password protected dashboard.
  TOKEN=$(curl -fsS "$SERVER/api/readers" | python3 -c 'import sys,json;print(json.load(sys.stdin)[0]["token"])') || {
    echo "Não consegui ler o token do primeiro leitor (dashboard com senha?). Rode com TOKEN=..." >&2; exit 1; }
fi
DEST=/mnt/us/koreader/plugins/dayfold.koplugin
ssh "$KINDLE" "test -d /mnt/us/koreader/plugins" || { echo "KOReader não encontrado no Kindle. Rode: make kindle-koreader" >&2; exit 1; }
tar -C koreader/plugins -cf - --exclude dayfold_config.lua dayfold.koplugin | ssh "$KINDLE" "rm -rf $DEST && tar -C /mnt/us/koreader/plugins -xf -"
ssh "$KINDLE" "cat > $DEST/dayfold_config.lua" <<LUA
return {
    server = "$SERVER",
    token = "$TOKEN",
    keep = 7,
}
LUA
# First edition, so there is something to read right away.
ssh "$KINDLE" "mkdir -p /mnt/us/documents/Dayfold"
META=$(curl -fsS "$SERVER/feed/latest.json?token=$TOKEN" || true)
if [ -n "$META" ]; then
  NAME=$(echo "$META" | python3 -c 'import sys,json;print(json.load(sys.stdin)["epub_name"])')
  GAMES=${NAME%.epub}.games.json
  curl -fsS "$SERVER/feed/latest.epub?token=$TOKEN" | ssh "$KINDLE" "cat > /mnt/us/documents/Dayfold/$NAME"
  curl -fsS "$SERVER/feed/latest.games.json?token=$TOKEN" | ssh "$KINDLE" "cat > /mnt/us/documents/Dayfold/$GAMES"
  echo "Edição copiada: documents/Dayfold/$NAME"
fi
echo "Plugin instalado. Reinicie o KOReader e use Menu › Ferramentas › Dayfold."
