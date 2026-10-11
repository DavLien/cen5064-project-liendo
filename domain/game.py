from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class Game:
    title: str
    platform: str
    game_modes: List[str]
    status: str = "Backlog"
    id: Optional[int] = None