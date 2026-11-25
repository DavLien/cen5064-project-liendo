import json
from pathlib import Path


class UiSettingsStore:
    """Handles persistence of user interface preferences to disk."""

    def __init__(self, settings_path: str | Path = "data/ui_settings.json"):
        self.settings_path = Path(settings_path)

    def load_sidebar_width(self, min_width: int = 185, default_width: int = 240) -> int:
        try:
            if self.settings_path.exists():
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    width = int(data.get("sidebar_width", default_width))
                    return max(min_width, width)
        except (ValueError, OSError, json.JSONDecodeError):
            pass
        return default_width

    def save_sidebar_width(self, width: int) -> None:
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump({"sidebar_width": int(width)}, f, indent=2)
        except OSError:
            pass
