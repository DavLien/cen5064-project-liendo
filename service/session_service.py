from data.interfaces import GameRepository, SessionRepository
from domain.session import PlaySession


class SessionService:
    def __init__(self, session_repo: SessionRepository, game_repo: GameRepository):
        self.session_repo = session_repo
        self.game_repo = game_repo

    def _recalculate_game_hours(self, game_id: int):
        """Helper to recalculate and save a game's total hours when sessions change."""
        sessions = self.session_repo.get_sessions_for_game(game_id)
        total_hours = sum(s.duration_hours for s in sessions)
        game = self.game_repo.get_game(game_id)
        if game:
            game.total_hours = round(total_hours, 2)
            # Automatically revert to Backlog if the last session is deleted
            if not sessions:
                game.status = "Backlog"
            self.game_repo.update_game(game)

    def log_play_session(
        self,
        game_id: int,
        date: str,
        duration_seconds: float,
        subject: str = "",
        notes: str = "",
    ) -> PlaySession:
        if duration_seconds <= 0:
            raise ValueError("Session duration must be greater than zero.")

        game = self.game_repo.get_game(game_id)
        if game is None:
            raise ValueError(f"Game with ID '{game_id}' not found.")

        duration_hours = duration_seconds / 3600.0
        game.total_hours = round(game.total_hours + duration_hours, 2)

        if game.status == "Backlog":
            game.status = "In Progress"

        self.game_repo.update_game(game)

        session = PlaySession(
            game_id=game_id,
            date=date,
            duration_hours=duration_hours,
            subject=subject,
            notes=notes,
            duration_seconds=duration_seconds,
        )

        return self.session_repo.save_session(session)

    def get_sessions_for_game(self, game_id: int) -> list[PlaySession]:
        return self.session_repo.get_sessions_for_game(game_id)

    def delete_all_sessions_for_game(self, game_id: int):
        """
        Permanently deletes all recorded play sessions for a specific game.
        Triggered when a user clicks 'Permanently Wipe Data'.
        """
        self.session_repo.delete_sessions_for_game(game_id)

        # Reset game hours to 0 since all sessions are wiped
        game = self.game_repo.get_game(game_id)
        if game:
            game.total_hours = 0.0
            self.game_repo.update_game(game)

    def edit_play_session(self, session: PlaySession):
        """Saves an edited session and recalculates the game's total playtime."""
        self.session_repo.update_session(session)
        self._recalculate_game_hours(session.game_id)

    def delete_play_session(self, session_id: int, game_id: int):
        """Deletes a single session and recalculates the game's total playtime."""
        self.session_repo.delete_session(session_id)
        self._recalculate_game_hours(game_id)

    def get_total_playtime(self, game_id: int) -> tuple[int, int]:
        sessions = self.session_repo.get_sessions_for_game(game_id)
        # Aggregates exactly recorded seconds from all valid session/review events
        total_seconds = sum(s.duration_seconds for s in sessions)
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        return hours, minutes
