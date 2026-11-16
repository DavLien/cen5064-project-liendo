from data.interfaces import GameRepository, SessionRepository
from domain.session import PlaySession

class SessionService:
    def __init__(self, session_repo: SessionRepository, game_repo: GameRepository):
        self.session_repo = session_repo
        self.game_repo = game_repo

    def log_play_session(self, game_id: int, date: str, duration_hours: float, subject: str = "", notes: str = "") -> PlaySession:
        if duration_hours <= 0:
            raise ValueError("Session duration must be greater than zero.")

        game = self.game_repo.get_game(game_id)
        if game is None:
            raise ValueError(f"Game with ID '{game_id}' not found.")

        # FIX 1: Prevent floating-point precision garbage from polluting the database
        game.total_hours = round(game.total_hours + duration_hours, 2)

        # Status transition logic
        if game.status == "Backlog":
            game.status = "In Progress"

        self.game_repo.update_game(game)

        session = PlaySession(
            game_id=game_id,
            date=date,
            duration_hours=duration_hours,
            subject=subject,
            notes=notes
        )
        
        return self.session_repo.save_session(session)