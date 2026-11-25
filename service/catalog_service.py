from typing import Any

from data.interfaces import CatalogRepository, GameRepository
from domain.game import Game


class CatalogService:
    def __init__(self, catalog_repo: CatalogRepository, game_repo: GameRepository):
        self.catalog_repo = catalog_repo
        self.game_repo = game_repo

    def search_games(self, query: str) -> list[dict[str, Any]]:
        # Guard clause: Prevent empty/whitespace queries from triggering a full database retrieval.
        if not query or not query.strip():
            return []
        return self.catalog_repo.search_catalog(query)

    def add_game_to_backlog(self, catalog_id: str, platform: str) -> Game:
        if not platform or not platform.strip():
            raise ValueError("A specific platform version must be explicitly selected.")

        catalog_record = self.catalog_repo.get_catalog_item(catalog_id)
        if catalog_record is None:
            raise ValueError(f"Catalog item with ID '{catalog_id}' not found.")

        title = catalog_record.get("title", "Unknown Title")
        platform_str = platform.strip()

        # Check if the game is already in our database (either active or archived)
        all_games = self.game_repo.get_all_games()
        for g in all_games:
            if g.title == title and g.platform == platform_str:
                if g.status.startswith("Archived_"):
                    # RESTORE the archived game to its exact previous library (keeps session data intact!)
                    g.status = g.status.replace("Archived_", "")
                    self.game_repo.update_game(g)
                    return g
                else:
                    raise ValueError("You've already added this game.")

        # If it's a completely new game, add it to Backlog
        game = Game(
            title=title,
            platform=platform_str,
            game_modes=catalog_record.get("game_modes", []),
            status="Backlog",
        )
        return self.game_repo.save_game(game)

    def get_all_games(self) -> list[dict[str, Any]]:
        return self.catalog_repo.get_all_catalog()

    def filter_games_by_mode(self, mode: str) -> list[dict[str, Any]]:
        all_games = self.catalog_repo.get_all_catalog()
        if mode == "All":
            return all_games
        return [g for g in all_games if mode in g.get("game_modes", [])]

    def get_backlog(self) -> list[Game]:
        # Only fetch active games to populate the sidebar (hides archived games)
        return [
            g
            for g in self.game_repo.get_all_games()
            if not g.status.startswith("Archived_")
        ]

    def remove_game(self, game_id: int):
        """
        If in Backlog (no sessions), completely delete.
        Otherwise, archive the status so sessions are preserved and it restores exactly where it left off.
        """
        game = self.game_repo.get_game(game_id)
        if not game:
            return

        if game.status == "Backlog":
            self.game_repo.delete_game(game_id)
        else:
            game.status = "Archived_" + game.status
            self.game_repo.update_game(game)

    def get_catalog_details_by_title(self, title: str) -> dict[str, Any]:
        for item in self.catalog_repo.get_all_catalog():
            if item.get("title", "").lower() == title.lower():
                return item
        return {}

    def update_game_status(self, game_id: int, new_status: str):
        """
        Updates the library status of a game (e.g., moving it to 'Backlog').
        """
        game = self.game_repo.get_game(game_id)
        if game:
            game.status = new_status
            self.game_repo.update_game(game)

    def filter_backlog(
        self, search_query: str, platform: str | None = None, mode: str | None = None
    ) -> list:
        games = self.game_repo.get_all_games()
        games.sort(key=lambda g: g.title.lower())

        filtered = []
        query_clean = search_query.replace(" ", "").lower() if search_query else ""

        for g in games:
            if query_clean and query_clean not in g.title.replace(" ", "").lower():
                continue
            if platform and g.platform != platform:
                continue
            if mode:
                modes = (
                    g.game_modes
                    if isinstance(g.game_modes, list)
                    else [g.game_modes]
                    if g.game_modes
                    else []
                )
                modes_lower = [m.lower() for m in modes]
                if mode == "Single-Player" and not any(
                    "single" in m for m in modes_lower
                ):
                    continue
                if mode == "Multi-Player" and not any(
                    "multi" in m for m in modes_lower
                ):
                    continue
            filtered.append(g)

        return filtered
