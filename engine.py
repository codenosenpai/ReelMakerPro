"""
engine.py — ReelMaker Pro v3
- Durée clips décidée par l'IA selon cohérence audio/visuel
- Mode automatique : génère en boucle depuis dossier sources + fallback YouTube
- Durée finale = durée audio source
"""

import os
import subprocess
import tempfile
import json
import base64
import urllib.request
import shutil
import re
import threading
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
CACHE_FILE = "rmpro_v3_cache.json"

TMP = os.path.join(tempfile.gettempdir(), "reelmaker_pro3")
os.makedirs(TMP, exist_ok=True)

ENCODE = [
    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
    "-profile:v", "baseline", "-level", "3.1",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart"
]

# Score minimum pour utiliser un clip en entier (vs durée scène)
COHERENCE_THRESHOLD = 3.0


class Engine:
    def __init__(self, log_fn=print, progress_fn=None, step_fn=None):
        self.log  = log_fn
        self.prog = progress_fn or (lambda v: None)
        self.step = step_fn or (lambda t: None)

        self.source_path = ""
        self.audio_path  = ""
        self.audio_dur   = 0.0
        self._library    = []
        self._cache      = {}
        self._cache_path = ""

    # ═════════════════════════════════════════════
    # ANALYSE
    # ═════════════════════════════════════════════
    def analyze(self, source: str, library: str) -> list:

        self.step("Chargement de la source…")
        self.source_path = self._load_source(source)
        self.log(f"Source : {Path(self.source_path).name}")
        self.prog(0.05)

        self.step("Extraction de l'audio original…")
        self.audio_path = self._extract_audio(self.source_path)
        self.audio_dur  = self._duration(self.audio_path) if self.audio_path else self._duration(self.source_path)
        self.log(f"Audio : {self.audio_dur:.1f}s")
        self.prog(0.10)

        self.step("Détection des scènes…")
        scenes = self._detect_scenes(self.source_path)
        self.log(f"{len(scenes)} scène(s)")
        self.prog(0.18)

        self.step("Analyse visuelle des scènes…")
        scenes = self._analyze_scenes(self.source_path, scenes)
        self.prog(0.38)

        self.step("Scan bibliothèque…")
        self._cache_path = os.path.join(library, CACHE_FILE)
        self._cache = self._load_cache()
        self._library = self._scan_library(library)
        self.log(f"Bibliothèque : {len(self._library)} fichier(s)")
        self.prog(0.43)

        self.step("Analyse IA bibliothèque…")
        self._analyze_library()
        self._save_cache()
        self.prog(0.78)

        self.step("Sélection + durée intelligente des clips…")
        proposals = self._match_with_smart_duration(scenes)
        self.log(f"✓ {len(proposals)} clip(s) — durée totale : {sum(p['clip_duration'] for p in proposals):.1f}s / audio : {self.audio_dur:.1f}s")
        self.prog(1.0)
        self.step("Analyse terminée ✓")
        return proposals

    # ═════════════════════════════════════════════
    # MODE AUTOMATIQUE
    # ═════════════════════════════════════════════
    def run_auto(self, sources_folder: str, library: str, output_folder: str,
                 cfg: dict, stop_event: threading.Event,
                 on_done_fn=None, on_error_fn=None):
        """
        Génère des vidéos en boucle depuis toutes les sources du dossier.
        Numérote les sorties 001.mp4, 002.mp4...
        Si bibliothèque insuffisante, cherche sur YouTube.
        """
        os.makedirs(output_folder, exist_ok=True)

        # Lister toutes les vidéos sources
        sources = []
        for f in sorted(os.listdir(sources_folder)):
            fp  = os.path.join(sources_folder, f)
            ext = Path(f).suffix.lower()
            if ext in VIDEO_EXTS and os.path.isfile(fp):
                sources.append(fp)

        if not sources:
            if on_error_fn:
                on_error_fn("Aucune vidéo trouvée dans le dossier sources.")
            return

        self.log(f"Mode auto : {len(sources)} source(s) trouvée(s)")

        for idx, src in enumerate(sources):
            if stop_event.is_set():
                self.log("Mode auto arrêté.")
                break

            num = f"{idx+1:03d}"
            out = os.path.join(output_folder, f"{num}.mp4")

            # Sauter si déjà généré
            if os.path.isfile(out) and os.path.getsize(out) > 100_000:
                self.log(f"[{num}] Déjà généré, on passe.")
                continue

            self.log(f"\n{'='*40}")
            self.log(f"[{num}] Traitement : {Path(src).name}")
            self.step(f"Auto [{num}] : {Path(src).name}")

            try:
                proposals = self.analyze(src, library)

                # Si bibliothèque insuffisante → chercher sur YouTube
                missing = [p for p in proposals if not p.get("proposed_clip")]
                if missing:
                    self.log(f"[{num}] {len(missing)} scène(s) sans clip → recherche YouTube…")
                    self._fill_from_youtube(missing, library)

                render_cfg = {**cfg, "output": out}
                self.render_from_proposals(proposals, render_cfg)

                self.log(f"[{num}] ✓ Exporté : {out}")
                if on_done_fn:
                    on_done_fn(num, out)

            except Exception as e:
                self.log(f"[{num}] ERREUR : {e}")
                if on_error_fn:
                    on_error_fn(f"[{num}] {e}")
                continue

        self.log("Mode auto terminé.")
        self.step("Mode auto terminé ✓")

    def _fill_from_youtube(self, missing_proposals: list, library: str):
        """Cherche et télécharge des clips YouTube pour compléter la bibliothèque."""
        dl_dir = os.path.join(library, "_auto_downloads")
        os.makedirs(dl_dir, exist_ok=True)

        for prop in missing_proposals:
            tags = prop.get("scene_tags", [])
            if not tags:
                continue

            query = " ".join(tags[:3]) + " nature cinematic footage free"
            self.log(f"  YouTube search : {query}")

            url = self._yt_search(query)
            if not url:
                continue

            out_path = os.path.join(dl_dir, f"yt_{abs(hash(url))}.mp4")
            if not os.path.isfile(out_path):
                cmd = ["python", "-m", "yt_dlp",
                       "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                       "--merge-output-format", "mp4",
                       "--no-playlist", "-o", out_path, url]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    continue

            if os.path.isfile(out_path):
                dur = self._duration(out_path)
                tags_clip = self._describe_image(
                    self._extract_frame(out_path, dur/2), mode="library"
                )
                new_item = {"path": out_path, "type": "video",
                            "duration": dur, "tags": tags_clip}
                self._library.append(new_item)
                self._cache[out_path] = tags_clip
                prop["proposed_clip"] = out_path
                prop["clip_tags"]     = tags_clip
                self.log(f"  Clip YouTube ajouté : {Path(out_path).name}")

    def _yt_search(self, query: str) -> str:
        cmd = ["python", "-m", "yt_dlp",
               f"ytsearch3:{query}",
               "--get-id", "--no-download", "--no-playlist", "--flat-playlist"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if re.match(r'^[a-zA-Z0-9_\-]{11}$', line):
                    return f"https://www.youtube.com/watch?v={line}"
        except Exception:
            pass
        return ""

    # ═════════════════════════════════════════════
    # MATCHING + DURÉE INTELLIGENTE
    # ═════════════════════════════════════════════
    def _match_with_smart_duration(self, scenes: list) -> list:
        """
        Pour chaque scène, choisit le clip ET décide sa durée :
        - Score élevé (≥ THRESHOLD) → utilise le clip en entier (ou jusqu'à l'audio)
        - Score moyen → durée scène × 1.5
        - Score faible → durée scène exacte
        L'ensemble est ensuite ajusté pour coller à audio_dur.
        """
        used = set()
        proposals = []
        remaining_audio = self.audio_dur

        for i, scene in enumerate(scenes):
            if remaining_audio <= 0:
                break

            scene_tags  = scene.get("scene_tags", [])
            best, score = self._best_clip_scored(scene_tags, scene["duration"], used)

            if best:
                used.add(best["path"])
                if len(used) >= len(self._library):
                    used.clear()

                clip_full_dur = best["duration"]
                scene_dur     = scene["duration"]

                # Décision durée selon score
                if score >= COHERENCE_THRESHOLD * 2:
                    # Très cohérent → clip entier (plafonné à l'audio restant)
                    chosen_dur = min(clip_full_dur, remaining_audio)
                    self.log(f"  Scène {i+1} → clip entier ({chosen_dur:.1f}s) [score={score:.1f}]")
                elif score >= COHERENCE_THRESHOLD:
                    # Cohérent → durée scène × 1.5 ou clip entier si court
                    target = min(scene_dur * 1.5, clip_full_dur, remaining_audio)
                    chosen_dur = max(target, min(10.0, clip_full_dur, remaining_audio))
                    self.log(f"  Scène {i+1} → {chosen_dur:.1f}s [score={score:.1f}]")
                else:
                    # Peu cohérent → durée scène, minimum 5s
                    chosen_dur = min(max(scene_dur, 5.0), remaining_audio)
                    self.log(f"  Scène {i+1} → {chosen_dur:.1f}s (faible cohérence, score={score:.1f})")

                remaining_audio -= chosen_dur
            else:
                chosen_dur = min(scene["duration"], remaining_audio)
                remaining_audio -= chosen_dur

            proposals.append({
                "start":         scene["start"],
                "end":           scene["end"],
                "duration":      scene["duration"],
                "clip_duration": chosen_dur,
                "scene_tags":    scene_tags,
                "proposed_clip": best["path"] if best else "",
                "clip_tags":     best["tags"] if best else [],
                "type":          best["type"] if best else "video",
            })

        # Si audio pas encore couvert → ajouter des clips supplémentaires
        while remaining_audio > 1.0:
            all_tags = [t for p in proposals for t in p.get("scene_tags", [])]
            best, score = self._best_clip_scored(all_tags, remaining_audio, used)
            if not best:
                break
            used.add(best["path"])
            chosen_dur = min(best["duration"], remaining_audio)
            proposals.append({
                "start": 0, "end": 0, "duration": chosen_dur,
                "clip_duration": chosen_dur,
                "scene_tags": all_tags[:3],
                "proposed_clip": best["path"],
                "clip_tags": best["tags"],
                "type": best["type"],
            })
            remaining_audio -= chosen_dur
            self.log(f"  Clip supplémentaire ajouté ({chosen_dur:.1f}s) — reste {remaining_audio:.1f}s")
            if len(used) >= len(self._library):
                used.clear()

        return proposals

    def _best_clip_scored(self, scene_tags: list, dur: float,
                           used: set) -> tuple:
        pool = [i for i in self._library if i["path"] not in used]
        if not pool:
            pool = list(self._library)
        if not pool:
            return None, 0.0

        def score(item):
            item_tags = item.get("tags", [])
            exact   = sum(4 for st in scene_tags for it in item_tags if st == it)
            partial = sum(2 for st in scene_tags for it in item_tags
                          if st != it and (st in it or it in st))
            dur_bonus  = 1.5 if item["duration"] >= max(dur, 5.0) else 0.3
            type_bonus = 0.5 if item["type"] == "video" else 0.0
            return exact + partial + dur_bonus + type_bonus

        best = max(pool, key=score)
        return best, score(best)

    # ═════════════════════════════════════════════
    # RENDU DEPUIS PROPOSALS
    # ═════════════════════════════════════════════
    def render_from_proposals(self, proposals: list, cfg: dict):
        """Utilisé par le mode auto."""
        clips = []
        for p in proposals:
            clips.append({
                "path":       p.get("proposed_clip", ""),
                "duration":   p.get("clip_duration", p.get("duration", 4.0)),
                "trim_start": 0.0,
                "trim_end":   p.get("clip_duration", p.get("duration", 4.0)),
                "speed":      1.0,
                "type":       p.get("type", "video"),
            })
        full_cfg = {**cfg, "clips": clips}
        self.render(full_cfg)

    def render(self, cfg: dict):
        clips       = cfg["clips"]
        logo_cfg    = cfg.get("logo")
        output      = cfg["output"]
        trans_dur   = cfg.get("transition_dur", 0.4)
        fadeout_dur = cfg.get("fadeout_dur", 3.0)
        out_w       = cfg.get("out_w", 1080)
        out_h       = cfg.get("out_h", 1920)

        # Filtrer clips vides
        clips = [c for c in clips if c.get("path") and os.path.exists(c["path"])]
        if not clips:
            raise RuntimeError("Aucun clip valide à monter.")

        self.log(f"Montage : {len(clips)} clip(s) | {out_w}×{out_h}")
        segments = []

        mute = cfg.get("mute_clips", True)
        for i, clip in enumerate(clips):
            self.step(f"Préparation clip {i+1}/{len(clips)}…")
            seg = self._prep_clip(clip, i, out_w, out_h, mute)
            segments.append(seg)
            self.prog(0.05 + 0.55 * (i+1) / len(clips))

        self.step("Transitions fondu noir…")
        merged = self._apply_transitions(segments, trans_dur, out_w, out_h)
        self.prog(0.65)

        self.step("Ajout audio…")
        with_audio = os.path.join(TMP, "with_audio.mp4")
        self._add_audio(merged, self.audio_path, self.audio_dur, with_audio)
        self.prog(0.78)

        self.step("Fondu de sortie…")
        with_fade = os.path.join(TMP, "with_fade.mp4")
        self._apply_fadeout(with_audio, fadeout_dur, with_fade)
        self.prog(0.88)

        if logo_cfg and logo_cfg.get("path"):
            self.step("Logo…")
            with_logo = os.path.join(TMP, "with_logo.mp4")
            self._add_logo(with_fade, logo_cfg, with_logo, out_w, out_h)
            final = with_logo
        else:
            final = with_fade

        self.prog(0.97)
        shutil.copy2(final, output)
        self.prog(1.0)
        self.step("Montage terminé ✓")

    # ═════════════════════════════════════════════
    # CHARGEMENT SOURCE
    # ═════════════════════════════════════════════
    def _load_source(self, source: str) -> str:
        if os.path.isfile(source):
            return source
        if source.startswith("http"):
            out = os.path.join(TMP, "source.mp4")
            cookies = os.path.join(os.path.dirname(__file__),
                                   "instagram.com_cookies.txt")
            cmd = ["python", "-m", "yt_dlp", "--no-playlist",
                   "-f", "mp4/best[ext=mp4]/best",
                   "--merge-output-format", "mp4", "-o", out]
            if os.path.isfile(cookies):
                cmd += ["--cookies", cookies]
            cmd.append(source)
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                raise RuntimeError(f"Téléchargement échoué.\n{r.stderr[-200:]}")
            for f in os.listdir(TMP):
                if f.startswith("source") and f.endswith(".mp4"):
                    return os.path.join(TMP, f)
        raise FileNotFoundError(f"Source introuvable : {source}")

    # ═════════════════════════════════════════════
    # AUDIO
    # ═════════════════════════════════════════════
    def _extract_audio(self, video: str) -> str:
        out = os.path.join(TMP, "source_audio.aac")
        cmd = ["ffmpeg", "-y", "-i", video, "-vn",
               "-acodec", "aac", "-b:a", "192k", out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True)
        return out if r.returncode == 0 and os.path.exists(out) else ""

    # ═════════════════════════════════════════════
    # SCÈNES
    # ═════════════════════════════════════════════
    def _detect_scenes(self, video: str) -> list:
        try:
            from scenedetect import open_video, SceneManager
            from scenedetect.detectors import ContentDetector
            v = open_video(video)
            sm = SceneManager()
            sm.add_detector(ContentDetector(threshold=25.0))
            sm.detect_scenes(v, show_progress=False)
            raw = sm.get_scene_list()
            scenes = [{"start": round(s.get_seconds(), 3),
                       "end":   round(e.get_seconds(), 3),
                       "duration": round(e.get_seconds() - s.get_seconds(), 3)}
                      for s, e in raw if e.get_seconds() - s.get_seconds() >= 0.5]
            if scenes:
                return scenes
        except Exception:
            pass
        dur = self._duration(video)
        scenes, t = [], 0.0
        while t < dur:
            end = min(t + 4.0, dur)
            scenes.append({"start": round(t,3), "end": round(end,3),
                           "duration": round(end-t,3)})
            t += 4.0
        return scenes

    def _analyze_scenes(self, video: str, scenes: list) -> list:
        frames_dir = os.path.join(TMP, "src_frames")
        os.makedirs(frames_dir, exist_ok=True)
        for i, scene in enumerate(scenes):
            ts = scene["start"] + scene["duration"] / 2
            frame = os.path.join(frames_dir, f"s{i}.jpg")
            subprocess.run(["ffmpeg", "-y", "-ss", str(ts), "-i", video,
                            "-frames:v", "1", "-q:v", "2", "-vf", "scale=720:-1",
                            frame, "-loglevel", "error"], capture_output=True)
            scene["scene_tags"] = self._describe_image(frame, "scene") if os.path.exists(frame) else []
            self.log(f"  Scène {i+1}/{len(scenes)} → {', '.join(scene['scene_tags']) or '—'}")
            self.prog(0.18 + 0.20 * (i+1) / len(scenes))
        return scenes

    # ═════════════════════════════════════════════
    # BIBLIOTHÈQUE
    # ═════════════════════════════════════════════
    def _scan_library(self, folder: str) -> list:
        items = []
        for root, _, files in os.walk(folder):
            for f in files:
                if f == CACHE_FILE:
                    continue
                fp  = os.path.join(root, f)
                ext = Path(f).suffix.lower()
                if ext in VIDEO_EXTS:
                    items.append({"path": fp, "type": "video",
                                  "duration": self._duration(fp), "tags": []})
                elif ext in IMAGE_EXTS:
                    items.append({"path": fp, "type": "image",
                                  "duration": 5.0, "tags": []})
        return items

    def _analyze_library(self):
        frames_dir = os.path.join(TMP, "lib_frames")
        os.makedirs(frames_dir, exist_ok=True)
        for i, item in enumerate(self._library):
            p = item["path"]
            if p in self._cache:
                item["tags"] = self._cache[p]
                continue
            frame = self._extract_frame(p, item["duration"]/2) if item["type"] == "video" else p
            tags  = self._describe_image(frame, "library") if frame and os.path.exists(frame) else []
            item["tags"]  = tags
            self._cache[p] = tags
            self.log(f"  [{i+1}/{len(self._library)}] {Path(p).name} → {', '.join(tags) or '—'}")
            self.prog(0.43 + 0.35 * (i+1) / len(self._library))

    def _extract_frame(self, video: str, ts: float) -> str:
        out = os.path.join(TMP, "lib_frames", f"f_{abs(hash(video+str(ts)))}.jpg")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-ss", str(ts), "-i", video,
                        "-frames:v", "1", "-q:v", "2", "-vf", "scale=720:-1",
                        out, "-loglevel", "error"], capture_output=True)
        return out if os.path.exists(out) else ""

    # ═════════════════════════════════════════════
    # CLAUDE VISION
    # ═════════════════════════════════════════════
    def _describe_image(self, path: str, mode: str = "scene") -> list:
        if not path or not os.path.exists(path):
            return []
        try:
            ext  = Path(path).suffix.lower()
            mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            if mode == "scene":
                prompt = (
                    "Analyse cette image. Donne 5 à 7 mots-clés décrivant : "
                    "lieu/décor, lumière/moment, émotion/ambiance, couleurs dominantes. "
                    "UNIQUEMENT les mots séparés par des virgules, en minuscules."
                )
            else:
                prompt = (
                    "Décris cette image avec 5 à 7 mots-clés : "
                    "lieu, ambiance, lumière, couleurs dominantes. "
                    "UNIQUEMENT les mots séparés par des virgules, en minuscules."
                )

            payload = json.dumps({
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 150,
                "messages": [{"role": "user", "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": mime, "data": b64}},
                    {"type": "text", "text": prompt}
                ]}]
            }).encode()

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={"Content-Type": "application/json",
                         "anthropic-version": "2023-06-01",
                         "x-api-key": "PLACEHOLDER"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                text = data["content"][0]["text"].strip()
                return [t.strip().lower() for t in text.split(",") if t.strip()][:7]
        except Exception:
            return []

    # ═════════════════════════════════════════════
    # PRÉPARATION CLIP
    # ═════════════════════════════════════════════
    def _prep_clip(self, clip: dict, idx: int, W: int, H: int, mute: bool = True) -> str:
        out  = os.path.join(TMP, f"seg_{idx:04d}.mp4")
        path = clip["path"]
        ext  = Path(path).suffix.lower()

        trim_start = clip.get("trim_start", 0.0)
        trim_end   = clip.get("trim_end",   clip.get("clip_duration", clip["duration"]))
        speed      = clip.get("speed", 1.0)
        seg_dur    = max(trim_end - trim_start, 0.5)

        vf_parts = [
            f"scale={W}:{H}:force_original_aspect_ratio=increase",
            f"crop={W}:{H}", "fps=30", "format=yuv420p"
        ]
        if abs(speed - 1.0) > 0.01:
            vf_parts.insert(0, f"setpts={1/speed:.4f}*PTS")
        vf = ",".join(vf_parts)

        if ext in IMAGE_EXTS:
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", path,
                   "-vf", vf, "-t", str(seg_dur), "-an"] + ENCODE + [out, "-loglevel", "error"]
        else:
            cmd = ["ffmpeg", "-y", "-ss", str(trim_start), "-i", path,
                   "-t", str(seg_dur), "-vf", vf, "-an"] + ENCODE + [out, "-loglevel", "error"]

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Clip {idx+1} : {r.stderr[-300:]}")
        return out

    # ═════════════════════════════════════════════
    # TRANSITIONS
    # ═════════════════════════════════════════════
    def _apply_transitions(self, segs: list, td: float, W: int, H: int) -> str:
        out = os.path.join(TMP, "merged.mp4")
        if len(segs) == 1:
            shutil.copy2(segs[0], out)
            return out
        try:
            return self._xfade_concat(segs, td, out)
        except Exception as e:
            self.log(f"xfade non dispo ({e}), concat simple")
            return self._simple_concat(segs, out)

    def _xfade_concat(self, segs: list, td: float, out: str) -> str:
        durations = [self._duration(s) for s in segs]
        inputs = []
        for s in segs:
            inputs += ["-i", s]
        fc = []
        for i in range(len(segs)):
            fc.append(f"[{i}:v]null[v{i}]")
        prev = "v0"
        offset = durations[0] - td
        for i in range(1, len(segs)):
            lbl = f"xf{i}" if i < len(segs)-1 else "out"
            fc.append(f"[{prev}][v{i}]xfade=transition=fadeblack:"
                      f"duration={td:.2f}:offset={max(offset,0.01):.3f}[{lbl}]")
            prev = lbl
            if i < len(segs)-1:
                offset += durations[i] - td
        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", ";".join(fc),
            "-map", "[out]"] + ENCODE + [out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-200:])
        return out

    def _simple_concat(self, segs: list, out: str) -> str:
        lst = os.path.join(TMP, "concat_list.txt")
        with open(lst, "w") as f:
            for s in segs:
                f.write(f"file '{s}'\n")
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", lst] + ENCODE + [out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Concat : {r.stderr[-200:]}")
        return out

    # ═════════════════════════════════════════════
    # AUDIO + FADEOUT + LOGO
    # ═════════════════════════════════════════════
    def _add_audio(self, video: str, audio: str, target_dur: float, out: str):
        if not audio or not os.path.isfile(audio):
            shutil.copy2(video, out)
            return
        cmd = ["ffmpeg", "-y",
               "-i", video, "-i", audio,
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-preset", "fast", "-crf", "22",
               "-profile:v", "baseline", "-level", "3.1",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-c:a", "aac", "-b:a", "192k",
               "-t", str(target_dur),   # exactement la durée audio
               out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Audio : {r.stderr[-300:]}")

    def _apply_fadeout(self, video: str, fade_dur: float, out: str):
        dur = self._duration(video)
        st  = max(0, dur - fade_dur)
        vf  = f"fade=t=out:st={st:.3f}:d={fade_dur:.3f}"
        af  = f"afade=t=out:st={st:.3f}:d={fade_dur:.3f}"
        cmd = ["ffmpeg", "-y", "-i", video, "-vf", vf, "-af", af,
               "-c:v", "libx264", "-preset", "fast", "-crf", "22",
               "-profile:v", "baseline", "-level", "3.1",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-c:a", "aac", "-b:a", "192k", out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            shutil.copy2(video, out)

    def _add_logo(self, video: str, logo_cfg: dict, out: str, W: int, H: int):
        lp      = logo_cfg["path"]
        opacity = logo_cfg["opacity"]
        lw      = int(W * logo_cfg["size_pct"] / 100)
        margin  = 30
        pos_map = {
            "Haut gauche": f"{margin}:{margin}",
            "Haut droite": f"W-w-{margin}:{margin}",
            "Bas gauche":  f"{margin}:H-h-{margin}",
            "Bas droite":  f"W-w-{margin}:H-h-{margin}",
            "Centre":      "(W-w)/2:(H-h)/2",
        }
        pos = pos_map.get(logo_cfg["position"], f"W-w-{margin}:H-h-{margin}")
        vf  = (f"[1:v]scale={lw}:-1,format=rgba,"
               f"colorchannelmixer=aa={opacity:.3f}[logo];"
               f"[0:v][logo]overlay={pos}:format=auto")
        cmd = ["ffmpeg", "-y", "-i", video, "-i", lp,
               "-filter_complex", vf,
               "-c:v", "libx264", "-preset", "fast", "-crf", "20",
               "-profile:v", "baseline", "-level", "3.1",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart",
               "-c:a", "aac", "-b:a", "192k",
               out, "-loglevel", "error"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Logo : {r.stderr[-300:]}")

    # ═════════════════════════════════════════════
    # UTILITAIRES
    # ═════════════════════════════════════════════
    def _duration(self, path: str) -> float:
        cmd = ["ffprobe", "-v", "error", "-show_entries",
               "format=duration", "-of", "json", path]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return float(json.loads(r.stdout)["format"]["duration"])
        except Exception:
            return 5.0

    def _load_cache(self) -> dict:
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cache(self):
        try:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
