# main.py
from data.repositories import (
    JsonCatalogRepository,
    SqliteGameRepository,
    SqliteReviewRepository,
    SqliteSessionRepository,
)
from presentation.gui import GameLedgerApp
from service.catalog_service import CatalogService
from service.review_service import ReviewService
from service.session_service import SessionService

if __name__ == "__main__":
    catalog_repo = JsonCatalogRepository()
    game_repo = SqliteGameRepository()
    session_repo = SqliteSessionRepository()
    review_repo = SqliteReviewRepository()

    catalog_service = CatalogService(catalog_repo, game_repo)
    session_service = SessionService(session_repo, game_repo)
    review_service = ReviewService(game_repo, review_repo, session_service)

    app = GameLedgerApp(catalog_service, session_service, review_service)
    app.mainloop()
