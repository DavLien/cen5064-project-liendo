import unittest
from unittest.mock import Mock

from domain.game import Game
from domain.session import PlaySession
from service.session_service import SessionService

class TestSessionService(unittest.TestCase):
    def setUp(self):
        self.mock_game_repo = Mock()
        self.mock_session_repo = Mock()
        self.service = SessionService(self.mock_session_repo, self.mock_game_repo)

    def test_log_play_session_updates_hours_and_status(self):
        game = Game(id=1, title="Elden Ring", platform="PS5", game_modes=["Single-Player"], status="Backlog", total_hours=5.0)
        self.mock_game_repo.get_game.return_value = game
        
        def mock_save_session(session):
            session.id = 100
            return session
            
        self.mock_session_repo.save_session.side_effect = mock_save_session

        result = self.service.log_play_session(1, "November 16, 2026", 2.5, "Boss Fight", "Defeated Margit")

        self.assertEqual(game.total_hours, 7.5)
        self.assertEqual(game.status, "In Progress")
        self.mock_game_repo.update_game.assert_called_once_with(game)
        self.assertEqual(result.id, 100)

    # FIX 2: Added the missing boundary test for games that are already active/completed
    def test_log_play_session_keeps_existing_status(self):
        # Arrange: Game is already "Completed"
        game = Game(id=2, title="Hollow Knight", platform="PC", game_modes=["Single-Player"], status="Completed", total_hours=40.33)
        self.mock_game_repo.get_game.return_value = game
        self.mock_session_repo.save_session.return_value = PlaySession(game_id=2, date="Nov 16", duration_hours=0.01)

        # Act
        self.service.log_play_session(game_id=2, date="Nov 16", duration_hours=0.01)

        # Assert: Use assertAlmostEqual for float validation
        self.assertAlmostEqual(game.total_hours, 40.34, places=2)
        self.assertEqual(game.status, "Completed")

    def test_log_play_session_invalid_duration_raises_error(self):
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            self.service.log_play_session(game_id=1, date="November 16, 2026", duration_hours=0.0)

    def test_log_play_session_game_not_found_raises_error(self):
        self.mock_game_repo.get_game.return_value = None
        with self.assertRaisesRegex(ValueError, "not found"):
            self.service.log_play_session(game_id=999, date="November 16, 2026", duration_hours=1.0)