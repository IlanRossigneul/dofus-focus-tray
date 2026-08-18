from pathlib import Path

from shortcuts.model import Shortcut
from shortcuts.storage import ShortcutConfiguration, ShortcutStorage


def test_load_returns_empty_configuration_when_file_does_not_exist(tmp_path):
    storage = ShortcutStorage(
        tmp_path / "shortcuts.json",
    )

    assert storage.load() == {}


def test_save_creates_storage_file(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    storage.save({})

    assert path.exists()


def test_save_and_load_shortcut_configuration(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    configurations = {
        "calibration": ShortcutConfiguration(
            primary=Shortcut(
                trigger="D",
                modifiers=frozenset({"CTRL"}),
            ),
            alternate=Shortcut(
                trigger="BTN_SIDE",
            ),
        ),
    }

    storage.save(configurations)

    loaded = storage.load()

    assert loaded == configurations


def test_save_and_load_configuration_without_shortcuts(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    configurations = {
        "calibration": ShortcutConfiguration(),
    }

    storage.save(configurations)

    assert storage.load() == configurations


def test_save_and_load_multiple_configurations(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    configurations = {
        "calibration": ShortcutConfiguration(
            primary=Shortcut(
                trigger="D",
                modifiers=frozenset({"CTRL"}),
            ),
            alternate=Shortcut(
                trigger="BTN_SIDE",
            ),
        ),
        "next": ShortcutConfiguration(
            primary=Shortcut(
                trigger="RIGHT",
                modifiers=frozenset({"CTRL"}),
            ),
        ),
        "previous": ShortcutConfiguration(
            primary=Shortcut(
                trigger="LEFT",
                modifiers=frozenset({"CTRL"}),
            ),
        ),
    }

    storage.save(configurations)

    assert storage.load() == configurations


def test_save_and_load_shortcut_with_multiple_modifiers(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    shortcut = Shortcut(
        trigger="D",
        modifiers=frozenset({
            "CTRL",
            "ALT",
            "SHIFT",
            "META",
        }),
    )

    configurations = {
        "calibration": ShortcutConfiguration(
            primary=shortcut,
        ),
    }

    storage.save(configurations)

    loaded = storage.load()

    assert loaded["calibration"].primary == shortcut


def test_replacing_shortcut_is_persisted(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    configurations = {
        "calibration": ShortcutConfiguration(
            primary=Shortcut(
                trigger="D",
            ),
        ),
    }

    storage.save(configurations)

    configurations["calibration"].primary = Shortcut(
        trigger="F",
    )

    storage.save(configurations)

    loaded = storage.load()

    assert loaded["calibration"].primary == Shortcut(
        trigger="F",
    )


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "config" / "shortcuts.json"
    storage = ShortcutStorage(path)

    storage.save({})

    assert path.exists()
