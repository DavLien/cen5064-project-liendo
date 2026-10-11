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

        # Explicitly check for None. An empty database {} means the record exists but is
        # corrupted, which we want to handle safely below.
        if catalog_record is None:
            raise ValueError(f"Catalog item with ID '{catalog_id}' not found.")

        game = Game(
            title=catalog_record.get("title", "Unknown Title"),
            platform=platform.strip(),
            game_modes=catalog_record.get("game_modes", []),
            status="Backlog"
        )

        return self.game_repo.save_game(game)