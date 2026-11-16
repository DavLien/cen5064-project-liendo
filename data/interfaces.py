from abc import ABC, abstractmethod
from typing import Any

from domain.game import Game
from domain.session import PlaySession

class CatalogRepository(ABC):
    @abstractmethod
    def search_catalog(self, query: str) -> list[dict[str, Any]]: ...
    
    @abstractmethod
    def get_catalog_item(self, catalog_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def get_all_catalog(self) -> list[dict[str, Any]]: ...

class GameRepository(ABC):
    @abstractmethod
    def save_game(self, game: Game) -> Game: ...

    @abstractmethod
    def is_game_in_backlog(self, title: str, platform: str) -> bool: ...

    @abstractmethod
    def get_game(self, game_id: int) -> Game | None: ...

    @abstractmethod
    def update_game(self, game: Game) -> None: ...

class SessionRepository(ABC):
    @abstractmethod
    def save_session(self, session: PlaySession) -> PlaySession: ...
    
    @abstractmethod
    def get_sessions_for_game(self, game_id: int) -> list[PlaySession]: ...