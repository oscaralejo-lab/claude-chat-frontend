#!/usr/bin/env python3
"""
Script de configuración ÚNICA — Genera el refresh_token para la automatización.

Ejecuta este script UNA SOLA VEZ en tu máquina local para obtener el
refresh_token que necesitas guardar en los GitHub Secrets.

Uso:
  1. Crea un proyecto en https://console.cloud.google.com
  2. Activa la YouTube Data API v3
  3. Crea credenciales OAuth 2.0 (tipo "Aplicación de escritorio")
  4. Descarga el archivo client_secret.json o rellena CLIENT_ID y CLIENT_SECRET abajo
  5. Ejecuta: python3 get_refresh_token.py
  6. Autoriza en el navegador
  7. Copia el refresh_token a tus GitHub Secrets
"""

import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow

# ────────────────────────────────────────────────────
# RELLENA ESTOS VALORES con tus credenciales de Google
CLIENT_ID = "TU_CLIENT_ID_AQUI.apps.googleusercontent.com"
CLIENT_SECRET = "TU_CLIENT_SECRET_AQUI"
# ────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CLIENT_CONFIG = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


def main():
    if CLIENT_ID == "TU_CLIENT_ID_AQUI.apps.googleusercontent.com":
        print("ERROR: Edita este archivo y rellena CLIENT_ID y CLIENT_SECRET primero.")
        return

    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    print("\n" + "=" * 60)
    print("COPIA ESTOS VALORES A TUS GITHUB SECRETS:")
    print("=" * 60)
    print(f"\nYOUTUBE_CLIENT_ID:\n  {CLIENT_ID}")
    print(f"\nYOUTUBE_CLIENT_SECRET:\n  {CLIENT_SECRET}")
    print(f"\nYOUTUBE_REFRESH_TOKEN:\n  {creds.refresh_token}")
    print("\n" + "=" * 60)
    print("GitHub > Settings > Secrets and variables > Actions > New secret")


if __name__ == "__main__":
    main()
