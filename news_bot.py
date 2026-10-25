from __future__ import annotations

# مراقب أخبار السعودية — ملف واحد. الإعدادات في config.yaml
# GDELT + Google News (لغات متعددة) -> تنقية -> تلقرام. وضع --fast للفحص السريع

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

import requests
import yaml

log = logging.getLogger("newsbot")
ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"
RIYADH = dt.timezone(dt.timedelta(hours=3))
UA = "Mozilla/5.0 (compatible; SaudiNewsWatch/1.0; +https://github.com)"

GDELT_LANG_CODES = {
    "english": "en", "arabic": "ar", "french": "fr", "german": "de", "spanish": "es", "russian": "ru",
    "chinese": "zh", "japanese": "ja", "korean": "ko", "turkish": "tr", "persian": "fa", "urdu": "ur",
    "hindi": "hi", "indonesian": "id", "portuguese": "pt", "italian": "it", "hebrew": "he",
    "thai": "th", "vietnamese": "vi", "malay": "ms", "bengali": "bn", "tamil": "ta", "polish": "pl",
    "dutch": "nl", "ukrainian": "uk", "greek": "el", "swedish": "sv", "czech": "cs", "romanian": "ro",
    "hungarian": "hu", "bulgarian": "bg", "serbian": "sr", "kazakh": "kk", "uzbek": "uz", "swahili": "sw",
    "amharic": "am", "somali": "so", "hausa": "ha", "nepali": "ne", "norwegian": "no", "danish": "da",
    "finnish": "fi",
}
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "cmpid"}


@dataclass
class Article:
    title: str
    url: str
    domain: str
    source_name: str
    lang: str
    country_ar: str
    published: Optional[dt.datetime]
    origin: str
    direct: bool
    tier: str = "other"
    uid: str = ""


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING]
        return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", urlencode(q), ""))
    except ValueError:
        return url.strip()


def norm_title(t: str) -> str:
    return re.sub(r"[\W_]+", " ", t.lower(), flags=re.U).strip()


def h(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def host_of(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def http_get(url: str, timeout: int = 20, **kw) -> Optional[requests.Response]:
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=timeout, **kw)
    except requests.RequestException as e:
        log.warning("خطأ شبكة: %s", e)
        return None


def fetch_gdelt(cfg: dict, deadline: float) -> tuple[List[Article], Dict[str, int]]:
    g = cfg["gdelt"]
    out: List[Article] = []
    counts: Dict[str, int] = {}
    for lang in g["languages"]:
        if time.monotonic() > deadline:
            log.warning("GDELT: انتهت الميزانية الزمنية")
            break
        query = f'{g["query_terms"]} sourcelang:{lang}'
        url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + quote_plus(query) +
               f'&mode=artlist&format=json&sort=datedesc&maxrecords={g.get("maxrecords", 60)}'
               f'&timespan={g.get("timespan", "3h")}')
        data = None
        for attempt in range(2):
            time.sleep(9)
            r = http_get(url, timeout=30)
            if r is None:
                continue
            if r.status_code == 429:
                log.warning("GDELT: 429 (تمهّل)")
                time.sleep(25)
                continue
            try:
                data = r.json()
                break
            except ValueError:
                log.warning("GDELT %s: رد غير JSON: %s", lang, r.text[:120].replace("\n", " "))
        items = (data or {}).get("articles") or []
        counts[f"gdelt:{lang}"] = len(items)
        log.info("gdelt | %s -> %d", lang, len(items))
        out.extend(parse_gdelt_items(items, cfg))
    return out, counts


def parse_gdelt_items(items: list, cfg: dict) -> List[Article]:
    res = []
    countries = cfg.get("countries_ar", {})
    for it in items:
        title, url = (it.get("title") or "").strip(), (it.get("url") or "").strip()
        if not title or not url:
            continue
        pub = None
        sd = it.get("seendate") or ""
        try:
            pub = dt.datetime.strptime(sd, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass
        lang_name = (it.get("language") or "").strip().lower()
        country = (it.get("sourcecountry") or "").strip()
        domain = (it.get("domain") or host_of(url)).lower()
        res.append(Article(
            title=title, url=url, domain=domain[4:] if domain.startswith("www.") else domain,
            source_name=domain, lang=GDELT_LANG_CODES.get(lang_name, lang_name or "?"),
            country_ar=countries.get(country.lower(), country), published=pub, origin="gdelt", direct=True))
    return res


def fetch_gnews(cfg: dict, deadline: float) -> tuple[List[Article], Dict[str, int]]:
    g = cfg["google_news"]
    out: List[Article] = []
    counts: Dict[str, int] = {}
    for ed in g["editions"]:
        if time.monotonic() > deadline:
            log.warning("Google News: انتهت الميزانية الزمنية")
            break
        q = f'{ed["query"]} when:{g.get("when", "3h")}'
        url = (f'https://news.google.com/rss/search?q={quote_plus(q)}'
               f'&hl={ed["hl"]}&gl={ed["gl"]}&ceid={quote_plus(ed["ceid"])}')
        time.sleep(1.5)
        r = http_get(url)
        key = f'gnews:{ed["lang"]}-{ed["gl"]}'
        if r is None or r.status_code != 200:
            log.warning("gnews %s: HTTP %s", key, getattr(r, "status_code", "-"))
            counts[key] = 0
            continue
        arts = parse_gnews_rss(r.content, ed)
        counts[key] = len(arts)
        log.info("gnews | %s -> %d", key, len(arts))
        out.extend(arts)
    return out, counts


def parse_gnews_rss(xml_bytes: bytes, ed: dict) -> List[Article]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    res = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        src = item.find("source")
        src_name = (src.text or "").strip() if src is not None and src.text else ""
        src_url = src.get("url", "") if src is not None else ""
        if src_name and title.endswith(" - " + src_name):
            title = title[: -len(" - " + src_name)].strip()
        pub = None
        try:
            pub =
