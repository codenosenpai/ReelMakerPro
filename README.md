# ReelMaker Pro

Montage vidéo automatique avec IA — Instagram + Pixabay + bibliothèque locale.

---

## Installation rapide (utilisateurs)

Télécharge `ReelMakerPro_Setup.exe` depuis la page [Releases](../../releases/latest) et lance-le.

---

## Développement

### Prérequis
- Python 3.11+
- ffmpeg dans le PATH : `winget install ffmpeg`

### Installer les dépendances
```
pip install customtkinter Pillow scenedetect[opencv] packaging pyinstaller
```

### Lancer en développement
```
python main.py
```

### Construire l'installateur
```
pip install pyinstaller
python build.py
```

---

## Système de mise à jour

Le fichier `version.json` à la racine du repo est vérifié à chaque démarrage de l'app.

Pour publier une mise à jour :

1. Modifie `version.json` :
```json
{
  "version": "1.1.0",
  "release_date": "2025-04-01",
  "changelog": "Description des changements",
  "download_url": "https://github.com/codenosenpai/ReelMakerPro/releases/latest/download/ReelMakerPro_Setup.exe",
  "mandatory": false
}
```

2. Lance `python build.py` pour créer le nouvel installateur

3. Crée une Release GitHub avec le fichier `ReelMakerPro_Setup.exe`

4. Push `version.json` sur GitHub

→ Les utilisateurs verront automatiquement la popup de mise à jour au prochain lancement.

---

## Configuration GitHub (première fois)

1. Crée un repo GitHub : `ReelMakerPro`
2. Dans `updater.py`, remplace `codenosenpai` par ton vrai username GitHub
3. Dans `setup.iss`, remplace `codenosenpai` par ton username
4. Dans `version.json`, remplace `codenosenpai` par ton username
5. Push tout sur GitHub
6. Va dans **Settings → Actions → Workflow permissions** → autoriser "Read and write"

---

## Structure des fichiers

```
ReelMakerPro/
├── main.py          Interface graphique
├── engine.py        Moteur IA + montage (mode manuel)
├── auto_mode.py     Mode automatique (Instagram + Pixabay)
├── updater.py       Vérification mises à jour GitHub
├── version.json     Version actuelle (uploadé sur GitHub)
├── build.py         Script de build installateur
├── setup.iss        Script Inno Setup
└── instagram.com_cookies.txt  (optionnel, pour Instagram)
```
