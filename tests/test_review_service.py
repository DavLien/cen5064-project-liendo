# tests/test_review_service.py
import unittest
from unittest.mock import MagicMock

from domain.game import Game
from domain.session import PlaySession
from service.review_service import ReviewService

class TestReviewService(unittest.TestCase):
    def setUp(self):
        self.mock_game_repo = MagicMock()
        self.mock_review_repo = MagicMock()
        self.mock_session_service = MagicMock()
        self.service = ReviewService(
            self.mock_game_repo, 
            self.mock_review_repo, 
            self.mock_session_service
        )
        
        self.mock_game = Game(
            id=1, 
            title="Elden Ring", 
            platform="PS5", 
            game_modes=["Single-Player"], 
            status="In Progress", 
            total_hours=10.0
        )
        self.mock_game_repo.get_game.return_value = self.mock_game

    def test_mark_completed_invalid_rating_raises_error(self):
        # Fixed: Explicitly testing the boundaries at 0.0 and 6.0
        with self.assertRaisesRegex(ValueError, "between 0.5 and 5.0"):
            self.service.mark_game_completed(game_id=1, rating=0.0)
            
        with self.assertRaisesRegex(ValueError, "between 0.5 and 5.0"):
            self.service.mark_game_completed(game_id=1, rating=6.0)
            
        with self.assertRaisesRegex(ValueError, "0.5 increments"):
            self.service.mark_game_completed(game_id=1, rating=4.3)

    def test_mark_completed_valid_half_star_rating_passes(self):
        # Fixed: Ensuring the 0.5 lower boundary passes successfully
        self.service.mark_game_completed(game_id=1, rating=0.5)
        self.assertEqual(self.mock_game.status, "Completed")
        self.mock_review_repo.save_review.assert_called_once()
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.rating, 0.5)

    def test_mark_completed_standalone_with_review(self):
        self.service.mark_game_completed(
            game_id=1, 
            rating=4.5, 
            review_text="Amazing game!"
        )
        
        self.assertEqual(self.mock_game.status, "Completed")
        self.mock_game_repo.update_game.assert_called_once_with(self.mock_game)
        
        self.mock_review_repo.save_review.assert_called_once()
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.rating, 4.5)
        self.assertEqual(saved_review.review_text, "Amazing game!")
        
        # Verify no session logic invoked
        self.mock_session_service.log_play_session.assert_not_called()

    def test_mark_completed_standalone_with_skip(self):
        self.service.mark_game_completed(game_id=1, rating=None, review_text=None)
        
        self.assertEqual(self.mock_game.status, "Completed")
        self.mock_game_repo.update_game.assert_called_once_with(self.mock_game)
        self.mock_review_repo.save_review.assert_not_called()

    def test_mark_completed_chained_with_pending_session(self):
        pending_session = PlaySession(
            game_id=1, 
            date="Nov 16, 2026", 
            duration_seconds=7200, 
            duration_hours=2.0,
            subject="Final Boss",
            notes="Defeated!"
        )
        
        self.service.mark_game_completed(
            game_id=1, 
            rating=5.0, 
            review_text=None, 
            pending_session=pending_session
        )
        
        # Verify session service is routed legally
        self.mock_session_service.log_play_session.assert_called_once_with(
            game_id=1,
            date="Nov 16, 2026",
            duration_seconds=7200,
            subject="Final Boss",
            notes="Defeated!"
        )
        
        # Verify review is saved
        self.mock_review_repo.save_review.assert_called_once()
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.rating, 5.0)
        
        # Verify status transition
        self.assertEqual(self.mock_game.status, "Completed")
        self.mock_game_repo.update_game.assert_called_once_with(self.mock_game)