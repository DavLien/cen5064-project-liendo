from abc import ABC, abstractmethod
from typing import Any

from domain.game import Game


class CatalogRepository(ABC):
    @abstractmethod
    def search_catalog(self, query: str) -> list[dict[str, Any]]: ...
    
    @abstractmethod
    def get_catalog_item(self, catalog_id: str) -> dict[str, Any] | None: ...

class GameRepository(ABC):
    @abstractmethod
    def save_game(self, game: Game) -> Game: ...