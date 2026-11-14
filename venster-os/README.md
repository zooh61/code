# Venster OS – een licht, Windows-achtig systeem voor de Raspberry Pi 4

Venster OS is een besturingssysteem voor de Raspberry Pi 4 (vanaf 2 GB).
Het is gebouwd op **Debian 13 (trixie)**, niet op Raspberry Pi OS.

| Wat | Hoe |
|---|---|
| Uiterlijk | Taakbalk onderaan, Start-knop linksonder, klok en systeemvak rechts, vensters met knoppen ─ ☐ ✕ rechtsboven |
| Aanmelden | Automatisch, zonder wachtwoord |
| Browser | Firefox (Nederlandstalig) |
| Windows-programma's | Dubbelklik op een `.exe` of `.msi` – draait via **Hangover** (Wine voor ARM) met **Box64** |
| Geheugen | Gecomprimeerd wisselgeheugen (zram), zodat 2 GB verder reikt |
| SD-kaart | Bij de eerste start wordt de hele SD-kaart in gebruik genomen |

## Installeren

1. Download het nieuwste `venster-os-….img.xz` bij **Releases** van deze repository
   (gemaakt door de GitHub Action *Venster OS image*).
2. Open **Raspberry Pi Imager**.
3. *Apparaat*: Raspberry Pi 4. *Besturingssysteem*: helemaal onderaan **Eigen image gebruiken** → kies het `.img.xz`-bestand.
4. Kies de SD-kaart (minimaal 8 GB, 16 GB of meer aanbevolen) en klik op **Volgende**.
5. Vraagt Imager of u instellingen wilt aanpassen? Kies **Nee** (die instellingen zijn voor Raspberry Pi OS).
6. Zet de SD-kaart in de Pi en zet hem aan. De eerste start duurt iets langer.

**Gebruiker:** `gebruiker` · **wachtwoord:** `venster` (nodig voor beheertaken, zoals software installeren).
Wijzig het wachtwoord via Start → Terminal → `passwd`.

## Gebruik

### Sneltoetsen

| Toets | Actie |
|---|---|
| Windows-toets | Startmenu |
| Windows + E | Verkenner (bestanden) |
| Windows + R | Uitvoeren |
| Windows + D | Bureaublad tonen |
| Windows + ← / → | Venster links/rechts vastzetten |
| Windows + ↑ / ↓ | Maximaliseren / minimaliseren |
| Alt + F4 | Venster sluiten |
| Alt + Tab | Wisselen tussen vensters |
| Ctrl + Shift + Esc of Ctrl + Alt + Del | Taakbeheer |
| Print Screen | Schermafbeelding |

### Wi-Fi en geluid

Klik rechtsonder in de taakbalk op het netwerkicoon voor Wi-Fi, en op het luidsprekericoon voor het volume.

### Windows-programma's installeren

1. Download het installatiebestand (`.exe` of `.msi`) met Firefox.
2. Open de map *Downloads* (Windows + E) en **dubbelklik** op het bestand.
   Of kies Start → **Windows-programma installeren**.
3. Doorloop de installatie zoals op Windows. Het programma verschijnt daarna in het Startmenu.

Andere handige onderdelen in het Startmenu:

- **Windows-programma's verwijderen**
- **Windows-instellingen (Wine)** – bijvoorbeeld de Windows-versie of schermresolutie van programma's

Goed om te weten:

- Windows-programma's worden **geëmuleerd**. Dat kost rekenkracht, dus reken op een lagere snelheid dan op een pc.
  Eenvoudige programma's (kantoor, oude spellen, hulpprogramma's) werken meestal goed;
  zware spellen, programma's met kopieerbeveiliging en stuurprogramma's werken niet.
- 32-bit programma's werken het best. 64-bit programma's zijn op de Pi 4 experimenteel.
- Voor 32-bit programma's wordt Box64 gebruikt (`HODLL=wowbox64.dll` in `/etc/environment`).
  Werkt een programma niet? Probeer de andere emulator (FEX): verwijder die regel en meld u opnieuw aan.
- Zat Hangover niet in de image (de download lukte niet tijdens het bouwen), dan wordt het
  automatisch gedownload en geïnstalleerd zodra u voor het eerst een Windows-programma opent (internet nodig).

## Zelf bouwen

Op een Debian- of Ubuntu-computer (arm64 is het snelst; op x86 wordt ARM geëmuleerd):

```bash
sudo apt install mmdebstrap debian-archive-keyring qemu-user-static binfmt-support \
                 parted dosfstools e2fsprogs xz-utils python3 curl rsync
sudo ./venster-os/build.sh
# Resultaat: venster-os/out/venster-os-<datum>.img.xz
```

Of start op GitHub de Action **Venster OS image** (tabblad *Actions* → *Run workflow*).
Die bouwt de image op een arm64-machine en zet hem bij *Releases*.

### Wat zit waar

| Pad | Inhoud |
|---|---|
| `build.sh` | Bouwt het bestandssysteem met `mmdebstrap` en maakt de SD-kaart-image |
| `packages.txt` | De Debian-pakketten die worden geïnstalleerd |
| `overlay/` | Bestanden die over het systeem heen worden gekopieerd (instellingen, scripts) |
| `overlay/etc/skel/.config/xfce4/` | Taakbalk, startmenu, thema en bureaublad van de gebruiker |
| `overlay/usr/local/lib/venster/` | Scripts voor het bouwen, de eerste start en Windows-ondersteuning |
| `tools/make-xfwm4-theme.py` | Tekent het Windows-achtige vensterthema *Venster* |
| `tools/patch-xfce-defaults.py` | Voegt de Windows-sneltoetsen toe |
| `tools/fetch-hangover.sh` | Downloadt Hangover (Wine voor ARM) |

### Aanpassen

- **Taal en toetsenbord**: standaard Nederlands, tijdzone Amsterdam, toetsenbord *US International (AltGr)*.
  Pas dit aan in `overlay/usr/local/lib/venster/setup-in-chroot.sh`, of later via
  Start → Instellingen → Toetsenbord.
- **Gebruikersnaam en wachtwoord**: bovenaan `setup-in-chroot.sh` en in
  `overlay/etc/lightdm/lightdm.conf.d/50-venster.conf`.
- **Extra programma's**: voeg Debian-pakketnamen toe aan `packages.txt`.
