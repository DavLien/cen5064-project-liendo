from dataclasses import dataclass


@dataclass
class GameReview:
    game_id: int
    rating: float | None = None
    review_text: str | None = None
    abandoned_reason: str | None = None
    id: int | None = None