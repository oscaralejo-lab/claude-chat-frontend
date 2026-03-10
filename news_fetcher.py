#!/usr/bin/env python3
"""
Obtiene las noticias de tecnología más recientes desde múltiples feeds RSS.
"""

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser


def strip_html(text: str) -> str:
    """Elimina etiquetas HTML y normaliza espacios."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_date(entry) -> datetime | None:
    """Intenta extraer la fecha de publicación de una entrada RSS."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            ts = time.mktime(val)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
    return None


def fetch_news(config_path: str = "config.json") -> list[dict]:
    """
    Descarga y filtra artículos de los feeds RSS configurados.
    Devuelve una lista de dicts con: title, summary, url, source.
    """
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    max_articles = config.get("max_articles", 5)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    articles = []
    seen_titles: set[str] = set()

    for feed_cfg in config["rss_feeds"]:
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        print(f"  Descargando {name} …")

        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "TechNoticiaBot/1.0"})
        except Exception as e:
            print(f"    [!] Error al descargar {name}: {e}")
            continue

        for entry in feed.entries[:15]:
            title = strip_html(entry.get("title", "")).strip()
            if not title or title.lower() in seen_titles:
                continue

            # Filtrar por fecha si está disponible
            pub_date = parse_date(entry)
            if pub_date and pub_date < cutoff:
                continue

            # Obtener resumen: summary > description > content
            raw_summary = (
                entry.get("summary")
                or entry.get("description")
                or (entry.get("content") or [{}])[0].get("value", "")
            )
            summary = strip_html(raw_summary)
            # Truncar a 300 caracteres para el guion
            if len(summary) > 300:
                summary = summary[:297] + "…"

            seen_titles.add(title.lower())
            articles.append({
                "title":     title,
                "summary":   summary,
                "url":       entry.get("link", ""),
                "source":    name,
                "lang":      feed_cfg.get("lang", "en"),
                "published": pub_date.isoformat() if pub_date else None,
            })

    # Ordenar por fecha (más recientes primero) y devolver los top N
    articles.sort(key=lambda x: x.get("published") or "", reverse=True)
    selected = articles[:max_articles]

    print(f"  {len(selected)} artículos seleccionados de {len(articles)} encontrados.")
    return selected


if __name__ == "__main__":
    arts = fetch_news()
    for i, a in enumerate(arts, 1):
        print(f"\n[{i}] {a['source']} — {a['title'][:80]}")
        print(f"    {a['summary'][:120]}")
