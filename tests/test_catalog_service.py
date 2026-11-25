import unittest
from unittest.mock import MagicMock

from data.interfaces import CatalogRepository, GameRepository
from domain.game import Game
from service.catalog_service import CatalogService


class TestCatalogService(unittest.TestCase):
    def setUp(self):
        self.catalog_repo = MagicMock(spec=CatalogRepository)
        self.game_repo = MagicMock(spec=GameRepository)
        self.service = CatalogService(self.catalog_repo, self.game_repo)

    def test_search_games_returns_ui_list(self):
        expected_results = [{"id": "1", "title": "Elden Ring"}]
        self.catalog_repo.search_catalog.return_value = expected_results

        results = self.service.search_games("Elden Ring")

        self.catalog_repo.search_catalog.assert_called_once_with("Elden Ring")
        self.assertEqual(results, expected_results)

    def test_add_game_to_backlog_success(self):
        self.catalog_repo.get_catalog_item.return_value = {
            "title": "Hades",
            "game_modes": ["Single-Player"],
        }
        self.game_repo.is_game_in_backlog.return_value = False

        # Mock the save_game to simulate returning a game with a generated SQLite PK
        def mock_save(game: Game) -> Game:
            game.id = 42
            return game

        self.game_repo.save_game.side_effect = mock_save

        saved_game = self.service.add_game_to_backlog("cat_789", "PC")

        self.catalog_repo.get_catalog_item.assert_called_once_with("cat_789")
        self.game_repo.save_game.assert_called_once()

        self.assertEqual(saved_game.title, "Hades")
        self.assertEqual(saved_game.platform, "PC")
        self.assertEqual(saved_game.game_modes, ["Single-Player"])
        self.assertEqual(saved_game.status, "Backlog")
        self.assertEqual(saved_game.id, 42)

    def test_add_game_requires_platform(self):
        with self.assertRaisesRegex(
            ValueError, "platform version must be explicitly selected"
        ):
            self.service.add_game_to_backlog("cat_789", "")

        with self.assertRaisesRegex(
            ValueError, "platform version must be explicitly selected"
        ):
            self.service.add_game_to_backlog("cat_789", None)

    def test_add_game_invalid_catalog_id_raises_error(self):
        self.catalog_repo.get_catalog_item.return_value = None

        with self.assertRaisesRegex(ValueError, "not found"):
            self.service.add_game_to_backlog("invalid_id", "PS5")

    # 'Boundary case: Verify the system safely falls back to default values without throwing
    # a KeyError if the raw JSON record is corrupted.
    def test_add_game_handles_missing_json_keys(self):
        self.catalog_repo.get_catalog_item.return_value = {}
        self.game_repo.is_game_in_backlog.return_value = False

        def mock_save(game: Game) -> Game:
            game.id = 99
            return game

        self.game_repo.save_game.side_effect = mock_save

        saved_game = self.service.add_game_to_backlog("cat_corrupt", "Xbox")

        self.assertEqual(saved_game.title, "Unknown Title")
        self.assertEqual(saved_game.game_modes, [])
        self.assertEqual(saved_game.platform, "Xbox")

    def test_filter_backlog_ignores_spaces_and_case(self):
        from domain.game import Game

        self.game_repo.get_all_games.return_value = [
            Game(
                id=1,
                title="Hollow Knight",
                platform="Nintendo Switch",
                game_modes=["Single-Player"],
                status="In Progress",
                total_hours=0.0,
            ),
            Game(
                id=2,
                title="The Legend of Zelda: Breath of the Wild",
                platform="Nintendo Switch",
                game_modes=["Single-Player"],
                status="Completed",
                total_hours=0.0,
            ),
        ]

        results = self.service.filter_backlog("ho l l ow", None, None)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, 1)

    def test_filter_backlog_multi_criteria(self):
        from domain.game import Game

        self.game_repo.get_all_games.return_value = [
            Game(
                id=1,
                title="Hollow Knight",
                platform="Nintendo Switch",
                game_modes=["Single-Player"],
                status="In Progress",
                total_hours=0.0,
            ),
            Game(
                id=2,
                title="Overwatch",
                platform="PC",
                game_modes=["Multi-Player"],
                status="Backlog",
                total_hours=0.0,
            ),
            Game(
                id=3,
                title="Overwatch",
                platform="PlayStation 5",
                game_modes=["Multi-Player"],
                status="Backlog",
                total_hours=0.0,
            ),
        ]

        results = self.service.filter_backlog("over", "PC", "Multi-Player")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, 2)


if __name__ == "__main__":
    unittest.main()
