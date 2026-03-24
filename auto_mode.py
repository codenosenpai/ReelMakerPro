"""
auto_mode.py — Mode automatique LOCAL uniquement
- Prend toutes les vidéos sources d'un dossier
- Pour chacune : choisit des clips depuis la bibliothèque locale
- Monte automatiquement N vidéos numérotées 001.mp4, 002.mp4...
- Reprise intelligente : saute les vidéos déjà générées
- Variété : jamais le même clip deux fois dans la même vidéo
"""

import os
import json
import subprocess
import tempfile
import random
import threading
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

TMP = os.path.join(tempfile.gettempdir(), "reelmaker_auto")
os.makedirs(TMP, exist_ok=True)

ENCODE = [
    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
    "-profile:v", "baseline", "-level", "3.1",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart"
]


class AutoMode:
    def __init__(self, log_fn=print, progress_fn=None, step_fn=None):
        self.log  = log_fn
        self.prog = progress_fn or (lambda v: None)
        self.step = step_fn or (lambda t: None)
        self._stop = threading.Event()

        # Suivi global : clips déjà utilisés entre vidéos
        self._used_global = set()

    def stop(self):
        self._stop.set()

    # ═════════════════════════════════════════════
    # POINT D'ENTRÉE
    # ═════════════════════════════════════════════
    def run(self, config: dict, on_done=None, on_error=None):
        """
        config = {
            sources_folder : str   dossier des vidéos sources (audio)
            library_path   : str   dossier bibliothèque clips
            output_folder  : str   dossier de sortie
            nb_videos      : int   nombre max de vidéos à générer
            start_from     : int   numéro de départ (reprise)
            out_w, out_h   : int
            transition_dur : float
            fadeout_dur    : float
            logo_cfg       : dict | None
        }
        """
        sources_folder = config["sources_folder"]
        library_path   = config["library_path"]
        output_folder  = config["output_folder"]
        nb_videos      = config["nb_videos"]
        start_from     = config.get("start_from", 1)

        os.makedirs(output_folder, exist_ok=True)

        # Scanner les sources
        sources = sorted([
            os.path.join(sources_folder, f)
            for f in os.listdir(sources_folder)
            if Path(f).suffix.lower() in VIDEO_EXTS
        ])

        if not sources:
            if on_error:
                on_error("Aucune vidéo trouvée dans le dossier sources.")
            return

        # Scanner la bibliothèque
        library = self._scan(library_path)
        if not library:
            if on_error:
                on_error("Bibliothèque vide — ajoute des clips.")
            return

        self.log(f"Sources : {len(sources)} vidéo(s)")
        self.log(f"Bibliothèque : {len(library)} clip(s)")

        generated = start_from - 1
        total     = min(nb_videos, len(sources))

        for i in range(start_from - 1, total):
            if self._stop.is_set():
                self.log("Arrêté.")
                break

            num = f"{i+1:03d}"
            out = os.path.join(output_folder, f"{num}.mp4")
            src = sources[i]

            self.step(f"Vidéo {num}/{total}…")
            self.log(f"\n{'─'*40}")
            self.log(f"[{num}] Source : {Path(src).name}")

            try:
                # Extraire l'audio
                audio, dur = self._extract_audio(src, num)
                if not audio:
                    self.log(f"[{num}] ⚠ Pas d'audio, on passe.")
                    continue

                self.log(f"[{num}] Durée audio : {dur:.1f}s")

                # Choisir les clips
                clips = self._pick_clips(library, dur)
                self.log(f"[{num}] {len(clips)} clip(s) sélectionné(s)")

                # Monter
                self._render(clips, audio, dur, out, config)
                generated += 1
                self.log(f"[{num}] ✓ {out}")
                if on_done:
                    on_done(num, out, generated)

            except Exception as e:
                self.log(f"[{num}] ERREUR : {e}")
                if on_error:
                    on_error(f"[{num}] {e}")

            self.prog(generated / total)

        self.log(f"\n✓ Terminé : {generated} vidéo(s) générée(s)")
        self.step("Terminé ✓")

    # ═════════════════════════════════════════════
    # SÉLECTION DES CLIPS — VARIÉTÉ GARANTIE
    # ═════════════════════════════════════════════
    def _pick_clips(self, library: list, total_dur: float) -> list:
        """
        Choisit des clips depuis la bibliothèque pour couvrir total_dur secondes.
        - Priorité aux clips pas encore utilisés dans cette session
        - Si bibliothèque épuisée → réinitialise et recommence
        - Jamais le même clip deux fois dans la même vidéo
        """
        clips     = []
        remaining = total_dur
        used_this = set()  # clips utilisés dans cette vidéo uniquement

        # Pool frais (pas utilisés dans les vidéos précédentes)
        fresh = [c for c in library if c["path"] not in self._used_global]

        # Si tout est épuisé → réinitialiser le suivi global
        if not fresh:
            self.log("  Bibliothèque épuisée → réinitialisation de la rotation")
            self._used_global.clear()
            fresh = list(library)

        # Mélanger pour la variété
        pool = list(fresh)
        random.shuffle(pool)

        while remaining > 0.5:
            # Clips disponibles pour cette vidéo
            available = [c for c in pool if c["path"] not in used_this]

            if not available:
                # Tous utilisés dans cette vidéo → prendre depuis le reste de la bibliothèque
                available = [c for c in library if c["path"] not in used_this]
                if not available:
                    break  # bibliothèque vraiment trop petite
                random.shuffle(available)

            # Choisir le clip dont la durée couvre le mieux ce qu'il reste
            # Priorité : clips assez longs, sinon le plus long dispo
            long_enough = [c for c in available if c["duration"] >= min(remaining, 10.0)]
            chosen = random.choice(long_enough) if long_enough else max(available, key=lambda c: c["duration"])

            dur_to_use = min(chosen["duration"], remaining)
            clips.append({
                "path":       chosen["path"],
                "duration":   dur_to_use,
                "trim_start": 0.0,
                "trim_end":   dur_to_use,
                "speed":      1.0,
                "type":       chosen["type"],
            })

            used_this.add(chosen["path"])
            self._used_global.add(chosen["path"])
            remaining -= dur_to_use

        return clips

    # ═════════════════════════════════════════════
    # AUDIO
    # ═════════════════════════════════════════════
    def _extract_audio(self, video: str, num: str) -> tuple:
        out = os.path.join(TMP, f"audio_{num}.aac")
        cmd = ["ffmpeg", "-y", "-i", video, "-vn",
               "-acodec", "aac", "-b:a", "192k", out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0 and os.path.exists(out):
            return out, self._duration(out)
        return None, 0

    # ═════════════════════════════════════════════
    # MONTAGE
    # ═════════════════════════════════════════════
    def _render(self, clips, audio, dur, output, config):
        out_w = config.get("out_w", 1080)
        out_h = config.get("out_h", 1920)
        fade  = config.get("fadeout_dur", 3.0)
        logo  = config.get("logo_cfg")

        # Préparer les segments
        mute = config.get("mute_clips", True)
        segments = []
        for i, clip in enumerate(clips):
            seg = self._prep(clip, i, out_w, out_h, mute)
            if seg:
                segments.append(seg)

        if not segments:
            raise RuntimeError("Aucun segment valide.")

        import shutil

        # Concat
        merged = os.path.join(TMP, "auto_merged.mp4")
        if len(segments) == 1:
            shutil.copy2(segments[0], merged)
        else:
            self._concat(segments, merged)

        # Audio
        with_audio = os.path.join(TMP, "auto_audio.mp4")
        self._add_audio(merged, audio, dur, with_audio)

        # Fondu sortie
        with_fade = os.path.join(TMP, "auto_fade.mp4")
        self._fadeout(with_audio, fade, with_fade)

        # Logo
        if logo and logo.get("path") and os.path.isfile(logo["path"]):
            with_logo = os.path.join(TMP, "auto_logo.mp4")
            self._add_logo(with_fade, logo, with_logo, out_w, out_h)
            final = with_logo
        else:
            final = with_fade

        shutil.copy2(final, output)

    def _prep(self, clip, idx, W, H, mute=True):
        out  = os.path.join(TMP, f"seg_{idx:04d}.mp4")
        path = clip["path"]
        dur  = max(clip.get("trim_end", clip["duration"]) - clip.get("trim_start", 0), 0.5)
        ext  = Path(path).suffix.lower()
        vf   = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},fps=30,format=yuv420p")
        try:
            if ext in IMAGE_EXTS:
                cmd = ["ffmpeg", "-y", "-loop", "1", "-i", path,
                       "-vf", vf, "-t", str(dur)] + (["-an"] if mute else []) + ENCODE + [out, "-loglevel", "error"]
            else:
                cmd = ["ffmpeg", "-y", "-ss", str(clip.get("trim_start", 0)),
                       "-i", path, "-t", str(dur),
                       "-vf", vf] + (["-an"] if mute else []) + ENCODE + [out, "-loglevel", "error"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            return out if r.returncode == 0 and os.path.exists(out) else None
        except Exception:
            return None

    def _concat(self, segs, out):
        lst = os.path.join(TMP, "concat.txt")
        with open(lst, "w") as f:
            for s in segs:
                f.write(f"file '{s}'\n")
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", lst] + ENCODE + [out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Concat : {r.stderr[-200:]}")

    def _add_audio(self, video, audio, dur, out):
        import shutil
        if not audio or not os.path.isfile(audio):
            shutil.copy2(video, out)
            return
        cmd = ["ffmpeg", "-y", "-i", video, "-i", audio,
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-preset", "fast", "-crf", "22",
               "-profile:v", "baseline", "-level", "3.1",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-c:a", "aac", "-b:a", "192k",
               "-t", str(dur), out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Audio : {r.stderr[-200:]}")

    def _fadeout(self, video, fade, out):
        import shutil
        dur = self._duration(video)
        st  = max(0, dur - fade)
        cmd = ["ffmpeg", "-y", "-i", video,
               "-vf", f"fade=t=out:st={st:.3f}:d={fade:.3f}",
               "-af", f"afade=t=out:st={st:.3f}:d={fade:.3f}",
               "-c:v", "libx264", "-preset", "fast", "-crf", "22",
               "-profile:v", "baseline", "-level", "3.1",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-c:a", "aac", "-b:a", "192k",
               out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            shutil.copy2(video, out)

    def _add_logo(self, video, logo, out, W, H):
        lw  = int(W * logo["size_pct"] / 100)
        m   = 30
        pos = {
            "Haut gauche": f"{m}:{m}", "Haut droite": f"W-w-{m}:{m}",
            "Bas gauche":  f"{m}:H-h-{m}", "Bas droite": f"W-w-{m}:H-h-{m}",
            "Centre":      "(W-w)/2:(H-h)/2"
        }.get(logo.get("position", "Bas droite"), f"W-w-{m}:H-h-{m}")
        vf  = (f"[1:v]scale={lw}:-1,format=rgba,"
               f"colorchannelmixer=aa={logo['opacity']:.3f}[l];"
               f"[0:v][l]overlay={pos}:format=auto")
        cmd = ["ffmpeg", "-y", "-i", video, "-i", logo["path"],
               "-filter_complex", vf,
               "-c:v", "libx264", "-preset", "fast", "-crf", "20",
               "-profile:v", "baseline", "-level", "3.1",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-c:a", "aac", "-b:a", "192k",
               out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Logo : {r.stderr[-200:]}")

    # ═════════════════════════════════════════════
    # UTILITAIRES
    # ═════════════════════════════════════════════
    def _scan(self, folder: str) -> list:
        items = []
        for root, _, files in os.walk(folder):
            for f in files:
                fp  = os.path.join(root, f)
                ext = Path(f).suffix.lower()
                if ext in VIDEO_EXTS:
                    items.append({"path": fp, "type": "video",
                                  "duration": self._duration(fp)})
                elif ext in IMAGE_EXTS:
                    items.append({"path": fp, "type": "image",
                                  "duration": 5.0})
        return items

    def _duration(self, path: str) -> float:
        cmd = ["ffprobe", "-v", "error", "-show_entries",
               "format=duration", "-of", "json", path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return float(json.loads(r.stdout)["format"]["duration"])
        except Exception:
            return 5.0
