from dataclasses import dataclass


@dataclass
class GameReview:
    game_id: int
    date: str
    rating: float | None = None
    review_text: str | None = None
    status_type: str = "Completed"
    id: int = 0
