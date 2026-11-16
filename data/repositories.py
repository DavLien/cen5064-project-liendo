import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from data.interfaces import CatalogRepository, GameRepository, SessionRepository
from domain.game import Game
from domain.session import PlaySession


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
            
            # NOTE: Removed 'DROP TABLE IF EXISTS games' so your added games persist between app restarts.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    game_modes TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_hours REAL NOT NULL DEFAULT 0.0
                )
            """)
            conn.commit()

    def save_game(self, game: Game) -> Game:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            modes_str = json.dumps(game.game_modes)
            
            cursor.execute("""
                INSERT INTO games (title, platform, game_modes, status, total_hours)
                VALUES (?, ?, ?, ?, ?)
            """, (game.title, game.platform, modes_str, game.status, game.total_hours))
            
            conn.commit()
            game.id = cursor.lastrowid
            
        return game

    def get_game(self, game_id: int) -> Game | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, platform, game_modes, status, total_hours FROM games WHERE id = ?", (game_id,))
            row = cursor.fetchone()
            
            if row:
                return Game(
                    id=row[0],
                    title=row[1],
                    platform=row[2],
                    game_modes=json.loads(row[3]),
                    status=row[4],
                    total_hours=row[5]
                )
            return None

    def update_game(self, game: Game) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            modes_str = json.dumps(game.game_modes)
            cursor.execute("""
                UPDATE games 
                SET title = ?, platform = ?, game_modes = ?, status = ?, total_hours = ?
                WHERE id = ?
            """, (game.title, game.platform, modes_str, game.status, game.total_hours, game.id))
            conn.commit()

    def is_game_in_backlog(self, title: str, platform: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM games 
                WHERE title = ? AND platform = ?
            """, (title, platform))
            return cursor.fetchone() is not None

    def get_all_games(self) -> list[Game]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, platform, game_modes, status, total_hours FROM games")
            games = []
            for row in cursor.fetchall():
                games.append(Game(
                    id=row[0],
                    title=row[1],
                    platform=row[2],
                    game_modes=json.loads(row[3]),
                    status=row[4],
                    total_hours=row[5]
                ))
            return games

    def delete_game(self, game_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM games WHERE id = ?", (game_id,))
            conn.commit()


class SqliteSessionRepository(SessionRepository):
    """Manages saving and loading individual play sessions."""
    
    def __init__(self, db_path: str = "data/gameledger.db"):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS play_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    duration_hours REAL NOT NULL,
                    subject TEXT,
                    notes TEXT,
                    FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def save_session(self, session: PlaySession) -> PlaySession:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO play_sessions (game_id, date, duration_hours, subject, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (session.game_id, session.date, session.duration_hours, session.subject, session.notes))
            
            conn.commit()
            session.id = cursor.lastrowid
            
        return session

    def get_sessions_for_game(self, game_id: int) -> list[PlaySession]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Fetches in descending order so the newest sessions appear at the top of the UI accordion
            cursor.execute("""
                SELECT id, game_id, date, duration_hours, subject, notes 
                FROM play_sessions 
                WHERE game_id = ?
                ORDER BY id DESC
            """, (game_id,))
            
            sessions = []
            for row in cursor.fetchall():
                sessions.append(PlaySession(
                    id=row[0],
                    game_id=row[1],
                    date=row[2],
                    duration_hours=row[3],
                    subject=row[4],
                    notes=row[5]
                ))
            return sessions