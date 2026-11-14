#!/bin/sh
# Dayfold agent for jailbroken Kindles (runs from the upstart job dayfold-agent).
#
# * Keeps the latest edition in documents/Dayfold, so it shows up on top of the Kindle library
#   (with KOmpanion) without opening KOReader. It checks when the Kindle wakes up and every
#   30 minutes while awake, and only when Wi-Fi is already connected: it never turns Wi-Fi on.
# * Draws the latest front page over the stock sleep screen when that option is on in the
#   dashboard (Jornal > Aparelho). Inside KOReader the plugin's own setting does it.
#
# Server and token come from the KOReader plugin config (dayfold_config.lua).

CFG=/mnt/us/koreader/plugins/dayfold.koplugin/dayfold_config.lua
DIR=/mnt/us/documents/Dayfold
VAR=/var/local/dayfold
IMG=/mnt/us/dayfold/screensaver/cover.png
FBINK=/var/local/kmc/bin/fbink
KEEP=7
INTERVAL=1800

mkdir -p "$VAR"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$VAR/agent.log"; }
cfg() { sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$CFG" 2>/dev/null | head -n 1; }
wifi_up() { [ "$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null)" = "CONNECTED" ]; }

prune() {
    ls -1 "$DIR"/dayfold-*.epub 2>/dev/null | sort -r | tail -n +$((KEEP + 1)) | while read -r old; do
        rm -f "$old" "${old%.epub}.games.json"
        rm -rf "${old%.epub}.sdr" "$old.sdr"
        log "removida $(basename "$old")"
    done
}

sync_edition() {
    server=$(cfg server)
    token=$(cfg token)
    [ -n "$server" ] && [ -n "$token" ] || return 0
    wifi_up || return 0
    meta=$(curl -fsS -m 20 -H "X-Dayfold-Token: $token" "$server/feed/latest.json") || { log "servidor indisponível"; return 0; }
    field() { echo "$meta" | sed -n "s/.*\"$1\": *\"\([^\"]*\)\".*/\1/p"; }
    id=$(field id)
    name=$(field epub_name)
    games=$(field games_name)
    [ -n "$id" ] && [ -n "$name" ] || return 0
    mkdir -p "$DIR"
    if [ ! -f "$DIR/$name" ]; then
        tmp="$DIR/.$name.part"
        if curl -fsS -m 600 -H "X-Dayfold-Token: $token" -o "$tmp" "$server/feed/latest.epub"; then
            curl -fsS -m 60 -H "X-Dayfold-Token: $token" -o "$DIR/$games" "$server/feed/latest.games.json"
            mv "$tmp" "$DIR/$name"   # the library picks it up as a new book
            echo "$id" > "$VAR/last_edition"
            log "nova edição $name"
            prune
        else
            rm -f "$tmp"
            log "falha ao baixar $name"
        fi
    fi
    if echo "$meta" | grep -q '"screensaver": *true'; then
        mkdir -p "${IMG%/*}"
        curl -fsS -m 60 -H "X-Dayfold-Token: $token" -o "$IMG.part" "$server/feed/latest.cover.png" && mv "$IMG.part" "$IMG"
    else
        rm -f "$IMG" "$IMG.part"
    fi
}

draw_sleep_screen() {
    [ -f "$IMG" ] || return 0
    ps | grep -q "[r]eader.lua" && return 0   # KOReader draws its own sleep screen
    sleep 2                                    # let the stock screensaver finish first
    "$FBINK" -q -c -f -g file="$IMG",halign=center,valign=center
}

# periodic check while awake (the timer stops while the Kindle sleeps)
( sleep 30; while true; do sync_edition; sleep "$INTERVAL"; done ) &

lipc-wait-event -m com.lab126.powerd goingToScreenSaver,outOfScreenSaver | while read -r event _; do
    case "$event" in
        goingToScreenSaver) draw_sleep_screen ;;
        outOfScreenSaver)
            # Wi-Fi reconnects a few seconds after waking up
            ( n=0; while [ $n -lt 12 ] && ! wifi_up; do sleep 5; n=$((n + 1)); done; sync_edition ) &
            ;;
    esac
done
