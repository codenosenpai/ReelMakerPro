"""
main.py — ReelMaker Pro v4
UI premium, reprise intelligente, mises à jour GitHub
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import subprocess
import tempfile
import webbrowser
from pathlib import Path
from PIL import Image

from engine import Engine
from auto_mode import AutoMode
from updater import check_update, CURRENT_VERSION

ctk.set_appearance_mode("dark")

# ── Palette raffinée ──────────────────────────────
BG      = "#08080E"
CARD    = "#0F0F18"
CARD2   = "#13131E"
INPUT   = "#0B0B14"
BORDER  = "#1A1A2E"
ACCENT  = "#6366F1"   # indigo vif
ACCENT2 = "#818CF8"
ACCENT3 = "#4F46E5"
WHITE   = "#F1F0F7"
MUTED   = "#4B4B6B"
MUTED2  = "#6B6B8B"
GREEN   = "#10B981"
RED     = "#EF4444"
ORANGE  = "#F59E0B"
PURPLE  = "#8B5CF6"
TEAL    = "#14B8A6"
DARK2   = "#0A0A15"

THUMB_W, THUMB_H = 78, 139
FMT_MAP = {
    "9:16 Reels": (1080, 1920),
    "16:9 YouTube": (1920, 1080),
    "1:1 Carré": (1080, 1080),
}


# ═══════════════════════════════════════════════════
# Popup mise à jour
# ═══════════════════════════════════════════════════
class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, parent, info: dict):
        super().__init__(parent)
        self.title("Mise à jour disponible")
        self.geometry("480x300")
        self.resizable(False, False)
        self.configure(fg_color=CARD)
        self.grab_set()
        self.lift()

        # Icône
        ctk.CTkLabel(self, text="⬆",
                     font=ctk.CTkFont(size=48),
                     text_color=ACCENT).pack(pady=(28, 4))

        ctk.CTkLabel(self, text=f"ReelMaker Pro  {info['version']}  est disponible !",
                     font=ctk.CTkFont("Georgia", 15, "bold"),
                     text_color=WHITE).pack()

        ctk.CTkLabel(self, text=f"Version actuelle : {CURRENT_VERSION}",
                     font=ctk.CTkFont(size=11), text_color=MUTED).pack(pady=2)

        # Changelog
        changelog = info.get("changelog", "")
        if changelog:
            box = ctk.CTkFrame(self, fg_color=INPUT, corner_radius=8)
            box.pack(fill="x", padx=28, pady=12)
            ctk.CTkLabel(box, text=changelog,
                         font=ctk.CTkFont(size=11), text_color=MUTED2,
                         wraplength=400).pack(padx=14, pady=10)

        # Boutons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 20))

        ctk.CTkButton(btns, text="⬇  Télécharger la mise à jour",
                      command=lambda: webbrowser.open(info.get("download_url", "")),
                      fg_color=ACCENT, hover_color=ACCENT3,
                      height=40, width=220,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      corner_radius=10).pack(side="left", padx=6)

        ctk.CTkButton(btns, text="Plus tard",
                      command=self.destroy,
                      fg_color=INPUT, hover_color=BORDER,
                      text_color=MUTED2, height=40, width=100,
                      font=ctk.CTkFont(size=12), corner_radius=10).pack(side="left", padx=6)


# ═══════════════════════════════════════════════════
# Carte clip
# ═══════════════════════════════════════════════════
class ClipCard(ctk.CTkFrame):
    def __init__(self, master, idx, prop, **kw):
        super().__init__(master, fg_color=CARD2, corner_radius=12, **kw)
        self.idx  = idx
        self.prop = prop
        dur       = prop.get("clip_duration", prop.get("duration", 4.0))
        self.clip_var  = tk.StringVar(value=prop.get("proposed_clip", ""))
        self.trim_s    = tk.DoubleVar(value=0.0)
        self.trim_e    = tk.DoubleVar(value=dur)
        self.speed_var = tk.DoubleVar(value=1.0)
        self._dur      = dur
        self._build()
        self._load_thumb()

    def _build(self):
        # Bande colorée en haut (pas côté)
        top_bar = ctk.CTkFrame(self, height=3, fg_color=ACCENT, corner_radius=0)
        top_bar.pack(fill="x")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=8)

        # Header
        hdr = ctk.CTkFrame(body, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 6))

        badge = ctk.CTkFrame(hdr, fg_color=ACCENT3, corner_radius=6,
                             width=32, height=22)
        badge.pack(side="left")
        badge.pack_propagate(False)
        ctk.CTkLabel(badge, text=f"{self.idx+1:02d}",
                     font=ctk.CTkFont("Courier New", 10, "bold"),
                     text_color=WHITE).pack(expand=True)

        ctk.CTkLabel(hdr, text=f"  {self._dur:.1f}s",
                     font=ctk.CTkFont("Courier New", 10),
                     text_color=ORANGE).pack(side="left")

        tags = self.prop.get("scene_tags", [])
        if tags:
            ctk.CTkLabel(hdr, text="  " + " · ".join(tags[:2]),
                         font=ctk.CTkFont(size=9),
                         text_color=PURPLE).pack(side="left")

        # Corps : miniature + contrôles
        mid = ctk.CTkFrame(body, fg_color="transparent")
        mid.pack(fill="x")

        # Miniature
        self.thumb = ctk.CTkLabel(mid, text="⏳",
                                   width=THUMB_W, height=THUMB_H,
                                   fg_color=INPUT, corner_radius=8,
                                   font=ctk.CTkFont(size=18))
        self.thumb.pack(side="left", padx=(0, 10))

        ctrl = ctk.CTkFrame(mid, fg_color="transparent")
        ctrl.pack(side="left", fill="both", expand=True)

        # Nom
        self.name_lbl = ctk.CTkLabel(ctrl, text=self._clip_name(),
                                      font=ctk.CTkFont(size=10),
                                      text_color=WHITE, anchor="w",
                                      wraplength=160)
        self.name_lbl.pack(fill="x", pady=(0, 6))

        # Boutons
        row = ctk.CTkFrame(ctrl, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        for txt, cmd, fc, tc, brd in [
            ("Changer", self._change, INPUT, WHITE, BORDER),
            ("URL", self._from_url, INPUT, ACCENT2, ACCENT),
            ("▶", self._preview, ACCENT3, WHITE, None),
        ]:
            b = ctk.CTkButton(row, text=txt,
                              width=62 if txt == "Changer" else (42 if txt == "URL" else 28),
                              height=24,
                              fg_color=fc, hover_color=BORDER,
                              text_color=tc,
                              border_color=brd or fc,
                              border_width=1 if brd else 0,
                              font=ctk.CTkFont(size=9),
                              corner_radius=6,
                              command=cmd)
            b.pack(side="left", padx=(0, 3))

        # Tags clip
        ct = self.prop.get("clip_tags", [])
        if ct:
            ctk.CTkLabel(ctrl, text="📁 " + " · ".join(ct[:2]),
                         font=ctk.CTkFont(size=9),
                         text_color=TEAL, anchor="w").pack(fill="x", pady=(0, 6))

        # Rognage compact
        trim_box = ctk.CTkFrame(ctrl, fg_color=INPUT, corner_radius=8)
        trim_box.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(trim_box, text="ROGNER",
                     font=ctk.CTkFont("Courier New", 8, "bold"),
                     text_color=MUTED).pack(anchor="w", padx=8, pady=(4, 0))
        for lbl, var, color, fr, to in [
            ("◀", self.trim_s, ACCENT2, 0.0, max(self._dur - 0.5, 0.5)),
            ("▶", self.trim_e, ORANGE, 0.5, self._dur),
        ]:
            r = ctk.CTkFrame(trim_box, fg_color="transparent")
            r.pack(fill="x", padx=8, pady=1)
            ctk.CTkLabel(r, text=lbl, font=ctk.CTkFont(size=10),
                         text_color=color, width=14).pack(side="left")
            l = ctk.CTkLabel(r, text=f"{var.get():.1f}s",
                             font=ctk.CTkFont("Courier New", 8),
                             text_color=color, width=30)
            l.pack(side="right")
            ctk.CTkSlider(r, from_=fr, to=to, variable=var,
                          button_color=color, progress_color=color,
                          fg_color=BORDER, height=10,
                          command=lambda v, _l=l: _l.configure(text=f"{v:.1f}s")
                          ).pack(side="left", fill="x", expand=True, padx=4)

        # Vitesse
        spd_box = ctk.CTkFrame(ctrl, fg_color=INPUT, corner_radius=8)
        spd_box.pack(fill="x")
        spd_row = ctk.CTkFrame(spd_box, fg_color="transparent")
        spd_row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(spd_row, text="⚡",
                     font=ctk.CTkFont(size=10), text_color=ORANGE).pack(side="left")
        self.spd_l = ctk.CTkLabel(spd_row, text="1.00×",
                                   font=ctk.CTkFont("Courier New", 8),
                                   text_color=ORANGE, width=34)
        self.spd_l.pack(side="right")
        ctk.CTkSlider(spd_row, from_=0.25, to=2.0, variable=self.speed_var,
                      button_color=ORANGE, progress_color=ORANGE,
                      fg_color=BORDER, height=10,
                      command=lambda v: self.spd_l.configure(text=f"{v:.2f}×")
                      ).pack(side="left", fill="x", expand=True, padx=4)

    def _clip_name(self):
        p = self.clip_var.get()
        return os.path.basename(p) if p else "— aucun clip —"

    def _load_thumb(self):
        p = self.clip_var.get()
        if p and os.path.exists(p):
            threading.Thread(target=self._extract_thumb, args=(p,), daemon=True).start()

    def _extract_thumb(self, path):
        ext = Path(path).suffix.lower()
        try:
            if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
                img = Image.open(path)
            else:
                tmp = os.path.join(tempfile.gettempdir(), f"th_{abs(hash(path))}.jpg")
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", "0.5", "-i", path,
                     "-frames:v", "1", "-q:v", "3",
                     "-vf", f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=increase,crop={THUMB_W}:{THUMB_H}",
                     tmp, "-loglevel", "error"],
                    capture_output=True)
                if not os.path.exists(tmp):
                    return
                img = Image.open(tmp)
            img   = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
            photo = ctk.CTkImage(img, size=(THUMB_W, THUMB_H))
            self.thumb.after(0, lambda: self.thumb.configure(image=photo, text=""))
            self._photo = photo
        except Exception:
            pass

    def _change(self):
        p = filedialog.askopenfilename(
            filetypes=[("Médias", "*.mp4 *.mov *.avi *.mkv *.jpg *.jpeg *.png *.webm")])
        if p:
            self._set(p)

    def _from_url(self):
        dlg = ctk.CTkInputDialog(text="URL (YouTube, Instagram…) :", title="Télécharger")
        url = dlg.get_input()
        if not url:
            return
        self.name_lbl.configure(text="⬇ Téléchargement…", text_color=ORANGE)
        threading.Thread(target=self._dl, args=(url,), daemon=True).start()

    def _dl(self, url):
        try:
            out = os.path.join(tempfile.gettempdir(), f"cl_{abs(hash(url))}.mp4")
            r = subprocess.run(
                ["python", "-m", "yt_dlp", "-f", "mp4/best[ext=mp4]/best",
                 "--merge-output-format", "mp4", "--no-playlist", "-o", out, url],
                capture_output=True, text=True, timeout=300)
            if r.returncode == 0 and os.path.exists(out):
                self.after(0, lambda: self._set(out))
            else:
                self.after(0, lambda: self.name_lbl.configure(
                    text="⚠ Échec", text_color=RED))
        except Exception as e:
            self.after(0, lambda: self.name_lbl.configure(
                text=f"⚠ {str(e)[:30]}", text_color=RED))

    def _set(self, path):
        self.clip_var.set(path)
        self.name_lbl.configure(text=os.path.basename(path), text_color=WHITE)
        self._load_thumb()

    def _preview(self):
        p = self.clip_var.get()
        if p and os.path.exists(p):
            os.startfile(p)

    def get_config(self):
        return {
            "path": self.clip_var.get(),
            "trim_start": self.trim_s.get(),
            "trim_end": self.trim_e.get(),
            "speed": self.speed_var.get(),
            "clip_duration": self._dur,
            "duration": self.prop.get("duration", 4.0),
            "type": self.prop.get("type", "video"),
        }


# ═══════════════════════════════════════════════════
# Application principale
# ═══════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"ReelMaker Pro  {CURRENT_VERSION}")
        self.geometry("1400x960")
        self.minsize(1100, 720)
        self.configure(fg_color=BG)

        # Variables
        self.source_var   = tk.StringVar()
        self.library_var  = tk.StringVar()
        self.output_var   = tk.StringVar(value=str(Path.home() / "Desktop" / "reel.mp4"))
        self.logo_path    = tk.StringVar()
        self.logo_pos     = tk.StringVar(value="Bas droite")
        self.logo_opacity = tk.DoubleVar(value=0.8)
        self.logo_size    = tk.IntVar(value=15)
        self.trans_dur    = tk.DoubleVar(value=0.4)
        self.fade_dur     = tk.DoubleVar(value=3.0)
        self.fmt_var      = tk.StringVar(value="9:16 Reels")
        self.mute_clips   = tk.BooleanVar(value=True)  # True = couper le son des clips

        self.auto_count   = tk.StringVar(value="0 vidéo(s) générée(s)")
        self._auto        = None

        self.clip_cards   = []
        self.engine       = None

        self.auto_sources = tk.StringVar()
        self.auto_output  = tk.StringVar(value=str(Path.home() / "Desktop" / "ReelAuto"))
        self.auto_nb      = tk.IntVar(value=5)
        self._build()
        self._check_updates()

    # ─────────────────────────────────────────────
    # Vérification mises à jour
    # ─────────────────────────────────────────────
    def _check_updates(self):
        def on_update(info):
            self.after(500, lambda: UpdateDialog(self, info))
        check_update(on_update)

    # ─────────────────────────────────────────────
    # Construction UI
    # ─────────────────────────────────────────────
    def _build(self):
        self._header()
        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=12, pady=(8, 12))
        left = ctk.CTkScrollableFrame(body, fg_color=CARD, corner_radius=16,
                                       label_text="", width=275)
        left.pack(side="left", fill="y", padx=(0, 10))
        self._left(left)
        center = ctk.CTkFrame(body, fg_color=BG)
        center.pack(side="left", fill="both", expand=True)
        self._center(center)

    def _header(self):
        hdr = ctk.CTkFrame(self, fg_color=CARD, height=58, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Logo / titre
        title_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frame.pack(side="left", padx=22, pady=10)

        ctk.CTkFrame(title_frame, width=4, height=30,
                     fg_color=ACCENT, corner_radius=2).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(title_frame, text="ReelMaker Pro",
                     font=ctk.CTkFont("Georgia", 18, "bold"),
                     text_color=WHITE).pack(side="left")
        ctk.CTkLabel(title_frame, text=f"  v{CURRENT_VERSION}",
                     font=ctk.CTkFont(size=10), text_color=MUTED).pack(side="left")

        # Status
        self.status_dot = ctk.CTkLabel(hdr, text="●",
                                        font=ctk.CTkFont(size=10), text_color=MUTED)
        self.status_dot.pack(side="right", padx=(0, 6))
        self.status_lbl = ctk.CTkLabel(hdr, text="Prêt",
                                        font=ctk.CTkFont(size=11), text_color=MUTED)
        self.status_lbl.pack(side="right", padx=(22, 0))

        # Ligne accent
        ctk.CTkFrame(self, height=1, fg_color=ACCENT3).pack(fill="x")

    # ─── PANNEAU GAUCHE ──────────────────────────
    def _left(self, col):
        self._sec(col, "SOURCE")
        ctk.CTkEntry(col, textvariable=self.source_var,
                     placeholder_text="URL Instagram / YouTube…",
                     fg_color=INPUT, border_color=BORDER,
                     text_color=WHITE, height=36,
                     font=ctk.CTkFont(size=11)
                     ).pack(fill="x", padx=12, pady=(0, 6))
        self._btn(col, "📁  Fichier local", self._pick_source)
        self.src_lbl = ctk.CTkLabel(col, text="", font=ctk.CTkFont(size=9),
                                     text_color=MUTED, wraplength=245, anchor="w")
        self.src_lbl.pack(fill="x", padx=12, pady=(0, 2))

        self._div(col)
        self._sec(col, "BIBLIOTHÈQUE")
        self.lib_lbl = ctk.CTkLabel(col, text="Aucun dossier",
                                     font=ctk.CTkFont(size=9), text_color=MUTED,
                                     wraplength=245, anchor="w")
        self.lib_lbl.pack(fill="x", padx=12, pady=(0, 4))
        self._btn(col, "📂  Choisir la bibliothèque", self._pick_lib)

        self._div(col)
        self._sec(col, "TRANSITIONS")
        self._srow(col, "Fondu entre clips", self.trans_dur, 0.1, 1.5, ACCENT2, "s")
        self._srow(col, "Fondu de sortie", self.fade_dur, 0.5, 5.0, ORANGE, "s")

        # Switch son des clips
        sw_frame = ctk.CTkFrame(col, fg_color=INPUT, corner_radius=8)
        sw_frame.pack(fill="x", padx=12, pady=(0,10))
        ctk.CTkSwitch(sw_frame, text="Couper le son des clips de fond",
                      variable=self.mute_clips,
                      font=ctk.CTkFont(size=11), text_color=WHITE,
                      button_color=ACCENT, button_hover_color=ACCENT2,
                      progress_color=ACCENT3
                      ).pack(padx=14, pady=10, anchor="w")

        self._div(col)
        self._sec(col, "LOGO")
        self.logo_lbl = ctk.CTkLabel(col, text="Aucun logo",
                                      font=ctk.CTkFont(size=9), text_color=MUTED,
                                      wraplength=245, anchor="w")
        self.logo_lbl.pack(fill="x", padx=12, pady=(0, 4))
        self._btn(col, "🖼  Logo PNG", self._pick_logo)
        ctk.CTkOptionMenu(col, variable=self.logo_pos,
                          values=["Haut gauche", "Haut droite",
                                  "Bas gauche", "Bas droite", "Centre"],
                          fg_color=INPUT, button_color=ACCENT3,
                          button_hover_color=ACCENT, dropdown_fg_color=CARD2,
                          text_color=WHITE, font=ctk.CTkFont(size=11)
                          ).pack(fill="x", padx=12, pady=(0, 6))
        self._srow(col, "Transparence", self.logo_opacity, 0.05, 1.0, ACCENT2, "%", pct=True)
        self._srow(col, "Taille", self.logo_size, 5, 40, ACCENT2, "%", iv=True)

        self._div(col)
        self._sec(col, "FORMAT")
        fmt_row = ctk.CTkFrame(col, fg_color=INPUT, corner_radius=8)
        fmt_row.pack(fill="x", padx=12, pady=(0, 10))
        for label in FMT_MAP:
            ctk.CTkRadioButton(fmt_row, text=label, variable=self.fmt_var, value=label,
                               font=ctk.CTkFont(size=11), text_color=WHITE,
                               fg_color=ACCENT, hover_color=ACCENT2
                               ).pack(anchor="w", padx=12, pady=4)

        self._sec(col, "SORTIE")
        ctk.CTkEntry(col, textvariable=self.output_var,
                     fg_color=INPUT, border_color=BORDER,
                     text_color=WHITE, height=30, font=ctk.CTkFont(size=9)
                     ).pack(fill="x", padx=12, pady=(0, 4))
        self._btn(col, "💾  Choisir emplacement", self._pick_output)

        self._div(col)

        self.btn_analyze = ctk.CTkButton(col, text="▶  Analyser la vidéo",
                                          command=self._run_analyze,
                                          fg_color=ACCENT, hover_color=ACCENT3,
                                          height=44, corner_radius=12,
                                          font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_analyze.pack(fill="x", padx=12, pady=(0, 8))

        self.btn_render = ctk.CTkButton(col, text="🎬  Monter la vidéo",
                                         command=self._run_render,
                                         fg_color=GREEN, hover_color="#059669",
                                         text_color=BG, height=42, corner_radius=12,
                                         font=ctk.CTkFont(size=13, weight="bold"),
                                         state="disabled")
        self.btn_render.pack(fill="x", padx=12, pady=(0, 14))

    # ─── CENTRE ──────────────────────────────────
    def _center(self, parent):
        tabs = ctk.CTkTabview(parent, fg_color=CARD, corner_radius=16,
                              segmented_button_fg_color=INPUT,
                              segmented_button_selected_color=ACCENT3,
                              segmented_button_selected_hover_color=ACCENT,
                              segmented_button_unselected_color=INPUT,
                              text_color=WHITE,
                              text_color_disabled=MUTED)
        tabs.pack(fill="both", expand=True)
        tabs.add("  Manuel  ")
        tabs.add("  🤖 Auto  ")
        self._tab_manual(tabs.tab("  Manuel  "))
        self._tab_auto(tabs.tab("  🤖 Auto  "))

    def _tab_manual(self, tab):
        # Progression
        prog_card = ctk.CTkFrame(tab, fg_color=CARD2, corner_radius=12)
        prog_card.pack(fill="x", padx=10, pady=(10, 8))

        prog_inner = ctk.CTkFrame(prog_card, fg_color="transparent")
        prog_inner.pack(fill="x", padx=16, pady=12)

        top_row = ctk.CTkFrame(prog_inner, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(top_row, text="PROGRESSION",
                     font=ctk.CTkFont("Courier New", 10, "bold"),
                     text_color=ACCENT).pack(side="left")
        self.prog_lbl = ctk.CTkLabel(top_row, text="En attente…",
                                      font=ctk.CTkFont(size=10), text_color=MUTED)
        self.prog_lbl.pack(side="right")

        self.prog = ctk.CTkProgressBar(prog_inner, fg_color=INPUT,
                                        progress_color=ACCENT, height=6,
                                        corner_radius=3)
        self.prog.pack(fill="x", pady=(0, 8))
        self.prog.set(0)

        self.log_box = ctk.CTkTextbox(prog_inner, fg_color=INPUT,
                                       text_color=MUTED2,
                                       font=ctk.CTkFont("Courier New", 10),
                                       border_width=0, height=65, corner_radius=8)
        self.log_box.pack(fill="x")
        self.log_box.configure(state="disabled")

        # Timeline header
        tl_hdr = ctk.CTkFrame(tab, fg_color="transparent")
        tl_hdr.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(tl_hdr, text="TIMELINE",
                     font=ctk.CTkFont("Courier New", 10, "bold"),
                     text_color=ACCENT).pack(side="left")
        self.count_lbl = ctk.CTkLabel(tl_hdr, text="",
                                       font=ctk.CTkFont(size=10), text_color=MUTED)
        self.count_lbl.pack(side="left", padx=8)

        # Timeline scrollable
        self.timeline = ctk.CTkScrollableFrame(tab, fg_color=DARK2,
                                                corner_radius=12, label_text="")
        self.timeline.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.timeline.columnconfigure(0, weight=1)
        self.timeline.columnconfigure(1, weight=1)

    def _tab_auto(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent", label_text="")
        scroll.pack(fill="both", expand=True, padx=12, pady=8)

        # Dossier sources
        self._sec(scroll, "DOSSIER SOURCES")
        self._lbl(scroll, "Dossier contenant tes vidéos sources (audio)")
        ctk.CTkEntry(scroll, textvariable=self.auto_sources,
                     placeholder_text="C:\\...",
                     fg_color=INPUT, border_color=BORDER,
                     text_color=WHITE, height=34, font=ctk.CTkFont(size=11)
                     ).pack(fill="x", pady=(0, 6))
        ctk.CTkButton(scroll, text="📂  Choisir le dossier sources",
                      command=self._pick_auto_sources,
                      fg_color=INPUT, hover_color=BORDER,
                      text_color=WHITE, border_color=BORDER, border_width=1,
                      height=30, font=ctk.CTkFont(size=11), corner_radius=8
                      ).pack(fill="x", pady=(0, 12))

        # Nombre de vidéos
        self._sec(scroll, "NOMBRE DE VIDÉOS")
        nb_card = ctk.CTkFrame(scroll, fg_color=CARD2, corner_radius=12)
        nb_card.pack(fill="x", pady=(0, 12))
        nb_inner = ctk.CTkFrame(nb_card, fg_color="transparent")
        nb_inner.pack(fill="x", padx=14, pady=12)
        self.nb_lbl = ctk.CTkLabel(nb_inner, text="5",
                                    font=ctk.CTkFont("Courier New", 36, "bold"),
                                    text_color=ACCENT)
        self.nb_lbl.pack(side="left")
        ctk.CTkLabel(nb_inner, text=" vidéos",
                     font=ctk.CTkFont("Georgia", 14),
                     text_color=MUTED).pack(side="left", pady=10)
        ctk.CTkSlider(nb_inner, from_=1, to=100, variable=self.auto_nb,
                      button_color=ACCENT, button_hover_color=ACCENT2,
                      progress_color=ACCENT3, fg_color=BORDER,
                      command=lambda v: self.nb_lbl.configure(text=str(int(v)))
                      ).pack(side="left", fill="x", expand=True, padx=(24, 0))

        # Dossier sortie
        self._sec(scroll, "DOSSIER DE SORTIE")
        self._lbl(scroll, "Vidéos nommées 001.mp4, 002.mp4… (reprise automatique si existantes)")
        ctk.CTkEntry(scroll, textvariable=self.auto_output,
                     fg_color=INPUT, border_color=BORDER,
                     text_color=WHITE, height=34, font=ctk.CTkFont(size=11)
                     ).pack(fill="x", pady=(0, 6))
        ctk.CTkButton(scroll, text="📂  Choisir le dossier",
                      command=self._pick_auto_out,
                      fg_color=INPUT, hover_color=BORDER,
                      text_color=WHITE, border_color=BORDER, border_width=1,
                      height=32, font=ctk.CTkFont(size=11), corner_radius=8
                      ).pack(fill="x", pady=(0, 12))

        # Info box
        info = ctk.CTkFrame(scroll, fg_color=CARD2, corner_radius=12)
        info.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(info, text=(
            "ℹ️  Fonctionnement\n\n"
            "• Prend chaque vidéo du dossier sources comme audio\n"
            "• Choisit des clips depuis ta bibliothèque locale\n"
            "• Variété garantie : jamais le même clip deux fois\n"
            "• Rotation automatique si bibliothèque épuisée\n"
            "• Reprise intelligente : si 003.mp4 existe, repart de 004.mp4"
        ), font=ctk.CTkFont(size=11), text_color=MUTED2,
           justify="left").pack(padx=16, pady=14, anchor="w")

        # Compteur + log
        ctk.CTkLabel(scroll, textvariable=self.auto_count,
                     font=ctk.CTkFont("Courier New", 16, "bold"),
                     text_color=GREEN).pack(pady=(0, 8))

        self._sec(scroll, "JOURNAL")
        self.auto_log = ctk.CTkTextbox(scroll, fg_color=CARD2,
                                        text_color=MUTED2,
                                        font=ctk.CTkFont("Courier New", 10),
                                        border_width=0, corner_radius=10,
                                        height=200)
        self.auto_log.pack(fill="x", pady=(0, 12))
        self.auto_log.configure(state="disabled")

        # Boutons
        br = ctk.CTkFrame(scroll, fg_color="transparent")
        br.pack(fill="x", pady=(0, 8))
        br.columnconfigure(0, weight=3)
        br.columnconfigure(1, weight=1)

        self.btn_auto = ctk.CTkButton(br, text="▶  Générer automatiquement",
                                       command=self._start_auto,
                                       fg_color=ACCENT, hover_color=ACCENT3,
                                       height=48, corner_radius=12,
                                       font=ctk.CTkFont(size=14, weight="bold"))
        self.btn_auto.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.btn_stop = ctk.CTkButton(br, text="⏹",
                                       command=self._stop_auto,
                                       fg_color=INPUT, hover_color=RED,
                                       text_color=RED, border_color=RED,
                                       border_width=1,
                                       height=48, corner_radius=12,
                                       font=ctk.CTkFont(size=18),
                                       state="disabled")
        self.btn_stop.grid(row=0, column=1, sticky="ew")

    # ─────────────────────────────────────────────
    # UI helpers
    # ─────────────────────────────────────────────
    def _sec(self, p, t):
        f = ctk.CTkFrame(p, fg_color="transparent")
        f.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(f, text=t,
                     font=ctk.CTkFont("Courier New", 10, "bold"),
                     text_color=ACCENT).pack(side="left")
        ctk.CTkFrame(f, height=1, fg_color=BORDER).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=1)

    def _lbl(self, p, t):
        ctk.CTkLabel(p, text=t, font=ctk.CTkFont(size=10),
                     text_color=MUTED).pack(anchor="w", padx=12, pady=(0, 2))

    def _btn(self, p, t, cmd):
        ctk.CTkButton(p, text=t, command=cmd,
                      fg_color=INPUT, hover_color=BORDER,
                      text_color=WHITE, border_color=BORDER, border_width=1,
                      height=30, font=ctk.CTkFont(size=10), corner_radius=8
                      ).pack(fill="x", padx=12, pady=(0, 6))

    def _div(self, p):
        ctk.CTkFrame(p, height=1, fg_color=BORDER).pack(fill="x", padx=12, pady=8)

    def _srow(self, p, label, var, mn, mx, color, suf, pct=False, iv=False):
        self._lbl(p, label)
        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 8))
        v0  = var.get()
        txt = f"{int(v0*100)}{suf}" if pct else (f"{int(v0)}{suf}" if iv else f"{v0:.1f}{suf}")
        lbl = ctk.CTkLabel(row, text=txt,
                           font=ctk.CTkFont("Courier New", 10),
                           text_color=color, width=40)
        lbl.pack(side="right")
        def upd(v, _l=lbl, _p=pct, _i=iv, _s=suf):
            _l.configure(text=f"{int(float(v)*100)}{_s}" if _p else
                         (f"{int(float(v))}{_s}" if _i else f"{float(v):.1f}{_s}"))
        ctk.CTkSlider(row, from_=mn, to=mx, variable=var,
                      button_color=color, button_hover_color=color,
                      progress_color=color, fg_color=INPUT,
                      command=upd).pack(side="left", fill="x", expand=True)

    def _pick_source(self):
        p = filedialog.askopenfilename(
            filetypes=[("Vidéo", "*.mp4 *.mov *.avi *.mkv *.webm")])
        if p:
            self.source_var.set(p)
            self.src_lbl.configure(text=os.path.basename(p), text_color=WHITE)

    def _pick_lib(self):
        d = filedialog.askdirectory()
        if d:
            self.library_var.set(d)
            self.lib_lbl.configure(text=d, text_color=WHITE)

    def _pick_logo(self):
        p = filedialog.askopenfilename(filetypes=[("Image", "*.png *.jpg *.jpeg")])
        if p:
            self.logo_path.set(p)
            self.logo_lbl.configure(text=os.path.basename(p), text_color=WHITE)

    def _pick_output(self):
        p = filedialog.asksaveasfilename(defaultextension=".mp4",
                                          filetypes=[("MP4", "*.mp4")])
        if p:
            self.output_var.set(p)

    def _pick_auto_sources(self):
        d = filedialog.askdirectory()
        if d:
            self.auto_sources.set(d)

    def _pick_auto_out(self):
        d = filedialog.askdirectory()
        if d:
            self.auto_output.set(d)

    # ─────────────────────────────────────────────
    # Log / Status
    # ─────────────────────────────────────────────
    def _wlog(self, box, msg):
        box.configure(state="normal")
        box.insert("end", f"› {msg}\n")
        box.see("end")
        box.configure(state="disabled")

    def log(self, m):   self._wlog(self.log_box, m)
    def alog(self, m):  self._wlog(self.auto_log, m)
    def _sl(self, m):   self.after(0, lambda: self.log(m))
    def _sp(self, v):   self.after(0, lambda: self.prog.set(v))
    def _slbl(self, t): self.after(0, lambda: self.prog_lbl.configure(text=t))
    def _asl(self, m):  self.after(0, lambda: self.alog(m))

    def _status(self, msg, color=None):
        c = color or MUTED
        self.after(0, lambda: (
            self.status_lbl.configure(text=msg, text_color=c),
            self.status_dot.configure(text_color=c)
        ))

    # ─────────────────────────────────────────────
    # Mode Manuel
    # ─────────────────────────────────────────────
    def _run_analyze(self):
        src = self.source_var.get().strip()
        lib = self.library_var.get().strip()
        if not src:
            messagebox.showwarning("Manque", "Source vidéo manquante.")
            return
        self.btn_analyze.configure(state="disabled")
        self.btn_render.configure(state="disabled")
        self.prog.set(0)
        self._status("Analyse en cours…", ORANGE)
        self.engine = Engine(log_fn=self._sl, progress_fn=self._sp, step_fn=self._slbl)
        threading.Thread(target=self._analyze_t, args=(src, lib), daemon=True).start()

    def _analyze_t(self, src, lib):
        try:
            proposals = self.engine.analyze(src, lib or src)
            self.after(0, lambda: self._populate(proposals))
            self.after(0, lambda: self.btn_render.configure(state="normal"))
            self.after(0, lambda: self.btn_analyze.configure(state="normal"))
            self._status("Analyse terminée ✓", GREEN)
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self._err(msg))

    def _populate(self, proposals):
        for w in self.timeline.winfo_children():
            w.destroy()
        self.clip_cards.clear()
        for i, p in enumerate(proposals):
            card = ClipCard(self.timeline, i, p)
            card.grid(row=i//2, column=i%2, padx=6, pady=6, sticky="ew")
            self.clip_cards.append(card)
        self.count_lbl.configure(text=f"{len(proposals)} scène(s)")

    def _run_render(self):
        if not self.clip_cards:
            messagebox.showwarning("Manque", "Lance d'abord l'analyse.")
            return
        clips   = [c.get_config() for c in self.clip_cards]
        missing = [i+1 for i, c in enumerate(clips) if not c["path"]]
        if missing:
            messagebox.showwarning("Clips manquants", f"Scènes sans clip : {missing}")
            return
        w, h = FMT_MAP.get(self.fmt_var.get(), (1080, 1920))
        logo  = ({"path": self.logo_path.get(), "position": self.logo_pos.get(),
                  "opacity": self.logo_opacity.get(), "size_pct": self.logo_size.get()}
                 if self.logo_path.get() and os.path.isfile(self.logo_path.get()) else None)
        cfg = {"clips": clips, "logo": logo, "output": self.output_var.get(),
               "transition_dur": self.trans_dur.get(),
               "fadeout_dur": self.fade_dur.get(), "out_w": w, "out_h": h,
               "mute_clips": self.mute_clips.get()}
        self.btn_render.configure(state="disabled")
        self.btn_analyze.configure(state="disabled")
        self.prog.set(0)
        self._status("Montage en cours…", ORANGE)
        threading.Thread(target=self._render_t, args=(cfg,), daemon=True).start()

    def _render_t(self, cfg):
        try:
            self.engine.render(cfg)
            self.prog.set(1.0)
            self._status("Vidéo exportée ✓", GREEN)
            self.after(0, lambda: self.btn_render.configure(state="normal"))
            self.after(0, lambda: self.btn_analyze.configure(state="normal"))
            self.log(f"✓ {cfg['output']}")
            self.after(0, lambda: messagebox.showinfo("Terminé !", f"Vidéo :\n{cfg['output']}"))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda: self._err(msg))

    # ─────────────────────────────────────────────
    # Mode Automatique — reprise intelligente
    # ─────────────────────────────────────────────
    def _start_auto(self):
        out_folder = self.auto_output.get().strip()
        if not out_folder:
            messagebox.showwarning("Manque", "Choisis le dossier de sortie.")
            return

        # ── Reprise intelligente ──────────────────
        nb_total   = int(self.auto_nb.get())
        start_from = self._find_resume_point(out_folder, nb_total)

        if start_from > nb_total:
            messagebox.showinfo("Déjà terminé",
                                f"Les {nb_total} vidéos existent déjà dans ce dossier.")
            return

        if start_from > 1:
            ok = messagebox.askyesno(
                "Reprise détectée",
                f"Les vidéos 001 à {start_from-1:03d} existent déjà.\n"
                f"Reprendre à partir de {start_from:03d}.mp4 ?")
            if not ok:
                return

        w, h = FMT_MAP.get(self.fmt_var.get(), (1080, 1920))
        logo = ({"path": self.logo_path.get(), "position": self.logo_pos.get(),
                 "opacity": self.logo_opacity.get(), "size_pct": self.logo_size.get()}
                if self.logo_path.get() and os.path.isfile(self.logo_path.get()) else None)

        sources_folder = self.auto_sources.get().strip()
        if not sources_folder or not os.path.isdir(sources_folder):
            messagebox.showwarning("Manque", "Choisis le dossier sources.")
            return
        lib = self.library_var.get().strip()
        if not lib:
            messagebox.showwarning("Manque", "Choisis ta bibliothèque.")
            return

        cfg = {
            "sources_folder": sources_folder,
            "library_path":   lib,
            "nb_videos":      nb_total,
            "start_from":     start_from,
            "output_folder":  out_folder,
            "transition_dur": self.trans_dur.get(),
            "fadeout_dur":    self.fade_dur.get(),
            "out_w": w, "out_h": h,
            "logo_cfg": logo,
            "mute_clips": self.mute_clips.get(),
        }

        self._auto = AutoMode(log_fn=self._asl,
                              progress_fn=lambda v: None,
                              step_fn=lambda t: self._status(t, ORANGE))
        count_h = [start_from - 1]

        def on_done(num, path, total):
            count_h[0] += 1
            self.after(0, lambda: self.auto_count.set(
                f"{count_h[0]}/{nb_total} vidéo(s) générée(s)"))

        def on_error(msg):
            self.after(0, lambda: self.alog(f"⚠ {msg}"))

        def run():
            self._auto.run(cfg, on_done=on_done, on_error=on_error)
            self.after(0, lambda: self.btn_auto.configure(state="normal"))
            self.after(0, lambda: self.btn_stop.configure(state="disabled"))
            self._status("Mode auto terminé ✓", GREEN)

        self.btn_auto.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._status(f"Mode auto en cours (depuis {start_from:03d})…", ORANGE)
        self.auto_count.set(f"{count_h[0]}/{nb_total} vidéo(s) générée(s)")
        threading.Thread(target=run, daemon=True).start()

    def _find_resume_point(self, folder: str, nb: int) -> int:
        """Retourne le premier numéro manquant dans le dossier."""
        os.makedirs(folder, exist_ok=True)
        for i in range(1, nb + 1):
            path = os.path.join(folder, f"{i:03d}.mp4")
            if not os.path.isfile(path) or os.path.getsize(path) < 100_000:
                return i
        return nb + 1  # tout existe déjà

    def _stop_auto(self):
        if self._auto:
            self._auto.stop()
        self.btn_stop.configure(state="disabled")
        self._status("Arrêt en cours…", ORANGE)

    def _err(self, msg):
        self.log(f"ERREUR : {msg}")
        self._status("Erreur", RED)
        self.after(0, lambda: self.btn_analyze.configure(state="normal"))
        self.after(0, lambda: messagebox.showerror("Erreur", msg))


if __name__ == "__main__":
    app = App()
    app.mainloop()
