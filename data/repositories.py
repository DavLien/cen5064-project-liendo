import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from data.interfaces import CatalogRepository, GameRepository
from domain.game import Game


class JsonCatalogRepository(CatalogRepository):
    def __init__(self, file_path: str = "data/games.json"):
        self.file_path = Path(file_path)

    def _load_data(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        with open(self.file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def get_all_catalog(self) -> list[dict[str, Any]]:
        return self._load_data()

    def search_catalog(self, query: str) -> list[dict[str, Any]]:
        data = self._load_data()
        # Remove spaces and non-alphanumeric characters for forgiving/fuzzy search
        clean_query = re.sub(r'[^a-z0-9]', '', query.lower())
        results = []
        for game in data:
            clean_title = re.sub(r'[^a-z0-9]', '', game.get("title", "").lower())
            if clean_query in clean_title:
                results.append(game)
        return results

    def get_catalog_item(self, catalog_id: str) -> dict[str, Any] | None:
        data = self._load_data()
        for game in data:
            if game.get("catalog_id") == catalog_id:
                return game
        return None


class SqliteGameRepository(GameRepository):
    """Persists the user's backlog into a local SQLite database."""
    
    def __init__(self, db_path: str = "data/gameledger.db"):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("DROP TABLE IF EXISTS games")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    game_modes TEXT NOT NULL,
                    status TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_game(self, game: Game) -> Game:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # SQLite does not natively support Python lists. 
            # We must convert the list of game_modes into a JSON string before inserting it.
            modes_str = json.dumps(game.game_modes)
            
            cursor.execute("""
                INSERT INTO games (title, platform, game_modes, status)
                VALUES (?, ?, ?, ?)
            """, (game.title, game.platform, modes_str, game.status))
            
            conn.commit()
            
            # Retrieve the auto-generated Primary Key from SQLite and assign it to the entity
            game.id = cursor.lastrowid
            
        return game

    def is_game_in_backlog(self, title: str, platform: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM games 
                WHERE title = ? AND platform = ?
            """, (title, platform))
            return cursor.fetchone() is not None