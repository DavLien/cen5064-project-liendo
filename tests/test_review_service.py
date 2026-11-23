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
        mock_game = Game(
            id=1,
            title="Test",
            platform="PC",
            game_modes=["Single-Player"],
            status="In Progress",
            total_hours=10.0,
        )
        self.mock_game_repo.get_game.return_value = mock_game

        self.service.mark_game_completed(
            1, "November 22, 2026 06:00:00 PM", 4.5, "Great game!"
        )

        self.mock_review_repo.save_review.assert_called_once()
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.rating, 4.5)
        self.assertEqual(saved_review.date, "November 22, 2026 06:00:00 PM")
        self.assertEqual(mock_game.status, "Completed")
        self.mock_game_repo.update_game.assert_called_once_with(mock_game)

    def test_mark_game_completed_with_chained_session(self):
        mock_game = Game(
            id=1,
            title="Test",
            platform="PC",
            game_modes=["Single-Player"],
            status="In Progress",
            total_hours=10.0,
        )
        self.mock_game_repo.get_game.return_value = mock_game

        pending = PlaySession(
            game_id=1,
            date="November 22, 2026 06:00 PM",
            duration_hours=1.0,
            duration_seconds=3600.0,
            subject="Boss",
            notes="Beat it",
        )

        self.service.mark_game_completed(1, "Dummy Date", 5.0, "Masterpiece", pending)

        self.mock_review_repo.save_review.assert_called_once()
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.date, "November 22, 2026 06:00 PM")
        self.assertEqual(mock_game.status, "Completed")

    def test_mark_game_completed_invalid_rating(self):
        with self.assertRaises(ValueError):
            self.service.mark_game_completed(1, "Date", 6.0, "Too high")

    def test_mark_game_completed_zero_rating_ignored(self):
        mock_game = Game(
            id=1,
            title="Test",
            platform="PC",
            game_modes=["Single-Player"],
            status="In Progress",
            total_hours=10.0,
        )
        self.mock_game_repo.get_game.return_value = mock_game

        self.service.mark_game_completed(1, "Date", 0.0, "Just text")

        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertIsNone(saved_review.rating)

    def test_mark_game_abandoned_standalone(self):
        mock_game = Game(
            id=1,
            title="Test",
            platform="PC",
            game_modes=["Single-Player"],
            status="In Progress",
            total_hours=10.0,
        )
        self.mock_game_repo.get_game.return_value = mock_game

        self.service.mark_game_abandoned(
            1, "November 23, 2026 09:00:00 AM", 2.0, "Too hard"
        )

        self.mock_review_repo.save_review.assert_called_once()
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.rating, 2.0)
        self.assertEqual(saved_review.date, "November 23, 2026 09:00:00 AM")
        self.assertEqual(mock_game.status, "Abandoned")
        self.mock_game_repo.update_game.assert_called_once_with(mock_game)

    def test_mark_game_abandoned_with_chained_session(self):
        mock_game = Game(
            id=1,
            title="Test",
            platform="PC",
            game_modes=["Single-Player"],
            status="In Progress",
            total_hours=10.0,
        )
        self.mock_game_repo.get_game.return_value = mock_game

        pending = PlaySession(
            game_id=1,
            date="November 23, 2026 09:00 AM",
            duration_hours=1.0,
            duration_seconds=3600.0,
            subject="Boss",
            notes="Gave up",
        )

        self.service.mark_game_abandoned(1, "Dummy Date", None, None, pending)

        self.mock_review_repo.save_review.assert_called_once()
        saved_review = self.mock_review_repo.save_review.call_args[0][0]
        self.assertEqual(saved_review.date, "November 23, 2026 09:00 AM")
        self.assertEqual(mock_game.status, "Abandoned")
