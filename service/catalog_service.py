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

        if self.game_repo.is_game_in_backlog(title, platform.strip()):
            raise ValueError("You've already added this game.")

        game = Game(
            title=title,
            platform=platform.strip(),
            game_modes=catalog_record.get("game_modes", []),
            status="Backlog"
        )
        return self.game_repo.save_game(game)

    def get_all_games(self) -> list[dict[str, Any]]:
        return self.catalog_repo.get_all_catalog()

    def filter_games_by_mode(self, mode: str) -> list[dict[str, Any]]:
        all_games = self.catalog_repo.get_all_catalog()
        if mode == "All":
            return all_games
        return [g for g in all_games if mode in g.get("game_modes", [])]