#!/usr/bin/env python3
"""
Usa la API de Claude para generar el guion de narración del video diario
a partir de las noticias de tecnología obtenidas por el fetcher.

Requiere la variable de entorno: ANTHROPIC_API_KEY
"""

import json
import os
from datetime import datetime, timezone

import anthropic


SYSTEM_PROMPT = """Eres el guionista de un canal de YouTube de noticias tecnológicas en español.
Tu objetivo es escribir guiones de narración naturales, dinámicos y entretenidos.
El presentador habla de forma cercana, clara y entusiasta.
Usa siempre español neutro (sin jerga regional muy marcada) para que te entiendan en toda Hispanoamérica y España.
Evita frases de relleno vacías. Ve al grano pero con energía."""


def generate_script(articles: list[dict], config_path: str = "config.json") -> dict:
    """
    Recibe la lista de artículos y devuelve un dict con:
      - title: título del video
      - description: descripción para YouTube
      - tags: lista de etiquetas adicionales
      - segments: lista de {type, title?, text}
    """
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    channel_name = config.get("channel_name", "TechNoticias")
    today = datetime.now(timezone.utc).strftime("%-d de %B de %Y")

    # Construir el resumen de noticias para el prompt
    news_block = "\n\n".join(
        f"[{i+1}] FUENTE: {a['source']}\nTÍTULO: {a['title']}\nRESUMEN: {a['summary']}"
        for i, a in enumerate(articles)
    )

    user_prompt = f"""Hoy es {today}. Genera el guion completo para el video diario del canal "{channel_name}".

Estas son las noticias de hoy:
{news_block}

Devuelve un JSON (y SOLO el JSON, sin texto extra) con esta estructura exacta:
{{
  "title": "Título del video para YouTube (máx 80 chars, con fecha, llamativo)",
  "description": "Descripción del video para YouTube (3-5 frases con las noticias del día, con hashtags al final)",
  "extra_tags": ["tag1", "tag2"],
  "segments": [
    {{
      "type": "intro",
      "text": "Texto de la introducción (15-20 segundos de locución, bienvenida al canal y preview de las noticias)"
    }},
    {{
      "type": "news",
      "headline": "Título corto de la noticia para mostrar en pantalla (máx 60 chars)",
      "text": "Texto de la locución para esta noticia (40-60 segundos, explica la noticia con contexto)"
    }},
    ... (un segmento "news" por noticia)
    {{
      "type": "outro",
      "text": "Texto de despedida (10-15 segundos, invita a suscribirse y activar la campanita)"
    }}
  ]
}}"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("  Generando guion con Claude …")
    raw = ""
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text_chunk in stream.text_stream:
            raw += text_chunk

    # Extraer el JSON de la respuesta (puede venir envuelto en ```json…```)
    json_match = raw.strip()
    if json_match.startswith("```"):
        lines = json_match.splitlines()
        json_match = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    script = json.loads(json_match)
    print(f"  Guion generado: {len(script['segments'])} segmentos.")
    return script


if __name__ == "__main__":
    # Prueba rápida con artículos de ejemplo
    sample = [
        {
            "title": "OpenAI presenta GPT-5 con capacidades multimodales avanzadas",
            "summary": "OpenAI ha anunciado oficialmente GPT-5, su modelo de lenguaje más avanzado hasta la fecha.",
            "source": "TechCrunch",
        },
        {
            "title": "Apple lanza sus nuevas gafas de realidad mixta para el mercado europeo",
            "summary": "Apple Vision Pro llega a Europa con nuevas características exclusivas.",
            "source": "The Verge",
        },
    ]
    result = generate_script(sample)
    print(json.dumps(result, ensure_ascii=False, indent=2))
