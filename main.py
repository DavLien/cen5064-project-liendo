from data.repositories import JsonCatalogRepository, SqliteGameRepository
from service.catalog_service import CatalogService
from presentation.gui import GameLedgerApp

if __name__ == "__main__":
    catalog_repo = JsonCatalogRepository()
    game_repo = SqliteGameRepository()

    catalog_service = CatalogService(catalog_repo, game_repo)
    
    app = GameLedgerApp(catalog_service)
    app.mainloop()