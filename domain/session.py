from dataclasses import dataclass


@dataclass
class PlaySession:
    game_id: int
    date: str
    duration_hours: float
    subject: str = ""
    notes: str = ""
    id: int | None = None
    duration_seconds: float = 0.0


class PlaySessionBuilder:
    """Builds a validated PlaySession step by step with required and optional fields."""

    def __init__(self, game_id: int, date: str, duration_seconds: float):
        self._game_id = game_id
        self._date = date
        self._duration_seconds = duration_seconds
        self._subject = ""
        self._notes = ""
        self._id: int | None = None

    def with_subject(self, subject: str) -> "PlaySessionBuilder":
        self._subject = subject.strip() if subject else ""
        return self

    def with_notes(self, notes: str) -> "PlaySessionBuilder":
        self._notes = notes.strip() if notes else ""
        return self

    def with_id(self, session_id: int | None) -> "PlaySessionBuilder":
        self._id = session_id
        return self

    def build(self) -> PlaySession:
        if self._duration_seconds <= 0:
            raise ValueError("Session duration must be greater than zero.")
        if not self._date or not self._date.strip():
            raise ValueError("Session date must not be empty.")

        duration_hours = self._duration_seconds / 3600.0
        return PlaySession(
            id=self._id,
            game_id=self._game_id,
            date=self._date,
            duration_hours=duration_hours,
            subject=self._subject,
            notes=self._notes,
            duration_seconds=self._duration_seconds,
        )
