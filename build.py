"""
build.py — Construit l'installateur Windows de ReelMaker Pro
Lance : python build.py

Prérequis :
  - pip install pyinstaller
  - Inno Setup 6 installé : https://jrsoftware.org/isdl.php
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

APP_NAME    = "ReelMakerPro"
VERSION     = "1.0.0"
MAIN_FILE   = "main.py"
INNO_SETUP  = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
SCRIPT_ISS  = "setup.iss"

# Fichiers à inclure à côté de l'exe
EXTRA_FILES = [
    "engine.py",
    "auto_mode.py",
    "updater.py",
    "version.json",
]


def clean():
    print("🧹 Nettoyage…")
    for d in ["dist", "build", "__pycache__"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    for f in Path(".").glob("*.spec"):
        f.unlink()


def build_exe():
    print("📦 Construction de l'exe avec PyInstaller…")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",          # dossier (plus rapide au lancement que onefile)
        "--windowed",        # pas de terminal noir
        "--name", APP_NAME,
        "--clean",
    ]

    # Ajouter les fichiers supplémentaires
    for f in EXTRA_FILES:
        if os.path.exists(f):
            cmd += ["--add-data", f"{f};."]

    # Icône
    cmd += ["--icon", "icon.ico"]

    cmd.append(MAIN_FILE)

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print("❌ PyInstaller a échoué.")
        sys.exit(1)
    print("✅ Exe créé dans dist/")


def build_installer():
    if not os.path.exists(INNO_SETUP):
        print(f"⚠️  Inno Setup introuvable : {INNO_SETUP}")
        print("   Télécharge-le sur https://jrsoftware.org/isdl.php")
        print("   L'exe est quand même disponible dans dist/")
        return

    print("🔧 Création de l'installateur avec Inno Setup…")
    os.makedirs("dist_installer", exist_ok=True)
    result = subprocess.run([INNO_SETUP, SCRIPT_ISS], capture_output=False)
    if result.returncode != 0:
        print("❌ Inno Setup a échoué.")
    else:
        installer = Path("dist_installer") / f"ReelMakerPro_Setup.exe"
        if installer.exists():
            size = installer.stat().st_size / (1024 * 1024)
            print(f"✅ Installateur créé : {installer} ({size:.1f} MB)")
        else:
            print("✅ Inno Setup terminé.")


if __name__ == "__main__":
    print(f"🎬 Build de ReelMaker Pro v{VERSION}")
    print("=" * 40)
    clean()
    build_exe()
    build_installer()
    print("\n✅ Build terminé !")
    print(f"   Exe          : dist/{APP_NAME}/{APP_NAME}.exe")
    print(f"   Installateur : dist_installer/ReelMakerPro_Setup.exe")
