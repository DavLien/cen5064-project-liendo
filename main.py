from tkinter import messagebox

import customtkinter as ctk

from data.repositories import JsonCatalogRepository, SqliteGameRepository
from service.catalog_service import CatalogService

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class GameLedgerApp(ctk.CTk):
    def __init__(self, service: CatalogService):
        super().__init__()
        self.service = service
        self.title("GameLedger")
        self.geometry("900x600")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- Sidebar ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="GameLedger", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Collapsible Backlog Dropdown
        self.is_backlog_expanded = True
        self.backlog_count = 0
        self.backlog_ui_items = []

        self.backlog_btn = ctk.CTkButton(
            self.sidebar_frame, text="v Backlog (0)", anchor="w", 
            fg_color="transparent", hover_color="gray25", command=self.toggle_backlog
        )
        self.backlog_btn.grid(row=1, column=0, padx=10, pady=10, sticky="ew")

        # Container for the added games
        self.backlog_list_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.backlog_list_frame.grid(row=2, column=0, padx=25, sticky="ew")

        # --- Main View ---
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Top Bar: Search and Filter
        self.top_bar = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.top_bar.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(self.top_bar, placeholder_text="Search Catalog...", height=40)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.perform_search)

        self.filter_btn = ctk.CTkButton(self.top_bar, text="≡", width=40, height=40, command=self.open_filter_dialog)
        self.filter_btn.grid(row=0, column=1, padx=(0, 0))

        # Search Results Area
        self.results_frame = ctk.CTkScrollableFrame(self.main_frame, label_text="Catalog Results")
        self.results_frame.grid(row=1, column=0, sticky="nsew")

        # Initial Load: Show all games
        self.render_catalog_results(self.service.get_all_games())

    def toggle_backlog(self):
        self.is_backlog_expanded = not self.is_backlog_expanded
        symbol = "v" if self.is_backlog_expanded else ">"
        self.backlog_btn.configure(text=f"{symbol} Backlog ({self.backlog_count})")
        
        if self.is_backlog_expanded:
            self.backlog_list_frame.grid(row=2, column=0, padx=25, sticky="ew")
        else:
            self.backlog_list_frame.grid_remove()

    def perform_search(self, event):
        query = self.search_entry.get()
        if not query.strip():
            self.render_catalog_results(self.service.get_all_games())
        else:
            self.render_catalog_results(self.service.search_games(query))

    def open_filter_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Filter Catalog")
        dialog.geometry("250x150")
        dialog.attributes("-topmost", True)
        
        # Grab set makes the window modal (freezes the main app)
        dialog.grab_set()

        filter_var = ctk.StringVar(value="-- Select --")
        # Swapped to OptionMenu to prevent typing
        dropdown = ctk.CTkOptionMenu(dialog, values=["All", "Single-Player", "Multi-Player"], variable=filter_var)
        dropdown.pack(pady=20)

        def apply_filter():
            selection = filter_var.get()
            if selection == "-- Select --":
                selection = "All"  # Safety fallback
            results = self.service.filter_games_by_mode(selection)
            self.render_catalog_results(results)
            dialog.destroy()

        ctk.CTkButton(dialog, text="Apply Filter", command=apply_filter).pack()

    def render_catalog_results(self, results):
        for widget in self.results_frame.winfo_children():
            widget.destroy()
            
        # Force the scrollbar back to the top to prevent empty screens
        self.results_frame._parent_canvas.yview_moveto(0)

        if not results:
            ctk.CTkLabel(self.results_frame, text="No games found.").pack(pady=20)
            return

        for game in results:
            card = ctk.CTkFrame(self.results_frame)
            card.pack(fill="x", pady=5, padx=5)
            
            title_lbl = ctk.CTkLabel(card, text=game.get("title"), font=ctk.CTkFont(weight="bold"))
            title_lbl.pack(side="left", padx=10, pady=10)

            # Extract the strings first to satisfy Ruff's B008 rule
            current_id = game.get("catalog_id")
            current_title = game.get("title")

            add_btn = ctk.CTkButton(
                card, text="+ Add Game", width=100,
                # Pass the variables directly instead of using .get() inside the lambda
                command=lambda c_id=current_id, t=current_title: self.open_platform_dialog(c_id, t)
            )
            add_btn.pack(side="right", padx=10, pady=10)

    def open_platform_dialog(self, catalog_id: str, title: str):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Version")
        dialog.geometry("300x200")
        dialog.attributes("-topmost", True)
        
        # Grab set makes the window modal (freezes the main app)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=f"Adding: {title}", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 10))

        platform_var = ctk.StringVar(value="-- Select --")
        platforms = ["PlayStation 5", "Xbox Series X", "PC", "Nintendo Switch"]
        # Swapped to OptionMenu to prevent typing
        dropdown = ctk.CTkOptionMenu(dialog, values=platforms, variable=platform_var)
        dropdown.pack(pady=10)

        def confirm_add():
            selected_platform = platform_var.get()
            
            # Validation rule
            if selected_platform == "-- Select --":
                messagebox.showwarning("Selection Required", "Please select a platform version to continue.")
                return
                
            try:
                saved_game = self.service.add_game_to_backlog(catalog_id, selected_platform)
                
                self.backlog_count += 1
                symbol = "v" if self.is_backlog_expanded else ">"
                self.backlog_btn.configure(text=f"{symbol} Backlog ({self.backlog_count})")
                
                display_title = saved_game.title if len(saved_game.title) < 18 else saved_game.title[:15] + "..."
                new_item = ctk.CTkLabel(self.backlog_list_frame, text=display_title, anchor="w", text_color="gray75")
                new_item.pack(fill="x", pady=2)
                self.backlog_ui_items.append(new_item)

                dialog.destroy()
            except ValueError as e:
                # Destroy the popup screen immediately as requested
                dialog.destroy()
                # Show the error message to the user on the main screen
                messagebox.showerror("Notice", str(e))

        ctk.CTkButton(dialog, text="Confirm Add", command=confirm_add).pack(pady=10)


if __name__ == "__main__":
    catalog_repo = JsonCatalogRepository()
    game_repo = SqliteGameRepository()
    catalog_service = CatalogService(catalog_repo, game_repo)
    app = GameLedgerApp(catalog_service)
    app.mainloop()