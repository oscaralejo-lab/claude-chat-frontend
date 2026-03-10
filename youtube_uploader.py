#!/usr/bin/env python3
"""
Sube un video a YouTube usando la YouTube Data API v3.

Requiere variables de entorno:
  YOUTUBE_CLIENT_ID
  YOUTUBE_CLIENT_SECRET
  YOUTUBE_REFRESH_TOKEN
"""

import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_service():
    client_id     = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise EnvironmentError(
            "Faltan variables de entorno: "
            "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN"
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category: str = "28",
    language: str = "es",
    privacy: str = "public",
) -> str:
    """
    Sube el video y devuelve la URL de YouTube.
    """
    video_file = Path(video_path)
    if not video_file.exists():
        raise FileNotFoundError(f"Video no encontrado: {video_path}")

    size_mb = video_file.stat().st_size / 1_000_000
    print(f"  Subiendo a YouTube: {title[:60]}")
    print(f"  Archivo: {video_file.name} ({size_mb:.1f} MB)")

    service = _get_service()

    body = {
        "snippet": {
            "title":           title,
            "description":     description,
            "tags":            tags,
            "categoryId":      category,
            "defaultLanguage": language,
        },
        "status": {
            "privacyStatus":              privacy,
            "selfDeclaredMadeForKids":    False,
        },
    }

    media = MediaFileUpload(
        str(video_file),
        chunksize=8 * 1024 * 1024,
        resumable=True,
    )

    request = service.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"    Subida: {pct}%", end="\r")

    video_id  = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"\n  ✓ Video subido: {video_url}")
    return video_url


if __name__ == "__main__":
    import argparse, json as _json

    parser = argparse.ArgumentParser(description="Sube un video a YouTube")
    parser.add_argument("video",       help="Ruta al archivo MP4")
    parser.add_argument("--title",       default="Video Tech", help="Título")
    parser.add_argument("--description", default="", help="Descripción")
    parser.add_argument("--tags",        default="tecnología", help="Tags separados por coma")
    args = parser.parse_args()

    url = upload_video(
        args.video,
        title=args.title,
        description=args.description,
        tags=[t.strip() for t in args.tags.split(",")],
    )
    print(url)
