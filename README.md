# SC Riesa – Heimspiele als Webcal-Kalender

Erzeugt automatisch einen Kalender mit allen **Heimspielen** des Vereins **SC Riesa**
(alle Mannschaften, Quelle: handball.net). Pro Tag genau **ein** Kalendereintrag,
auch wenn mehrere Mannschaften am selben Tag zuhause spielen.

Läuft komplett kostenlos über **GitHub Actions** (holt alle 6 Stunden die aktuellen
Daten) und **GitHub Pages** (stellt die Datei `heimspiele.ics` unter einer festen
Adresse bereit, die Outlook/Google/Apple Kalender abonnieren können).

Es werden keine persönlichen Daten verarbeitet – nur öffentliche Spieltermine.

## Einrichtung (einmalig, ca. 5 Minuten)

1. **Neues Repository anlegen**: auf github.com oben rechts auf **+** → **New repository**.
   Name z. B. `sc-riesa-heimspiele`, Sichtbarkeit **Public** (nötig für kostenloses
   GitHub Pages), sonst Standardeinstellungen. **Create repository** klicken.

2. **Dateien hochladen**: auf der leeren Repo-Seite auf **uploading an existing file**
   klicken (oder **Add file → Upload files**) und den kompletten Inhalt dieses Ordners
   hineinziehen (inklusive des Unterordners `.github/workflows/`). Unten **Commit changes**.

3. **GitHub Pages aktivieren**: **Settings → Pages** → unter „Build and deployment“
   bei **Source** **„GitHub Actions“** auswählen (nicht „Deploy from a branch“).

4. **Workflow einmal manuell starten**: Tab **Actions** → links **„Heimspiele
   aktualisieren“** → rechts **„Run workflow“** → **Run workflow**. Nach ca. einer
   Minute ist der Lauf grün.

5. **Kalender-Adresse holen**: **Settings → Pages** zeigt oben die Adresse, z. B.
   `https://DEINNAME.github.io/sc-riesa-heimspiele/`. Die Kalenderdatei liegt unter
   `https://DEINNAME.github.io/sc-riesa-heimspiele/heimspiele.ics`.

## In Outlook abonnieren

Damit Outlook den Kalender selbst aktuell hält (statt einmalig zu importieren):

- **Outlook.com / neues Outlook**: Kalender → **Kalender hinzufügen** →
  **Aus dem Internet abonnieren** → obige Adresse einfügen (mit `webcal://` statt
  `https://` funktioniert genauso) → Namen vergeben, z. B. „SC Riesa Heimspiele“.
- **Klassisches Outlook (Windows/Mac)**: Kalender-Ansicht → **Kalender öffnen** →
  **Aus dem Internet …** → Adresse einfügen.

Outlook fragt den Feed danach selbstständig in regelmäßigen Abständen ab (je nach
Outlook-Version alle paar Stunden bis täglich) – neue oder verlegte Spiele
erscheinen dann automatisch.

## Anpassen

- Zeitfenster, Vereins-ID etc.: oben in `build_heimspiele.py` unter „Konfiguration“.
- Rhythmus der Aktualisierung: `cron`-Zeile in `.github/workflows/update.yml`
  (aktuell alle 6 Stunden).
- Datenquelle: die öffentliche, nicht dokumentierte JSON-API von handball.net
  (`/api/new/matches`), mit der auch die Website selbst arbeitet.
