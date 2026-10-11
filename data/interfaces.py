from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

from domain.game import Game

class CatalogRepository(ABC):
    @abstractmethod
    def search_catalog(self, query: str) -> List[Dict[str, Any]]: ...
    
    @abstractmethod
    def get_catalog_item(self, catalog_id: str) -> Optional[Dict[str, Any]]: ...

class GameRepository(ABC):
    @abstractmethod
    def save_game(self, game: Game) -> Game: ...