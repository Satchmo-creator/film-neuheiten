import json
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


def scrape_shopify_api(source):
    data = json.loads(fetch(source["api"]))
    products = []
    for p in data.get("products", []):
        url = source["base"] + "/products/" + p["handle"]
        image = ""
        if p.get("images"):
            image = p["images"][0]["src"]
        products.append({
            "title": p["title"],
            "url": url,
            "image": image,
            "source_id": source["id"],
            "source_label": source["label"],
            "source_url": source["url"],
        })
    return products


class CapelightParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.products = []
        self._current_link = None
        self._current_title = None
        self._current_img = None
        self._in_link = False
        self._last_img = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img":
            src = attrs.get("src", "")
            if "media" in src:
                self._last_img = src
        elif tag == "a":
            href = attrs.get("href", "")
            if re.search(r"/\d{6,}$", href):
                self._current_link = self.base + href if href.startswith("/") else href
                self._current_title = ""
                self._current_img = self._last_img
                self._in_link = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            self._in_link = False
            title = (self._current_title or "").strip()
            if self._current_link and title:
                self.products.append({
                    "title": title,
                    "url": self._current_link,
                    "image": self._current_img or "",
                })
            self._current_link = None
            self._current_title = None

    def handle_data(self, data):
        if self._in_link:
            self._current_title = (self._current_title or "") + data


class PlaionParser(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.products = []
        self._current_link = None
        self._current_title = None
        self._current_img = None
        self._in_link = False
        self._last_img = None

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
                    self._in_link = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            self._in_link = False
            title = (self._current_title or "").strip()
            if self._current_link and title and len(title) > 3:
                urls = [p["url"] for p in self.products]
                if self._current_link not in urls:
                    self.products.append({
                        "title": title,
                        "url": self._current_link,
                        "image": self._current_img or "",
                    })
            self._current_link = None
            self._current_title = None

    def handle_data(self, data):
        if self._in_link:
            self._current_title = (self._current_title or "") + data


def scrape_html(source):
    html = fetch(source["url"])
    if source["type"] == "capelight":
        parser = CapelightParser(source["base"])
    elif source["type"] == "plaion":
        parser = PlaionParser(source["base"])
    else:
        return []
    parser.feed(html)
    products = []
    for p in parser.products:
        p["source_id"] = source["id"]
        p["source_label"] = source["label"]
        p["source_url"] = source["url"]
        products.append(p)
    return products


def scrape_source(source):
    try:
        if source["type"] == "shopify_api":
            products = scrape_shopify_api(source)
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
