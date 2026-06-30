import json
import math
import re
import sys
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError
from html.parser import HTMLParser


SOURCES = [
    {
        "id": "leonine_vorbestellungen",
        "label": "Leonine – Vorbestellungen",
        "url": "https://shop.leoninestudios.com/collections/jetzt-vorbestellen",
        "base": "https://shop.leoninestudios.com",
        "type": "shopify_api",
        "api": "https://shop.leoninestudios.com/collections/jetzt-vorbestellen/products.json?limit=250",
    },
    {
        "id": "leonine_neuheiten",
        "label": "Leonine – Neuheiten",
        "url": "https://shop.leoninestudios.com/collections/neuheiten/Neuheiten",
        "base": "https://shop.leoninestudios.com",
        "type": "shopify_api",
        "api": "https://shop.leoninestudios.com/collections/neuheiten/products.json?limit=250",
    },
    {
        "id": "capelight_vorschau",
        "label": "Capelight – Vorschau",
        "url": "https://shop.capelight.de/VORSCHAU/",
        "base": "https://shop.capelight.de",
        "type": "capelight",
    },
    {
        "id": "capelight_neuheiten",
        "label": "Capelight – Neuheiten",
        "url": "https://shop.capelight.de/NEUHEITEN/",
        "base": "https://shop.capelight.de",
        "type": "capelight",
    },
    {
        "id": "eykmedia_vorbestellen",
        "label": "EYK Media – Vorbestellen",
        "url": "https://eykmedia.de/collections/vorbestellen",
        "base": "https://eykmedia.de",
        "type": "shopify_api",
        "api": "https://eykmedia.de/collections/vorbestellen/products.json?limit=250",
    },
    {
        "id": "plaion_neuheiten",
        "label": "Plaion Pictures – Neuheiten",
        "url": "https://shop.plaionpictures.com/film-neuheiten/",
        "base": "https://shop.plaionpictures.com",
        "type": "plaion",
    },
    {
        "id": "plaion_vorbesteller",
        "label": "Plaion Pictures – Vorbesteller",
        "url": "https://shop.plaionpictures.com/film-vorbesteller/",
        "base": "https://shop.plaionpictures.com",
        "type": "plaion",
    },
    {
        "id": "plaion_exclusives",
        "label": "Plaion Pictures – Exclusives",
        "url": "https://shop.plaionpictures.com/exclusives/",
        "base": "https://shop.plaionpictures.com",
        "type": "plaion",
    },
    {
        "id": "plaion_sale",
        "label": "Plaion Pictures – Sale",
        "url": "https://shop.plaionpictures.com/sale/",
        "base": "https://shop.plaionpictures.com",
        "type": "plaion",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
}


def fetch(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def extract_date_from_html(html):
    """Find a German date pattern DD.MM.YYYY in HTML."""
    m = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", html)
    return m.group(1) if m else ""


def format_price(raw):
    """Turn '39.99' into '39,99 €'."""
    if not raw:
        return ""
    try:
        return f"{float(raw):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return ""


def scrape_shopify_api(source):
    products = []
    page = 1
    while True:
        url = source["api"] + f"&page={page}"
        data = json.loads(fetch(url))
        batch = data.get("products", [])
        if not batch:
            break
        for p in batch:
            product_url = source["base"] + "/products/" + p["handle"]
            image = p["images"][0]["src"] if p.get("images") else ""

            price = ""
            if p.get("variants"):
                price = format_price(p["variants"][0].get("price", ""))

            # Try to find a release date in the product description
            release_date = extract_date_from_html(p.get("body_html", ""))

            products.append({
                "title": p["title"],
                "url": product_url,
                "image": image,
                "price": price,
                "release_date": release_date,
                "source_id": source["id"],
                "source_label": source["label"],
                "source_url": source["url"],
            })
        if len(batch) < 250:
            break
        page += 1
    return products


def scrape_capelight(source):
    """Regex-based scraper for shop.capelight.de."""
    html = fetch(source["url"])
    products = []

    # Split HTML into per-product blocks using the product-box div as boundary
    blocks = re.split(r'(?=<div[^>]+class="[^"]*product-box[^"]*")', html)

    for block in blocks:
        # Product link with numeric ID at end (absolute URL)
        m_link = re.search(
            r'<a\s[^>]*href="(https://shop\.capelight\.de/[^"]+/\d{6,})"[^>]*>\s*(.*?)\s*</a>',
            block, re.DOTALL
        )
        if not m_link:
            continue
        url = m_link.group(1)
        title = re.sub(r"<[^>]+>", "", m_link.group(2)).strip()
        if not title or len(title) < 3:
            continue

        # Image
        img = ""
        m_img = re.search(r'<img[^>]+src="(https://shop\.capelight\.de/media/[^"?]+)"', block)
        if m_img:
            img = m_img.group(1)

        # Price from <span class="product-price">14,99 €</span>
        price = ""
        m_price = re.search(r'class="product-price"[^>]*>\s*([\d]+,[\d]{2})\s*€', block)
        if m_price:
            price = format_price(m_price.group(1).replace(",", "."))

        # Release date from <b>Erscheinungsdatum:</b> DD.MM.YYYY
        release_date = ""
        m_date = re.search(r"Erscheinungsdatum.*?(\d{2}\.\d{2}\.\d{4})", block, re.DOTALL)
        if m_date:
            release_date = m_date.group(1)

        products.append({
            "title": title,
            "url": url,
            "image": img,
            "price": price,
            "release_date": release_date,
            "source_id": source["id"],
            "source_label": source["label"],
            "source_url": source["url"],
        })

    return products


class PlaionParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.products = []
        self._current_link = None
        self._current_title = None
        self._current_img = None
        self._current_price = ""
        self._in_link = False
        self._last_img = None
        self._in_price = False
        self._price_text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img":
            src = attrs.get("src", "")
            if "/media/" in src:
                self._last_img = src if src.startswith("http") else self.base + src
        elif tag == "a":
            href = attrs.get("href", "")
            if href.startswith(self.base):
                href = href[len(self.base):]
            if href.startswith("/") and "-" in href and href not in ("/", "/#"):
                parts = href.strip("/").split("/")
                if len(parts) == 1 and len(href) > 5:
                    self._current_link = self.base + href
                    self._current_title = ""
                    self._current_img = self._last_img
                    self._current_price = ""
                    self._in_link = True
        elif tag in ("span", "strong", "p") and self._current_link:
            self._in_price = True
            self._price_text = ""

    def handle_endtag(self, tag):
        if tag in ("span", "strong", "p") and self._in_price:
            self._in_price = False
            t = self._price_text.strip()
            if "Preis" in t or "€" in t:
                m = re.search(r"([\d]+[,.][\d]{2})\s*€", t)
                if m and not self._current_price:
                    raw = m.group(1).replace(",", ".")
                    self._current_price = format_price(raw)
        elif tag == "a" and self._in_link:
            self._in_link = False
            title = (self._current_title or "").strip()
            if self._current_link and title and len(title) > 3:
                urls = [p["url"] for p in self.products]
                if self._current_link not in urls:
                    self.products.append({
                        "title": title,
                        "url": self._current_link,
                        "image": self._current_img or "",
                        "price": self._current_price,
                        "release_date": "",
                    })
            self._current_link = None
            self._current_title = None

    def handle_data(self, data):
        if self._in_link and not self._in_price:
            self._current_title = (self._current_title or "") + data
        elif self._in_price:
            self._price_text += data


def get_plaion_total(html):
    m = re.search(r"von\s+(\d+)\s+Produkten\s+angezeigt", html, re.IGNORECASE)
    return int(m.group(1)) if m else None


def scrape_html(source):
    products = []
    if source["type"] == "plaion":
        html = fetch(source["url"])
        parser = PlaionParser(source["base"])
        parser.feed(html)
        products.extend(parser.products)

        total = get_plaion_total(html)
        per_page = 20
        if total and total > per_page:
            num_pages = math.ceil(total / per_page)
            for page in range(2, num_pages + 1):
                paged_url = source["url"].rstrip("/") + f"/?p={page}"
                try:
                    html = fetch(paged_url)
                    p2 = PlaionParser(source["base"])
                    p2.feed(html)
                    products.extend(p2.products)
                except Exception as e:
                    print(f"    Seite {page} Fehler: {e}", file=sys.stderr)
    else:
        return []

    result = []
    for p in products:
        p["source_id"] = source["id"]
        p["source_label"] = source["label"]
        p["source_url"] = source["url"]
        result.append(p)
    return result


def scrape_source(source):
    try:
        if source["type"] == "shopify_api":
            products = scrape_shopify_api(source)
        elif source["type"] == "capelight":
            products = scrape_capelight(source)
        else:
            products = scrape_html(source)
        print(f"  {source['label']}: {len(products)} Produkte", file=sys.stderr)
        return products
    except URLError as e:
        print(f"  FEHLER {source['label']}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  FEHLER {source['label']}: {e}", file=sys.stderr)
        return []


def deduplicate(products):
    seen_urls = set()
    seen_titles = set()
    result = []
    for p in products:
        url = p["url"].rstrip("/").split("?")[0]
        title = p["title"].strip().lower()
        if url not in seen_urls and title not in seen_titles:
            seen_urls.add(url)
            seen_titles.add(title)
            result.append(p)
    return result


def main():
    print("Scraping gestartet...", file=sys.stderr)
    all_products = []
    for source in SOURCES:
        all_products.extend(scrape_source(source))

    before = len(all_products)
    all_products = deduplicate(all_products)
    dupes = before - len(all_products)
    if dupes:
        print(f"  Duplikate entfernt: {dupes}", file=sys.stderr)

    data = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(all_products),
        "products": all_products,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Fertig: {len(all_products)} Produkte gespeichert.", file=sys.stderr)


if __name__ == "__main__":
    main()
