#!/usr/bin/env python3
"""
Convierte texto a voz usando Microsoft Edge TTS (gratuito).
Genera un archivo de audio MP3 por segmento del guion.
"""

import asyncio
import os
import tempfile
from pathlib import Path

import edge_tts


async def _synthesize(text: str, voice: str, rate: str, pitch: str, output_path: str) -> None:
    """Tarea async interna: convierte text → MP3."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def text_to_speech(
    text: str,
    output_path: str,
    voice: str = "es-ES-AlvaroNeural",
    rate: str = "+5%",
    pitch: str = "+0Hz",
) -> str:
    """
    Genera audio TTS y lo guarda en output_path.
    Devuelve output_path.
    """
    asyncio.run(_synthesize(text, voice, rate, pitch, output_path))
    size_kb = os.path.getsize(output_path) / 1024
    print(f"    Audio generado: {Path(output_path).name} ({size_kb:.1f} KB)")
    return output_path


def generate_segment_audios(
    segments: list[dict],
    work_dir: str,
    tts_config: dict,
) -> list[str]:
    """
    Genera un archivo MP3 por segmento y devuelve la lista de rutas en orden.

    Args:
        segments:   Lista de dicts con campo 'text'.
        work_dir:   Carpeta donde guardar los MP3.
        tts_config: Dict con voice, rate, pitch.
    """
    voice = tts_config.get("voice", "es-ES-AlvaroNeural")
    rate  = tts_config.get("rate",  "+5%")
    pitch = tts_config.get("pitch", "+0Hz")

    Path(work_dir).mkdir(parents=True, exist_ok=True)
    audio_paths = []

    for i, seg in enumerate(segments):
        out = os.path.join(work_dir, f"segment_{i:02d}.mp3")
        text = seg["text"].strip()
        if not text:
            text = "…"
        text_to_speech(text, out, voice=voice, rate=rate, pitch=pitch)
        audio_paths.append(out)

    return audio_paths


# Voces disponibles en español (para referencia en config.json)
SPANISH_VOICES = {
    "es-ES-AlvaroNeural":   "España — masculino (recomendado)",
    "es-ES-ElviraNeural":   "España — femenino",
    "es-MX-JorgeNeural":    "México — masculino",
    "es-MX-DaliaNeural":    "México — femenino",
    "es-AR-TomasNeural":    "Argentina — masculino",
    "es-AR-ElenaNeural":    "Argentina — femenino",
    "es-CO-GonzaloNeural":  "Colombia — masculino",
}


if __name__ == "__main__":
    print("Probando TTS…")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        out = tmp.name
    text_to_speech(
        "Hola, bienvenidos a TechNoticias. Estas son las noticias más importantes del día.",
        out,
    )
    print(f"Audio guardado en: {out}")
