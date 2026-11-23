from data.interfaces import GameRepository, ReviewRepository
from domain.session import PlaySession
from domain.review import GameReview
from service.session_service import SessionService

class ReviewService:
    def __init__(
        self, 
        game_repo: GameRepository, 
        review_repo: ReviewRepository, 
        session_service: SessionService
    ):
        self.game_repo = game_repo
        self.review_repo = review_repo
        self.session_service = session_service

    def mark_game_completed(
        self, 
        game_id: int, 
        date: str, 
        rating: float | None = None, 
        review_text: str | None = None, 
        pending_session: PlaySession | None = None
    ) -> None:
        
        # 1. Validate constraints
        if rating is not None and rating > 0.0:
            if not (0.5 <= rating <= 5.0):
                raise ValueError("Rating must be between 0.5 and 5.0 stars.")
            if rating % 0.5 != 0:
                raise ValueError("Rating must be in 0.5 increments.")

        # 2. Extract perfectly synchronized date
        final_date = date
        if pending_session:
            if pending_session.game_id != game_id:
                raise ValueError("Pending session game_id does not match target game_id.")
            
            # The session was already securely saved by the UI before reaching this step.
            # We ONLY need to inherit its exact timestamp to guarantee a perfect UI merge.
            final_date = pending_session.date

        # 3. Fetch parent entity
        game = self.game_repo.get_game(game_id)
        if not game:
            raise ValueError(f"Game with ID {game_id} not found.")

        # 4. Save review feedback (ALWAYS save to record the completion event)
        has_text = bool(review_text and review_text.strip())
        review = GameReview(
            game_id=game_id, 
            date=final_date, 
            rating=rating if rating and rating > 0.0 else None, 
            review_text=review_text.strip() if has_text else None
        )
        self.review_repo.save_review(review)

        # 5. Execute state transition and update aggregate data
        game.status = "Completed"
        game.total_hours = round(game.total_hours, 2)
        self.game_repo.update_game(game)