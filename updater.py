"""
updater.py — Vérification des mises à jour depuis GitHub
Vérifie au démarrage, affiche une popup si nouvelle version disponible
"""

import json
import threading
import urllib.request
import os
import tempfile
import subprocess

GITHUB_RAW_URL = "https://raw.githubusercontent.com/codenosenpai/ReelMakerPro/main/version.json"
CURRENT_VERSION = "1.0.0"


def check_update(callback):
    """
    Vérifie en arrière-plan s'il y a une mise à jour.
    callback(info: dict) appelé si update disponible.
    """
    def _check():
        try:
            req = urllib.request.Request(
                GITHUB_RAW_URL,
                headers={"User-Agent": "ReelMakerPro-Updater/1.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            remote = data.get("version", "0.0.0")
            if _newer(remote, CURRENT_VERSION):
                callback(data)

        except Exception:
            pass

    threading.Thread(target=_check, daemon=True).start()


def download_and_install(url: str, log_fn=print):
    """
    Télécharge le setup .exe et le lance automatiquement.
    """
    def _dl():
        try:
            log_fn("Téléchargement de la mise à jour…")
            tmp = os.path.join(tempfile.gettempdir(), "ReelMakerPro_Update.exe")

            req = urllib.request.Request(
                url, headers={"User-Agent": "ReelMakerPro-Updater/1.0"})

            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.getheader("Content-Length", 0))
                done  = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total > 0:
                            pct = int(done / total * 100)
                            log_fn(f"Téléchargement : {pct}%")

            log_fn("Lancement de l'installation…")
            subprocess.Popen([tmp, "/SILENT", "/CLOSEAPPLICATIONS"],
                             creationflags=subprocess.DETACHED_PROCESS)
            # Fermer l'app après 2s pour laisser l'installateur prendre la main
            import time, sys
            time.sleep(2)
            sys.exit(0)

        except Exception as e:
            log_fn(f"Erreur mise à jour : {e}")

    threading.Thread(target=_dl, daemon=True).start()


def _newer(remote: str, current: str) -> bool:
    """Compare deux versions x.y.z"""
    try:
        r = tuple(int(x) for x in remote.split("."))
        c = tuple(int(x) for x in current.split("."))
        return r > c
    except Exception:
        return False
