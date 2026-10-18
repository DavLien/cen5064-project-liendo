from data.repositories import JsonCatalogRepository, SqliteGameRepository
from presentation.gui import GameLedgerApp
from service.catalog_service import CatalogService

if __name__ == "__main__":
    catalog_repo = JsonCatalogRepository()
    game_repo = SqliteGameRepository()

    catalog_service = CatalogService(catalog_repo, game_repo)
    
    app = GameLedgerApp(catalog_service)
    app.mainloop()