# MintShare

Een **ShareX-kloon voor Linux Mint** (Cinnamon, MATE en Xfce op X11): screenshots, schermopnames, annoteren,
OCR, uploaden naar tientallen diensten en een hele set extra gereedschappen. Geschreven in Python 3 + GTK3, zodat het
zonder extra frameworks draait op een standaard Linux Mint 21/22.

## Installeren

```bash
cd mintshare
./install.sh            # installeert de benodigde apt-pakketten en MintShare in ~/.local
mintshare --apply-hotkeys
```

Verwijderen: `./uninstall.sh`. Starten zonder installeren: `./bin/mintshare`.

## Wat verandert er op je systeem? (en hoe draai je het terug)

* `./install.sh --dry-run` laat zien welke apt-pakketten en bestanden erbij komen; er wordt niets gewijzigd.
  Zonder `--dry-run` vraagt het script eerst om bevestiging. Alles van MintShare zelf komt in `~/.local` (geen root nodig).
* Sneltoetsen worden **alleen** aangepast als je zelf `mintshare --apply-hotkeys` uitvoert. Bekijk eerst wat er zou
  veranderen met `mintshare --show-hotkey-changes`. Van de ingebouwde Cinnamon-sneltoetsen die worden vrijgemaakt
  (bijv. `Print`) wordt een back-up bewaard.
* `mintshare --remove-hotkeys` of `./uninstall.sh` zet de originele sneltoetsen exact terug en verwijdert de
  eigen sneltoetsen, het menu-item en de autostart. Instellingen blijven in `~/.config/mintshare` (zelf te verwijderen).
* Er wordt **niets automatisch geüpload**: uploaden staat standaard uit en gebeurt alleen als jij het kiest. Er is geen
  telemetrie. Uploads gaan naar de dienst die jij kiest (ook je eigen server via FTP/SFTP/WebDAV/S3/map).
* HiDPI (bijv. 4K met 200% schaling) wordt ondersteund en is getest met `GDK_SCALE=2`.

## Wat kan het

| ShareX-functie | MintShare |
|---|---|
| Volledig scherm / monitor / actief venster / venster kiezen | ✅ (`fullscreen`, `monitor`, `active_window`, `window`) |
| Regio-capture met vergrootglas, kruisdraad, maatvoering, snappen op vensters | ✅ (`region`, `last_region`) |
| Scrolling capture | ✅ (muiswiel + automatisch aan elkaar plakken) |
| Auto capture (timer) | ✅ |
| Webpagina-capture | ✅ (via Chromium/Chrome of Firefox headless) |
| Schermopname MP4/WebM/MKV + audio, GIF-opname | ✅ (ffmpeg) |
| Tekst herkennen (OCR) | ✅ (Tesseract; `eng`, `nld`, …) |
| Afbeeldingseditor: rechthoek, ellips, lijn, pijl, pen, markeerstift, tekst, stapnummers, blur, pixelate, spotlight, crop, roteren, spiegelen, ongedaan maken | ✅ |
| Effecten: rand, schaduw, afgeronde hoeken, watermerk (tekst/afbeelding), grijstinten, formaat | ✅ (automatisch na capture of via Tools) |
| Na-capture-taken: kopiëren, opslaan, opslaan als, uploaden, editor, pinnen, printen, OCR, bestand verwijderen na upload | ✅ (instelbaar, per workflow te overschrijven) |
| Na-upload-taken: URL verkorten, kopiëren, openen, QR-code tonen | ✅ |
| Uploaders | ✅ Catbox, Litterbox, 0x0.st, Imgur, paste.rs, dpaste, Pastebin, GitHub Gist, Dropbox, FTP/FTPS, SFTP, WebDAV/Nextcloud, Amazon S3 (+MinIO/R2/Backblaze), map/NAS |
| URL-verkorters | ✅ is.gd, v.gd, TinyURL, eigen |
| **Custom uploaders (`.sxcu`)** | ✅ ShareX-bestanden importeren (`$json:…$`, `$regex:…$`, `$header:…$`, `$xml:…$`, `$response$`, `$filename$`, `$input$`, multipart/form/JSON/binary) |
| Upload bestand, klembord, tekst, URL, slepen en neerzetten, drop-venster | ✅ |
| Geschiedenis met zoeken, miniaturen, opnieuw uploaden | ✅ (SQLite) |
| Workflows / hotkeys met eigen na-capture-instellingen | ✅ |
| Kleurkiezer (scherm + palet, HEX/RGB/HSL/HSV/CMYK), liniaal, pin-to-screen | ✅ |
| QR-code maken en scannen, hash check, directory indexer, metadata-viewer | ✅ |
| Image combiner / splitter / thumbnailer, video converter, video thumbnailer | ✅ |
| Ping & DNS, monitor test | ✅ |
| Systeemvak-icoon, meldingen, geluid, autostart | ✅ |

## Hotkeys

Standaard (net als ShareX): `Print` hele scherm, `Ctrl+Print` regio, `Alt+Print` actief venster,
`Shift+Print` opname, `Ctrl+Shift+Print` GIF, `Ctrl+Shift+O` OCR, `Ctrl+Shift+C` kleurkiezer.
Aanpassen onder **Instellingen → Hotkeys & workflows** en op *Apply hotkeys* drukken.

* **Cinnamon:** de sneltoetsen worden als eigen sneltoetsen in Cinnamon gezet (werkt ook als het venster dicht is) en de
  ingebouwde Print Screen-acties worden vrijgemaakt.
* **MATE / Xfce / overig X11:** MintShare grijpt de toetsen zelf (vereist dat het in het systeemvak draait).

Opdrachtregel (stuurt naar de draaiende instantie):

```bash
mintshare region                       # elke actie: mintshare --list-actions
mintshare --workflow "Region + upload"
mintshare --upload foto.png dok.pdf
mintshare --edit foto.png
```

## Beperkingen ten opzichte van ShareX (eerlijk overzicht)

* Alleen **X11** (Cinnamon/MATE/Xfce op Mint). Onder Wayland kan MintShare het scherm niet vastleggen.
* Uploaders die **OAuth-inloggen** vereisen (Google Drive, OneDrive, Box, Flickr, …) zijn niet ingebouwd; gebruik daarvoor
  een `.sxcu` custom uploader of Dropbox/Imgur/GitHub met een token.
* De editor "bakt" annotaties direct in de afbeelding (met ongedaan maken); objecten zijn achteraf niet meer te verplaatsen.
* Vensterlaptures maken een schermfoto van het venstergebied (geen transparante schaduw / verborgen delen).
* Geen webcam-opname, geen ffmpeg-presetbeheer, geen Windows-specifieke tools (DNS-changer, Explorer-integratie, Steam).
* De interface is in het Engels.
* Getest op een virtuele X-server (Xvfb) met Python 3.12 / GTK 3.24; op een echte Cinnamon-desktop zijn de
  sneltoets-registratie via `gsettings` en het XApp-tray-icoon niet in deze omgeving uit te proberen geweest.

## Ontwikkelen

```bash
sudo apt install python3-pytest
python3 -m pytest -q tests
```

Structuur: `mintshare/app.py` (applicatie, acties) · `capture.py`, `selector.py` (scherm/regio) · `recorder.py` ·
`tasks.py` (na-capture/upload pipeline) · `uploaders.py` · `tools/core.py` · `ui/*` (GTK-vensters).
