#!/usr/bin/env bash
# Install (or remove with UNINSTALL=1) the Dayfold agent on a jailbroken Kindle.
# The script lives in /var/local/dayfold (outside the USB volume); an upstart job starts it with
# the framework. The root filesystem is remounted read-write only to copy the job file.
set -euo pipefail
cd "$(dirname "$0")"
KINDLE=${KINDLE:-kindle}
# older versions shipped only the sleep screen watcher
CLEAN_OLD="stop dayfold-screensaver 2>/dev/null; rm -f /etc/upstart/dayfold-screensaver.conf /var/local/dayfold/screensaver.sh"
if [ "${UNINSTALL:-0}" = "1" ]; then
  ssh "$KINDLE" "stop dayfold-agent 2>/dev/null; mntroot rw && { rm -f /etc/upstart/dayfold-agent.conf; $CLEAN_OLD; }; mntroot ro; rm -rf /var/local/dayfold /mnt/us/dayfold/screensaver"
  echo "Agente Dayfold removido."
  exit 0
fi
ssh "$KINDLE" "mkdir -p /var/local/dayfold && cat > /var/local/dayfold/agent.sh && chmod +x /var/local/dayfold/agent.sh" < dayfold-agent.sh
ssh "$KINDLE" "mntroot rw && { cat > /etc/upstart/dayfold-agent.conf; $CLEAN_OLD; }; mntroot ro" < dayfold-agent.conf
ssh "$KINDLE" "stop dayfold-agent 2>/dev/null; start dayfold-agent"
echo "Agente instalado: edições novas entram na biblioteca sozinhas (com Wi-Fi ligado)."
