import json

import pytest

from shortcuts.model import Shortcut
from shortcuts.storage import ShortcutConfiguration, ShortcutStorage


def test_load_returns_empty_configurations_when_file_does_not_exist(tmp_path):
    storage = ShortcutStorage(
        tmp_path / "shortcuts.json",
    )

    assert storage.load() == {
        "calibration": ShortcutConfiguration(),
        "next": ShortcutConfiguration(),
        "previous": ShortcutConfiguration(),
    }


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
        "next": ShortcutConfiguration(),
        "previous": ShortcutConfiguration(),
    }

    storage.save(configurations)

    loaded = storage.load()

    assert loaded == configurations


def test_save_and_load_configuration_without_shortcuts(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    configurations = {
        "calibration": ShortcutConfiguration(),
        "next": ShortcutConfiguration(),
        "previous": ShortcutConfiguration(),
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
        modifiers=frozenset(
            {
                "CTRL",
                "ALT",
                "SHIFT",
                "META",
            }
        ),
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


def test_save_writes_trailing_newline(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    storage.save({})

    assert path.read_text(encoding="utf-8").endswith("\n")


def test_load_rejects_missing_shortcut_slot(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        ValueError,
        match="Invalid shortcut slots",
    ):
        storage.load()


def test_load_rejects_unknown_shortcut_slot(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": null,
                "alternate": null,
                "tertiary": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        ValueError,
        match="Invalid shortcut slots",
    ):
        storage.load()


def test_load_rejects_non_dictionary_action_configuration(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": null
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        TypeError,
        match="Invalid configuration for action",
    ):
        storage.load()


def test_load_rejects_unknown_action(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "foobar": {
                "primary": null,
                "alternate": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        ValueError,
        match="Unknown shortcut action",
    ):
        storage.load()


def test_save_replaces_existing_file_atomically(tmp_path):
    path = tmp_path / "shortcuts.json"
    storage = ShortcutStorage(path)

    storage.save({})

    configurations = {
        "calibration": ShortcutConfiguration(
            primary=Shortcut(
                trigger="F1",
                modifiers=frozenset({"CTRL"}),
            ),
        ),
        "next": ShortcutConfiguration(),
        "previous": ShortcutConfiguration(),
    }

    storage.save(configurations)

    assert storage.load() == configurations
    assert not path.with_suffix(".json.tmp").exists()


def test_load_rejects_non_dictionary_shortcut(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": "invalid",
                "alternate": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        TypeError,
        match="Invalid shortcut data",
    ):
        storage.load()


def test_load_rejects_shortcut_without_trigger(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": {
                    "modifiers": ["CTRL"]
                },
                "alternate": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        ValueError,
        match="missing trigger",
    ):
        storage.load()


def test_load_rejects_non_string_trigger(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": {
                    "trigger": 123,
                    "modifiers": []
                },
                "alternate": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        TypeError,
        match="Invalid shortcut trigger",
    ):
        storage.load()


def test_load_rejects_non_list_modifiers(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": {
                    "trigger": "F1",
                    "modifiers": "CTRL"
                },
                "alternate": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        TypeError,
        match="Invalid shortcut modifiers",
    ):
        storage.load()


def test_load_rejects_non_string_modifier(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": {
                    "trigger": "F1",
                    "modifiers": ["CTRL", 123]
                },
                "alternate": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        TypeError,
        match="Invalid shortcut modifiers",
    ):
        storage.load()


def test_load_accepts_shortcut_without_modifiers(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": {
                    "trigger": "F1"
                },
                "alternate": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    assert storage.load() == {
        "calibration": ShortcutConfiguration(
            primary=Shortcut(
                trigger="F1",
            ),
        ),
        "next": ShortcutConfiguration(),
        "previous": ShortcutConfiguration(),
    }


@pytest.mark.parametrize(
    "data",
    [
        [],
        None,
        "invalid",
    ],
)
def test_load_rejects_non_dictionary_root(tmp_path, data):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        json.dumps(data),
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    with pytest.raises(
        TypeError,
        match="Shortcut configuration data must be a dictionary.",
    ):
        storage.load()


def test_load_adds_missing_required_configurations(tmp_path):
    path = tmp_path / "shortcuts.json"
    path.write_text(
        """
        {
            "calibration": {
                "primary": {
                    "trigger": "D",
                    "modifiers": ["CTRL"]
                },
                "alternate": null
            }
        }
        """,
        encoding="utf-8",
    )

    storage = ShortcutStorage(path)

    assert storage.load() == {
        "calibration": ShortcutConfiguration(
            primary=Shortcut(
                trigger="D",
                modifiers=frozenset({"CTRL"}),
            ),
        ),
        "next": ShortcutConfiguration(),
        "previous": ShortcutConfiguration(),
    }
