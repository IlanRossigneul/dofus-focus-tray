from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu


@dataclass(slots=True)
class MenuWidgets:
    menu: QMenu

    name_item: QAction

    windows_item: QAction
    order_item: QAction
    active_window_item: QAction

    calibration_item: QAction
    shortcuts_item: QAction


def create_menu_item(
    icon_path: Path | None = None,
    text: str = "",
) -> QAction:
    """Create a menu action with an optional icon and text."""
    action = QAction()

    if icon_path is not None:
        action.setIcon(QIcon(str(icon_path)))

    action.setText(text)

    return action


def add_separator(menu: QMenu) -> None:
    """Add a separator to the menu."""
    menu.addSeparator()


def create_menu(menu_icon_dir: Path) -> MenuWidgets:
    """Create the Dofus Focus tray menu and its actions."""
    menu = QMenu()

    name_item = create_menu_item(
        menu_icon_dir / "dofus.webp",
        "Dofus Focus",
    )

    windows_item = create_menu_item(
        menu_icon_dir / "windows.png",
        "Fenêtre : —",
    )

    order_item = create_menu_item(
        menu_icon_dir / "order.png",
        "Ordre : —",
    )

    active_window_item = create_menu_item(
        menu_icon_dir / "active_window.png",
        "Dernière fenêtre active : —",
    )

    calibration_item = create_menu_item(
        menu_icon_dir / "calibration.png",
        "Calibrer les fenêtres",
    )

    shortcuts_item = create_menu_item(
        menu_icon_dir / "shortcuts.png",
        "Configurer les raccourcis",
    )

    menu.addAction(name_item)

    add_separator(menu)

    menu.addAction(windows_item)
    menu.addAction(order_item)
    menu.addAction(active_window_item)

    add_separator(menu)

    menu.addAction(calibration_item)

    add_separator(menu)

    menu.addAction(shortcuts_item)

    return MenuWidgets(
        menu=menu,
        name_item=name_item,
        windows_item=windows_item,
        order_item=order_item,
        active_window_item=active_window_item,
        calibration_item=calibration_item,
        shortcuts_item=shortcuts_item,
    )
