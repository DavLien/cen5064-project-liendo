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
            self.mock_game_repo, self.mock_review_repo, self.mock_session_service
        )

    def test_mark_game_completed_standalone(self):
        # Arrange
        mock_game = Game(
            id=1,
            title="Test Game",
            platform="PC",
            game_modes=["Single-Player"],
            status="In Progress",
            total_hours=10.0,
        )
        self.mock_game_repo.get_game.return_value = mock_game

        # Act
        self.service.mark_game_completed(
            1, "November 22, 2026 06:00:00 PM", 4.5, "Great game!"
        )

        # Assert
        self.mock_review_repo.save_review.assert_called_once()
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.rating, 4.5)
        self.assertEqual(saved_review.review_text, "Great game!")
        self.assertEqual(saved_review.date, "November 22, 2026 06:00:00 PM")
        self.assertEqual(mock_game.status, "Completed")
        self.mock_game_repo.update_game.assert_called_once_with(mock_game)

    def test_mark_game_completed_with_chained_session(self):
        # Arrange
        mock_game = Game(
            id=1,
            title="Test",
            platform="PC",
            game_modes=["Single-Player"],
            status="In Progress",
            total_hours=10.0,
        )
        self.mock_game_repo.get_game.return_value = mock_game

        # This session is simulating one that gui.py ALREADY saved and passed down
        pending = PlaySession(
            game_id=1,
            date="November 22, 2026 06:00 PM",
            duration_hours=1.0,
            duration_seconds=3600.0,
            subject="Final Boss",
            notes="Beat it",
        )

        # Act
        # The ReviewService receives the dummy date, but should override it with the pending session's date
        self.service.mark_game_completed(1, "Dummy Date", 5.0, "Masterpiece", pending)

        # Assert
        # Verify it saved the review
        self.mock_review_repo.save_review.assert_called_once()

        # Verify the review completely inherited the exact timestamp of the chained session
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.date, "November 22, 2026 06:00 PM")

    def test_mark_game_completed_invalid_rating(self):
        # Act & Assert
        with self.assertRaises(ValueError):
            self.service.mark_game_completed(1, "Date", 6.0, "Too high")

        with self.assertRaises(ValueError):
            self.service.mark_game_completed(1, "Date", 4.2, "Not an increment")

    def test_mark_game_completed_zero_rating_ignored(self):
        # Arrange
        mock_game = Game(
            id=1,
            title="Test",
            platform="PC",
            game_modes=["Single-Player"],
            status="In Progress",
            total_hours=10.0,
        )
        self.mock_game_repo.get_game.return_value = mock_game

        # Act (0.0 should be interpreted as 'None/Skipped' instead of throwing an out-of-bounds error)
        self.service.mark_game_completed(1, "Date", 0.0, "Just text")

        # Assert
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertIsNone(saved_review.rating)
