#!/usr/bin/env python3
"""
Crea el video diario combinando:
  - Slides generados con Pillow (fondo degradado + texto)
  - Audio TTS por segmento (moviepy)
Exporta un MP4 listo para subir a YouTube.
"""

import os
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    concatenate_videoclips,
)


# ──────────────────────────────────────────────
# Utilidades de imagen con Pillow
# ──────────────────────────────────────────────

def _gradient_bg(width: int, height: int, top: tuple, bottom: tuple) -> np.ndarray:
    """Crea un fondo con degradado vertical."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        t = y / height
        arr[y, :] = [int(top[c] * (1 - t) + bottom[c] * t) for c in range(3)]
    return arr


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Intenta cargar una fuente del sistema; cae en la fuente por defecto."""
    candidates = []
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    font: ImageFont.FreeTypeFont,
    color: tuple,
    line_spacing: int = 8,
    align: str = "center",
) -> int:
    """Dibuja texto con salto de línea automático. Devuelve la Y final."""
    # Estimar caracteres por línea (aproximado)
    try:
        char_w = font.getlength("A")
    except AttributeError:
        char_w = font.getsize("A")[0]
    chars_per_line = max(1, int(max_width / char_w))
    lines = textwrap.wrap(text, width=chars_per_line)

    current_y = y
    for line in lines:
        try:
            bbox = font.getbbox(line)
            line_w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
        except AttributeError:
            line_w, line_h = font.getsize(line)

        if align == "center":
            draw_x = x + (max_width - line_w) // 2
        elif align == "right":
            draw_x = x + max_width - line_w
        else:
            draw_x = x

        draw.text((draw_x, current_y), line, font=font, fill=color)
        current_y += line_h + line_spacing

    return current_y


def _draw_accent_bar(draw: ImageDraw.ImageDraw, width: int, y: int, color: tuple, h: int = 4):
    """Dibuja una barra decorativa horizontal."""
    draw.rectangle([(40, y), (width - 40, y + h)], fill=color)


def create_slide(
    segment: dict,
    cfg: dict,
    slide_index: int,
    total_slides: int,
) -> np.ndarray:
    """
    Genera un slide (imagen numpy) para un segmento del guion.
    """
    W = cfg["width"]
    H = cfg["height"]
    bg_top    = tuple(cfg["bg_color_top"])
    bg_bot    = tuple(cfg["bg_color_bottom"])
    title_clr = tuple(cfg["title_color"])
    body_clr  = tuple(cfg["body_color"])
    accent_clr = tuple(cfg["accent_color"])
    channel   = cfg.get("channel_name", "TechNoticias")

    arr = _gradient_bg(W, H, bg_top, bg_bot)
    img = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(img)

    seg_type = segment.get("type", "news")

    # ── Fonts ───────────────────────────────────────────────
    font_channel  = _load_font(26)
    font_big      = _load_font(54, bold=True)
    font_medium   = _load_font(40, bold=True)
    font_body     = _load_font(30)
    font_counter  = _load_font(22)

    padding = 48
    content_w = W - padding * 2

    # ── Cabecera: nombre del canal ───────────────────────────
    _draw_accent_bar(draw, W, 0, accent_clr, h=6)
    draw.text((padding, 18), channel.upper(), font=font_channel, fill=title_clr)

    # ── Contador de noticias (top-right) ─────────────────────
    if seg_type == "news":
        counter_text = f"Noticia {slide_index} / {total_slides}"
        draw.text((W - padding - 160, 18), counter_text, font=font_counter, fill=body_clr)

    # ── Contenido central según tipo ─────────────────────────
    if seg_type == "intro":
        # Pantalla de intro: canal grande + fecha
        from datetime import datetime, timezone
        fecha = datetime.now(timezone.utc).strftime("%-d de %B de %Y")

        cy = H // 2 - 80
        _draw_wrapped_text(draw, channel.upper(), padding, cy, content_w,
                           font_big, title_clr, align="center")
        cy += 80
        _draw_accent_bar(draw, W, cy, accent_clr)
        cy += 20
        _draw_wrapped_text(draw, f"Noticias Tech — {fecha}", padding, cy, content_w,
                           font_body, body_clr, align="center")

    elif seg_type == "outro":
        cy = H // 2 - 60
        _draw_wrapped_text(draw, "¡Gracias por ver!", padding, cy, content_w,
                           font_big, title_clr, align="center")
        cy += 80
        _draw_accent_bar(draw, W, cy, accent_clr)
        cy += 20
        _draw_wrapped_text(draw, "Suscríbete · Like · Activa la campanita 🔔",
                           padding, cy, content_w, font_body, body_clr, align="center")

    else:  # seg_type == "news"
        headline = segment.get("headline", segment.get("title", "Noticia del día"))
        # Headline grande en la parte superior del área de contenido
        cy = 90
        _draw_accent_bar(draw, W, cy, accent_clr)
        cy += 20

        cy = _draw_wrapped_text(draw, headline, padding, cy, content_w,
                                 font_medium, title_clr, line_spacing=10, align="left")
        cy += 24

        # Resumen / texto breve del segmento (primeros ~180 chars para la pantalla)
        snippet = segment.get("text", "")
        if len(snippet) > 200:
            snippet = snippet[:197] + "…"
        _draw_wrapped_text(draw, snippet, padding, cy, content_w,
                           font_body, body_clr, line_spacing=8, align="left")

    # ── Footer: barra inferior ────────────────────────────────
    _draw_accent_bar(draw, W, H - 10, accent_clr, h=6)

    return np.array(img)


# ──────────────────────────────────────────────
# Construcción del video
# ──────────────────────────────────────────────

def build_video(
    segments: list[dict],
    audio_paths: list[str],
    output_path: str,
    cfg: dict,
) -> str:
    """
    Combina slides + audios y genera el MP4 final.

    Args:
        segments:    Lista de segmentos del guion (dicts con type, text, headline…).
        audio_paths: Ruta a cada MP3, en el mismo orden que segments.
        output_path: Ruta de salida del MP4.
        cfg:         Dict de configuración (video + channel_name).
    """
    assert len(segments) == len(audio_paths), "Segmentos y audios deben tener la misma longitud"

    fps = cfg["video"].get("fps", 24)
    video_cfg = {**cfg["video"], "channel_name": cfg.get("channel_name", "TechNoticias")}

    # Contar sólo las noticias para el contador
    news_count = sum(1 for s in segments if s.get("type") == "news")
    news_seen = 0

    clips = []
    for i, (seg, audio_path) in enumerate(zip(segments, audio_paths)):
        # Índice de noticia para el contador
        if seg.get("type") == "news":
            news_seen += 1
            slide_idx = news_seen
        else:
            slide_idx = 0

        # Generar slide
        slide_arr = create_slide(seg, video_cfg, slide_idx, news_count)

        # Cargar audio para conocer su duración
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration + 0.4  # pequeño margen al final

        # Crear clip de imagen con la duración del audio
        img_clip = (
            ImageClip(slide_arr)
            .set_duration(duration)
            .set_fps(fps)
        )

        # Añadir audio al clip
        video_clip = img_clip.set_audio(audio_clip)
        clips.append(video_clip)

        print(f"    Clip {i+1}/{len(segments)} — {seg.get('type')} — {duration:.1f}s")

    # Concatenar todos los clips
    final = concatenate_videoclips(clips, method="compose")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    print(f"  Exportando video a: {output_path}")
    final.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="/tmp/tmp_audio.m4a",
        remove_temp=True,
        logger=None,      # silencia el progress bar de moviepy
    )

    size_mb = os.path.getsize(output_path) / 1_000_000
    total_s = final.duration
    print(f"  Video listo: {size_mb:.1f} MB, {total_s:.0f}s ({total_s/60:.1f} min)")

    # Liberar recursos
    for c in clips:
        c.close()
    final.close()

    return output_path


if __name__ == "__main__":
    import json, tempfile
    with open("config.json") as f:
        cfg = json.load(f)

    # Prueba con segmentos de ejemplo
    segs = [
        {"type": "intro",  "text": "Bienvenidos a TechNoticias. Hoy tenemos grandes novedades."},
        {"type": "news",   "headline": "OpenAI lanza GPT-5",
         "text": "OpenAI ha presentado su modelo más avanzado hasta la fecha."},
        {"type": "outro",  "text": "Hasta mañana. No olvides suscribirte."},
    ]
    # Crear audios silenciosos de prueba (edge-tts no disponible en este test)
    from tts_generator import generate_segment_audios
    tmp = tempfile.mkdtemp()
    audios = generate_segment_audios(segs, tmp, cfg["tts"])
    build_video(segs, audios, "/tmp/test_video.mp4", cfg)
    print("Prueba completada.")
