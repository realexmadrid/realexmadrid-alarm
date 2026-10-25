"""realexmadrid News-Alarm: prüft spanische News-Feeds und schickt neue Treffer per Telegram."""
import json
import os
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# ================= EINSTELLUNGEN =================
# Zeitungen: es kommen nur Schlagzeilen mit Stichwort (siehe KEYWORDS).
SEARCHES = [
    'site:marca.com "Real Madrid"',
    'site:as.com "Real Madrid"',
    'site:cadenaser.com "Real Madrid"',
    'site:cope.es "Real Madrid"',
    'site:relevo.com "Real Madrid"',
    'site:realmadrid.com',
]

# Reporter: ALLES mit ihrem Namen wird geschickt, ohne Stichwort-Filter.
# Findet ihre Artikel UND Berichte anderer Medien, die sie zitieren.
# Format: "Anzeigename": "Suchbegriff"
REPORTERS = {
    "Mario Cortegana": '"Mario Cortegana" Real Madrid',
    "José Félix Díaz": '"José Félix Díaz" Real Madrid',
    "Arancha Rodríguez": '"Arancha Rodríguez" Real Madrid',
    "José Luis Sánchez": '"José Luis Sánchez" Real Madrid',
    "El Chiringuito": '"El Chiringuito" Real Madrid',
}

# Nur Schlagzeilen mit einem dieser Wörter werden geschickt
# (Groß-/Kleinschreibung und Akzente egal). Liste leer = alles schicken.
KEYWORDS = [
    "oficial", "exclusiva", "ultima hora", "fichaje", "fichar",
    "renovacion", "renueva", "lesion", "lesionado", "baja",
    "acuerdo", "traspaso", "clausula", "sancion", "destitucion",
]

MAX_AGE_HOURS = 6    # ältere Artikel ignorieren
MAX_PER_RUN = 10     # Schutz vor Nachrichten-Flut
SEEN_FILE = "seen.json"
# =================================================

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]


def normalize(text):
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


KEYWORDS_NORM = [normalize(k) for k in KEYWORDS]


def feed_url(query):
    params = {"q": query + " when:1d", "hl": "es", "gl": "ES", "ceid": "ES:es"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def parse(xml_bytes):
    items = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        source = (it.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        try:
            date = parsedate_to_datetime(it.findtext("pubDate") or "")
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
        except Exception:
            date = None
        items.append({
            "id": (it.findtext("guid") or link).strip(),
            "title": title, "link": link, "source": source, "date": date,
        })
    return items


def relevant(item):
    if not KEYWORDS_NORM:
        return True
    title = normalize(item["title"])
    return any(k in title for k in KEYWORDS_NORM)


def send(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    urllib.request.urlopen(url, data=data, timeout=20)


def main():
    first_run = not os.path.exists(SEEN_FILE)
    seen = [] if first_run else json.load(open(SEEN_FILE))
    seen_set = set(seen)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    new = []

    jobs = [(q, name) for name, q in REPORTERS.items()] + [(q, None) for q in SEARCHES]
    for query, reporter in jobs:
        try:
            items = parse(fetch(feed_url(query)))
        except Exception as e:
            print("Fehler bei", query, "->", e)
            continue
        for it in items:
            if it["id"] in seen_set:
                continue
            seen_set.add(it["id"])
            seen.append(it["id"])
            if it["date"] and it["date"] < cutoff:
                continue
            if reporter or relevant(it):
                it["reporter"] = reporter
                new.append(it)

    if first_run:
        send("✅ realexmadrid News-Alarm läuft! Ab jetzt kommen neue Meldungen hierher. ¡Hala Madrid!")
    else:
        new.sort(key=lambda i: i["date"] or cutoff)
        for it in new[:MAX_PER_RUN]:
            head = f"⭐ {it['reporter']}\n" if it.get("reporter") else "🚨 "
            send(f"{head}{it['title']}\n📰 {it['source']}\n{it['link']}")
        if len(new) > MAX_PER_RUN:
            send(f"➕ {len(new) - MAX_PER_RUN} weitere Meldungen – heute ist was los!")

    json.dump(seen[-3000:], open(SEEN_FILE, "w"))
    print(f"Fertig: {len(new)} neue Treffer")


if __name__ == "__main__":
    main()
