from data.repositories import (
    JsonCatalogRepository,
    SqliteGameRepository,
    SqliteSessionRepository,
)
from presentation.gui import GameLedgerApp
from service.catalog_service import CatalogService
from service.session_service import SessionService

if __name__ == "__main__":
    catalog_repo = JsonCatalogRepository()
    game_repo = SqliteGameRepository()
    session_repo = SqliteSessionRepository()

    catalog_service = CatalogService(catalog_repo, game_repo)
    session_service = SessionService(session_repo, game_repo)

    app = GameLedgerApp(catalog_service, session_service)
    app.mainloop()
