import ctypes
import json
import math
import sys
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox

import customtkinter as ctk

from service.catalog_service import CatalogService
from service.session_service import SessionService

try:
    from PIL import Image, ImageDraw, ImageTk

    _PIL_RESAMPLE = getattr(Image, "Resampling", Image)
    _PIL_LANCZOS = _PIL_RESAMPLE.LANCZOS
    _PIL_BILINEAR = _PIL_RESAMPLE.BILINEAR
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Exact CustomTkinter dark-mode palette for native tk containers/labels (zero canvas redraw overhead)
BG_MAIN = "#242424"
BG_HOVER = "#3B3B3B"
BG_SELECTED = "#4D4D4D"
BG_DIVIDER = "#4D4D4D"
BG_DIVIDER_HOVER = "#808080"
FG_TEXT = "#DCE4EE"
FG_DESC = "#CCCCCC"
FG_MUTED = "#999999"
FG_DIM = "#808080"

# Stopwatch button palette (B6-B10)
TIMER_PLAY_GREEN = "#7CB342"
TIMER_PLAY_GREEN_HOVER = "#8BC34A"
TIMER_PAUSE_ORANGE = "#F59E0B"
TIMER_PAUSE_ORANGE_HOVER = "#FBBF24"
TIMER_STOP_RED = "#DC2626"
TIMER_STOP_RED_HOVER = "#EF4444"
TIMER_STOP_DISABLED_BG = "#6B3A3A"
TIMER_STOP_DISABLED_ICON = "#A68282"
TIMER_RESTART_DISABLED = "#555555"

# 64-bit safe Win32 RedrawWindow binding to flush WM_PAINT synchronously during sash drags
_WIN32_REDRAW = None
_RDW_ALLCHILDREN_UPDATENOW = 0x0080 | 0x0100
if sys.platform == "win32":
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _user32.RedrawWindow.argtypes = [
        wintypes.HWND,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    _user32.RedrawWindow.restype = wintypes.BOOL
    _WIN32_REDRAW = _user32.RedrawWindow


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class GameLedgerApp(ctk.CTk):
    SETTINGS_PATH = Path("data/ui_settings.json")
    MIN_SIDEBAR_WIDTH = 185
    MIN_MAIN_WIDTH = 560
    SASH_WIDTH = 6

    def __init__(self, catalog_service: CatalogService, session_service: SessionService):
        super().__init__()
        self.service = catalog_service
        self.session_service = session_service
        self.title("GameLedger")

        self.geometry("1000x650")
        self.minsize(1000, 650)

        # Shared font objects used for both rendering and pixel-exact sidebar truncation
        self._sidebar_font = tkfont.Font(family="Segoe UI", size=10)
        self._sidebar_bold_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self._sidebar_dot_font = tkfont.Font(family="Segoe UI", size=11)

        # Load persisted sidebar width (defaults to 240px)
        self.sidebar_width = self._load_sidebar_width()
        self._last_placed_sidebar_width = self.sidebar_width
        self._is_dragging_sash = False
        self._in_sash_update = False
        self._save_width_after_update = False
        self._sash_drag_job = None
        self._pending_sidebar_width: int | None = None
        self._active_scroll_canvas: tk.Canvas | None = None
        self._details_sync_fn = None
        self._accordion_labels = []

        # Steam-style in-place hover overlay state
        self._hover_after_id = None
        self._hover_overlay = None
        self._hover_row_frame = None
        self._hover_row_selected = False
        self._hover_game_id: int | None = None

        # Stopwatch state machine & anti-aliased sprite caches (B6-B10)
        self._timer_game = None
        self._timer_state = "ready"  # "ready" | "running" | "paused" | "reset"
        self._timer_elapsed = 0.0
        self._timer_start_perf = 0.0
        self._timer_after_id = None
        self._timer_resize_job = None
        self._timer_hq_job = None
        self._timer_pending_stage: tuple[int, int] | None = None
        self._timer_masters: dict[str, "Image.Image"] = {}
        self._timer_photos: dict[str, tk.PhotoImage] = {}
        self._timer_rendered_sizes: dict[str, int] = {}
        self._timer_hovered_btn: str | None = None
        self._timer_btn_geom: dict[str, tuple[float, float, float]] = {}

        # Fetch actual database on startup
        self.backlog_games = self.service.get_backlog()
        self.selected_game_id: int | None = None

        self.catalog_results = []
        self.current_page = 0
        self.items_per_page = 3

        self.saved_search_query = ""
        self.active_filter = None

        # All libraries default to CLOSED ('>') on startup
        self.category_states = {
            "Backlog": False,
            "In Progress": False,
            "Completed": False,
            "Abandoned": False,
        }

        self.platform_colors = {
            "PlayStation 4": "#2563EB",      # Blue
            "PlayStation 5": "white",
            "Xbox Series X": "#007A33",      # Green
            "PC": "#87CEEB",                 # Sky-Blue
            "Nintendo Switch": "#E60012",    # True Red
            "Nintendo Switch 2": "#D2042D",  # Cherry Red
        }

        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Configure>", self._on_window_configure)
        self.bind_all("<MouseWheel>", self._on_details_mousewheel)

        self.build_main_hub()

    # ==========================================
    #        UI SETTINGS & RESIZE HELPERS
    # ==========================================
    def _load_sidebar_width(self) -> int:
        try:
            if self.SETTINGS_PATH.exists():
                with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    width = int(data.get("sidebar_width", 240))
                    return max(self.MIN_SIDEBAR_WIDTH, width)
        except (ValueError, OSError, json.JSONDecodeError):
            pass
        return 240

    def _save_sidebar_width(self) -> None:
        try:
            self.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(self.SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump({"sidebar_width": int(self.sidebar_width)}, f, indent=2)
        except OSError:
            pass

    def _get_max_sidebar_width(self, total_w: int | None = None) -> int:
        win_w = total_w if (total_w and total_w > 1) else max(self.winfo_width(), 1000)
        by_ratio = int(win_w * 0.45)
        by_main_min = win_w - self.MIN_MAIN_WIDTH - self.SASH_WIDTH
        return max(self.MIN_SIDEBAR_WIDTH, min(by_ratio, by_main_min))

    def _clamp_sidebar_width(self, width: int, total_w: int | None = None) -> int:
        return max(
            self.MIN_SIDEBAR_WIDTH, min(width, self._get_max_sidebar_width(total_w))
        )

    def _on_window_configure(self, event=None):
        # Ignore child widget <Configure> events so resizing stays fast
        if event is None or event.widget is not self:
            return
        self._sync_filter_overlay(event)

    def _layout_split_pane(self, event=None):
        if not (hasattr(self, "body_frame") and self.body_frame.winfo_exists()):
            return
        total_w = self.body_frame.winfo_width()
        total_h = self.body_frame.winfo_height()
        if total_w <= 1 or total_h <= 1:
            return

        w = self._clamp_sidebar_width(self.sidebar_width, total_w)
        growing = w >= self._last_placed_sidebar_width
        self.sidebar_width = w
        self._last_placed_sidebar_width = w
        main_w = max(1, total_w - w - self.SASH_WIDTH)

        # Direction-aware order ensures sidebar_frame and main_view NEVER overlap
        if growing:
            self.main_view.place(
                x=w + self.SASH_WIDTH, y=0, width=main_w, height=total_h
            )
            self.sash.place(x=w, y=0, width=self.SASH_WIDTH, height=total_h)
            self.sidebar_frame.place(x=0, y=0, width=w, height=total_h)
        else:
            self.sidebar_frame.place(x=0, y=0, width=w, height=total_h)
            self.sash.place(x=w, y=0, width=self.SASH_WIDTH, height=total_h)
            self.main_view.place(
                x=w + self.SASH_WIDTH, y=0, width=main_w, height=total_h
            )

        self._update_sidebar_truncation()

        # Sync Game Details canvas/wraplengths in the exact same frame
        if self._details_sync_fn is not None:
            self._details_sync_fn(max(100, main_w - 36))

    def _flush_win32_paint(self):
        """Forces Windows to synchronously complete pending WM_PAINTs on body_frame."""
        if (
            _WIN32_REDRAW is not None
            and hasattr(self, "body_frame")
            and self.body_frame.winfo_exists()
        ):
            _WIN32_REDRAW(
                self.body_frame.winfo_id(), None, None, _RDW_ALLCHILDREN_UPDATENOW
            )

    def _start_sash_drag(self, event):
        self._is_dragging_sash = True
        self._save_width_after_update = False
        self._cancel_hover_overlay()
        if hasattr(self, "remove_btn") and self.remove_btn.winfo_exists():
            self.remove_btn.place_forget()

    def _on_sash_drag(self, event):
        if not self._is_dragging_sash:
            return
        total_w = self.body_frame.winfo_width()
        new_width = event.x_root - self.body_frame.winfo_rootx()
        clamped = self._clamp_sidebar_width(new_width, total_w)
        if clamped == self.sidebar_width and self._pending_sidebar_width is None:
            return
        self._pending_sidebar_width = clamped
        if self._sash_drag_job is None and not self._in_sash_update:
            self._sash_drag_job = self.after(16, self._apply_sash_drag)

    def _apply_sash_drag(self):
        self._sash_drag_job = None
        if self._pending_sidebar_width is None or self._in_sash_update:
            return

        target = self._pending_sidebar_width
        self._pending_sidebar_width = None
        if target == self.sidebar_width:
            return

        self._in_sash_update = True
        try:
            self.sidebar_width = target
            self._layout_split_pane()
            # Drain <Configure> (CTkEntry/CTkButton/CTkFrame), idle layouts, and WM_PAINT
            self.update()
            self._flush_win32_paint()
        finally:
            self._in_sash_update = False

        if self._save_width_after_update:
            self._save_width_after_update = False
            if self._pending_sidebar_width is not None:
                final_w = self._pending_sidebar_width
                self._pending_sidebar_width = None
                if final_w != self.sidebar_width:
                    self.sidebar_width = final_w
                    self._layout_split_pane()
                    self.update_idletasks()
                    self._flush_win32_paint()
            self._save_sidebar_width()
        elif self._is_dragging_sash and self._pending_sidebar_width is not None:
            self._sash_drag_job = self.after(16, self._apply_sash_drag)

    def _end_sash_drag(self, event):
        if not self._is_dragging_sash:
            return
        self._is_dragging_sash = False
        if self._sash_drag_job is not None:
            self.after_cancel(self._sash_drag_job)
            self._sash_drag_job = None
        if self._in_sash_update:
            self._save_width_after_update = True
            return
        if self._pending_sidebar_width is not None:
            final_w = self._pending_sidebar_width
            self._pending_sidebar_width = None
            if final_w != self.sidebar_width:
                self.sidebar_width = final_w
                self._layout_split_pane()
                self.update_idletasks()
                self._flush_win32_paint()
        self._save_sidebar_width()

    def _on_details_mousewheel(self, event):
        canvas = self._active_scroll_canvas
        if canvas is None or not canvas.winfo_exists():
            return
        if not self._is_pointer_inside(canvas):
            return
        # Only scroll when content exceeds the visible viewport
        if canvas.yview() == (0.0, 1.0):
            return
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ==========================================
    #    STEAM-STYLE IN-PLACE HOVER (0.5s DELAY)
    # ==========================================
    def _is_pointer_inside(self, widget) -> bool:
        if widget is None or not widget.winfo_exists():
            return False
        px, py = self.winfo_pointerxy()
        wx = widget.winfo_rootx()
        wy = widget.winfo_rooty()
        ww = widget.winfo_width()
        wh = widget.winfo_height()
        return wx <= px <= wx + ww and wy <= py <= wy + wh

    def _schedule_hover_overlay(self, row_frame, game, is_selected: bool):
        self._cancel_hover_overlay()
        self._hover_game_id = game.id
        self._hover_row_frame = row_frame
        self._hover_row_selected = is_selected
        self._hover_after_id = self.after(
            500, lambda: self._show_hover_overlay(row_frame, game, is_selected)
        )

    def _cancel_hover_overlay(self):
        if self._hover_after_id is not None:
            self.after_cancel(self._hover_after_id)
            self._hover_after_id = None
        if self._hover_overlay is not None and self._hover_overlay.winfo_exists():
            self._hover_overlay.destroy()
        self._hover_overlay = None
        if (
            self._hover_row_frame is not None
            and self._hover_row_frame.winfo_exists()
            and not self._hover_row_selected
            and not self._is_pointer_inside(self._hover_row_frame)
        ):
            self._set_row_bg(self._hover_row_frame, BG_MAIN)
        self._hover_row_frame = None
        self._hover_game_id = None

    def _set_row_bg(self, frame: tk.Frame, color: str):
        if not frame.winfo_exists():
            return
        frame.configure(bg=color)
        for child in frame.winfo_children():
            child.configure(bg=color)

    def _show_hover_overlay(self, row_frame, game, is_selected: bool):
        self._hover_after_id = None
        if self._is_dragging_sash or not self._is_pointer_inside(row_frame):
            self._cancel_hover_overlay()
            return

        _, is_trunc = self._truncate_text(
            game.title, max(50, self.sidebar_width - 78)
        )
        if not is_trunc:
            return

        if self._hover_overlay is not None and self._hover_overlay.winfo_exists():
            self._hover_overlay.destroy()

        x = row_frame.winfo_rootx() - self.winfo_rootx()
        y = row_frame.winfo_rooty() - self.winfo_rooty()
        h = row_frame.winfo_height()

        row_bg = BG_SELECTED if is_selected else BG_HOVER
        row_cursor = "" if is_selected else "hand2"
        dot_color = self.platform_colors.get(game.platform, "gray")

        overlay = tk.Frame(
            self,
            bg=row_bg,
            cursor=row_cursor,
            highlightthickness=0,
            bd=0,
        )

        ov_dot = tk.Label(
            overlay,
            text="●",
            fg=dot_color,
            bg=row_bg,
            font=self._sidebar_dot_font,
            cursor=row_cursor,
        )
        ov_dot.pack(side="left", padx=(8, 6), pady=3)

        ov_lbl = tk.Label(
            overlay,
            text=game.title,
            fg=FG_TEXT,
            bg=row_bg,
            font=self._sidebar_font,
            anchor="w",
            cursor=row_cursor,
        )
        ov_lbl.pack(side="left", pady=3, padx=(0, 12))

        overlay.place(x=x, y=y, height=h)
        overlay.lift()
        self._hover_overlay = overlay

        def on_overlay_leave(e):
            self.after(20, self._check_overlay_dismiss)

        for w in (overlay, ov_dot, ov_lbl):
            w.bind("<Leave>", on_overlay_leave)
            if not is_selected:
                w.bind("<Button-1>", lambda e, g=game: self.select_game(g))

    def _check_overlay_dismiss(self):
        if self._is_pointer_inside(self._hover_overlay):
            return
        if self._is_pointer_inside(self._hover_row_frame):
            return
        self._cancel_hover_overlay()

    def _truncate_text(self, text: str, max_px: int) -> tuple[str, bool]:
        """Truncates text with '...' if it exceeds max_px. Returns (display_text, was_truncated)."""
        if self._sidebar_font.measure(text) <= max_px:
            return text, False

        ellipsis = "..."
        ellipsis_w = self._sidebar_font.measure(ellipsis)
        target = max(0, max_px - ellipsis_w)

        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._sidebar_font.measure(text[:mid]) <= target:
                lo = mid
            else:
                hi = mid - 1

        trimmed = text[:lo].rstrip()
        return (trimmed + ellipsis) if trimmed else ellipsis, True

    def _update_sidebar_truncation(self):
        """Updates truncated sidebar labels live while dragging, skipping unchanged labels."""
        max_px = max(50, self.sidebar_width - 78)
        updated_entries = []
        for lbl, full_title, last_text in getattr(self, "_sidebar_title_labels", []):
            if lbl.winfo_exists():
                display_text, _ = self._truncate_text(full_title, max_px)
                if display_text != last_text:
                    lbl.configure(text=display_text)
                    last_text = display_text
                updated_entries.append((lbl, full_title, last_text))
        self._sidebar_title_labels = updated_entries

    # ==========================================
    #           NAVIGATION & TRANSITIONS
    # ==========================================
    def _cancel_timer_loop(self):
        if self._timer_after_id is not None:
            self.after_cancel(self._timer_after_id)
            self._timer_after_id = None

    def _cancel_timer_resize_jobs(self):
        if self._timer_resize_job is not None:
            self.after_cancel(self._timer_resize_job)
            self._timer_resize_job = None
        if self._timer_hq_job is not None:
            self.after_cancel(self._timer_hq_job)
            self._timer_hq_job = None
        self._timer_pending_stage = None

    def _on_focus_out(self, event):
        if (
            event.widget == self
            and hasattr(self, "filter_overlay")
            and self.filter_overlay.winfo_exists()
        ):
            self.filter_overlay.destroy()
        self._cancel_hover_overlay()

    def _sync_filter_overlay(self, event=None):
        if (
            hasattr(self, "filter_overlay")
            and self.filter_overlay.winfo_exists()
            and hasattr(self, "filter_btn")
            and self.filter_btn.winfo_exists()
        ):
            x = self.filter_btn.winfo_rootx() - self.winfo_rootx() - 110
            y = (
                self.filter_btn.winfo_rooty()
                - self.winfo_rooty()
                + self.filter_btn.winfo_height()
                + 5
            )
            self.filter_overlay.place(x=x, y=y)
            self.filter_overlay.lift()

    def navigate_to_add_game_fresh(self):
        self._cancel_hover_overlay()
        self.saved_search_query = ""
        self.active_filter = None
        self.current_page = 0
        self.catalog_loaded_once = False
        self.transition_to(self.build_adding_game_screen)

    def transition_to(self, target_screen_method, *args):
        self._cancel_hover_overlay()
        self._cancel_timer_loop()
        self._cancel_timer_resize_jobs()
        self._active_scroll_canvas = None
        self._details_sync_fn = None
        self._fade_out(target_screen_method, args, alpha=1.0)

    def _fade_out(self, target_method, args, alpha):
        alpha -= 0.15
        if alpha > 0:
            self.attributes("-alpha", alpha)
            self.after(20, self._fade_out, target_method, args, alpha)
        else:
            self.clear_screen()
            target_method(*args)
            self._fade_in(0)

    def _fade_in(self, alpha):
        alpha += 0.15
        if alpha <= 1.0:
            self.attributes("-alpha", alpha)
            self.after(20, self._fade_in, alpha)
        else:
            self.attributes("-alpha", 1.0)

    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()
        for r in range(4):
            self.grid_rowconfigure(r, weight=0, minsize=0)
        for c in range(4):
            self.grid_columnconfigure(c, weight=0, minsize=0)

    def _paginate_transition(self, step):
        if getattr(self, "is_animating", False):
            return
        self.is_animating = True
        self.slide_step = step
        self.slide_pos = 0.0
        self._slide_out()

    def _slide_out(self):
        move_dir = -1 if self.slide_step > 0 else 1
        self.slide_pos += 0.2 * move_dir
        if abs(self.slide_pos) < 1.0:
            self.center_container.place(
                relx=0.5 + self.slide_pos, rely=0.5, anchor="center"
            )
            self.after(15, self._slide_out)
        else:
            self.current_page += self.slide_step
            self.render_catalog_cards()
            self.slide_pos = 1.0 * move_dir
            self.center_container.place(
                relx=0.5 + self.slide_pos, rely=0.5, anchor="center"
            )
            self._slide_in()

    def _slide_in(self):
        move_dir = -1 if self.slide_step > 0 else 1
        self.slide_pos -= 0.2 * move_dir
        if (move_dir < 0 and self.slide_pos < 0.0) or (
            move_dir > 0 and self.slide_pos > 0.0
        ):
            self.center_container.place(
                relx=0.5 + self.slide_pos, rely=0.5, anchor="center"
            )
            self.after(15, self._slide_in)
        else:
            self.center_container.place(relx=0.5, rely=0.5, anchor="center")
            self.is_animating = False

    def _parse_modes(self, game_dict):
        modes = game_dict.get("game_modes", [])
        if isinstance(modes, str):
            modes = [modes]
        modes_lower = [m.lower() for m in modes]
        return (
            any("single" in m for m in modes_lower),
            any("multi" in m for m in modes_lower),
        )

    # ==========================================
    #             SCREEN 1: MAIN HUB
    # ==========================================
    def build_main_hub(self, selected_game=None):
        self.selected_game_id = selected_game.id if selected_game is not None else None
        self._active_scroll_canvas = None
        self._details_sync_fn = None

        if selected_game is not None and selected_game.status in self.category_states:
            self.category_states[selected_game.status] = True

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header_frame = tk.Frame(self, bg=BG_MAIN, highlightthickness=0, bd=0)
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        header_frame.grid_columnconfigure(1, weight=1)

        # Clickable "GameLedger" title to return to the Recently/Last Played hub
        logo_lbl = tk.Label(
            header_frame,
            text="GameLedger",
            fg=FG_TEXT,
            bg=BG_MAIN,
            font=("Segoe UI", 18, "bold"),
            cursor="hand2",
        )
        logo_lbl.grid(row=0, column=0)
        logo_lbl.bind("<Button-1>", lambda e: self.return_to_hub_panel())

        ctk.CTkButton(
            header_frame,
            text="+ Add Game",
            cursor="hand2",
            command=lambda: self.after(10, self.navigate_to_add_game_fresh),
        ).grid(row=0, column=2)

        tk.Frame(self, height=2, bg=BG_DIVIDER, highlightthickness=0, bd=0).grid(
            row=1, column=0, sticky="ew"
        )

        # Native split-pane container driven by .place() for zero-lag dragging & window resizing
        self.body_frame = tk.Frame(self, bg=BG_MAIN, highlightthickness=0, bd=0)
        self.body_frame.grid(row=2, column=0, sticky="nsew")
        self.body_frame.bind("<Configure>", self._layout_split_pane)

        self.sidebar_frame = tk.Frame(
            self.body_frame, bg=BG_MAIN, highlightthickness=0, bd=0
        )

        # Draggable divider (sash) between left sidebar and right main panel
        self.sash = tk.Frame(
            self.body_frame,
            bg=BG_MAIN,
            cursor="sb_h_double_arrow",
            highlightthickness=0,
            bd=0,
        )
        sash_line = tk.Frame(
            self.sash, bg=BG_DIVIDER, width=2, highlightthickness=0, bd=0
        )
        sash_line.place(relx=0.5, rely=0, anchor="n", width=2, relheight=1.0)

        for w in (self.sash, sash_line):
            w.bind("<Enter>", lambda e: sash_line.configure(bg=BG_DIVIDER_HOVER))
            w.bind("<Leave>", lambda e: sash_line.configure(bg=BG_DIVIDER))
            w.bind("<ButtonPress-1>", self._start_sash_drag)
            w.bind("<B1-Motion>", self._on_sash_drag)
            w.bind("<ButtonRelease-1>", self._end_sash_drag)

        self.main_view = tk.Frame(
            self.body_frame, bg=BG_MAIN, highlightthickness=0, bd=0
        )

        self.render_sidebar()
        if selected_game is not None:
            fresh_game = next(
                (g for g in self.backlog_games if g.id == selected_game.id),
                selected_game,
            )
            self.render_inline_game_details(fresh_game)
        else:
            self.render_recently_played()
        self.after_idle(self._layout_split_pane)

    def return_to_hub_panel(self):
        """Clears active game selection and restores the Recently/Last Played panel."""
        self._cancel_hover_overlay()
        if self.selected_game_id is not None:
            self.selected_game_id = None
            self.render_sidebar()
        self.render_recently_played()

    def render_recently_played(self):
        self._active_scroll_canvas = None
        self._details_sync_fn = None
        for widget in self.main_view.winfo_children():
            widget.destroy()

        wrapper = tk.Frame(self.main_view, bg=BG_MAIN, highlightthickness=0, bd=0)
        wrapper.place(x=30, y=20, anchor="nw")

        tk.Label(
            wrapper,
            text="Recently/Last Played -",
            fg=FG_TEXT,
            bg=BG_MAIN,
            font=("Segoe UI", 14),
        ).pack(anchor="w", pady=(0, 20))

        games_frame = tk.Frame(wrapper, bg=BG_MAIN, highlightthickness=0, bd=0)
        games_frame.pack(fill="x")

        for _ in range(3):
            cover = ctk.CTkFrame(games_frame, width=140, height=200, corner_radius=5)
            cover.pack(side="left", padx=(0, 25))
            cover.pack_propagate(False)
            tk.Label(
                cover,
                text="Game\nCover",
                fg=FG_DIM,
                bg="#2B2B2B",
                font=("Segoe UI", 12, "bold"),
            ).pack(expand=True)

        ctk.CTkButton(
            games_frame,
            text=">",
            width=45,
            height=45,
            corner_radius=25,
            font=ctk.CTkFont(size=20),
            cursor="hand2",
            fg_color="transparent",
            border_width=2,
        ).pack(side="left", padx=10)

    def render_sidebar(self):
        self._cancel_hover_overlay()
        self.backlog_games = self.service.get_backlog()
        self._sidebar_title_labels = []

        for widget in self.sidebar_frame.winfo_children():
            widget.destroy()

        inner = tk.Frame(self.sidebar_frame, bg=BG_MAIN, highlightthickness=0, bd=0)
        inner.pack(fill="both", expand=True, padx=16, pady=20)

        search_frame = tk.Frame(inner, bg=BG_MAIN, highlightthickness=0, bd=0)
        search_frame.pack(fill="x", pady=(0, 18))
        search_frame.grid_columnconfigure(0, weight=1)
        search_frame.grid_columnconfigure(1, weight=0)

        ctk.CTkEntry(
            search_frame, placeholder_text="Search local...", width=10
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(search_frame, text="≡", width=30, cursor="hand2").grid(
            row=0, column=1, sticky="e"
        )

        max_title_px = max(50, self.sidebar_width - 78)

        for cat in ["Backlog", "In Progress", "Completed", "Abandoned"]:
            # Sort each library's games alphabetically (A-Z)
            cat_games = sorted(
                [g for g in self.backlog_games if g.status == cat],
                key=lambda g: g.title.lower(),
            )
            arrow = "v" if self.category_states[cat] else ">"

            cat_row = tk.Frame(
                inner, bg=BG_MAIN, cursor="hand2", highlightthickness=0, bd=0
            )
            cat_row.pack(fill="x", pady=2)

            cat_lbl = tk.Label(
                cat_row,
                text=f"{arrow} {cat} ({len(cat_games)})",
                fg=FG_TEXT,
                bg=BG_MAIN,
                font=self._sidebar_bold_font,
                anchor="w",
                cursor="hand2",
                padx=6,
                pady=4,
            )
            cat_lbl.pack(fill="x")

            def _cat_enter(e, r=cat_row, l=cat_lbl):
                r.configure(bg=BG_HOVER)
                l.configure(bg=BG_HOVER)

            def _cat_leave(e, r=cat_row, l=cat_lbl):
                r.configure(bg=BG_MAIN)
                l.configure(bg=BG_MAIN)

            for w in (cat_row, cat_lbl):
                w.bind("<Enter>", _cat_enter)
                w.bind("<Leave>", _cat_leave)
                w.bind("<Button-1>", lambda e, c=cat: self.toggle_category(c))

            if self.category_states[cat]:
                for game in cat_games:
                    is_selected = game.id == self.selected_game_id
                    dot_color = self.platform_colors.get(game.platform, "gray")

                    row_bg = BG_SELECTED if is_selected else BG_MAIN
                    row_cursor = "" if is_selected else "hand2"

                    item_frame = tk.Frame(
                        inner,
                        bg=row_bg,
                        cursor=row_cursor,
                        highlightthickness=0,
                        bd=0,
                    )
                    item_frame.pack(fill="x", padx=(12, 0), pady=2)

                    dot_lbl = tk.Label(
                        item_frame,
                        text="●",
                        fg=dot_color,
                        bg=row_bg,
                        font=self._sidebar_dot_font,
                        cursor=row_cursor,
                    )
                    dot_lbl.pack(side="left", padx=(8, 6), pady=3)

                    display_title, _ = self._truncate_text(game.title, max_title_px)
                    title_lbl = tk.Label(
                        item_frame,
                        text=display_title,
                        fg=FG_TEXT,
                        bg=row_bg,
                        font=self._sidebar_font,
                        anchor="w",
                        cursor=row_cursor,
                    )
                    title_lbl.pack(
                        side="left", fill="x", expand=True, pady=3, padx=(0, 8)
                    )
                    self._sidebar_title_labels.append(
                        (title_lbl, game.title, display_title)
                    )

                    def on_enter(
                        e, frame=item_frame, selected=is_selected, g=game
                    ):
                        if not selected:
                            self._set_row_bg(frame, BG_HOVER)
                        if self._hover_game_id != g.id:
                            _, is_trunc = self._truncate_text(
                                g.title, max(50, self.sidebar_width - 78)
                            )
                            if is_trunc:
                                self._schedule_hover_overlay(frame, g, selected)
                            else:
                                self._cancel_hover_overlay()

                    def on_leave(
                        e, frame=item_frame, selected=is_selected, gid=game.id
                    ):
                        def _check():
                            if self._is_pointer_inside(frame):
                                return
                            if (
                                self._hover_game_id == gid
                                and self._is_pointer_inside(self._hover_overlay)
                            ):
                                return
                            if not selected and frame.winfo_exists():
                                self._set_row_bg(frame, BG_MAIN)
                            if self._hover_game_id == gid:
                                self._cancel_hover_overlay()

                        self.after(20, _check)

                    for w in (item_frame, dot_lbl, title_lbl):
                        w.bind("<Enter>", on_enter)
                        w.bind("<Leave>", on_leave)
                        if not is_selected:
                            w.bind("<Button-1>", lambda e, g=game: self.select_game(g))

    def select_game(self, game):
        """Highlights the selected game in the sidebar and opens its inline details."""
        self._cancel_hover_overlay()
        self.selected_game_id = game.id
        self.render_sidebar()
        self.render_inline_game_details(game)

    def toggle_category(self, cat):
        self.category_states[cat] = not self.category_states[cat]
        self.render_sidebar()

    # ==========================================
    #      INLINE GAME DETAILS & REMOVE (B2-B5)
    # ==========================================
    def render_inline_game_details(self, game):
        self._details_sync_fn = None
        for widget in self.main_view.winfo_children():
            widget.destroy()

        scroll_container = tk.Frame(
            self.main_view, bg=BG_MAIN, highlightthickness=0, bd=0
        )
        scroll_container.pack(fill="both", expand=True, padx=(10, 6), pady=10)
        scroll_container.grid_rowconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(0, weight=1)
        scroll_container.grid_columnconfigure(1, weight=0)

        details_canvas = tk.Canvas(
            scroll_container, bg=BG_MAIN, highlightthickness=0, bd=0
        )
        details_canvas.grid(row=0, column=0, sticky="nsew")
        self._active_scroll_canvas = details_canvas

        v_scroll = ctk.CTkScrollbar(
            scroll_container, orientation="vertical", command=details_canvas.yview
        )
        v_scroll.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        details_canvas.configure(yscrollcommand=v_scroll.set)

        details_inner = tk.Frame(
            details_canvas, bg=BG_MAIN, highlightthickness=0, bd=0
        )
        inner_window_id = details_canvas.create_window(
            (0, 0), window=details_inner, anchor="nw"
        )

        # Fetch dynamic game metadata from games.json via CatalogService
        details = self.service.get_catalog_details_by_title(game.title)
        developer = details.get("developer", "Unknown Developer")
        publisher = details.get("publisher", "Unknown Publisher")
        genre = details.get("genre", "Unknown Genre")
        general_release = details.get("general_release", "N/A")
        desc = details.get("description", "No description available for this title yet.")

        # B5: Both "+ New Session" buttons launch the Game Timer screen for this game
        def start_new_session(g=game):
            self.after(10, self.transition_to, self.build_timer_screen, g)

        # ---------------------------------------------
        # TOP ROW: Game Cover + Title + Action Buttons
        # ---------------------------------------------
        top_section = tk.Frame(details_inner, bg=BG_MAIN, highlightthickness=0, bd=0)
        top_section.pack(fill="x", pady=(10, 20), padx=16)
        top_section.grid_columnconfigure(0, weight=0)
        top_section.grid_columnconfigure(1, weight=1)

        cover_frame = ctk.CTkFrame(top_section, width=180, height=250, corner_radius=6)
        cover_frame.grid(row=0, column=0, sticky="nw", padx=(0, 22))
        cover_frame.pack_propagate(False)
        tk.Label(
            cover_frame,
            text="Game\nCover",
            fg=FG_DIM,
            bg="#2B2B2B",
            font=("Segoe UI", 12, "bold"),
        ).pack(expand=True)

        title_section = tk.Frame(
            top_section, bg=BG_MAIN, height=250, highlightthickness=0, bd=0
        )
        title_section.grid(row=0, column=1, sticky="nsew")
        title_section.grid_propagate(False)
        title_section.grid_rowconfigure(0, weight=0)
        title_section.grid_rowconfigure(1, weight=0)
        title_section.grid_rowconfigure(2, weight=1)
        title_section.grid_rowconfigure(3, weight=0)
        title_section.grid_columnconfigure(0, weight=1)

        title_lbl = tk.Label(
            title_section,
            text=game.title,
            fg=FG_TEXT,
            bg=BG_MAIN,
            font=("Segoe UI", 24, "bold"),
            anchor="w",
            justify="left",
            wraplength=420,
        )
        title_lbl.grid(row=0, column=0, sticky="nw", pady=(0, 4))

        meta_str = f"{developer} · {genre} · {game.platform}"
        tk.Label(
            title_section,
            text=meta_str,
            fg=FG_MUTED,
            bg=BG_MAIN,
            font=("Segoe UI", 10),
            anchor="w",
        ).grid(row=1, column=0, sticky="nw")

        btn_row = tk.Frame(title_section, bg=BG_MAIN, highlightthickness=0, bd=0)
        btn_row.grid(row=3, column=0, sticky="sw")

        ctk.CTkButton(
            btn_row,
            text="+ New Session",
            fg_color="transparent",
            border_width=2,
            cursor="hand2",
            width=120,
            command=start_new_session,
        ).pack(side="left", padx=(0, 5))
        ctk.CTkButton(
            btn_row,
            text="✓",
            width=35,
            fg_color="transparent",
            border_width=2,
            cursor="hand2",
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_row,
            text="X",
            width=35,
            fg_color="transparent",
            border_width=2,
            cursor="hand2",
        ).pack(side="left", padx=2)

        dots_btn = ctk.CTkButton(
            btn_row,
            text="...",
            width=35,
            fg_color="transparent",
            border_width=2,
            cursor="hand2",
        )
        dots_btn.pack(side="left", padx=2)

        self.remove_btn = ctk.CTkButton(
            details_inner,
            text="Remove",
            fg_color="red",
            hover_color="darkred",
            cursor="hand2",
            command=lambda: self.execute_remove_game(game.id),
            width=242,
        )

        def toggle_remove():
            if self.remove_btn.winfo_ismapped():
                self.remove_btn.place_forget()
            else:
                self.update_idletasks()
                x = btn_row.winfo_rootx() - details_inner.winfo_rootx()
                y = (
                    btn_row.winfo_rooty()
                    - details_inner.winfo_rooty()
                    + btn_row.winfo_height()
                    + 6
                )
                self.remove_btn.place(x=x, y=y)
                self.remove_btn.lift()

        dots_btn.configure(command=toggle_remove)

        # ---------------------------------------------
        # MIDDLE ROW: Description + Full Details
        # ---------------------------------------------
        mid_section = tk.Frame(details_inner, bg=BG_MAIN, highlightthickness=0, bd=0)
        mid_section.pack(fill="x", pady=(10, 20), padx=16)
        mid_section.grid_columnconfigure(0, weight=1)
        mid_section.grid_columnconfigure(1, weight=0)

        desc_lbl = tk.Label(
            mid_section,
            text=desc,
            fg=FG_DESC,
            bg=BG_MAIN,
            font=("Segoe UI", 10),
            wraplength=360,
            anchor="nw",
            justify="left",
        )
        desc_lbl.grid(row=0, column=0, sticky="nsew", padx=(0, 24))

        details_frame = tk.Frame(mid_section, bg=BG_MAIN, highlightthickness=0, bd=0)
        details_frame.grid(row=0, column=1, sticky="ne")
        details_frame.grid_columnconfigure(0, weight=1)
        details_frame.grid_columnconfigure(1, weight=1)

        header_font = ("Segoe UI", 8, "bold")
        val_font = ("Segoe UI", 10)
        today_date = datetime.now().strftime("%m/%d/%y")

        meta_cells = [
            ("DEVELOPER", developer, 0, 0),
            ("PUBLISHER", publisher, 0, 1),
            ("GENERAL RELEASE", general_release, 2, 0),
            ("ADDED", today_date, 2, 1),
            ("VERSION", game.platform, 4, 0),
        ]
        for label_text, value_text, r, c in meta_cells:
            tk.Label(
                details_frame,
                text=label_text,
                fg=FG_DIM,
                bg=BG_MAIN,
                font=header_font,
                anchor="w",
            ).grid(row=r, column=c, sticky="w", padx=(0, 18))
            tk.Label(
                details_frame,
                text=value_text,
                fg=FG_TEXT,
                bg=BG_MAIN,
                font=val_font,
                anchor="w",
            ).grid(row=r + 1, column=c, sticky="w", padx=(0, 18), pady=(0, 12))

        # ---------------------------------------------
        # BOTTOM ROW: PROGRESS (Accordion B18)
        # ---------------------------------------------
        progress_section = tk.Frame(
            details_inner, bg=BG_MAIN, highlightthickness=0, bd=0
        )
        progress_section.pack(fill="x", pady=(16, 20), padx=16)

        tk.Label(
            progress_section,
            text="PROGRESS",
            fg=FG_TEXT,
            bg=BG_MAIN,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        # Dynamically render all submitted sessions for this game
        sessions = self.session_service.get_sessions_for_game(game.id)
        for session in sessions:
            has_subj = bool(session.subject.strip())
            has_notes = bool(session.notes.strip())
            is_clickable = has_subj or has_notes

            row_container = tk.Frame(progress_section, bg=BG_MAIN)
            row_container.pack(fill="x", pady=2)

            main_row = tk.Frame(row_container, bg=BG_MAIN, cursor="hand2" if is_clickable else "")
            main_row.pack(fill="x", pady=4)

            left_f = tk.Frame(main_row, bg=BG_MAIN)
            left_f.pack(side="left")
            
            # Blue dot for now (will adapt to green/red in future updates)
            tk.Label(left_f, text="●", fg="#2563EB", bg=BG_MAIN, font=self._sidebar_dot_font).pack(side="left", padx=(0, 6))
            tk.Label(left_f, text=session.date, fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 11)).pack(side="left")

            arrow_lbl = None
            if is_clickable:
                arrow_lbl = tk.Label(left_f, text=">", fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 10, "bold"))
                arrow_lbl.pack(side="left", padx=(8, 0))

            s_main, s_ms = self._format_stopwatch(session.duration_seconds)
            right_f = tk.Frame(main_row, bg=BG_MAIN)
            right_f.pack(side="right")
            tk.Label(right_f, text=s_ms, fg=FG_MUTED, bg=BG_MAIN, font=("Segoe UI", 9)).pack(side="right", anchor="s", pady=(0, 1))
            tk.Label(right_f, text=s_main, fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 11)).pack(side="right", anchor="s")

            details_f = tk.Frame(row_container, bg=BG_MAIN)
            if has_subj:
                tk.Label(details_f, text="Subject", fg=FG_DIM, bg=BG_MAIN, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=(22, 0), pady=(4, 0))
                s_lbl = tk.Label(details_f, text=session.subject, fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 10), justify="left", wraplength=400)
                s_lbl.pack(anchor="w", padx=(22, 0), pady=(0, 6))
                self._accordion_labels.append(s_lbl)
            if has_notes:
                tk.Label(details_f, text="Notes", fg=FG_DIM, bg=BG_MAIN, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=(22, 0), pady=(4, 0))
                n_lbl = tk.Label(details_f, text=session.notes, fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 10), justify="left", wraplength=400)
                n_lbl.pack(anchor="w", padx=(22, 0), pady=(0, 6))
                self._accordion_labels.append(n_lbl)

            tk.Frame(progress_section, height=1, bg=BG_DIVIDER).pack(fill="x", pady=(2, 6))

            if is_clickable:
                def _toggle_accordion(e, df=details_f, al=arrow_lbl):
                    if df.winfo_ismapped():
                        df.pack_forget()
                        al.configure(text=">")
                    else:
                        df.pack(fill="x", pady=(0, 6))
                        al.configure(text="v")
                    _sync_scrollregion()

                main_row.bind("<Button-1>", _toggle_accordion)
                for w in main_row.winfo_children():
                    w.bind("<Button-1>", _toggle_accordion)
                    for child in w.winfo_children():
                        child.bind("<Button-1>", _toggle_accordion)

        ctk.CTkButton(
            progress_section,
            text="+ New Session",
            fg_color="transparent",
            border_width=2,
            cursor="hand2",
            width=120,
            command=start_new_session,
        ).pack(anchor="w", pady=(10, 0))

        layout_state = {"w": -1}

        def _sync_details_width(canvas_w: int):
            if canvas_w <= 1 or canvas_w == layout_state["w"]:
                return
            if not (details_canvas.winfo_exists() and details_frame.winfo_exists()):
                return
            layout_state["w"] = canvas_w
            details_canvas.itemconfigure(inner_window_id, width=canvas_w)

            avail_title = max(180, canvas_w - 245)
            title_lbl.configure(wraplength=avail_title)

            details_w = details_frame.winfo_reqwidth()
            avail_desc = max(150, canvas_w - details_w - 64)
            desc_lbl.configure(wraplength=avail_desc)

            # Keep all accordion subject/notes text dynamically wrapped inside the boundaries
            avail_acc = max(150, canvas_w - 90)
            for acc_lbl in self._accordion_labels:
                if acc_lbl.winfo_exists():
                    acc_lbl.configure(wraplength=avail_acc)

        def _sync_scrollregion(event=None):
            if details_canvas.winfo_exists():
                details_canvas.configure(scrollregion=details_canvas.bbox("all"))

        def _on_canvas_configure(event):
            _sync_details_width(event.width)

        self._details_sync_fn = _sync_details_width
        details_inner.bind("<Configure>", _sync_scrollregion)
        details_canvas.bind("<Configure>", _on_canvas_configure)

        # Auto-scroll to bottom of right panel immediately after returning from a new submission
        if getattr(self, "_scroll_to_bottom_pending", False):
            self._scroll_to_bottom_pending = False
            self.after(50, lambda: details_canvas.yview_moveto(1.0))

    def execute_remove_game(self, game_id):
        self.service.remove_game(game_id)
        self.selected_game_id = None
        self.render_sidebar()
        self.render_recently_played()

    # ==========================================
    #       SCREEN 4: STOPWATCH TIMER (B6-B10)
    # ==========================================
    def _ensure_timer_masters(self):
        """Pre-renders high-resolution master sprites ONCE for silky anti-aliased dynamic scaling."""
        if not HAS_PIL or self._timer_masters:
            return

        bg = _hex_to_rgb(BG_MAIN)
        white = (255, 255, 255)

        # 1. Master stopwatch ring (720x720 RGB — fast BILINEAR scaling during live drag)
        ring_m = Image.new("RGB", (720, 720), bg)
        dr = ImageDraw.Draw(ring_m)
        dr.ellipse((24, 24, 696, 696), outline=_hex_to_rgb(FG_TEXT), width=5)
        self._timer_masters["ring"] = ring_m

        # 2. Master orbiting dot (64x64 RGBA — overlaps the ring line cleanly)
        dot_m = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dot_m)
        dd.ellipse((4, 4, 60, 60), fill=(255, 255, 255, 255), outline=(*bg, 255), width=4)
        self._timer_masters["dot"] = dot_m

        # 3. Master Play / Pause buttons (256x256 RGB)
        def _make_play(fill_hex: str):
            img = Image.new("RGB", (256, 256), bg)
            d = ImageDraw.Draw(img)
            d.ellipse((8, 8, 248, 248), fill=_hex_to_rgb(fill_hex))
            d.polygon([(100, 76), (100, 180), (182, 128)], fill=white)
            return img

        def _make_pause(fill_hex: str):
            img = Image.new("RGB", (256, 256), bg)
            d = ImageDraw.Draw(img)
            d.ellipse((8, 8, 248, 248), fill=_hex_to_rgb(fill_hex))
            d.rounded_rectangle((88, 78, 114, 178), radius=5, fill=white)
            d.rounded_rectangle((142, 78, 168, 178), radius=5, fill=white)
            return img

        self._timer_masters["play_normal"] = _make_play(TIMER_PLAY_GREEN)
        self._timer_masters["play_hover"] = _make_play(TIMER_PLAY_GREEN_HOVER)
        self._timer_masters["pause_normal"] = _make_pause(TIMER_PAUSE_ORANGE)
        self._timer_masters["pause_hover"] = _make_pause(TIMER_PAUSE_ORANGE_HOVER)

        # 4. Master Stop buttons (256x256 RGB)
        def _make_stop(fill_hex: str, icon_hex: str):
            img = Image.new("RGB", (256, 256), bg)
            d = ImageDraw.Draw(img)
            d.ellipse((8, 8, 248, 248), fill=_hex_to_rgb(fill_hex))
            d.rounded_rectangle((92, 92, 164, 164), radius=6, fill=_hex_to_rgb(icon_hex))
            return img

        self._timer_masters["stop_normal"] = _make_stop(TIMER_STOP_RED, "#FFFFFF")
        self._timer_masters["stop_hover"] = _make_stop(TIMER_STOP_RED_HOVER, "#FFFFFF")
        self._timer_masters["stop_disabled"] = _make_stop(
            TIMER_STOP_DISABLED_BG, TIMER_STOP_DISABLED_ICON
        )

        # 5. Master Restart buttons (256x256 RGB)
        def _make_restart(fill_hex: str, stroke_hex: str):
            img = Image.new("RGB", (256, 256), bg)
            d = ImageDraw.Draw(img)
            stroke = _hex_to_rgb(stroke_hex)
            d.ellipse(
                (12, 12, 244, 244),
                fill=_hex_to_rgb(fill_hex),
                outline=stroke,
                width=8,
            )
            # Clockwise circular arrow centered at (128, 128)
            cx, cy = 128, 128
            r_arc = 48
            arc_w = 10
            d.arc(
                (cx - r_arc, cy - r_arc, cx + r_arc, cy + r_arc),
                start=345,
                end=270,
                fill=stroke,
                width=arc_w,
            )
            # Arrowhead centered cleanly on the arc stroke at 12 o'clock pointing right
            y_mid = cy - (r_arc - arc_w // 2)
            d.polygon(
                [(cx + 20, y_mid), (cx - 4, y_mid - 16), (cx - 4, y_mid + 16)],
                fill=stroke,
            )
            return img

        self._timer_masters["restart_normal"] = _make_restart(BG_MAIN, FG_TEXT)
        self._timer_masters["restart_hover"] = _make_restart(BG_HOVER, FG_TEXT)
        self._timer_masters["restart_disabled"] = _make_restart(
            BG_MAIN, TIMER_RESTART_DISABLED
        )

    def _build_crisp_ring_photo(self, ring_img_size: int, ring_r: float) -> tk.PhotoImage:
        """Renders a 3x-supersampled ring with exact constant-crispness stroke at resting size."""
        ss = 3
        bg = _hex_to_rgb(BG_MAIN)
        s_img = ring_img_size * ss
        img = Image.new("RGB", (s_img, s_img), bg)
        d = ImageDraw.Draw(img)
        stroke_ss = max(5, int(round(2.0 * ss)))
        c = s_img / 2.0
        # Draw outward by half stroke so the stroke centerline lands at exact radius ring_r
        r_outer = ring_r * ss + stroke_ss / 2.0
        d.ellipse(
            (c - r_outer, c - r_outer, c + r_outer, c + r_outer),
            outline=_hex_to_rgb(FG_TEXT),
            width=stroke_ss,
        )
        final = img.resize((ring_img_size, ring_img_size), _PIL_LANCZOS)
        return ImageTk.PhotoImage(final)

    def _refresh_timer_sprites(
        self,
        ring_img_size: int,
        ring_r: float,
        dot_d: int,
        play_d: int,
        side_d: int,
        high_quality: bool,
    ):
        """Updates scaled anti-aliased PhotoImages; uses fast BILINEAR during live drag and LANCZOS on settle."""
        if not HAS_PIL:
            return
        self._ensure_timer_masters()
        resample = _PIL_LANCZOS if high_quality else _PIL_BILINEAR
        q_flag = 1 if high_quality else 0

        if (
            self._timer_rendered_sizes.get("ring") != ring_img_size
            or self._timer_rendered_sizes.get("ring_q") != q_flag
        ):
            if high_quality:
                self._timer_photos["ring"] = self._build_crisp_ring_photo(
                    ring_img_size, ring_r
                )
            else:
                scaled = self._timer_masters["ring"].resize(
                    (ring_img_size, ring_img_size), resample
                )
                self._timer_photos["ring"] = ImageTk.PhotoImage(scaled)
            self._timer_rendered_sizes["ring"] = ring_img_size
            self._timer_rendered_sizes["ring_q"] = q_flag

        if (
            self._timer_rendered_sizes.get("dot") != dot_d
            or self._timer_rendered_sizes.get("dot_q") != q_flag
        ):
            scaled = self._timer_masters["dot"].resize((dot_d, dot_d), resample)
            self._timer_photos["dot"] = ImageTk.PhotoImage(scaled)
            self._timer_rendered_sizes["dot"] = dot_d
            self._timer_rendered_sizes["dot_q"] = q_flag

        if (
            self._timer_rendered_sizes.get("play") != play_d
            or self._timer_rendered_sizes.get("play_q") != q_flag
        ):
            for key in ("play_normal", "play_hover", "pause_normal", "pause_hover"):
                scaled = self._timer_masters[key].resize((play_d, play_d), resample)
                self._timer_photos[key] = ImageTk.PhotoImage(scaled)
            self._timer_rendered_sizes["play"] = play_d
            self._timer_rendered_sizes["play_q"] = q_flag

        if (
            self._timer_rendered_sizes.get("side") != side_d
            or self._timer_rendered_sizes.get("side_q") != q_flag
        ):
            for key in (
                "restart_normal",
                "restart_hover",
                "restart_disabled",
                "stop_normal",
                "stop_hover",
                "stop_disabled",
            ):
                scaled = self._timer_masters[key].resize((side_d, side_d), resample)
                self._timer_photos[key] = ImageTk.PhotoImage(scaled)
            self._timer_rendered_sizes["side"] = side_d
            self._timer_rendered_sizes["side_q"] = q_flag

    def _format_stopwatch(self, elapsed_seconds: float) -> tuple[str, str]:
        total_cs = max(0, int(elapsed_seconds * 100))
        cs = total_cs % 100
        total_sec = total_cs // 100
        secs = total_sec % 60
        mins = (total_sec // 60) % 60
        hrs = total_sec // 3600
        return f"{hrs:02d}:{mins:02d}:{secs:02d}", f".{cs:02d}"

    def _get_timer_elapsed(self) -> float:
        if self._timer_state == "running":
            return self._timer_elapsed + (time.perf_counter() - self._timer_start_perf)
        return self._timer_elapsed

    def build_timer_screen(self, game):
        self._cancel_timer_loop()
        self._cancel_timer_resize_jobs()
        self._timer_game = game
        self._timer_state = "ready"
        self._timer_elapsed = 0.0
        self._timer_start_perf = 0.0
        self._timer_hovered_btn = None
        self._timer_rendered_sizes = {}
        self._timer_btn_geom = {}

        if HAS_PIL:
            self._ensure_timer_masters()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Single unified native canvas spans the ENTIRE window for true dead-center alignment
        self._timer_stage_canvas = tk.Canvas(
            self, bg=BG_MAIN, highlightthickness=0, bd=0
        )
        self._timer_stage_canvas.grid(row=0, column=0, sticky="nsew")

        # Floating top-left Back Button (does not push the timer off vertical center)
        back_btn = ctk.CTkButton(
            self,
            text="← Back",
            width=60,
            cursor="hand2",
            command=lambda g=game: self.after(
                10, self.transition_to, self.build_main_hub, g
            ),
        )
        back_btn.place(x=20, y=20)
        back_btn.lift()

        # Reusable font objects mutated in place during resize (no font-object churn)
        self._ready_font = tkfont.Font(family="Segoe UI", size=24)
        self._time_main_font = tkfont.Font(family="Segoe UI", size=32)
        self._time_ms_font = tkfont.Font(family="Segoe UI", size=15)

        c = self._timer_stage_canvas
        self._ring_cx = 500.0
        self._ring_cy = 220.0
        self._ring_r = 148.0
        self._dot_r = 6.0

        if HAS_PIL:
            self._ring_item_id = c.create_image(0, 0, anchor="center")
            self._dot_item_id = c.create_image(0, 0, anchor="center", state="hidden")
            self._restart_item_id = c.create_image(0, 0, anchor="center")
            self._play_item_id = c.create_image(0, 0, anchor="center")
            self._stop_item_id = c.create_image(0, 0, anchor="center")
        else:
            # Graceful fallback if Pillow is not installed yet
            self._ring_item_id = c.create_oval(0, 0, 0, 0, outline=FG_TEXT, width=2)
            self._dot_item_id = c.create_oval(
                0, 0, 0, 0, fill="#FFFFFF", outline=BG_MAIN, width=1, state="hidden"
            )
            self._restart_item_id = None
            self._play_item_id = None
            self._stop_item_id = None

        self._ready_text_id = c.create_text(
            0, 0, text="Ready to Start?", fill=FG_TEXT, font=self._ready_font
        )
        self._time_main_id = c.create_text(
            0,
            0,
            text="00:00:00",
            fill=FG_TEXT,
            font=self._time_main_font,
            anchor="se",
            state="hidden",
        )
        self._time_ms_id = c.create_text(
            0,
            0,
            text=".00",
            fill=FG_MUTED,
            font=self._time_ms_font,
            anchor="sw",
            state="hidden",
        )

        # Keep orbiting dot stacked cleanly above the ring line
        c.tag_raise(self._dot_item_id)

        c.bind("<Configure>", self._on_timer_stage_configure)
        c.bind("<Motion>", self._on_timer_mouse_move)
        c.bind("<Leave>", self._on_timer_mouse_leave)
        c.bind("<Button-1>", self._on_timer_mouse_click)

        # Perform initial high-quality layout immediately
        self.after_idle(self._initial_timer_layout)

    def _initial_timer_layout(self):
        if not (
            hasattr(self, "_timer_stage_canvas")
            and self._timer_stage_canvas.winfo_exists()
        ):
            return
        w = max(self._timer_stage_canvas.winfo_width(), 960)
        h = max(self._timer_stage_canvas.winfo_height(), 560)
        self._layout_timer_stage(w, h, high_quality=True)

    def _on_timer_stage_configure(self, event):
        if event.width <= 1 or event.height <= 1:
            return
        self._timer_pending_stage = (event.width, event.height)
        if self._timer_resize_job is None:
            self._timer_resize_job = self.after(16, self._flush_timer_resize)

    def _flush_timer_resize(self):
        self._timer_resize_job = None
        if self._timer_pending_stage is None:
            return
        w, h = self._timer_pending_stage
        self._timer_pending_stage = None
        self._layout_timer_stage(w, h, high_quality=False)

        # Once resizing settles for 80ms, perform one crisp LANCZOS pass
        if self._timer_hq_job is not None:
            self.after_cancel(self._timer_hq_job)
        self._timer_hq_job = self.after(80, self._apply_timer_hq_pass)

    def _apply_timer_hq_pass(self):
        self._timer_hq_job = None
        if not (
            hasattr(self, "_timer_stage_canvas")
            and self._timer_stage_canvas.winfo_exists()
        ):
            return
        w = self._timer_stage_canvas.winfo_width()
        h = self._timer_stage_canvas.winfo_height()
        if w > 1 and h > 1:
            self._layout_timer_stage(w, h, high_quality=True)

    def _layout_timer_stage(self, stage_w: int, stage_h: int, high_quality: bool):
        if not (
            hasattr(self, "_timer_stage_canvas")
            and self._timer_stage_canvas.winfo_exists()
        ):
            return
        c = self._timer_stage_canvas

        # Proportional scale factor anchored to the full 1000x650 window (B6-B10)
        scale = min((stage_w - 80) / 560.0, (stage_h - 80) / 560.0)
        scale = max(0.65, min(scale, 2.5))

        ring_r = max(90.0, round(148.0 * scale))
        ring_img_size = int(round(ring_r * 2.0 * (720.0 / 672.0)))
        dot_d = max(10, int(round(13.0 * scale)))
        play_d = max(56, int(round(86.0 * scale)))
        side_d = max(44, int(round(64.0 * scale)))
        btn_gap_y = round(34.0 * scale)
        btn_spacing_x = round(152.0 * scale)

        total_h = ring_r * 2.0 + btn_gap_y + play_d
        top_y = (stage_h - total_h) / 2.0

        cx = stage_w / 2.0
        ring_cy = top_y + ring_r
        btn_cy = top_y + ring_r * 2.0 + btn_gap_y + play_d / 2.0

        self._ring_cx = cx
        self._ring_cy = ring_cy
        self._ring_r = ring_r
        self._dot_r = dot_d / 2.0

        # Circular hitboxes for hover/click detection
        self._timer_btn_geom = {
            "restart": (cx - btn_spacing_x, btn_cy, side_d / 2.0),
            "play": (cx, btn_cy, play_d / 2.0),
            "stop": (cx + btn_spacing_x, btn_cy, side_d / 2.0),
        }

        # Scale fonts smoothly with the ring
        ready_sz = max(14, int(round(24 * scale)))
        main_sz = max(18, int(round(32 * scale)))
        ms_sz = max(10, int(round(15 * scale)))
        if self._ready_font.cget("size") != ready_sz:
            self._ready_font.configure(size=ready_sz)
        if self._time_main_font.cget("size") != main_sz:
            self._time_main_font.configure(size=main_sz)
        if self._time_ms_font.cget("size") != ms_sz:
            self._time_ms_font.configure(size=ms_sz)

        # Optically center HH:MM:SS + .cc on a shared baseline inside the ring
        main_w = self._time_main_font.measure("00:00:00")
        ms_w = self._time_ms_font.measure(".00")
        split_x = cx + (main_w - ms_w) / 2.0

        main_ascent = self._time_main_font.metrics("ascent")
        main_descent = self._time_main_font.metrics("descent")
        ms_descent = self._time_ms_font.metrics("descent")
        baseline_y = ring_cy + (main_ascent - main_descent) / 2.0

        c.coords(self._ready_text_id, cx, ring_cy)
        c.coords(self._time_main_id, split_x, baseline_y + main_descent)
        c.coords(
            self._time_ms_id,
            split_x + max(1, round(2 * scale)),
            baseline_y + ms_descent,
        )

        if HAS_PIL:
            self._refresh_timer_sprites(
                ring_img_size, ring_r, dot_d, play_d, side_d, high_quality
            )
            c.coords(self._ring_item_id, cx, ring_cy)
            c.itemconfigure(self._ring_item_id, image=self._timer_photos["ring"])
            c.itemconfigure(self._dot_item_id, image=self._timer_photos["dot"])

            rx, ry, _ = self._timer_btn_geom["restart"]
            px, py, _ = self._timer_btn_geom["play"]
            sx, sy, _ = self._timer_btn_geom["stop"]
            c.coords(self._restart_item_id, rx, ry)
            c.coords(self._play_item_id, px, py)
            c.coords(self._stop_item_id, sx, sy)
        else:
            c.coords(
                self._ring_item_id,
                cx - ring_r,
                ring_cy - ring_r,
                cx + ring_r,
                ring_cy + ring_r,
            )

        self._render_timer_buttons()
        self._update_ring_display(self._get_timer_elapsed())

    def _is_restart_enabled(self) -> bool:
        # Greyed out only in B6 "Ready to Start?" phase
        return self._timer_state != "ready"

    def _is_stop_enabled(self) -> bool:
        # Greyed out in B6 "Ready to Start?" AND B9 "Reset" phases
        return self._timer_state in ("running", "paused")

    def _hit_test_timer_button(self, x: float, y: float) -> str | None:
        for name, (bx, by, br) in self._timer_btn_geom.items():
            dx = x - bx
            dy = y - by
            if (dx * dx + dy * dy) <= (br * br):
                return name
        return None

    def _is_timer_btn_enabled(self, name: str | None) -> bool:
        if name == "play":
            return True
        if name == "restart":
            return self._is_restart_enabled()
        if name == "stop":
            return self._is_stop_enabled()
        return False

    def _on_timer_mouse_move(self, event):
        hit = self._hit_test_timer_button(event.x, event.y)
        active_hit = hit if self._is_timer_btn_enabled(hit) else None
        if active_hit != self._timer_hovered_btn:
            self._timer_hovered_btn = active_hit
            self._timer_stage_canvas.configure(cursor="hand2" if active_hit else "")
            self._render_timer_buttons()

    def _on_timer_mouse_leave(self, event):
        if self._timer_hovered_btn is not None:
            self._timer_hovered_btn = None
            self._timer_stage_canvas.configure(cursor="")
            self._render_timer_buttons()

    def _on_timer_mouse_click(self, event):
        hit = self._hit_test_timer_button(event.x, event.y)
        if hit == "play":
            self._on_timer_play_pause()
        elif hit == "restart":
            self._on_timer_restart()
        elif hit == "stop":
            self._on_timer_stop()

    def _render_timer_buttons(self):
        if not (
            hasattr(self, "_timer_stage_canvas")
            and self._timer_stage_canvas.winfo_exists()
        ):
            return
        c = self._timer_stage_canvas

        if HAS_PIL:
            if not self._timer_photos:
                return
            # Restart button
            if not self._is_restart_enabled():
                r_key = "restart_disabled"
            elif self._timer_hovered_btn == "restart":
                r_key = "restart_hover"
            else:
                r_key = "restart_normal"
            c.itemconfigure(self._restart_item_id, image=self._timer_photos[r_key])

            # Play / Pause button
            if self._timer_state == "running":
                p_key = (
                    "pause_hover"
                    if self._timer_hovered_btn == "play"
                    else "pause_normal"
                )
            else:
                p_key = (
                    "play_hover"
                    if self._timer_hovered_btn == "play"
                    else "play_normal"
                )
            c.itemconfigure(self._play_item_id, image=self._timer_photos[p_key])

            # Stop button
            if not self._is_stop_enabled():
                s_key = "stop_disabled"
            elif self._timer_hovered_btn == "stop":
                s_key = "stop_hover"
            else:
                s_key = "stop_normal"
            c.itemconfigure(self._stop_item_id, image=self._timer_photos[s_key])
        else:
            # Non-PIL fallback vector rendering
            c.delete("fallback_btn")
            if not self._timer_btn_geom:
                return
            rx, ry, rr = self._timer_btn_geom["restart"]
            r_stroke = FG_TEXT if self._is_restart_enabled() else TIMER_RESTART_DISABLED
            r_bg = (
                BG_HOVER
                if (self._is_restart_enabled() and self._timer_hovered_btn == "restart")
                else BG_MAIN
            )
            c.create_oval(
                rx - rr, ry - rr, rx + rr, ry + rr,
                fill=r_bg, outline=r_stroke, width=2, tags="fallback_btn",
            )
            ar = rr * 0.4
            c.create_arc(
                rx - ar, ry - ar, rx + ar, ry + ar,
                start=18, extent=-288, style="arc",
                outline=r_stroke, width=2.5, tags="fallback_btn",
            )

            px, py, pr = self._timer_btn_geom["play"]
            if self._timer_state == "running":
                p_bg = (
                    TIMER_PAUSE_ORANGE_HOVER
                    if self._timer_hovered_btn == "play"
                    else TIMER_PAUSE_ORANGE
                )
                c.create_oval(
                    px - pr, py - pr, px + pr, py + pr,
                    fill=p_bg, outline="", tags="fallback_btn",
                )
                bw, bh, bgap = pr * 0.22, pr * 0.38, pr * 0.14
                c.create_rectangle(
                    px - bgap - bw, py - bh, px - bgap, py + bh,
                    fill="#FFFFFF", outline="", tags="fallback_btn",
                )
                c.create_rectangle(
                    px + bgap, py - bh, px + bgap + bw, py + bh,
                    fill="#FFFFFF", outline="", tags="fallback_btn",
                )
            else:
                p_bg = (
                    TIMER_PLAY_GREEN_HOVER
                    if self._timer_hovered_btn == "play"
                    else TIMER_PLAY_GREEN
                )
                c.create_oval(
                    px - pr, py - pr, px + pr, py + pr,
                    fill=p_bg, outline="", tags="fallback_btn",
                )
                c.create_polygon(
                    px - pr * 0.22, py - pr * 0.4,
                    px - pr * 0.22, py + pr * 0.4,
                    px + pr * 0.42, py,
                    fill="#FFFFFF", outline="", tags="fallback_btn",
                )

            sx, sy, sr = self._timer_btn_geom["stop"]
            if self._is_stop_enabled():
                s_bg = (
                    TIMER_STOP_RED_HOVER
                    if self._timer_hovered_btn == "stop"
                    else TIMER_STOP_RED
                )
                s_icon = "#FFFFFF"
            else:
                s_bg = TIMER_STOP_DISABLED_BG
                s_icon = TIMER_STOP_DISABLED_ICON
            c.create_oval(
                sx - sr, sy - sr, sx + sr, sy + sr,
                fill=s_bg, outline="", tags="fallback_btn",
            )
            sq = sr * 0.32
            c.create_rectangle(
                sx - sq, sy - sq, sx + sq, sy + sq,
                fill=s_icon, outline="", tags="fallback_btn",
            )

        # Keep cursor synchronized if a button just disabled under the pointer
        if self._timer_hovered_btn and not self._is_timer_btn_enabled(
            self._timer_hovered_btn
        ):
            self._timer_hovered_btn = None
            c.configure(cursor="")

    def _update_ring_display(self, elapsed: float):
        if not (
            hasattr(self, "_timer_stage_canvas")
            and self._timer_stage_canvas.winfo_exists()
        ):
            return
        c = self._timer_stage_canvas
        main_str, ms_str = self._format_stopwatch(elapsed)
        c.itemconfigure(self._time_main_id, text=main_str)
        c.itemconfigure(self._time_ms_id, text=ms_str)

        # Clockwise orbit starting at 12 o'clock (-pi/2), 1 full revolution per 60 seconds
        angle = -math.pi / 2.0 + ((elapsed % 60.0) / 60.0) * 2.0 * math.pi
        dx = self._ring_cx + self._ring_r * math.cos(angle)
        dy = self._ring_cy + self._ring_r * math.sin(angle)

        if HAS_PIL:
            c.coords(self._dot_item_id, dx, dy)
        else:
            c.coords(
                self._dot_item_id,
                dx - self._dot_r,
                dy - self._dot_r,
                dx + self._dot_r,
                dy + self._dot_r,
            )

    def _tick_timer(self):
        if self._timer_state != "running":
            self._timer_after_id = None
            return
        if not (
            hasattr(self, "_timer_stage_canvas")
            and self._timer_stage_canvas.winfo_exists()
        ):
            self._timer_after_id = None
            return
        self._update_ring_display(self._get_timer_elapsed())
        self._timer_after_id = self.after(20, self._tick_timer)

    def _on_timer_play_pause(self, event=None):
        c = self._timer_stage_canvas
        if self._timer_state in ("ready", "paused", "reset"):
            if self._timer_state == "ready":
                # Hide "Ready to Start?" and reveal live stopwatch + orbiting dot (B7)
                c.itemconfigure(self._ready_text_id, state="hidden")
                c.itemconfigure(self._time_main_id, state="normal")
                c.itemconfigure(self._time_ms_id, state="normal")
                c.itemconfigure(self._dot_item_id, state="normal")
            self._timer_state = "running"
            self._timer_start_perf = time.perf_counter()
            self._render_timer_buttons()
            self._tick_timer()
        elif self._timer_state == "running":
            # Freeze elapsed time and dot in place (B8)
            self._timer_elapsed = self._get_timer_elapsed()
            self._timer_state = "paused"
            self._cancel_timer_loop()
            self._update_ring_display(self._timer_elapsed)
            self._render_timer_buttons()

    def _on_timer_restart(self, event=None):
        if not self._is_restart_enabled():
            return
        # B9: Reset to 00:00:00.00, move dot to 12 o'clock, switch to Play, grey out Stop
        self._cancel_timer_loop()
        self._timer_elapsed = 0.0
        self._timer_state = "reset"
        self._update_ring_display(0.0)
        self._render_timer_buttons()

    def _on_timer_stop(self, event=None):
        if not self._is_stop_enabled():
            return
        # B10: Freeze exact recorded elapsed time and transition to submission screen
        recorded_seconds = self._get_timer_elapsed()
        self._timer_elapsed = recorded_seconds
        self._timer_state = "paused"
        self._cancel_timer_loop()
        self._update_ring_display(recorded_seconds)
        self.after(
            10,
            self.transition_to,
            self.build_session_submission_screen,
            self._timer_game,
            recorded_seconds,
        )

    # ==========================================
    #    STEP 4: SUBMISSION SCREEN (B11-B17)
    # ==========================================
    def build_session_submission_screen(self, game, recorded_seconds: float):
        self._cancel_hover_overlay()
        self._cancel_timer_loop()
        self._cancel_timer_resize_jobs()
        self._active_scroll_canvas = None
        self._details_sync_fn = None
        for widget in self.winfo_children():
            widget.destroy()
            
        for r in range(4): self.grid_rowconfigure(r, weight=0, minsize=0)
        for c in range(4): self.grid_columnconfigure(c, weight=0, minsize=0)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        main_bg = tk.Frame(self, bg=BG_MAIN, highlightthickness=0, bd=0)
        main_bg.grid(row=0, column=0, sticky="nsew")

        # Main centered container (B11)
        container = tk.Frame(main_bg, bg=BG_MAIN, highlightthickness=0, bd=0)
        container.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.85, relheight=0.85)

        header = tk.Frame(container, bg=BG_MAIN)
        header.pack(fill="x", pady=(0, 40))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=1)
        header.grid_columnconfigure(2, weight=1)

        # Game
        g_frame = tk.Frame(header, bg=BG_MAIN)
        g_frame.grid(row=0, column=0)
        tk.Label(g_frame, text="Game:", fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 16)).pack()
        tk.Label(g_frame, text=game.title, fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 18, "bold"), wraplength=300).pack(pady=(5,0))

        # Session Time (Much bigger to highlight importance)
        t_frame = tk.Frame(header, bg=BG_MAIN)
        t_frame.grid(row=0, column=1)
        tk.Label(t_frame, text="Session Time:", fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 16)).pack()
        main_str, ms_str = self._format_stopwatch(recorded_seconds)
        time_lbl_frame = tk.Frame(t_frame, bg=BG_MAIN)
        time_lbl_frame.pack(pady=(5,0))
        tk.Label(time_lbl_frame, text=main_str, fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 36, "bold")).pack(side="left", anchor="s")
        tk.Label(time_lbl_frame, text=ms_str, fg=FG_MUTED, bg=BG_MAIN, font=("Segoe UI", 18, "bold")).pack(side="left", anchor="s", pady=(0, 6))

        # Session Date
        d_frame = tk.Frame(header, bg=BG_MAIN)
        d_frame.grid(row=0, column=2)
        tk.Label(d_frame, text="Session Date:", fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 16)).pack()
        today_str = datetime.now().strftime("%B %d, %Y")
        tk.Label(d_frame, text=today_str, fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 18, "bold")).pack(pady=(5,0))

        # Form Inputs
        tk.Label(container, text="Session Subject (optional):", fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 14)).pack(anchor="w", pady=(10, 5))
        subject_entry = tk.Entry(container, font=("Segoe UI", 14), bg="#2B2B2B", fg=FG_TEXT, insertbackground=FG_TEXT, highlightbackground=FG_DIM, highlightcolor="#2563EB", relief="flat", bd=4)
        subject_entry.pack(fill="x", pady=(0, 20))

        tk.Label(container, text="Session Notes (optional):", fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 14)).pack(anchor="w", pady=(10, 5))
        notes_text = tk.Text(container, height=6, font=("Segoe UI", 14), bg="#2B2B2B", fg=FG_TEXT, insertbackground=FG_TEXT, highlightbackground=FG_DIM, highlightcolor="#2563EB", relief="flat", bd=4, wrap="word")
        notes_text.pack(fill="x", pady=(0, 30))

        btn_row = tk.Frame(container, bg=BG_MAIN)
        btn_row.pack()

        # Placeholders for ✓ and X
        ctk.CTkButton(btn_row, text="✓", width=40, height=40, fg_color="transparent", border_width=2, cursor="hand2").pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="X", width=40, height=40, fg_color="transparent", border_width=2, cursor="hand2").pack(side="left", padx=5)

        def do_cancel():
            self.transition_to(self.build_main_hub, game)

        def prompt_cancel():
            self._show_modal_popup("Are You Sure?", main_bg, do_cancel)

        def do_submit():
            subj = subject_entry.get().strip()
            notes = notes_text.get("1.0", "end").strip()
            
            # Post session to DB (automatically moves game to In Progress)
            self.session_service.log_play_session(
                game_id=game.id,
                date=today_str,
                duration_seconds=recorded_seconds,
                subject=subj,
                notes=notes
            )
            # Set flag so accordion auto-scrolls to the bottom upon return
            self._scroll_to_bottom_pending = True
            self.transition_to(self.build_main_hub, game)

        def prompt_submit():
            self._show_modal_popup("Submit?", main_bg, do_submit)

        ctk.CTkButton(btn_row, text="Submit", width=120, height=40, fg_color=TIMER_PLAY_GREEN, hover_color=TIMER_PLAY_GREEN_HOVER, cursor="hand2", font=("Segoe UI", 14, "bold"), command=prompt_submit).pack(side="left", padx=10)
        ctk.CTkButton(btn_row, text="Cancel", width=120, height=40, fg_color="#737373", hover_color="#525252", cursor="hand2", font=("Segoe UI", 14, "bold"), command=prompt_cancel).pack(side="left", padx=10)

    def _show_modal_popup(self, text, parent, on_yes):
        # B12-B14 & B16: Native overlay that blocks all clicks to the form behind it
        trap = tk.Frame(parent, bg="")
        trap.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)
        trap.bind("<Button-1>", lambda e: "break")

        overlay = tk.Frame(trap, bg=BG_MAIN, highlightbackground=FG_DIM, highlightthickness=2)
        overlay.place(relx=0.5, rely=0.5, anchor="center", width=360, height=180)

        tk.Label(overlay, text=text, fg=FG_TEXT, bg=BG_MAIN, font=("Segoe UI", 20)).pack(pady=(35, 25))

        btn_row = tk.Frame(overlay, bg=BG_MAIN)
        btn_row.pack()
        
        def yes_click():
            trap.destroy()
            on_yes()
            
        def no_click():
            trap.destroy()

        ctk.CTkButton(btn_row, text="Yes", width=80, height=36, fg_color=TIMER_PLAY_GREEN, hover_color=TIMER_PLAY_GREEN_HOVER, cursor="hand2", command=yes_click).pack(side="left", padx=10)
        ctk.CTkButton(btn_row, text="No", width=80, height=36, fg_color=TIMER_STOP_RED, hover_color=TIMER_STOP_RED_HOVER, cursor="hand2", command=no_click).pack(side="left", padx=10)

    # ==========================================
    #             SCREEN 2: ADDING GAME
    # ==========================================
    def build_adding_game_screen(self):
        self._active_scroll_canvas = None
        self._details_sync_fn = None
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            header_frame,
            text="← Back",
            width=60,
            cursor="hand2",
            command=lambda: self.after(10, self.transition_to, self.build_main_hub),
        ).grid(row=0, column=0, padx=(0, 20))

        self.catalog_search = ctk.CTkEntry(
            header_frame, placeholder_text="Search Catalog...", height=40
        )
        self.catalog_search.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        if self.saved_search_query:
            self.catalog_search.insert(0, self.saved_search_query)
        self.catalog_search.bind("<KeyRelease>", self.perform_catalog_search)

        self.filter_btn = ctk.CTkButton(
            header_frame,
            text="≡",
            width=40,
            height=40,
            cursor="hand2",
            command=self.toggle_filter_overlay,
        )
        self.filter_btn.grid(row=0, column=2)

        self.catalog_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.catalog_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))

        self.catalog_frame.grid_rowconfigure(0, weight=1)
        self.catalog_frame.grid_columnconfigure(0, minsize=60)
        self.catalog_frame.grid_columnconfigure(1, weight=1)
        self.catalog_frame.grid_columnconfigure(2, minsize=60)

        self.left_arrow = ctk.CTkButton(
            self.catalog_frame,
            text="<",
            width=45,
            height=45,
            corner_radius=25,
            font=ctk.CTkFont(size=20),
            fg_color="transparent",
            border_width=2,
            cursor="hand2",
            command=lambda: self._paginate_transition(-1),
        )
        self.right_arrow = ctk.CTkButton(
            self.catalog_frame,
            text=">",
            width=45,
            height=45,
            corner_radius=25,
            font=ctk.CTkFont(size=20),
            fg_color="transparent",
            border_width=2,
            cursor="hand2",
            command=lambda: self._paginate_transition(1),
        )

        self.carousel_viewport = ctk.CTkFrame(self.catalog_frame, fg_color="transparent")
        self.carousel_viewport.grid(row=0, column=1, sticky="nsew")

        self.center_container = ctk.CTkFrame(
            self.carousel_viewport, fg_color="transparent"
        )
        self.center_container.place(relx=0.5, rely=0.5, anchor="center")

        if not getattr(self, "catalog_loaded_once", False):
            self.catalog_loaded_once = True
            self.perform_catalog_search(reset_page=False)
        else:
            self.render_catalog_cards()

    def toggle_filter_overlay(self):
        if hasattr(self, "filter_overlay") and self.filter_overlay.winfo_exists():
            self.filter_overlay.destroy()
            return

        self.filter_overlay = ctk.CTkFrame(
            self,
            width=150,
            height=120,
            border_width=2,
            border_color="gray25",
            corner_radius=5,
        )
        self.filter_overlay.pack_propagate(False)

        self._sync_filter_overlay()

        ctk.CTkLabel(
            self.filter_overlay,
            text="PLAY STATE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#00A8E8",
        ).pack(anchor="w", padx=15, pady=(10, 5))

        self.sp_var = ctk.StringVar(
            value="checked" if self.active_filter == "Single-Player" else "unchecked"
        )
        self.mp_var = ctk.StringVar(
            value="checked" if self.active_filter == "Multi-Player" else "unchecked"
        )

        ctk.CTkCheckBox(
            self.filter_overlay,
            text="Single player",
            variable=self.sp_var,
            onvalue="checked",
            offvalue="unchecked",
            command=lambda: self.apply_filter("Single-Player"),
        ).pack(anchor="w", padx=15, pady=5)
        ctk.CTkCheckBox(
            self.filter_overlay,
            text="Multiplayer",
            variable=self.mp_var,
            onvalue="checked",
            offvalue="unchecked",
            command=lambda: self.apply_filter("Multi-Player"),
        ).pack(anchor="w", padx=15, pady=5)

    def apply_filter(self, selected):
        if selected == "Single-Player":
            if self.sp_var.get() == "checked":
                self.active_filter = "Single-Player"
                self.mp_var.set("unchecked")
            else:
                self.active_filter = None
        elif selected == "Multi-Player":
            if self.mp_var.get() == "checked":
                self.active_filter = "Multi-Player"
                self.sp_var.set("unchecked")
            else:
                self.active_filter = None
        self.perform_catalog_search(reset_page=True)

    def perform_catalog_search(self, event=None, reset_page=True):
        self.saved_search_query = self.catalog_search.get()
        results = (
            self.service.get_all_games()
            if not self.saved_search_query.strip()
            else self.service.search_games(self.saved_search_query)
        )

        if self.active_filter:
            filtered = []
            for g in results:
                is_sp, is_mp = self._parse_modes(g)
                if self.active_filter == "Single-Player" and is_sp:
                    filtered.append(g)
                elif self.active_filter == "Multi-Player" and is_mp:
                    filtered.append(g)
            self.catalog_results = filtered
        else:
            self.catalog_results = results

        if reset_page or getattr(event, "keysym", None):
            self.current_page = 0

        self.render_catalog_cards()

    def render_catalog_cards(self):
        for widget in self.center_container.winfo_children():
            widget.destroy()

        if not self.catalog_results:
            ctk.CTkLabel(
                self.center_container,
                text="No games found.",
                font=ctk.CTkFont(size=16),
            ).pack(pady=50)
            self.left_arrow.grid_remove()
            self.right_arrow.grid_remove()
            return

        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_items = self.catalog_results[start_idx:end_idx]

        if self.current_page > 0:
            self.left_arrow.grid(row=0, column=0, sticky="e")
        else:
            self.left_arrow.grid_remove()

        for game in page_items:
            card = ctk.CTkFrame(
                self.center_container,
                width=160,
                height=280,
                fg_color="transparent",
                corner_radius=8,
                cursor="hand2",
            )
            card.pack(side="left", padx=15)
            card.pack_propagate(False)

            cover = ctk.CTkFrame(
                card, width=140, height=190, corner_radius=5, cursor="hand2"
            )
            cover.pack(pady=(10, 5))
            cover.pack_propagate(False)

            lbl1 = ctk.CTkLabel(
                cover,
                text="Game\nCover",
                text_color="gray50",
                font=ctk.CTkFont(size=16, weight="bold"),
                cursor="hand2",
            )
            lbl1.pack(expand=True)

            lbl2 = ctk.CTkLabel(
                card,
                text=game.get("title"),
                wraplength=145,
                justify="center",
                cursor="hand2",
            )
            lbl2.pack(pady=2)

            def enter(e, c=card):
                c.configure(fg_color="gray25")

            def leave(e, c=card):
                c.configure(fg_color="transparent")

            def click(e, g=game):
                if (
                    hasattr(self, "filter_overlay")
                    and self.filter_overlay.winfo_exists()
                ):
                    self.filter_overlay.destroy()
                self.after(10, self.transition_to, self.build_game_details_screen, g)

            for widget in [card, cover, lbl1, lbl2]:
                widget.bind("<Enter>", enter)
                widget.bind("<Leave>", leave)
                widget.bind("<Button-1>", click)

        if end_idx < len(self.catalog_results):
            self.right_arrow.grid(row=0, column=2, sticky="w")
        else:
            self.right_arrow.grid_remove()

    # ==========================================
    #      SCREEN 3: GAME DETAILS (Catalog)
    # ==========================================
    def build_game_details_screen(self, game):
        self._active_scroll_canvas = None
        self._details_sync_fn = None
        if hasattr(self, "filter_overlay") and self.filter_overlay.winfo_exists():
            self.filter_overlay.destroy()

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        ctk.CTkButton(
            header_frame,
            text="← Back",
            width=60,
            cursor="hand2",
            command=lambda: self.after(
                10, self.transition_to, self.build_adding_game_screen
            ),
        ).pack(side="left")

        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=1, column=0, sticky="nsew", padx=40, pady=20)
        content_frame.grid_columnconfigure(1, weight=1)

        cover_frame = ctk.CTkFrame(content_frame, width=200, height=280)
        cover_frame.grid(row=0, column=0, sticky="n", padx=(0, 30))
        cover_frame.pack_propagate(False)

        ctk.CTkLabel(
            cover_frame,
            text="Game\nCover",
            text_color="gray50",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(expand=True)

        mid_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        mid_frame.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(
            mid_frame,
            text=game.get("title"),
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        ).pack(fill="x")
        desc = game.get("description", "No description available for this title yet.")
        ctk.CTkLabel(
            mid_frame,
            text=desc,
            wraplength=400,
            anchor="nw",
            justify="left",
            text_color="gray75",
        ).pack(fill="both", expand=True, pady=10)

        right_frame = ctk.CTkFrame(content_frame, fg_color="transparent", width=150)
        right_frame.grid(row=0, column=2, sticky="n", padx=(30, 0))
        ctk.CTkLabel(
            right_frame, text="Info & Modes:", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        is_sp, is_mp = self._parse_modes(game)
        modes_to_display = []
        if is_sp:
            modes_to_display.append("Single-Player")
        if is_mp:
            modes_to_display.append("Multi-Player")

        final_mode_text = (
            " & ".join(modes_to_display) if modes_to_display else "Single-Player"
        )
        ctk.CTkLabel(right_frame, text=final_mode_text).pack(anchor="w")

        ctk.CTkButton(
            content_frame,
            text="+ Add Game",
            width=180,
            height=40,
            cursor="hand2",
            command=lambda: self.open_platform_popup(game),
        ).grid(row=1, column=0, columnspan=3, pady=40)

    # ==========================================
    #             POPUP 4: SELECT VERSION
    # ==========================================
    def open_platform_popup(self, game_dict):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Version")
        dialog.geometry("320x220")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="Select Version", font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(20, 15))

        available_platforms = game_dict.get(
            "platforms",
            [
                "PlayStation 4",
                "PlayStation 5",
                "Xbox Series X",
                "PC",
                "Nintendo Switch",
                "Nintendo Switch 2",
            ],
        )
        platform_var = ctk.StringVar(value="-- Select --")
        ctk.CTkOptionMenu(
            dialog, values=available_platforms, variable=platform_var
        ).pack(pady=10)

        def confirm_add():
            selected = platform_var.get()
            if selected == "-- Select --":
                messagebox.showwarning(
                    "Selection Required",
                    "Please select a platform version to continue.",
                )
                return
            try:
                self.service.add_game_to_backlog(game_dict.get("catalog_id"), selected)
                dialog.destroy()
                self.after(10, self.transition_to, self.build_main_hub)
            except ValueError as e:
                dialog.destroy()
                messagebox.showerror("Notice", str(e))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(
            btn_frame, text="+ Add Game", width=120, cursor="hand2", command=confirm_add
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            cursor="hand2",
            fg_color="gray30",
            hover_color="gray20",
            command=dialog.destroy,
        ).pack(side="left", padx=5)