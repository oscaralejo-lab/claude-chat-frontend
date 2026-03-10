#!/usr/bin/env python3
"""
Automatización de subida diaria a YouTube.
Lee la cola de videos (video_queue.json) y sube el siguiente video pendiente.

Requiere las siguientes variables de entorno (GitHub Secrets):
  - YOUTUBE_CLIENT_ID
  - YOUTUBE_CLIENT_SECRET
  - YOUTUBE_REFRESH_TOKEN
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError


QUEUE_FILE = Path(__file__).parent / "video_queue.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_authenticated_service():
    """Autentica con YouTube Data API usando credenciales OAuth2 del entorno."""
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("ERROR: Faltan variables de entorno de autenticación.")
        print("  Necesitas: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN")
        sys.exit(1)

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )

    # Refresca el token automáticamente
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def load_queue():
    """Carga la cola de videos desde el archivo JSON."""
    if not QUEUE_FILE.exists():
        print(f"ERROR: No se encontró {QUEUE_FILE}")
        sys.exit(1)

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(data):
    """Guarda la cola actualizada en el archivo JSON."""
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_next_video(queue_data):
    """Devuelve el índice y datos del siguiente video pendiente."""
    for i, video in enumerate(queue_data.get("videos", [])):
        if not video.get("uploaded", False):
            return i, video
    return None, None


def upload_video(service, video_data):
    """Sube un video a YouTube y devuelve el ID del video subido."""
    video_file = Path(video_data["file"])

    if not video_file.exists():
        raise FileNotFoundError(f"Archivo de video no encontrado: {video_file}")

    body = {
        "snippet": {
            "title": video_data.get("title", "Video sin título"),
            "description": video_data.get("description", ""),
            "tags": video_data.get("tags", []),
            "categoryId": video_data.get("category", "22"),  # 22 = People & Blogs
            "defaultLanguage": video_data.get("language", "es"),
        },
        "status": {
            "privacyStatus": video_data.get("privacy", "public"),
            "selfDeclaredMadeForKids": video_data.get("made_for_kids", False),
        },
    }

    # Añadir thumbnail programado si se especifica
    if video_data.get("scheduled_publish_at"):
        body["status"]["publishAt"] = video_data["scheduled_publish_at"]
        body["status"]["privacyStatus"] = "private"  # Requerido para programación

    media = MediaFileUpload(
        str(video_file),
        chunksize=8 * 1024 * 1024,  # Chunks de 8MB
        resumable=True,
    )

    print(f"Subiendo: {video_data['title']}")
    print(f"Archivo:  {video_file} ({video_file.stat().st_size / 1_000_000:.1f} MB)")

    request = service.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            print(f"  Progreso: {progress}%")

    return response["id"]


def main():
    print(f"=== YouTube Uploader — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")

    queue_data = load_queue()
    idx, video_data = get_next_video(queue_data)

    if video_data is None:
        print("No hay videos pendientes en la cola. ¡Cola vacía!")
        sys.exit(0)

    print(f"Video seleccionado: [{idx + 1}/{len(queue_data['videos'])}] {video_data['title']}")

    service = get_authenticated_service()

    try:
        video_id = upload_video(service, video_data)
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Marcar como subido
        queue_data["videos"][idx]["uploaded"] = True
        queue_data["videos"][idx]["uploaded_at"] = datetime.now(timezone.utc).isoformat()
        queue_data["videos"][idx]["youtube_id"] = video_id
        queue_data["videos"][idx]["youtube_url"] = video_url
        save_queue(queue_data)

        print(f"\n✓ Video subido exitosamente!")
        print(f"  URL: {video_url}")

        # Mostrar cuántos quedan
        pending = sum(1 for v in queue_data["videos"] if not v.get("uploaded"))
        print(f"  Videos pendientes restantes: {pending}")

    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    except HttpError as e:
        print(f"\nERROR de la API de YouTube: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
