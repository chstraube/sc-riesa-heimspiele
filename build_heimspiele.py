#!/usr/bin/env python3
"""Baut einen ICS-Kalender mit den Heimspieltagen des SC Riesa (alle Mannschaften).

Holt alle Spiele des Vereins über die öffentliche handball.net-API, filtert auf
Heimspiele und fasst alle Heimspiele eines Kalendertags zu EINEM Termin zusammen
(wie gewünscht: ein Eintrag pro Tag, nicht pro Spiel).

Aufruf:  python build_heimspiele.py
Schreibt: docs/heimspiele.ics, docs/index.html
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar, Event as VEvent, Timezone

# --------------------------------------------------------------------------- Konfiguration

CLUB_ID = 470174  # SC Riesa e.V. (Handballverband Sachsen) auf handball.net
TIMEZONE = "Europe/Berlin"
CALENDAR_NAME = "SC Riesa – Heimspiele"
MATCH_DURATION_MIN = 120  # Annahme je Spiel, falls Ende unbekannt

BASE = "https://www.handball.net/api/new"
SITE = "https://www.handball.net/"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
    "sc-riesa-heimspiele-kalender/1.0 (privates Kalender-Abo)"
)

DOCS = Path("docs")
OUT_ICS = DOCS / "heimspiele.ics"
OUT_HTML = DOCS / "index.html"

# Statuswerte (kleingeschrieben), bei denen ein Spiel als verlegt/abgesagt markiert wird
ABGESAGT_STATUS = {
    "suspendido", "anulado", "aplazado",
    "abgesagt", "verlegt", "ausgefallen", "annulliert",
    "cancelled", "canceled", "postponed",
}

_DATE_RE =re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})")


# --------------------------------------------------------------------------- API-Client

class Api:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "de-DE,de;q=0.9",
                "Referer": SITE,
            }
        )

    def get(self, path: str, params: dict) -> dict:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        resp = self.session.get(f"{BASE}/{path.lstrip('/')}", params=clean, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("success") is False:
            fehler = payload.get("error", {})
            raise RuntimeError(f"{fehler.get('code')}: {fehler.get('message')}")
        return payload

    def get_all(self, path: str, params: dict) -> list[dict]:
        seiten = dict(params)
        seiten["per_page"] = 100
        items: list[dict] = []
        page = 1
        while True:
            seiten["page"] = page
            payload = self.get(path, seiten)
            items.extend(payload.get("data") or [])
            pag = payload.get("pagination") or {}
            last = pag.get("last_page")
            if not last or page >= last:
                break
            page += 1
        return items


def club_ids(api: Api, club_id: int) -> set[str]:
    """Beide Schreibweisen der Vereins-ID sammeln (Zahl und neue Zeichenkette)."""
    ids = {str(club_id)}
    try:
        verein = api.get(f"teams/clubs/{club_id}", {})
        daten = verein.get("data") or verein
        if daten.get("id") is not None:
            ids.add(str(daten["id"]))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Vereins-Detailabfrage fehlgeschlagen: {exc}", file=sys.stderr)
    return ids


# --------------------------------------------------------------------------- Parsing

def parse_local_datetime(raw: str | None) -> datetime | None:
    """Naiv parsen: der Zeitzonen-Offset der API ist Ortszeit, kein echter Offset."""
    if not raw:
        return None
    m = _DATE_RE.match(str(raw).strip())
    if not m:
        return None
    jahr, monat, tag, stunde, minute = (int(g) for g in m.groups())
    return datetime(jahr, monat, tag, stunde, minute)


def team_name(seite: dict | None) -> str:
    if not seite:
        return "unbekannt"
    return (seite.get("name") or "").strip() or f"Team {seite.get('id')}"


def venue(spiel: dict) -> str:
    feld = spiel.get("field") or {}
    anlage = feld.get("installation") or {}
    name = (feld.get("name") or anlage.get("name") or "").strip()
    return name


class Heimspiel:
    def __init__(self, spiel: dict) -> None:
        self.id = spiel.get("id")
        self.start = parse_local_datetime(spiel.get("date"))
        self.all_day = bool(self.start and self.start.hour == 0 and self.start.minute == 0)
        heim, gast = spiel.get("local") or {}, spiel.get("visitor") or {}
        self.heim = team_name(heim)
        self.gast = team_name(gast)
        phase = spiel.get("phase") or {}
        self.liga = (phase.get("name") or "").strip()
        self.venue = venue(spiel)
        status = spiel.get("status") or ""
        if isinstance(status, dict):
            status = status.get("name") or ""
        self.status = str(status).strip()
        self.abgesagt = self.status.lower() in ABGESAGT_STATUS

    @property
    def zeile(self) -> str:
        zeit = "Zeit tbd." if self.all_day else self.start.strftime("%H:%M Uhr")
        ort = f" ({self.venue})" if self.venue else ""
        zusatz = " [VERLEGT/ABGESAGT]" if self.abgesagt else ""
        return f"{zeit} – {self.heim} vs. {self.gast}{ort}{zusatz}"


def hole_heimspiele(api: Api, *, date_from: str, date_to: str) -> list[Heimspiel]:
    ids = club_ids(api, CLUB_ID)
    rohe = api.get_all("matches", {"club_id": CLUB_ID, "date_from": date_from, "date_to": date_to})
    heimspiele = []
    for spiel in rohe:
        heim = spiel.get("local") or {}
        if str((heim.get("club") or {}).get("id")) not in ids:
            continue  # Auswärtsspiel unserer Mannschaft
        hs = Heimspiel(spiel)
        if hs.start is not None:
            heimspiele.append(hs)
    return heimspiele


# --------------------------------------------------------------------------- ICS bauen

def _vtimezone_europe_berlin() -> Timezone:
    """Handgeschriebene VTIMEZONE (RRULE statt RDATE-Liste).

    Ein Client, der per TZID auf eine Zeitzone verweist, muss sie laut RFC 5545 auch
    selbst definieren – sonst lehnen strengere Clients (u. a. manche Outlook-Versionen)
    den Feed ab. Diese Form (mit RRULE für die EU-Sommerzeitregel) ist die, die auch
    handball.net selbst in seinen eigenen Kalender-Exporten verwendet.
    """
    return Timezone.from_ical(
        "BEGIN:VTIMEZONE\r\n"
        "TZID:Europe/Berlin\r\n"
        "X-LIC-LOCATION:Europe/Berlin\r\n"
        "BEGIN:DAYLIGHT\r\n"
        "TZOFFSETFROM:+0100\r\n"
        "TZOFFSETTO:+0200\r\n"
        "TZNAME:CEST\r\n"
        "DTSTART:19700329T020000\r\n"
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\n"
        "END:DAYLIGHT\r\n"
        "BEGIN:STANDARD\r\n"
        "TZOFFSETFROM:+0200\r\n"
        "TZOFFSETTO:+0100\r\n"
        "TZNAME:CET\r\n"
        "DTSTART:19701025T030000\r\n"
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\n"
        "END:STANDARD\r\n"
        "END:VTIMEZONE\r\n"
    )


def build_calendar(tage: dict[date, list[Heimspiel]]) -> Calendar:
    tz = ZoneInfo(TIMEZONE)
    stempel = datetime.now(dt_timezone.utc)
    cal = Calendar()
    cal.add("prodid", "-//sc-riesa-heimspiele//Heimspieltage//DE")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", CALENDAR_NAME)
    cal.add("x-wr-timezone", TIMEZONE)
    if TIMEZONE == "Europe/Berlin":
        cal.add_component(_vtimezone_europe_berlin())

    for tag, spiele in sorted(tage.items()):
        spiele = sorted(spiele, key=lambda s: (s.all_day, s.start))
        zeitspiele = [s for s in spiele if not s.all_day]

        ve = VEvent()
        ve.add("uid", f"heimspieltag-{tag.isoformat()}@sc-riesa")

        if len(spiele) == 1:
            s = spiele[0]
            ve.add("summary", f"Heimspiel SC Riesa: {s.heim} – {s.gast}")
        else:
            ve.add("summary", f"Heimspieltag SC Riesa ({len(spiele)} Spiele)")

        if zeitspiele:
            start = zeitspiele[0].start.replace(tzinfo=tz)
            ende = max(s.start for s in zeitspiele) + timedelta(minutes=MATCH_DURATION_MIN)
            ende = ende.replace(tzinfo=tz)
            ve.add("dtstart", start)
            ve.add("dtend", ende)
        else:
            ve.add("dtstart", tag)
            ve.add("dtend", tag + timedelta(days=1))

        orte = ", ".join(dict.fromkeys(s.venue for s in spiele if s.venue))
        if orte:
            ve.add("location", orte)

        beschreibung = "\n".join(s.zeile for s in spiele)
        ve.add("description", beschreibung)
        ve.add("status", "CONFIRMED")
        ve.add("dtstamp", stempel)
        ve.add("last-modified", stempel)
        cal.add_component(ve)

    return cal


def render_index(tage: dict[date, list[Heimspiel]], gebaut_am: datetime) -> str:
    anzahl = sum(len(v) for v in tage.values())
    naechste = sorted(t for t in tage if t >= date.today())[:5]
    zeilen = "\n".join(
        f"<li><strong>{t.strftime('%d.%m.%Y')}</strong>: "
        + "; ".join(s.zeile for s in tage[t])
        + "</li>"
        for t in naechste
    ) or "<li>Keine bevorstehenden Heimspiele im Fenster.</li>"
    return f"""<!doctype html>
<html lang="de"><meta charset="utf-8">
<title>SC Riesa – Heimspiele</title>
<body style="font-family: sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem;">
<h1>SC Riesa – Heimspieltage</h1>
<p>Automatisch aus handball.net erzeugter Kalender mit allen Heimspielen des Vereins.
Ein Kalender-Eintrag fasst alle Heimspiele eines Tages zusammen.</p>
<p><a href="heimspiele.ics">heimspiele.ics</a> laden, oder als Abo (webcal) hinzufügen –
siehe README im Repository für die genaue Adresse.</p>
<p>{anzahl} Heimspiele im aktuellen Fenster. Zuletzt aktualisiert:
{gebaut_am.astimezone(ZoneInfo(TIMEZONE)).strftime('%d.%m.%Y %H:%M')} Uhr.</p>
<h2>Nächste Heimspieltage</h2>
<ul>{zeilen}</ul>
</body></html>"""


def main() -> int:
    heute = date.today()
    date_from = (heute - timedelta(days=7)).isoformat()
    date_to = (heute + timedelta(days=300)).isoformat()

    api = Api()
    heimspiele = hole_heimspiele(api, date_from=date_from, date_to=date_to)
    print(f"→ {len(heimspiele)} Heimspiele im Fenster {date_from} … {date_to}")

    tage: dict[date, list[Heimspiel]] = defaultdict(list)
    for hs in heimspiele:
        tage[hs.start.date()].append(hs)

    if not tage:
        print("Keine Heimspiele gefunden – nichts geschrieben.", file=sys.stderr)
        return 1

    DOCS.mkdir(exist_ok=True)
    cal = build_calendar(tage)
    OUT_ICS.write_bytes(cal.to_ical())
    print(f"✓ {OUT_ICS} ({len(tage)} Heimspieltage)")

    gebaut_am = datetime.now(dt_timezone.utc)
    OUT_HTML.write_text(render_index(tage, gebaut_am), encoding="utf-8")
    print(f"✓ {OUT_HTML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
