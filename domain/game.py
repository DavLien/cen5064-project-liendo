from dataclasses import dataclass


@dataclass
class Game:
    title: str
    platform: str
    game_modes: list[str]
    status: str = "Backlog"
    id: int | None = None