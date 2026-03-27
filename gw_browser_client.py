# gw_browser_client.py
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
)


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def strip_query_and_fragment(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def abs_url(base: str, u: str) -> str:
    return urljoin(base, u)


def strip_query(u: str) -> str:
    try:
        p = urlparse(u)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return u


def filename_key(u: str) -> str:
    u2 = strip_query(u)
    return urlparse(u2).path.lower().split("/")[-1]


def uniq_keep_order(seq: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in seq:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def dedupe_by_filename(urls: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for u in urls:
        key = filename_key(u)
        if key and key not in seen:
            out.append(u)
            seen.add(key)
    return out


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


def is_missing_image(u: str) -> bool:
    low = (u or "").lower()
    return "missing_image" in low or "missing_image_servo_skull" in low


def filter_gw_product_images(urls: List[str], keep_360: bool = False) -> List[str]:
    out: List[str] = []

    for u in urls:
        if not u or is_missing_image(u):
            continue

        low = u.lower()

        allowed = (
            "/app/resources/catalog/product/" in low
            or "/catalog/product/" in low
            or "/resources/catalog/product/" in low
            or "/media/catalog/product/" in low
        )
        if not allowed:
            continue

        if not keep_360 and ("threesixty" in low or "threeSixty" in u):
            continue

        out.append(u)

    return out


def keep_real_product_images(images: List[str]) -> List[str]:
    out: List[str] = []
    bad_markers = [
        "landscape",
        "header",
        "banner",
        "category",
        "aeronautica_imperialis",
    ]

    for u in images:
        low = u.lower()

        if any(b in low for b in bad_markers):
            continue

        if (
            "/app/resources/catalog/product/" in low
            or "/catalog/product/" in low
            or "/resources/catalog/product/" in low
            or "/media/catalog/product/" in low
        ):
            out.append(u)

    return out if out else images


def extract_imgs_from_scoped_node(node: BeautifulSoup, base_url: str) -> List[str]:
    urls: List[str] = []

    for img in node.select("img[src]"):
        src = (img.get("src") or "").strip()
        if src:
            urls.append(abs_url(base_url, src))

    for img in node.select("img[srcset]"):
        best = pick_best_srcset((img.get("srcset") or "").strip())
        if best:
            urls.append(abs_url(base_url, best))

    for source in node.select("source[srcset]"):
        best = pick_best_srcset((source.get("srcset") or "").strip())
        if best:
            urls.append(abs_url(base_url, best))

    return urls


def extract_imgs_from_soup(
    soup: BeautifulSoup,
    base_url: str,
    keep_360: bool = False,
) -> List[str]:
    urls: List[str] = []

    scoped_selectors = [
        '[data-testid="container-image-carousel"]',
        '[data-testid="image-carousel-active-image"]',
        '[data-testid="image-carousel-mobile"]',
        '[data-testid="image-gallery"]',
        '[data-testid="gallery-modal-image"]',
        '[data-testid="container-gallery-modal"]',
    ]

    for sel in scoped_selectors:
        for node in soup.select(sel):
            urls.extend(extract_imgs_from_scoped_node(node, base_url))

    for img in soup.select("img[src]"):
        src = (img.get("src") or "").strip()
        if src:
            urls.append(abs_url(base_url, src))

    for img in soup.select("img[srcset]"):
        best = pick_best_srcset((img.get("srcset") or "").strip())
        if best:
            urls.append(abs_url(base_url, best))

    for source in soup.select("source[srcset]"):
        best = pick_best_srcset((source.get("srcset") or "").strip())
        if best:
            urls.append(abs_url(base_url, best))

    urls = filter_gw_product_images(urls, keep_360=keep_360)
    urls = uniq_keep_order(urls)
    urls = dedupe_by_filename(urls)
    urls = keep_real_product_images(urls)
    return urls


def extract_price_from_html(html: str) -> tuple[Optional[float], Optional[str]]:
    if not html:
        return None, None

    soup = BeautifulSoup(html, "lxml")

    selectors = [
        '[data-testid="hero-product-card-price"]',
        '[data-testid="quantity-and-price-container"]',
    ]

    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            txt = norm_ws(el.get_text(" "))
            m = re.search(r"([€$£])\s*([0-9]+(?:[.,][0-9]{1,2})?)", txt)
            if m:
                try:
                    return float(m.group(2).replace(",", ".")), m.group(1)
                except Exception:
                    pass

    m = re.search(r"([€$£])\s*([0-9]+(?:[.,][0-9]{1,2})?)", html, flags=re.I | re.S)
    if m:
        try:
            return float(m.group(2).replace(",", ".")), m.group(1)
        except Exception:
            pass

    return None, None


def extract_name_from_html(html: str, final_url: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    h2 = soup.select_one('[data-testid="hero-product-card-name"]')
    if h2:
        return norm_ws(h2.get_text(" "))

    title_el = soup.select_one("title")
    if title_el:
        title_txt = norm_ws(title_el.get_text(" "))
        if title_txt:
            return title_txt

    path = urlparse(final_url).path.strip("/")
    slug = path.split("/")[-1] if path else ""
    slug = re.sub(r"^\d+-", "", slug)
    slug = slug.replace("-", " ")
    return norm_ws(slug.title())


def extract_features_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    features: List[str] = []

    selectors = [
        '[data-testid^="product-detail-feature-"]',
        '[data-testid="product-detail-features-grid"] p',
        '[data-testid="product-detail-hero-features"] p',
    ]

    for sel in selectors:
        for el in soup.select(sel):
            txt = norm_ws(el.get_text(" "))
            if txt and txt not in features:
                features.append(txt)

    return features


def extract_code_from_images(images: List[str]) -> str:
    for u in images:
        m = re.search(
            r"/(\d{8,14})_[^/]+(?:\.jpg|\.jpeg|\.png|\.webp|\.avif)",
            u,
            flags=re.I,
        )
        if m:
            return m.group(1)
    return ""


class GWBrowserClient:
    def __init__(
        self,
        headless: bool = True,
        debug: bool = False,
        timeout_ms: int = 45000,
    ) -> None:
        self.headless = headless
        self.debug = debug
        self.timeout_ms = timeout_ms

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def __enter__(self) -> "GWBrowserClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self._playwright is not None:
            return

        self._playwright = sync_playwright().start()

        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        self._context = self._browser.new_context(
            viewport={"width": 1440, "height": 1600},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            java_script_enabled=True,
            ignore_https_errors=True,
        )

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None

        if self._browser is not None:
            self._browser.close()
            self._browser = None

        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def _new_page(self) -> Page:
        if self._context is None:
            self.start()

        assert self._context is not None
        page = self._context.new_page()

        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        return page

    def _wait_for_product_ready(self, page: Page) -> None:
        waited_any = False

        selectors = [
            '[data-testid="hero-product-card-name"]',
            '[data-testid="hero-product-card-price"]',
            '[data-testid="quantity-and-price-container"]',
            '[data-testid="container-image-carousel"]',
            '[data-testid="image-carousel-active-image"]',
            '[data-testid="image-gallery"]',
        ]

        for sel in selectors:
            try:
                page.wait_for_selector(sel, timeout=7000)
                waited_any = True
            except Exception:
                pass

        if not waited_any:
            page.wait_for_timeout(2500)
        else:
            page.wait_for_timeout(1200)

    def _trigger_lazy_load(self, page: Page) -> None:
        scroll_steps = [
            "window.scrollTo(0, document.body.scrollHeight * 0.25)",
            "window.scrollTo(0, document.body.scrollHeight * 0.50)",
            "window.scrollTo(0, document.body.scrollHeight * 0.75)",
            "window.scrollTo(0, document.body.scrollHeight)",
            "window.scrollTo(0, 0)",
        ]

        for script in scroll_steps:
            try:
                page.evaluate(script)
            except Exception:
                pass
            page.wait_for_timeout(700)

    def _extract_from_page(
        self,
        page: Page,
        keep_360: bool,
        max_images: int,
    ) -> Dict[str, object]:
        html = page.content()
        final_url = page.url

        soup = BeautifulSoup(html, "lxml")
        images = extract_imgs_from_soup(soup, final_url, keep_360=keep_360)
        images = keep_real_product_images(images)
        images = dedupe_by_filename(uniq_keep_order(images))
        images = images[:max_images]

        price_value, price_currency = extract_price_from_html(html)
        name = extract_name_from_html(html, final_url)
        features = extract_features_from_html(html)
        image_code = extract_code_from_images(images)

        return {
            "html": html,
            "final_url": final_url,
            "name": name,
            "price": price_value,
            "currency": price_currency,
            "price_value": price_value,
            "price_currency": price_currency,
            "images": images,
            "image_code": image_code,
            "features": features,
        }

    def fetch_product(
        self,
        url: str,
        keep_360: bool = False,
        max_images: int = 20,
        retries: int = 3,
        save_debug_html: bool = False,
    ) -> Dict[str, object]:
        candidates = [url]
        stripped = strip_query_and_fragment(url)
        if stripped != url:
            candidates.append(stripped)
        candidates = uniq_keep_order(candidates)

        last_error = None
        best_result: Dict[str, object] = {
            "html": "",
            "final_url": url,
            "name": "",
            "price": None,
            "currency": None,
            "price_value": None,
            "price_currency": None,
            "images": [],
            "image_code": "",
            "features": [],
        }

        for candidate in candidates:
            page = self._new_page()
            try:
                for attempt in range(1, retries + 1):
                    try:
                        page.goto(candidate, wait_until="domcontentloaded", timeout=self.timeout_ms)
                        self._wait_for_product_ready(page)
                        self._trigger_lazy_load(page)

                        result = self._extract_from_page(
                            page,
                            keep_360=keep_360,
                            max_images=max_images,
                        )

                        current_score = 0
                        if result["name"]:
                            current_score += 1
                        if result["price_value"] is not None:
                            current_score += 1
                        if result["images"]:
                            current_score += 2
                        if result["features"]:
                            current_score += 1

                        best_score = 0
                        if best_result["name"]:
                            best_score += 1
                        if best_result["price_value"] is not None:
                            best_score += 1
                        if best_result["images"]:
                            best_score += 2
                        if best_result["features"]:
                            best_score += 1

                        if current_score >= best_score:
                            best_result = result

                        success = bool(
                            result["html"] and (
                                result["name"]
                                or result["price_value"] is not None
                                or len(result["images"]) > 0
                            )
                        )

                        strong_success = bool(
                            result["name"]
                            and (result["price_value"] is not None or len(result["images"]) > 0)
                        )

                        if self.debug:
                            print(f"GW browser attempt {attempt}/{retries}: {candidate}")
                            print("final_url:", result["final_url"])
                            print("name:", result["name"])
                            print("price:", result["price_value"], result["price_currency"])
                            print("images:", len(result["images"]))
                            print("features:", len(result["features"]))

                        if save_debug_html and result["html"]:
                            Path("DEBUG_GW_BROWSER.html").write_text(
                                result["html"],
                                encoding="utf-8",
                            )
                            try:
                                page.screenshot(path="DEBUG_GW_BROWSER.png", full_page=True)
                            except Exception:
                                pass

                        if strong_success or (success and attempt >= 2):
                            return best_result

                        if attempt < retries:
                            page.reload(wait_until="domcontentloaded", timeout=self.timeout_ms)
                            page.wait_for_timeout(1200)

                    except PlaywrightTimeoutError as e:
                        last_error = e
                        if self.debug:
                            print(f"Playwright timeout {attempt}/{retries}: {candidate} | {e}")
                        if attempt < retries:
                            try:
                                page.reload(wait_until="domcontentloaded", timeout=self.timeout_ms)
                            except Exception:
                                pass
                            page.wait_for_timeout(1200)

                    except Exception as e:
                        last_error = e
                        if self.debug:
                            print(f"Playwright error {attempt}/{retries}: {candidate} | {e}")
                        if attempt < retries:
                            try:
                                page.reload(wait_until="domcontentloaded", timeout=self.timeout_ms)
                            except Exception:
                                pass
                            page.wait_for_timeout(1200)

                if best_result.get("html"):
                    return best_result

            finally:
                try:
                    page.close()
                except Exception:
                    pass

        if not best_result.get("html") and last_error:
            raise last_error

        return best_result


def fetch_gw_product_browser(
    url: str,
    keep_360: bool = False,
    timeout_ms: int = 45000,
    debug: bool = False,
) -> Dict[str, object]:
    with GWBrowserClient(
        headless=True,
        debug=debug,
        timeout_ms=timeout_ms,
    ) as client:
        return client.fetch_product(
            url=url,
            keep_360=keep_360,
            max_images=20,
            retries=3,
            save_debug_html=debug,
        )