# Creational Pattern Map

One line per creational pattern: where it genuinely fits in THIS system, or an honest "no fit." An honest "no" is deliberate — forcing a pattern where nothing needs it is itself a design smell.

| Pattern | Genuine fit here? |
| :--- | :--- |
| **Factory Method** | No genuine fit. Each repository interface (`CatalogRepository`, `GameRepository`, `SessionRepository`, `ReviewRepository`) has only one concrete implementation, and no workflow defers subclass product creation. |
| **Abstract Factory** | No genuine fit. GameLedger uses a single dark-mode UI palette and one local SQLite storage backend, so there are no multiple *families* of matching products to swap at runtime. |
| **Builder** | **Yes — implemented.** `PlaySessionBuilder` (in `domain/session.py`) assembles `PlaySession` objects step by step from required fields (`game_id`, `date`, `duration_seconds`) and optional fields (`subject`, `notes`, `id`), automatically deriving `duration_hours` and replacing duplicated multi-argument construction across `SessionService` and `presentation/gui.py`. |
| **Prototype** | No genuine fit. Every `Game`, `PlaySession`, and `GameReview` is created fresh from catalog records, stopwatch runs, or user input rather than cloned from a pre-configured template. |
| **Singleton** | No genuine fit (intentionally). Persistence stores (`Sqlite*Repository`, `JsonCatalogRepository`, `UiSettingsStore`) are instantiated once at startup and passed via constructor injection rather than accessed through a global singleton, keeping dependencies explicit and testable (DIP). |

**Chosen and implemented:** Builder (`PlaySessionBuilder`), because `PlaySession` combines required timing/identity fields, multiple optional metadata fields, and a coupled `duration_hours = duration_seconds / 3600.0` invariant that was previously duplicated across the service and presentation layers.