#!/usr/bin/env bash
# Install (or remove with UNINSTALL=1) the Dayfold sleep screen watcher on a jailbroken Kindle.
# The script lives in /var/local/dayfold (survives USB mounts); an upstart job starts it with the
# framework. The root filesystem is remounted read-write only to copy the job file.
set -euo pipefail
cd "$(dirname "$0")"
KINDLE=${KINDLE:-kindle}
if [ "${UNINSTALL:-0}" = "1" ]; then
  ssh "$KINDLE" "stop dayfold-screensaver 2>/dev/null; mntroot rw && rm -f /etc/upstart/dayfold-screensaver.conf; mntroot ro; rm -rf /var/local/dayfold /mnt/us/dayfold/screensaver"
  echo "Vigia da tela de descanso removido."
  exit 0
fi
ssh "$KINDLE" "mkdir -p /var/local/dayfold /mnt/us/dayfold/screensaver && cat > /var/local/dayfold/screensaver.sh && chmod +x /var/local/dayfold/screensaver.sh" < dayfold-screensaver.sh
ssh "$KINDLE" "mntroot rw && cat > /etc/upstart/dayfold-screensaver.conf; mntroot ro" < dayfold-screensaver.conf
ssh "$KINDLE" "stop dayfold-screensaver 2>/dev/null; start dayfold-screensaver"
echo "Vigia instalado. Ligue a opção em Jornal › Aparelho e sincronize o plugin."
