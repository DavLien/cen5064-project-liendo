from abc import ABC, abstractmethod
from typing import Any

from domain.game import Game
from domain.session import PlaySession
from domain.review import GameReview


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

    # --- NEW FOR STEP 2 ---
    @abstractmethod
    def get_all_games(self) -> list[Game]: ...

    @abstractmethod
    def delete_game(self, game_id: int) -> None: ...


class SessionRepository(ABC):
    @abstractmethod
    def save_session(self, session: PlaySession) -> PlaySession: ...

    @abstractmethod
    def get_sessions_for_game(self, game_id: int) -> list[PlaySession]: ...

    @abstractmethod
    def delete_sessions_for_game(self, game_id: int) -> None: ...

    @abstractmethod
    def update_session(self, session: PlaySession) -> None: ...

    @abstractmethod
    def delete_session(self, session_id: int) -> None: ...

class ReviewRepository(ABC):
    @abstractmethod
    def save_review(self, review: GameReview) -> GameReview: ...

    @abstractmethod
    def get_review_for_game(self, game_id: int) -> GameReview | None: ...

    @abstractmethod
    def delete_review(self, review_id: int) -> None: ...
