from __future__ import annotations

import calendar
import concurrent.futures
import datetime as dt
import logging
import os
import time
from urllib.parse import quote_plus, urlparse

import feedparser
import requests

UA = "Mozilla/5.0 (compatible; SaudiNewsWatch/3.0; +https://github.com)"


def _request(url, *, timeout, headers=None, params=None):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": UA, **(headers or {})},
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        logging.warning("News source request failed (%s): %s", url, exc)
        return None


def _published(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return dt.datetime.fromtimestamp(calendar.timegm(parsed), dt.timezone.utc)
    except (OverflowError, TypeError, ValueError):
        return None


def _host(url):
    return (urlparse(url).hostname or "").lower()


def _item(title, url, *, domain="", source_name="", lang="en", country_ar="", published=None, origin):
    if not title or not url:
        return None
    return {
        "title": title.strip(),
        "url": url.strip(),
        "domain": domain or _host(url),
        "source_name": source_name or domain or _host(url) or "News",
        "lang": lang or "en",
        "country_ar": country_ar or "",
        "published": published,
        "origin": origin,
        "direct": origin != "gnews",
    }


def parse_feed(content, metadata, origin):
    parsed = feedparser.parse(content)
    if parsed.bozo:
        logging.warning(
            "RSS parse warning (%s): %s",
            metadata.get("name", origin),
            parsed.bozo_exception,
        )
    items = []
    for entry in parsed.entries:
        source = entry.get("source") or {}
        source_url = source.get("href", "")
        item = _item(
            entry.get("title", ""),
            entry.get("link", ""),
            domain=_host(source_url),
            source_name=source.get("title", ""),
            lang=metadata.get("lang", "en"),
            country_ar=metadata.get("country_ar", ""),
            published=_published(entry),
            origin=origin,
        )
        if item:
            items.append(item)
    return items


def fetch_gnews_edition(edition, deadline):
    if time.monotonic() >= deadline:
        return []
    query = edition.get("query", '"Saudi Arabia"')
    url = "https://news.google.com/rss/search?" + (
        f"q={quote_plus(query)}&hl={quote_plus(edition.get('hl', 'en-US'))}"
        f"&gl={quote_plus(edition.get('gl', 'US'))}"
        f"&ceid={quote_plus(edition.get('ceid', 'US:en'))}"
    )
    response = _request(url, timeout=min(15, max(1, deadline - time.monotonic())))
    if response is None:
        return []
    return parse_feed(response.content, edition, "gnews")


def fetch_rss(feed, deadline):
    if time.monotonic() >= deadline:
        return []
    url = feed.get("url", "")
    response = _request(url, timeout=min(15, max(1, deadline - time.monotonic())))
    if response is None:
        return []
    return parse_feed(response.content, feed, "rss")


def fetch_gdelt_language(language, config, deadline):
    if time.monotonic() >= deadline:
        return []
    query = config.get("query_terms", '"Saudi Arabia" OR Riyadh')
    params = {
        "query": f"{query} sourcelang:{language}",
        "mode": "artlist",
        "format": "json",
        "maxrecords": config.get("maxrecords", 60),
        "sort": "datedesc",
        "timespan": config.get("timespan", "2h"),
    }
    response = _request(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params=params,
        timeout=min(20, max(1, deadline - time.monotonic())),
    )
    if response is None:
        return []
    try:
        records = (response.json() or {}).get("articles") or []
    except (ValueError, TypeError, AttributeError) as exc:
        logging.warning("GDELT response parse failed (%s): %s", language, exc)
        return []
    items = []
    for record in records:
        seen = record.get("seendate", "")
        try:
            published = dt.datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            published = None
        item = _item(
            record.get("title", ""),
            record.get("url", ""),
            domain=record.get("domain", ""),
            source_name=record.get("domain", ""),
            lang=record.get("language", language),
            country_ar=record.get("sourcecountry", ""),
            published=published,
            origin="gdelt",
        )
        if item:
            items.append(item)
    return items


def fetch_newsapi(config, deadline):
    token = os.getenv(config.get("api_key_env", "NEWSAPI_API_KEY"))
    if not config.get("enabled", True) or not token:
        if config.get("enabled", True):
            logging.info("NewsAPI skipped: API key environment variable is not set")
        return []
    if time.monotonic() >= deadline:
        return []
    params = {
        "q": config.get("query", '"Saudi Arabia" OR Riyadh OR Aramco OR NEOM'),
        "pageSize": min(100, max(1, int(config.get("page_size", 100)))),
        "sortBy": config.get("sort_by", "publishedAt"),
    }
    language = config.get("language", "all")
    if language and language != "all":
        params["language"] = language
    response = _request(
        config.get("endpoint", "https://newsapi.org/v2/everything"),
        headers={"X-Api-Key": token},
        params=params,
        timeout=min(15, max(1, deadline - time.monotonic())),
    )
    if response is None:
        return []
    try:
        data = response.json()
        if data.get("status") != "ok":
            logging.warning("NewsAPI returned an error: %s", data.get("message", "unknown error"))
            return []
        records = data.get("articles") or []
    except (ValueError, TypeError, AttributeError) as exc:
        logging.warning("NewsAPI response parse failed: %s", exc)
        return []
    items = []
    for record in records:
        source = record.get("source") or {}
        try:
            published = dt.datetime.fromisoformat(record.get("publishedAt", "").replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            published = None
        item = _item(
            record.get("title", ""),
            record.get("url", ""),
            source_name=source.get("name", ""),
            lang=config.get("lang", "und"),
            published=published,
            origin="newsapi",
        )
        if item:
            items.append(item)
    return items


def fetch_bing_news(config, deadline):
    endpoint = config.get("endpoint")
    if not endpoint:
        logging.warning("Bing News Search API was retired; configure a compatible endpoint to enable this source")
        return []
    token = os.getenv(config.get("api_key_env", "BING_NEWS_API_KEY"))
    if not config.get("enabled", True) or not token:
        if config.get("enabled", True):
            logging.info("Bing News skipped: API key environment variable is not set")
        return []
    if time.monotonic() >= deadline:
        return []
    params = {
        "q": config.get("query", '"Saudi Arabia" OR Riyadh OR Aramco OR NEOM'),
        "count": min(100, max(1, int(config.get("count", 100)))),
        "sortBy": config.get("sort_by", "Date"),
        "safeSearch": config.get("safe_search", "Off"),
    }
    market = config.get("market", "")
    if market and market != "all":
        params["mkt"] = market
    response = _request(
        endpoint,
        headers={"Ocp-Apim-Subscription-Key": token},
        params=params,
        timeout=min(15, max(1, deadline - time.monotonic())),
    )
    if response is None:
        return []
    try:
        records = (response.json() or {}).get("value") or []
    except (ValueError, TypeError, AttributeError) as exc:
        logging.warning("Bing News response parse failed: %s", exc)
        return []
    items = []
    for record in records:
        providers = record.get("provider") or []
        provider = providers[0] if providers else {}
        try:
            published = dt.datetime.fromisoformat(record.get("datePublished", "").replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            published = None
        item = _item(
            record.get("name", ""),
            record.get("url", ""),
            source_name=provider.get("name", ""),
            lang=config.get("lang", "und"),
            country_ar=config.get("country_ar", ""),
            published=published,
            origin="bing",
        )
        if item:
            items.append(item)
    return items


def fetch_sources(config, deadline):
    jobs = []
    gdelt = config.get("gdelt", {})
    if gdelt.get("enabled", True):
        jobs.extend(
            (f"gdelt:{language}", fetch_gdelt_language, language, gdelt, deadline)
            for language in gdelt.get("languages", ["english", "arabic"])
        )
    google_news = config.get("google_news", {})
    if google_news.get("enabled", True):
        jobs.extend(
            (f"gnews:{edition.get('lang')}-{edition.get('gl')}", fetch_gnews_edition, edition, deadline)
            for edition in google_news.get("editions", [])
        )
    rss = config.get("rss", {})
    for feed in rss.get("feeds", []) if rss.get("enabled", True) else []:
        if feed.get("enabled", True) and feed.get("url"):
            jobs.append((f"rss:{feed.get('name') or feed['url']}", fetch_rss, feed, deadline))
    for name, function, source_config in (
        ("newsapi", fetch_newsapi, config.get("newsapi", {})),
        ("bing", fetch_bing_news, config.get("bing_news", {})),
    ):
        if source_config.get("enabled", False):
            jobs.append((name, function, source_config, deadline))

    if not jobs:
        return [], {}

    max_workers = max(1, min(int(config.get("source_workers", 12)), len(jobs)))
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    pending = {
        executor.submit(function, *args): source_name
        for source_name, function, *args in jobs
    }
    done, unfinished = concurrent.futures.wait(
        pending,
        timeout=max(0, deadline - time.monotonic()),
    )
    articles = []
    counts = {}
    for future in done:
        source_name = pending[future]
        try:
            items = future.result()
            articles.extend(items)
            counts[source_name] = len(items)
        except Exception:
            logging.exception("News source failed: %s", source_name)
            counts[source_name] = 0
    for future in unfinished:
        source_name = pending[future]
        future.cancel()
        counts[source_name] = 0
        logging.warning("News source timed out: %s", source_name)
    executor.shutdown(wait=False, cancel_futures=True)
    return articles, counts
