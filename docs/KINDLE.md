# Reading Dayfold on a Kindle (and other e-readers)

The stock Kindle reader does not open EPUB files. Dayfold therefore targets
[KOReader](https://koreader.rocks), a free reader that runs on Kindle, Kobo, PocketBook,
reMarkable and Android. On a Kindle, KOReader requires a jailbroken device. A Kindle without
jailbreak can still get the edition through Amazon's Send to Kindle, without the interactive
games: see [Kindle without jailbreak](#kindle-without-jailbreak-send-to-kindle).

There are three ways to get the daily edition on KOReader, from most to least integrated.

## 1. KOReader + the Dayfold plugin (recommended)

The plugin:

* downloads the latest EPUB and its `games.json` over Wi-Fi (menu, or automatically on start and on wake when Wi-Fi is already on);
* opens the interactive game when you tap **Jogar no KOReader** on a puzzle page;
* shows an **end of edition** dialog after the last page (play the puzzles, back to the front page,
  fetch a new edition, library);
* keeps the progress of each game per edition;
* hides solutions and pocket-guess pages from the page flow (they stay reachable by link).

### Install over SSH (jailbroken Kindle)

You need SSH access to the Kindle (for example the `dropbear-ssh` KPM package) and an entry in
`~/.ssh/config`:

```
Host kindle
    HostName 192.168.0.5
    Port 2022
    User root
```

Then, from the repository:

```bash
make kindle-koreader                                   # installs KOReader through KPM, if missing
make kindle-install SERVER=http://192.168.0.10:8422    # plugin + config + today's edition
```

`kindle-install` reads the feed token from the dashboard API. If the dashboard has a password,
pass it explicitly: `TOKEN=... make kindle-install SERVER=...`.

### Install by hand (USB)

1. Install KOReader for your device (Kindle: KPM package `koreader`, or the official
   `koreader-kindlehf-*.zip` from the KOReader releases).
2. Copy `koreader/plugins/dayfold.koplugin` to `koreader/plugins/` on the device.
3. Copy `dayfold_config.sample.lua` to `dayfold_config.lua` in the same folder and fill in the
   server address and the feed token (dashboard › **Kindle**). You can also set them on the
   device: KOReader menu › **Tools** (wrench) › **Dayfold** › **Configurar servidor**.
4. Restart KOReader. Editions are saved to `<home folder>/Dayfold`
   (`/mnt/us/documents/Dayfold` on a Kindle) and only the last 7 are kept.

### Show editions in the Kindle library (optional)

```bash
make kindle-library
```

Installs [KOmpanion](https://github.com/KindleModding/repo) through KPM. The stock Kindle
library then lists every Dayfold edition as a book, with the front page as cover and a title like
**Dayfold · 13 nov. 2026**; tapping it opens the edition in KOReader with the plugin. KOmpanion
registers an EPUB extractor and launcher in `/var/local/appreg.db` (backed up first to
`/mnt/us/appreg.db.backup-dayfold`); undo with `kpm uninstall kompanion`.

## 2. OPDS catalog

KOReader: **Search** › **OPDS catalog** › **+** and paste the address shown on the dashboard
Kindle page, for example `http://192.168.0.10:8422/opds?token=...`. Every recent edition appears
with its cover. Games work as printed puzzles; the interactive versions need the plugin.

## 3. Direct download

Any EPUB reader can fetch `http://SERVER:8422/feed/latest.epub?token=...`. The token can also be
sent as the password of HTTP Basic authentication or in the `X-Dayfold-Token` header.

### The device feed (`/feed/latest.json`)

The plugin reads this file to decide whether there is anything new to download; your own scripts
can use it the same way. It describes the latest ready edition:

| Field | Meaning |
| --- | --- |
| `id` | the edition: `dayfold-<date>-<number>` |
| `rev` | a revision of the EPUB file itself: its modification time in seconds |
| `epub`, `games`, `cover` | paths to fetch, with the token |
| `epub_name`, `games_name` | the names the device must save those files under |
| `size` | the EPUB size in bytes, when the file exists |
| `title`, `number`, `date`, `headline` | what the device shows when an edition arrives |
| `screensaver` | whether the cover is used as the sleep screen |

**A device is up to date only when both `id` and `rev` match what it downloaded.** `id` alone is
not enough: re-typesetting an edition (**Recompor** on the dashboard) rewrites it in place, keeping
the date and the number, so the file changes while its name does not. The plugin stores the pair
on every sync and downloads again when either differs, which is how a corrected edition replaces
the copy already on the device.

`rev` is optional for compatibility: a server that does not send it (or has no EPUB yet, when it
is `null`) is treated as a match, and the file name stays the only evidence — the behaviour before
revisions existed. A device upgrading from such a version downloads the current edition once more,
then settles into the `id` + `rev` rule.

## Kindle without jailbreak (Send to Kindle)

On the dashboard **Kindle** page choose **No jailbreak**. Amazon converts the EPUB and delivers it
to the device over Wi-Fi, under Documents (it also stays in the Amazon cloud and syncs with the
Kindle apps). Every edition gets a native Kindle EPUB next to the KOReader one: no
`dayfold://` links and, when puzzles are included, the answer pages only after an "Answers ahead"
page at the very end.

**Automatic delivery through Gmail.** The server e-mails the EPUB to the device's
`@kindle.com` address from your own Gmail account:

1. Turn on 2-Step Verification on the Google account and create an app password at
   <https://myaccount.google.com/apppasswords> (16 letters; it is not the account password).
2. At Amazon, **Content & Devices** › **Preferences** › **Personal Document Settings**: add the
   Gmail address to the approved e-mail list and copy the device's `@kindle.com` address.
3. Fill in both addresses and the app password on the dashboard, save, and tick
   **Send every new edition automatically**. "Send the latest edition now" sends on demand.

The app password is stored in the Dayfold database and never sent back to the browser. A failed
delivery is logged in the generation job and shown on the Kindle page; it does not fail the
edition. Gmail limits attachments to 25 MB (an edition is usually 2 to 5 MB).

**Manual delivery.** "Download EPUB for Kindle" (or `/feed/latest.kindle.epub?token=...` on a
phone) and send it with the [Send to Kindle website](https://www.amazon.com/sendtokindle), the
Send to Kindle app for Windows and macOS, or the Kindle phone app (**Share** › **Kindle**).
Copying the EPUB over USB does not work.

**Puzzles.** On by default. They were validated on a Kindle Paperwhite 5 through Send to Kindle:
Sudoku, Word Search and Crossword as printed puzzles, the pocket Word of the Day with its hint
links, and "See solution" links, with no solution or hint showing up as you turn pages. To check
another device, use **Test edition** (the latest edition with every game and a checklist page);
if solutions leak while turning pages, choose **No games** and the native version has no puzzles
at all.

## Battery

* The server does all the work; the device only downloads one file per day.
* Images are already grayscale and sized for the screen, fonts are embedded, nothing is
  processed on the device.
* The plugin never turns Wi-Fi on by itself during automatic sync. It syncs only if Wi-Fi is
  already connected, or when you tap **Baixar edição de hoje**.

## Dayfold agent: new editions in the library without opening KOReader

```bash
make kindle-agent                       # UNINSTALL=1 ./kindle/install-agent.sh removes it
```

A small shell script (`/var/local/dayfold/agent.sh`, started with the Kindle interface by the
upstart job `/etc/upstart/dayfold-agent.conf`) that:

* checks the server when the Kindle wakes up and every 30 minutes while it is awake, **only if Wi-Fi
  is already connected** (it never turns Wi-Fi on), and downloads a new edition to
  `documents/Dayfold`. Each edition has its own file name (`dayfold-2026-11-13-0002.epub`), so a
  second edition on the same day is a new book;
* keeps the last 7 editions;
* draws the front page over the stock sleep screen when that option is on (see below).

With KOmpanion and the library sorted by **Mais recentes / Recent**, the newest edition is always the
first book. Server and token are read from the plugin's `dayfold_config.lua`; the log is in
`/var/local/dayfold/agent.log`. Installing remounts the root filesystem read-write for a moment, and
a firmware update removes the job (run `make kindle-agent` again).

## Front page as sleep screen (optional, off by default)

Turn on **Jornal › Aparelho › Usar a capa do último jornal como tela de descanso do Kindle** in the
dashboard. On the next sync the plugin downloads the latest cover to
`/mnt/us/dayfold/screensaver/cover.png` and:

* **inside KOReader**, sets KOReader's sleep screen to that image (no "Sleeping" message). The
  previous sleep screen settings are saved and restored when you turn the option off;
* **in the stock Kindle interface**, the Dayfold agent (below) draws it over the stock screensaver.

Turning the option off makes the plugin delete the cover on the next sync. The cover is also served
at `/feed/latest.cover.png?token=...` for your own scripts.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "token inválido" | The token was rotated on the dashboard. Update it in **Configurar servidor**. |
| "rede indisponível" | The Kindle cannot reach the server. Use the server LAN IP, not `localhost`. |
| Puzzle link shows "Invalid or external link" | The plugin is not installed or the file name was changed. Keep `dayfold-YYYY-MM-DD.epub` and the `.games.json` next to it. |
| No games menu | The `.games.json` file is missing. Sync again from the plugin. |
