from tkinter import messagebox

import customtkinter as ctk

from service.catalog_service import CatalogService

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class GameLedgerApp(ctk.CTk):
    def __init__(self, service: CatalogService):
        super().__init__()
        self.service = service
        self.title("GameLedger")
        
        self.geometry("1000x650")
        self.minsize(1000, 650)

        # --- Application State ---
        self.backlog_games = []  
        self.catalog_results = []
        self.current_page = 0
        self.items_per_page = 3
        
        self.saved_search_query = ""
        self.active_filter = None

        self.category_states = {
            "Backlog": False,
            "In Progress": False,
            "Completed": False,
            "Abandoned": False
        }

        self.platform_colors = {
            "PlayStation 5": "white",
            "Xbox Series X": "#007A33",
            "PC": "#00A8E8",
            "Nintendo Switch": "#E60012"
        }

        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Configure>", self._sync_filter_overlay)

        self.build_main_hub()

    def _on_focus_out(self, event):
        if event.widget == self and hasattr(self, "filter_overlay") and self.filter_overlay.winfo_exists():
            self.filter_overlay.destroy()

    def _sync_filter_overlay(self, event=None):
        """Ensures the filter overlay tracks precisely with the filter button."""
        if hasattr(self, "filter_overlay") and self.filter_overlay.winfo_exists() and hasattr(self, "filter_btn") and self.filter_btn.winfo_exists():
            x = self.filter_btn.winfo_rootx() - self.winfo_rootx() - 110
            y = self.filter_btn.winfo_rooty() - self.winfo_rooty() + self.filter_btn.winfo_height() + 5
            self.filter_overlay.place(x=x, y=y)
            self.filter_overlay.lift()

    # ==========================================
    #             FULL SCREEN TRANSITIONS
    # ==========================================
    def navigate_to_add_game_fresh(self):
        self.saved_search_query = ""
        self.active_filter = None
        self.current_page = 0
        self.catalog_loaded_once = False
        self.transition_to(self.build_adding_game_screen)

    def transition_to(self, target_screen_method, *args):
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

    # ==========================================
    #             CAROUSEL SLIDE ANIMATION
    # ==========================================
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
            self.center_container.place(relx=0.5 + self.slide_pos, rely=0.5, anchor="center")
            self.after(15, self._slide_out)
        else:
            self.current_page += self.slide_step
            self.render_catalog_cards()
            self.slide_pos = 1.0 * move_dir
            self.center_container.place(relx=0.5 + self.slide_pos, rely=0.5, anchor="center")
            self._slide_in()

    def _slide_in(self):
        move_dir = -1 if self.slide_step > 0 else 1
        self.slide_pos -= 0.2 * move_dir
        
        if (move_dir < 0 and self.slide_pos < 0.0) or (move_dir > 0 and self.slide_pos > 0.0):
            self.center_container.place(relx=0.5 + self.slide_pos, rely=0.5, anchor="center")
            self.after(15, self._slide_in)
        else:
            self.center_container.place(relx=0.5, rely=0.5, anchor="center")
            self.is_animating = False

    # ==========================================
    #             DATA PARSING HELPER
    # ==========================================
    def _parse_modes(self, game):
        modes = game.get("game_modes", [])
        if isinstance(modes, str):
            modes = [modes]

        modes_lower = [m.lower() for m in modes]
        is_sp = any(m in ["single-player", "singleplayer", "single player"] for m in modes_lower)
        is_mp = any(m in ["multi-player", "multiplayer", "multi player"] for m in modes_lower)
        return is_sp, is_mp

    # ==========================================
    #             SCREEN 1: MAIN HUB
    # ==========================================
    def build_main_hub(self):
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(header_frame, text="GameLedger", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0)
        ctk.CTkButton(header_frame, text="+ Add Game", cursor="hand2", command=lambda: self.after(10, self.navigate_to_add_game_fresh)).grid(row=0, column=2)

        ctk.CTkFrame(self, height=2, fg_color="gray30").grid(row=1, column=0, sticky="ew")

        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.grid(row=2, column=0, sticky="nsew")
        body_frame.grid_rowconfigure(0, weight=1)
        body_frame.grid_columnconfigure(2, weight=1)

        self.sidebar_frame = ctk.CTkFrame(body_frame, width=220, corner_radius=0, fg_color="transparent")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.render_sidebar()

        ctk.CTkFrame(body_frame, width=2, fg_color="gray30").grid(row=0, column=1, sticky="ns")

        main_view = ctk.CTkFrame(body_frame, fg_color="transparent")
        main_view.grid(row=0, column=2, sticky="nsew", padx=30, pady=20)
        
        ctk.CTkLabel(main_view, text="Recently/Last Played -", font=ctk.CTkFont(size=18)).pack(anchor="w", pady=(0, 20))

        games_frame = ctk.CTkFrame(main_view, fg_color="transparent")
        games_frame.pack(fill="x")
        
        for _ in range(3):
            cover = ctk.CTkFrame(games_frame, width=140, height=200, corner_radius=5)
            cover.pack(side="left", padx=(0, 25))
            cover.pack_propagate(False)
            ctk.CTkLabel(cover, text="Game\nCover", text_color="gray50", font=ctk.CTkFont(size=16, weight="bold")).pack(expand=True)
            
        ctk.CTkButton(games_frame, text=">", width=45, height=45, corner_radius=25, font=ctk.CTkFont(size=20), cursor="hand2", fg_color="transparent", border_width=2).pack(side="left", padx=10)

    def render_sidebar(self):
        for widget in self.sidebar_frame.winfo_children():
            widget.destroy()
            
        search_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 20))
        
        ctk.CTkEntry(search_frame, placeholder_text="Search local...").pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(search_frame, text="≡", width=30, cursor="hand2").pack(side="right")

        bold_font = ctk.CTkFont(weight="bold")

        bg_arrow = "v" if self.category_states["Backlog"] else ">"
        ctk.CTkButton(self.sidebar_frame, text=f"{bg_arrow} Backlog ({len(self.backlog_games)})", font=bold_font, anchor="w", fg_color="transparent", hover_color="gray25", cursor="hand2", command=lambda: self.toggle_category("Backlog")).pack(fill="x", pady=2)
        
        if self.category_states["Backlog"]:
            for game in self.backlog_games:
                dot_color = self.platform_colors.get(game["platform"], "gray")
                item_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
                item_frame.pack(fill="x", padx=(15, 0), pady=2)
                ctk.CTkLabel(item_frame, text="●", text_color=dot_color, font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 5))
                ctk.CTkLabel(item_frame, text=game["title"]).pack(side="left")

        for cat in ["In Progress", "Completed", "Abandoned"]:
            arrow = "v" if self.category_states[cat] else ">"
            ctk.CTkButton(self.sidebar_frame, text=f"{arrow} {cat} (0)", font=bold_font, anchor="w", fg_color="transparent", hover_color="gray25", cursor="hand2", command=lambda c=cat: self.toggle_category(c)).pack(fill="x", pady=2)

    def toggle_category(self, cat):
        self.category_states[cat] = not self.category_states[cat]
        self.render_sidebar()

    # ==========================================
    #             SCREEN 2: ADDING GAME
    # ==========================================
    def build_adding_game_screen(self):
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        header_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(header_frame, text="← Back", width=60, cursor="hand2", command=lambda: self.after(10, self.transition_to, self.build_main_hub)).grid(row=0, column=0, padx=(0, 20))

        self.catalog_search = ctk.CTkEntry(header_frame, placeholder_text="Search Catalog...", height=40)
        self.catalog_search.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        if self.saved_search_query:
            self.catalog_search.insert(0, self.saved_search_query) 
        self.catalog_search.bind("<KeyRelease>", self.perform_catalog_search)

        self.filter_btn = ctk.CTkButton(header_frame, text="≡", width=40, height=40, cursor="hand2", command=self.toggle_filter_overlay)
        self.filter_btn.grid(row=0, column=2)

        self.catalog_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.catalog_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        
        self.catalog_frame.grid_rowconfigure(0, weight=1)
        self.catalog_frame.grid_columnconfigure(0, minsize=60) 
        self.catalog_frame.grid_columnconfigure(1, weight=1)   
        self.catalog_frame.grid_columnconfigure(2, minsize=60) 

        self.left_arrow = ctk.CTkButton(self.catalog_frame, text="<", width=45, height=45, corner_radius=25, font=ctk.CTkFont(size=20), 
                                        fg_color="transparent", border_width=2, cursor="hand2", command=lambda: self._paginate_transition(-1))
        self.right_arrow = ctk.CTkButton(self.catalog_frame, text=">", width=45, height=45, corner_radius=25, font=ctk.CTkFont(size=20), 
                                         fg_color="transparent", border_width=2, cursor="hand2", command=lambda: self._paginate_transition(1))

        self.carousel_viewport = ctk.CTkFrame(self.catalog_frame, fg_color="transparent")
        self.carousel_viewport.grid(row=0, column=1, sticky="nsew")

        self.center_container = ctk.CTkFrame(self.carousel_viewport, fg_color="transparent")
        self.center_container.place(relx=0.5, rely=0.5, anchor="center")
        
        if not getattr(self, "catalog_loaded_once", False):
            self.catalog_loaded_once = True
            self.perform_catalog_search(reset_page=False)
        else:
            self.render_catalog_cards()

    # ==========================================
    #             STEAM-STYLE FILTER OVERLAY
    # ==========================================
    def toggle_filter_overlay(self):
        if hasattr(self, "filter_overlay") and self.filter_overlay.winfo_exists():
            self.filter_overlay.destroy()
            return

        self.filter_overlay = ctk.CTkFrame(self, width=150, height=120, border_width=2, border_color="gray25", corner_radius=5)
        self.filter_overlay.pack_propagate(False)
        
        self._sync_filter_overlay()

        ctk.CTkLabel(self.filter_overlay, text="PLAY STATE", font=ctk.CTkFont(size=11, weight="bold"), text_color="#00A8E8").pack(anchor="w", padx=15, pady=(10,5))
        
        self.sp_var = ctk.StringVar(value="checked" if self.active_filter == "Single-Player" else "unchecked")
        self.mp_var = ctk.StringVar(value="checked" if self.active_filter == "Multi-Player" else "unchecked")

        ctk.CTkCheckBox(self.filter_overlay, text="Single player", variable=self.sp_var, onvalue="checked", offvalue="unchecked", command=lambda: self.apply_filter("Single-Player")).pack(anchor="w", padx=15, pady=5)
        ctk.CTkCheckBox(self.filter_overlay, text="Multiplayer", variable=self.mp_var, onvalue="checked", offvalue="unchecked", command=lambda: self.apply_filter("Multi-Player")).pack(anchor="w", padx=15, pady=5)

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
        results = self.service.get_all_games() if not self.saved_search_query.strip() else self.service.search_games(self.saved_search_query)
        
        if self.active_filter:
            filtered = []
            for g in results:
                is_sp, is_mp = self._parse_modes(g)
                if self.active_filter == "Single-Player" and is_sp or self.active_filter == "Multi-Player" and is_mp:
                    filtered.append(g)
            self.catalog_results = filtered
        else:
            self.catalog_results = results
            
        if reset_page or getattr(event, 'keysym', None):
            self.current_page = 0
            
        self.render_catalog_cards()

    def render_catalog_cards(self):
        for widget in self.center_container.winfo_children():
            widget.destroy()

        if not self.catalog_results:
            ctk.CTkLabel(self.center_container, text="No games found.", font=ctk.CTkFont(size=16)).pack(pady=50)
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
            card = ctk.CTkFrame(self.center_container, width=160, height=280, fg_color="transparent", corner_radius=8, cursor="hand2")
            card.pack(side="left", padx=15)
            card.pack_propagate(False)
            
            cover = ctk.CTkFrame(card, width=140, height=190, corner_radius=5, cursor="hand2")
            cover.pack(pady=(10, 5))
            cover.pack_propagate(False)
            
            lbl1 = ctk.CTkLabel(cover, text="Game\nCover", text_color="gray50", font=ctk.CTkFont(size=16, weight="bold"), cursor="hand2")
            lbl1.pack(expand=True)
            
            lbl2 = ctk.CTkLabel(card, text=game.get("title"), wraplength=145, justify="center", cursor="hand2")
            lbl2.pack(pady=2)

            def enter(e, c=card):
                c.configure(fg_color="gray25")
            def leave(e, c=card):
                c.configure(fg_color="transparent")
            def click(e, g=game):
                if hasattr(self, "filter_overlay") and self.filter_overlay.winfo_exists():
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
    #             SCREEN 3: GAME DETAILS
    # ==========================================
    def build_game_details_screen(self, game):
        if hasattr(self, "filter_overlay") and self.filter_overlay.winfo_exists():
            self.filter_overlay.destroy()

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        ctk.CTkButton(header_frame, text="← Back", width=60, cursor="hand2", command=lambda: self.after(10, self.transition_to, self.build_adding_game_screen)).pack(side="left")

        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=1, column=0, sticky="nsew", padx=40, pady=20)
        content_frame.grid_columnconfigure(1, weight=1)

        cover_frame = ctk.CTkFrame(content_frame, width=200, height=280)
        cover_frame.grid(row=0, column=0, sticky="n", padx=(0, 30))
        cover_frame.pack_propagate(False)
        
        ctk.CTkLabel(cover_frame, text="Game\nCover", text_color="gray50", font=ctk.CTkFont(size=16, weight="bold")).pack(expand=True)

        mid_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        mid_frame.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(mid_frame, text=game.get("title"), font=ctk.CTkFont(size=28, weight="bold"), anchor="w").pack(fill="x")
        desc = game.get("description", "No description available for this title yet.")
        ctk.CTkLabel(mid_frame, text=desc, wraplength=400, anchor="nw", justify="left", text_color="gray75").pack(fill="both", expand=True, pady=10)

        right_frame = ctk.CTkFrame(content_frame, fg_color="transparent", width=150)
        right_frame.grid(row=0, column=2, sticky="n", padx=(30, 0))
        ctk.CTkLabel(right_frame, text="Info & Modes:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        
        is_sp, is_mp = self._parse_modes(game)
        modes_to_display = []
        if is_sp: modes_to_display.append("Single-Player")
        if is_mp: modes_to_display.append("Multi-Player")
        
        final_mode_text = " & ".join(modes_to_display) if modes_to_display else "Single-Player"
        ctk.CTkLabel(right_frame, text=final_mode_text).pack(anchor="w")

        ctk.CTkButton(content_frame, text="+ Add Game", width=180, height=40, cursor="hand2", command=lambda: self.open_platform_popup(game)).grid(row=1, column=0, columnspan=3, pady=40)

    # ==========================================
    #             POPUP 4: SELECT VERSION
    # ==========================================
    def open_platform_popup(self, game):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Version")
        dialog.geometry("320x220")
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Select Version", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 15))

        available_platforms = game.get("platforms", ["PlayStation 5", "Xbox Series X", "PC", "Nintendo Switch"])
        
        platform_var = ctk.StringVar(value="-- Select --")
        dropdown = ctk.CTkOptionMenu(dialog, values=available_platforms, variable=platform_var)
        dropdown.pack(pady=10)

        def confirm_add():
            selected = platform_var.get()
            if selected == "-- Select --":
                messagebox.showwarning("Selection Required", "Please select a platform version to continue.")
                return
            try:
                self.service.add_game_to_backlog(game.get("catalog_id"), selected)
                self.backlog_games.append({"title": game.get("title"), "platform": selected})
                dialog.destroy()
                self.after(10, self.transition_to, self.build_main_hub)
            except ValueError as e:
                dialog.destroy()
                messagebox.showerror("Notice", str(e))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        ctk.CTkButton(btn_frame, text="+ Add Game", width=120, cursor="hand2", command=confirm_add).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", width=100, cursor="hand2", fg_color="gray30", hover_color="gray20", command=dialog.destroy).pack(side="left", padx=5)