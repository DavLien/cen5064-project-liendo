from dataclasses import dataclass

@dataclass
class PlaySession:
    game_id: int
    date: str
    duration_hours: float
    subject: str = ""
    notes: str = ""
    id: int | None = None