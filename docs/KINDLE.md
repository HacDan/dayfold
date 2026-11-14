# Reading Dayfold on a Kindle (and other e-readers)

The stock Kindle reader does not open EPUB files. Dayfold therefore targets
[KOReader](https://koreader.rocks), a free reader that runs on Kindle, Kobo, PocketBook,
reMarkable and Android. On a Kindle, KOReader requires a jailbroken device.

There are three ways to get the daily edition, from most to least integrated.

## 1. KOReader + the Dayfold plugin (recommended)

The plugin:

* downloads today's EPUB and its `games.json` over Wi-Fi (menu or automatically when Wi-Fi is already on);
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

## 2. OPDS catalog

KOReader: **Search** › **OPDS catalog** › **+** and paste the address shown on the dashboard
Kindle page, for example `http://192.168.0.10:8422/opds?token=...`. Every recent edition appears
with its cover. Games work as printed puzzles; the interactive versions need the plugin.

## 3. Direct download

Any EPUB reader can fetch `http://SERVER:8422/feed/latest.epub?token=...`. The token can also be
sent as the password of HTTP Basic authentication or in the `X-Dayfold-Token` header.
`/feed/latest.json` returns the edition metadata for scripts.

## Battery

* The server does all the work; the device only downloads one file per day.
* Images are already grayscale and sized for the screen, fonts are embedded, nothing is
  processed on the device.
* The plugin never turns Wi-Fi on by itself during automatic sync. It syncs only if Wi-Fi is
  already connected, or when you tap **Baixar edição de hoje**.

## Cover and screensaver

The cover is a 16 gray level PNG sized for the device (1236 × 1648 by default; change it on the
dashboard **Jornal** page). It is the EPUB cover, so KOReader shows it in the library and can use
it as the sleep screen: KOReader menu › **Settings** › **Screen** › **Sleep screen** › **Wallpaper** ›
**Show book cover on sleep screen**. The latest cover is also served at
`/feed/latest.cover.png?token=...` for custom screensaver scripts.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| "token inválido" | The token was rotated on the dashboard. Update it in **Configurar servidor**. |
| "rede indisponível" | The Kindle cannot reach the server. Use the server LAN IP, not `localhost`. |
| Puzzle link shows "Invalid or external link" | The plugin is not installed or the file name was changed. Keep `dayfold-YYYY-MM-DD.epub` and the `.games.json` next to it. |
| No games menu | The `.games.json` file is missing. Sync again from the plugin. |
