from data.ui_settings_store import UiSettingsStore


def test_load_sidebar_width_returns_default_when_missing(tmp_path):
    store = UiSettingsStore(tmp_path / "ui_settings.json")
    assert store.load_sidebar_width() == 240


def test_save_and_load_sidebar_width_round_trip(tmp_path):
    store = UiSettingsStore(tmp_path / "nested" / "ui_settings.json")
    store.save_sidebar_width(310)
    assert store.load_sidebar_width() == 310


def test_load_sidebar_width_enforces_minimum_and_handles_corrupt_json(tmp_path):
    settings_file = tmp_path / "ui_settings.json"
    store = UiSettingsStore(settings_file)

    store.save_sidebar_width(100)
    assert store.load_sidebar_width(min_width=185) == 185

    settings_file.write_text("{corrupt json", encoding="utf-8")
    assert store.load_sidebar_width() == 240
