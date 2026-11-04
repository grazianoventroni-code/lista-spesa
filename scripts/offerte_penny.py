"""Legge le offerte a volantino di Penny e le pubblica su Supabase.

Uso personale: una o due letture a settimana, solo pagine pubbliche, nessun accesso riservato.
Variabili d'ambiente: SUPABASE_URL, SUPABASE_KEY, OFFERS_SECRET (come per Lidl). DRY_RUN=1 = non pubblica.
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

BASE = "https://www.penny.it"
UA = "Mozilla/5.0 (compatible; ListaSpesaFamiliare/1.0; uso personale)"
MIN_PRODOTTI = 8          # sotto questa soglia la pagina è cambiata: non tocco i dati della settimana scorsa


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def testo(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or "")).replace("\xa0", " ")).strip()


def euro(s):
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})", s or "")
    return float(m.group(1).replace(".", "") + "." + m.group(2)) if m else None


def data(s):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s or "")
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat() if m else None
    except ValueError:
        return None


def prodotti(pagina):
    righe = []
    for blocco in pagina.split('data-test="product-tile"')[1:]:
        blocco = re.split(r'data-test="product-tile"', blocco)[0]
        m = re.search(r'data-test="product-title"[^>]*>(.*?)</h3>', blocco, re.S)
        titolo = testo(m.group(1)) if m else ""
        if not titolo:
            continue
        peso = testo((re.search(r'product-information-piece-description"[^>]*>(.*?)</ul>', blocco, re.S) or [None, ""])[1])
        valido = re.search(r'product-price-validity"[^>]*>(.*?)</div></div>', blocco, re.S)
        date = re.findall(r"\d{1,2}\.\d{1,2}\.\d{4}", testo(valido.group(1)) if valido else "")
        prezzi = [euro(testo(x)) for x in re.findall(r'class="ws-product-price-value__main"[^>]*>(.*?)</span>', blocco, re.S)]
        prezzi = [p for p in prezzi if p]
        slug = re.search(r'href="(/prodotto/[^"]+)"', blocco)
        righe.append({
            "title": (titolo + (" " + peso if peso else ""))[:190],
            "price": min(prezzi) if prezzi else None,
            "old_price": max(prezzi) if len(set(prezzi)) > 1 else None,   # con la PENNYCard (gratuita) / senza
            "valid_from": data(date[0]) if date else None,
            "valid_to": data(date[1]) if len(date) > 1 else None,
            "url": BASE + slug.group(1) if slug else None,
            "image": None,
        })
    return righe


def main():
    oggi = dt.date.today().isoformat()
    viste, righe = set(), []
    for r in prodotti(get(BASE + "/offerte")):
        if r["title"] not in viste and (not r["valid_to"] or r["valid_to"] >= oggi):
            viste.add(r["title"])
            righe.append(r)
    print(f"Penny: {len(righe)} offerte valide")
    for r in righe[:5]:
        print("  ", r["title"], r["price"], r["old_price"], r["valid_from"], r["valid_to"])
    if len(righe) < MIN_PRODOTTI:
        print("Troppo poche offerte: la pagina potrebbe essere cambiata. Non pubblico nulla.", file=sys.stderr)
        sys.exit(1)
    if os.environ.get("DRY_RUN"):
        print("DRY_RUN: non pubblico.")
        return
    req = urllib.request.Request(
        os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/rpc/publish_offers",
        data=json.dumps({"p_secret": os.environ["OFFERS_SECRET"], "p_store": "Penny", "p_rows": righe}).encode(),
        headers={"Content-Type": "application/json", "apikey": os.environ["SUPABASE_KEY"],
                 "Authorization": "Bearer " + os.environ["SUPABASE_KEY"]},
    )
    print("Pubblicate:", urllib.request.urlopen(req, timeout=30).read().decode())


if __name__ == "__main__":
    main()
