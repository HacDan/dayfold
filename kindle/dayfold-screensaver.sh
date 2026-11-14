#!/bin/sh
# Dayfold sleep screen watcher for jailbroken Kindles.
#
# Waits for powerd's goingToScreenSaver event and draws the latest Dayfold front page over the
# stock screensaver. It does nothing unless the KOReader plugin left a cover at $IMG, and the
# plugin only does that when "use the front page as sleep screen" is on in the dashboard.
# Inside KOReader the plugin's own sleep screen setting is used instead.
IMG=/mnt/us/dayfold/screensaver/cover.png
FBINK=/var/local/kmc/bin/fbink

lipc-wait-event -m com.lab126.powerd goingToScreenSaver | while read -r _event; do
    [ -f "$IMG" ] || continue
    ps | grep -q "[r]eader.lua" && continue   # KOReader draws its own sleep screen
    sleep 2                                    # let the stock screensaver finish first
    "$FBINK" -q -c -f -g file="$IMG",halign=center,valign=center
done
