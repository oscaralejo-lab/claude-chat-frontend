#!/usr/bin/env python3
"""
Pipeline principal de automatización diaria.

Flujo:
  1. Obtener noticias tecnológicas desde feeds RSS
  2. Generar guion de narración con Claude API
  3. Convertir guion a audio (TTS)
  4. Crear video (slides + audio)
  5. Subir a YouTube

Variables de entorno requeridas:
  ANTHROPIC_API_KEY
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from news_fetcher    import fetch_news
from script_generator import generate_script
from tts_generator   import generate_segment_audios
from video_creator   import build_video
from youtube_uploader import upload_video


def run(config_path: str = "config.json", dry_run: bool = False) -> None:
    separator = "=" * 60
    print(f"\n{separator}")
    print(f"  TechNoticias — Pipeline Diario")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{separator}")

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    # ── 1. Noticias ──────────────────────────────────────────
    print("\n[1/5] Obteniendo noticias RSS…")
    articles = fetch_news(config_path)

    if not articles:
        print("  [!] No se encontraron artículos. Abortando.")
        sys.exit(1)

    print(f"  {len(articles)} noticias seleccionadas:")
    for i, a in enumerate(articles, 1):
        print(f"    {i}. [{a['source']}] {a['title'][:70]}")

    # ── 2. Guion con Claude ──────────────────────────────────
    print("\n[2/5] Generando guion con Claude API…")
    script = generate_script(articles, config_path)

    print(f"  Título del video: {script['title']}")
    print(f"  Segmentos: {len(script['segments'])}")

    # ── 3. Audio TTS ─────────────────────────────────────────
    print("\n[3/5] Generando audios TTS…")
    work_dir = tempfile.mkdtemp(prefix="technoticias_")
    audio_paths = generate_segment_audios(
        script["segments"],
        work_dir=os.path.join(work_dir, "audio"),
        tts_config=config["tts"],
    )

    # ── 4. Video ─────────────────────────────────────────────
    print("\n[4/5] Creando video…")
    video_path = config["video"]["output_path"]
    build_video(
        segments=script["segments"],
        audio_paths=audio_paths,
        output_path=video_path,
        cfg=config,
    )

    if dry_run:
        print(f"\n  [DRY RUN] Video generado en: {video_path}")
        print("  Subida a YouTube omitida (dry_run=True).")
        return

    # ── 5. Subir a YouTube ───────────────────────────────────
    print("\n[5/5] Subiendo a YouTube…")

    # Combinar tags de config + tags generados por Claude
    all_tags = config["youtube"]["tags"] + script.get("extra_tags", [])
    # Deduplicar y limitar a 500 chars totales (límite de YouTube)
    seen, tags_final = set(), []
    for t in all_tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            tags_final.append(t)

    video_url = upload_video(
        video_path=video_path,
        title=script["title"],
        description=script["description"],
        tags=tags_final,
        category=config["youtube"]["category"],
        language=config["youtube"]["language"],
        privacy=config["youtube"]["privacy"],
    )

    print(f"\n{separator}")
    print(f"  ¡Pipeline completado con éxito!")
    print(f"  Video publicado: {video_url}")
    print(f"{separator}\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline diario de TechNoticias")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Genera el video pero no lo sube a YouTube",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Ruta al archivo de configuración",
    )
    args = parser.parse_args()

    run(config_path=args.config, dry_run=args.dry_run)
