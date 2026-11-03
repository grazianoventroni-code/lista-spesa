"""Legge le offerte in evidenza di Lidl Italia e le pubblica su Supabase.

Uso personale: una o due letture a settimana, solo pagine pubbliche, nessun accesso riservato.
Variabili d'ambiente:
  SUPABASE_URL, SUPABASE_KEY   indirizzo del progetto e chiave pubblica (publishable)
  OFFERS_SECRET                la frase segreta scelta in supabase-offerte.sql
  DRY_RUN=1                    stampa il risultato senza pubblicare
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

BASE = "https://www.lidl.it"
UA = "Mozilla/5.0 (compatible; ListaSpesaFamiliare/1.0; uso personale)"
MIN_PRODOTTI = 8          # sotto questa soglia la pagina è cambiata: non tocco i dati della settimana scorsa


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def pagine_offerte():
    home = get(BASE + "/")
    links = sorted(set(re.findall(r'href="(/c/[^"]*offert[^"]*)"', home)))
    return [l for l in links if "volantino" not in l]


def periodo(testo, oggi):
    """'solo in punto vendita dal 29.10. al 04.11.' -> (2026-10-29, 2026-11-04)"""
    m = re.search(r"dal\s+(\d{1,2})\.(\d{1,2})\.?\s+al\s+(\d{1,2})\.(\d{1,2})", testo or "")
    if not m:
        return None, None
    g1, m1, g2, m2 = map(int, m.groups())
    try:
        fine = dt.date(oggi.year, m2, g2)
        inizio = dt.date(oggi.year - (1 if m1 > m2 else 0), m1, g1)
        if fine < oggi - dt.timedelta(days=200):      # passaggio d'anno
            fine = dt.date(oggi.year + 1, m2, g2)
            inizio = dt.date(oggi.year, m1, g1)
        return inizio, fine
    except ValueError:
        return None, None


def prodotti(pagina, oggi):
    t = get(BASE + pagina)
    out = []
    for m in re.finditer(r'data-grid-data="([^"]+)"', t):
        try:
            d = json.loads(html.unescape(m.group(1)))
        except ValueError:
            continue
        titolo = (d.get("title") or d.get("fullTitle") or "").strip()
        if not titolo:
            continue
        marca = ((d.get("brand") or {}).get("name") or "").strip()
        nome = titolo if marca.lower() in titolo.lower() else f"{marca} {titolo}".strip()
        nome = re.sub(r"^[-–\s]+", "", nome)
        prezzo = (d.get("price") or {}).get("price")
        vecchio = ((d.get("price") or {}).get("discount") or {}).get("deletedPrice")
        if d.get("category") == "Food" and prezzo and prezzo > 40:   # prezzo al chilo o dato sbagliato
            prezzo = vecchio = None
        badge = ""
        try:
            badge = d["stockAvailability"]["badgeInfo"]["badges"][0]["text"]
        except (KeyError, IndexError, TypeError):
            pass
        da, a = periodo(badge, oggi)
        img = ""
        try:
            img = (d.get("imageList_V1") or d.get("imageList") or [{}])[0].get("image", "") or d.get("image", "")
        except (IndexError, AttributeError):
            pass
        out.append({
            "title": nome, "price": prezzo, "old_price": vecchio,
            "valid_from": da.isoformat() if da else None, "valid_to": a.isoformat() if a else None,
            "url": BASE + (d.get("canonicalUrl") or ""), "image": img if str(img).startswith("https://") else None,
        })
    return out


def main():
    oggi = dt.date.today()
    viste, righe = set(), []
    for p in pagine_offerte():
        for r in prodotti(p, oggi):
            if r["title"] not in viste:
                viste.add(r["title"])
                righe.append(r)
    # tengo solo offerte non ancora scadute
    righe = [r for r in righe if not r["valid_to"] or r["valid_to"] >= oggi.isoformat()]
    print(f"Lidl: {len(righe)} offerte valide")
    for r in righe[:5]:
        print("  ", r["title"], r["price"], r["valid_to"])
    if len(righe) < MIN_PRODOTTI:
        print("Troppo poche offerte: la pagina potrebbe essere cambiata. Non pubblico nulla.", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("DRY_RUN"):
        print("DRY_RUN: non pubblico.")
        return
    req = urllib.request.Request(
        os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/rpc/publish_offers",
        data=json.dumps({"p_secret": os.environ["OFFERS_SECRET"], "p_store": "Lidl", "p_rows": righe}).encode(),
        headers={"Content-Type": "application/json", "apikey": os.environ["SUPABASE_KEY"],
                 "Authorization": "Bearer " + os.environ["SUPABASE_KEY"]},
    )
    print("Pubblicate:", urllib.request.urlopen(req, timeout=30).read().decode())


if __name__ == "__main__":
    main()
