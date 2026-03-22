# gw_novinky_core.py
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup


GW_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

FX_RATES = {
    "€": 24.50,
    "$": 21.00,
    "£": 28.00,
}

CREATE_COLUMNS = [
    "code",
    "pairCode",
    "name",
    "price",
    "description",
    "image", "image2", "image3", "image4", "image5",
    "image6", "image7", "image8", "image9", "image10",
    "image11", "image12", "image13", "image14", "image15",
    "image16", "image17", "image18", "image19", "image20",
]

SOURCE_COLUMNS = [
    "code",
    "pairCode",
    "name",
    "ean",
    "externalCode",
    "price",
    "priceWithoutVat",
    "standardPrice",
    "categoryText",
    "warranty",
    "supplier",
    "googleCategoryIdInFeed",
    "heurekaCategoryId",
    "zboziCategoryId",
    "googleCategoryId",
    "stock",
    "percentVat",
    "ossTaxRate:CZ",
    "availabilityInStock",
    "availabilityOutOfStock",
    "productVisibility",
    "xmlFeedName",
    "seoTitle",
    "system",
    "faction",
    "productType",
    "hp_url",
    "gw_url",
    "image", "image2", "image3", "image4", "image5",
    "image6", "image7", "image8", "image9", "image10",
    "image11", "image12", "image13", "image14", "image15",
    "image16", "image17", "image18", "image19", "image20",
]


FACTION_ALIASES = {
    "Astra Militarum": [
        "astra militarum",
        "imperial guard",
        "cadian",
        "catachan",
        "death korps",
    ],
    "Aeldari": ["aeldari", "eldar"],
    "Drukhari": ["drukhari", "dark eldar"],
    "Adepta Sororitas": ["adepta sororitas", "sisters of battle"],
    "Adeptus Mechanicus": ["adeptus mechanicus", "mechanicus"],
    "Adeptus Custodes": ["adeptus custodes", "custodes"],
    "Imperial Knights": ["imperial knights", "questor imperialis"],
    "Imperial Agents": ["imperial agents"],
    "Space Marines": ["space marines", "adeptus astartes"],
    "Black Templars": ["black templars"],
    "Blood Angels": ["blood angels"],
    "Dark Angels": ["dark angels"],
    "Deathwatch": ["deathwatch"],
    "Grey Knights": ["grey knights"],
    "Imperial Fists": ["imperial fists"],
    "Iron Hands": ["iron hands"],
    "Raven Guard": ["raven guard"],
    "Salamanders": ["salamanders"],
    "Space Wolves": ["space wolves"],
    "Ultramarines": ["ultramarines"],
    "White Scars": ["white scars"],
    "Death Guard": ["death guard"],
    "Thousand Sons": ["thousand sons"],
    "World Eaters": ["world eaters"],
    "Chaos Space Marines": ["chaos space marines"],
    "Chaos Daemons": ["chaos daemons", "daemons of chaos"],
    "Chaos Knights": ["chaos knights"],
    "Emperor's Children": ["emperor's children", "emperors children"],
    "Aeldari": ["aeldari", "eldar"],
    "Orks": ["orks", "ork"],
    "Tyranids": ["tyranids", "tyranid"],
    "Genestealer Cults": ["genestealer cults"],
    "T'au Empire": ["tau empire", "t'au empire"],
    "Necrons": ["necrons", "necron"],
    "Leagues of Votann": ["leagues of votann", "votann"],
    "Stormcast Eternals": ["stormcast eternals"],
    "Fyreslayers": ["fyreslayers"],
    "Kharadron Overlords": ["kharadron overlords"],
    "Sylvaneth": ["sylvaneth"],
    "Lumineth Realm-lords": ["lumineth realm-lords", "lumineth realm lords"],
    "Cities of Sigmar": ["cities of sigmar"],
    "Daughters of Khaine": ["daughters of khaine"],
    "Idoneth Deepkin": ["idoneth deepkin"],
    "Seraphon": ["seraphon"],
    "Slaves to Darkness": ["slaves to darkness"],
    "Blades of Khorne": ["blades of khorne"],
    "Disciples of Tzeentch": ["disciples of tzeentch"],
    "Maggotkin of Nurgle": ["maggotkin of nurgle"],
    "Hedonites of Slaanesh": ["hedonites of slaanesh"],
    "Skaven": ["skaven"],
    "Soulblight Gravelords": ["soulblight gravelords"],
    "Ossiarch Bonereapers": ["ossiarch bonereapers"],
    "Nighthaunt": ["nighthaunt"],
    "Flesh-eater Courts": ["flesh-eater courts", "flesh eater courts"],
    "Orruk Warclans": ["orruk warclans"],
    "Ogor Mawtribes": ["ogor mawtribes", "ogres"],
    "Gloomspite Gitz": ["gloomspite gitz", "grot", "grots"],
    "Sons of Behemat": ["sons of behemat"],
}

KNOWN_SYSTEMS = [
    "Warhammer 40,000",
    "Warhammer 40k",
    "Warhammer Age of Sigmar",
    "The Horus Heresy",
    "Warhammer: The Old World",
    "Kill Team",
    "Necromunda",
    "Warcry",
    "Underworlds",
    "Middle-earth",
    "Blood Bowl",
]


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def clean_title(title: str) -> str:
    return norm_ws(title)


def normalize_system_name(system: str) -> str:
    system = norm_ws(system)
    if system == "Warhammer 40,000":
        return "Warhammer 40k"
    return system


def make_xml_feed_name_from_name(name: str) -> str:
    value = clean_title(norm_ws(name))
    return value if value else "Produkt"


def make_seo_title_from_name(name: str) -> str:
    value = make_xml_feed_name_from_name(name)
    return f"{value} | PlasticWargaming" if value else ""


def to_float_price(txt: str) -> Optional[float]:
    if not txt:
        return None
    t = txt.replace("\xa0", " ")
    t = re.sub(r"[^\d,\. ]", "", t)
    t = t.replace(" ", "")
    if t.count(",") == 1 and t.count(".") == 0:
        t = t.replace(",", ".")
    try:
        return float(t)
    except Exception:
        return None


def price_without_vat(price_with_vat: float, vat_percent: float) -> float:
    return round(price_with_vat / (1.0 + vat_percent / 100.0), 2)


def strip_query_and_fragment(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def fetch_html(url: str, timeout: int = 30) -> Tuple[str, str]:
    r = requests.get(url, headers=GW_HEADERS, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return (r.text or ""), str(r.url)


def fetch_gw_html(url: str, timeout: int = 30) -> Tuple[str, str]:
    candidates = [url]
    stripped = strip_query_and_fragment(url)
    if stripped != url:
        candidates.append(stripped)

    last_err = None
    for candidate in candidates:
        try:
            html, final_url = fetch_html(candidate, timeout=timeout)
            if html:
                return html, final_url
        except Exception as e:
            last_err = e

    if last_err:
        raise last_err
    return "", url


def abs_url(base: str, u: str) -> str:
    return requests.compat.urljoin(base, u)


def pick_best_srcset(srcset: str) -> Optional[str]:
    if not srcset:
        return None
    parts = []
    for p in srcset.split(","):
        p = p.strip()
        if not p:
            continue
        parts.append(p.split(" ")[0].strip())
    return parts[-1] if parts else None


def strip_query(url: str) -> str:
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return url


def filename_key(u: str) -> str:
    u2 = strip_query(u)
    return Path(urlparse(u2).path).name.lower()


def uniq_keep_order(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def dedupe_by_filename(urls: List[str]) -> List[str]:
    seen = set()
    out = []
    for u in urls:
        key = filename_key(u)
        if key and key not in seen:
            out.append(u)
            seen.add(key)
    return out


def is_missing_image(u: str) -> bool:
    return "Missing_Image_Servo_Skull" in u or "missing_image" in u.lower()


def filter_gw_product_images(urls: List[str], keep_360: bool) -> List[str]:
    out = []
    for u in urls:
        if not u or is_missing_image(u):
            continue

        low = u.lower()
        if not keep_360 and "threesixty" in low:
            continue

        allowed = (
            "/app/resources/catalog/product/" in low
            or "/catalog/product/" in low
            or "/media/catalog/product/" in low
            or "/resources/catalog/product/" in low
        )
        if allowed:
            out.append(u)

    return out


def keep_real_product_images(images: List[str]) -> List[str]:
    out = []
    bad_markers = [
        "aeronautica_imperialis",
        "landscape",
        "hero",
        "header",
        "banner",
        "carousel",
        "category",
    ]

    for u in images:
        low = u.lower()
        if any(marker in low for marker in bad_markers):
            continue
        if (
            "/catalog/product/" in low
            or "/app/resources/catalog/product/" in low
            or "/media/catalog/product/" in low
            or "/resources/catalog/product/" in low
        ):
            out.append(u)

    return out if out else images


def extract_imgs_from_node(node: BeautifulSoup, base_url: str) -> List[str]:
    urls = []
    for img in node.select("img"):
        src = (img.get("src") or "").strip()
        if src:
            urls.append(abs_url(base_url, src))
        best = pick_best_srcset((img.get("srcset") or "").strip())
        if best:
            urls.append(abs_url(base_url, best))

    for s in node.select("source"):
        best = pick_best_srcset((s.get("srcset") or "").strip())
        if best:
            urls.append(abs_url(base_url, best))
    return urls


def scrape_gw_images(gw_url: str, html: str, max_images: int = 20, keep_360: bool = False) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: List[str] = []

    # hlavní carousel
    for btn in soup.select('[data-testid="image-carousel-image-button"]'):
        urls.extend(extract_imgs_from_node(btn, gw_url))

    # gallery fallback
    for btn in soup.select('[data-testid="gallery-image-button"]'):
        urls.extend(extract_imgs_from_node(btn, gw_url))

    # active image fallback
    active = soup.select_one('[data-testid="image-carousel-active-image"]')
    if active:
        urls.extend(extract_imgs_from_node(active, gw_url))

    urls = filter_gw_product_images(urls, keep_360=keep_360)
    urls = uniq_keep_order(urls)
    urls = dedupe_by_filename(urls)
    urls = keep_real_product_images(urls)

    return urls[:max_images]


def extract_code_from_images(images: List[str]) -> str:
    for u in images:
        m = re.search(r"/(\d{8,14})_[^/]+(?:\.jpg|\.jpeg|\.png|\.webp|\.avif)", u, flags=re.I)
        if m:
            return m.group(1)
    return ""


def gw_extract_name(soup: BeautifulSoup, gw_url: str) -> str:
    h2 = soup.select_one('[data-testid="hero-product-card-name"]')
    if h2:
        return norm_ws(h2.get_text(" "))

    path = urlparse(gw_url).path.strip("/")
    slug = path.split("/")[-1] if path else ""
    slug = re.sub(r"^\d+-", "", slug)
    slug = slug.replace("-", " ")
    return norm_ws(slug.title())


def gw_extract_price(html: str) -> Tuple[Optional[float], Optional[str]]:
    soup = BeautifulSoup(html, "lxml")

    hero = soup.select_one('[data-testid="hero-product-card-price"]')
    if hero:
        txt = hero.get_text(" ", strip=True)
        m = re.search(r"([€$£])\s*([0-9]+(?:[.,][0-9]{1,2})?)", txt)
        if m:
            return float(m.group(2).replace(",", ".")), m.group(1)

    qty = soup.select_one('[data-testid="quantity-and-price-container"]')
    if qty:
        txt = qty.get_text(" ", strip=True)
        m = re.search(r"([€$£])\s*([0-9]+(?:[.,][0-9]{1,2})?)", txt)
        if m:
            return float(m.group(2).replace(",", ".")), m.group(1)

    return None, None


def gw_extract_features(soup: BeautifulSoup) -> List[str]:
    out = []
    for p in soup.select('[data-testid^="product-detail-feature-"]'):
        txt = norm_ws(p.get_text(" "))
        if txt:
            out.append(txt)
    return out


def gw_detect_system(name: str, features: List[str], gw_url: str) -> str:
    text = " | ".join([name, gw_url] + features).lower()

    if "warhammer 40,000" in text or "warhammer 40k" in text:
        return "Warhammer 40k"
    if "age of sigmar" in text:
        return "Warhammer Age of Sigmar"
    if "horus heresy" in text:
        return "The Horus Heresy"
    if "old world" in text:
        return "Warhammer: The Old World"
    if "kill team" in text:
        return "Kill Team"
    if "necromunda" in text:
        return "Necromunda"
    if "warcry" in text:
        return "Warcry"
    if "underworlds" in text:
        return "Underworlds"
    if "blood bowl" in text:
        return "Blood Bowl"
    if "middle-earth" in text or "middle earth" in text:
        return "Middle-earth"

    return "Warhammer"


def gw_detect_faction(name: str, features: List[str], gw_url: str) -> str:
    text = " | ".join([name, gw_url] + features).lower()

    matches = []
    for faction, aliases in FACTION_ALIASES.items():
        for alias in aliases:
            if alias.lower() in text:
                matches.append(faction)
                break

    matches = sorted(set(matches), key=len, reverse=True)
    return matches[0] if matches else ""


def detect_product_type(name: str, system: str, faction: str, features: List[str]) -> str:
    s = f"{name} {system} {faction} {' '.join(features)}".lower()

    if any(k in s for k in ["codex", "rulebook", "battletome", "novel", "book", "cards", "reference cards"]):
        return "book"
    if any(k in s for k in ["dice", "dice set", "kostk"]):
        return "dice"
    if any(k in s for k in ["warscroll", "datacards", "data cards"]):
        return "warscroll"
    if any(k in s for k in ["upgrade", "upgrades", "upgrade pack", "transfer sheet"]):
        return "upgrades"
    if any(k in s for k in ["paint", "brush", "glue", "tool", "tools", "primer", "spray", "basing"]):
        return "accessories"
    return "miniatures"


def build_final_name(system: str, faction: str, product_name: str) -> str:
    system = normalize_system_name(system)
    faction = norm_ws(faction)
    product_name = clean_title(product_name)

    if system and faction:
        return f"{system}: {faction} - {product_name}"
    if system:
        return f"{system}: {product_name}"
    return product_name


def build_novinka_from_gw(
    gw_url: str,
    sale_price_czk: Optional[float] = None,
    keep_360: bool = False,
    only_first_image: bool = False,
    vat: float = 21.0,
    warranty: str = "2 roky",
    supplier: str = "Games Workshop",
    stock: str = "0",
    percent_vat: str = "21",
    oss_tax_rate_cz: str = "",
    availability_in_stock: str = "Skladem",
    availability_out_of_stock: str = "Na dotaz",
    product_visibility: str = "hidden",
    google_category_id_in_feed: str = "1246",
    heureka_category_id: str = "1475",
    zbozi_category_id: str = "412",
    google_category_id: str = "1246",
) -> Dict[str, object]:
    html, final_url = fetch_gw_html(gw_url)
    soup = BeautifulSoup(html, "lxml")

    raw_name = gw_extract_name(soup, final_url)
    features = gw_extract_features(soup)
    system = gw_detect_system(raw_name, features, final_url)
    faction = gw_detect_faction(raw_name, features, final_url)
    product_type = detect_product_type(raw_name, system, faction, features)

    final_name = build_final_name(system, faction, raw_name)

    gw_price, gw_currency = gw_extract_price(html)
    standard_price = round(gw_price * FX_RATES[gw_currency], 2) if (gw_price is not None and gw_currency in FX_RATES) else None

    price = sale_price_czk if sale_price_czk is not None else standard_price
    price_wo_vat = price_without_vat(price, vat) if price is not None else None

    images = scrape_gw_images(final_url, html, max_images=20, keep_360=keep_360)
    if only_first_image and images:
        images = [images[0]]

    code = extract_code_from_images(images)
    external_code = code
    ean = ""

    xml_feed_name = make_xml_feed_name_from_name(final_name)
    seo_title = make_seo_title_from_name(final_name)

    create_row: Dict[str, str] = {c: "" for c in CREATE_COLUMNS}
    source_row: Dict[str, str] = {c: "" for c in SOURCE_COLUMNS}

    create_row.update({
        "code": code,
        "pairCode": "",
        "name": final_name,
        "price": f"{price:.2f}".replace(".", ",") if price is not None else "",
        "description": "",
    })

    source_row.update({
        "code": code,
        "pairCode": "",
        "name": final_name,
        "ean": ean,
        "externalCode": external_code,
        "price": f"{price:.2f}".replace(".", ",") if price is not None else "",
        "priceWithoutVat": f"{price_wo_vat:.2f}".replace(".", ",") if price_wo_vat is not None else "",
        "standardPrice": f"{standard_price:.2f}".replace(".", ",") if standard_price is not None else "",
        "categoryText": "Warhammer",
        "warranty": warranty,
        "supplier": supplier,
        "googleCategoryIdInFeed": google_category_id_in_feed,
        "heurekaCategoryId": heureka_category_id,
        "zboziCategoryId": zbozi_category_id,
        "googleCategoryId": google_category_id,
        "stock": stock,
        "percentVat": percent_vat,
        "ossTaxRate:CZ": oss_tax_rate_cz,
        "availabilityInStock": availability_in_stock,
        "availabilityOutOfStock": availability_out_of_stock,
        "productVisibility": product_visibility,
        "xmlFeedName": xml_feed_name,
        "seoTitle": seo_title,
        "system": system,
        "faction": faction,
        "productType": product_type,
        "hp_url": "",
        "gw_url": final_url,
    })

    if images:
        create_row["image"] = images[0]
        source_row["image"] = images[0]

        for idx_img in range(1, min(20, len(images))):
            col = f"image{idx_img + 1}"
            create_row[col] = images[idx_img]
            source_row[col] = images[idx_img]

    create_df = pd.DataFrame([create_row], columns=CREATE_COLUMNS)
    source_df = pd.DataFrame([source_row], columns=SOURCE_COLUMNS)

    return {
        "raw_name": raw_name,
        "final_name": final_name,
        "system": system,
        "faction": faction,
        "product_type": product_type,
        "code": code,
        "standard_price": standard_price,
        "price": price,
        "features": features,
        "images": images,
        "create_df": create_df,
        "source_df": source_df,
    }


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(
        sep=";",
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL
    ).encode("utf-8-sig")