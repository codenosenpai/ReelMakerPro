"""
updater.py — Vérification des mises à jour depuis GitHub
"""

import json
import threading
import urllib.request
import urllib.error
from packaging import version as pkg_version

# ⚠️ Remplace par ton vrai repo GitHub
GITHUB_RAW_URL = "https://raw.githubusercontent.com/TON_USERNAME/reelmaker-pro/main/version.json"
CURRENT_VERSION = "1.0.0"


def check_update(callback):
    """
    Vérifie en arrière-plan s'il y a une mise à jour.
    callback(info: dict) est appelé si une update est dispo.
    info = {"version", "changelog", "download_url", "mandatory"}
    """
    def _check():
        try:
            req = urllib.request.Request(
                GITHUB_RAW_URL,
                headers={"User-Agent": "ReelMakerPro-Updater/1.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            remote_ver = data.get("version", "0.0.0")
            if pkg_version.parse(remote_ver) > pkg_version.parse(CURRENT_VERSION):
                callback(data)

        except Exception:
            pass  # Silencieux si pas de connexion

    threading.Thread(target=_check, daemon=True).start()
