from pathlib import Path

from KStatusNotifierItem import KStatusNotifierItem
from PySide6.QtGui import QPixmap


def create_indicator(icon_dir: Path) -> KStatusNotifierItem:
    """Create and configure the Dofus Focus tray indicator."""
    indicator = KStatusNotifierItem()

    indicator.setIconByPixmap(
        QPixmap(str(icon_dir / "dofus.webp"))
    )

    indicator.setTitle("Dofus Focus")
    indicator.setToolTipTitle("Dofus Focus")
    indicator.setIsMenu(True)
    indicator.setStandardActionsEnabled(True)
    indicator.setStatus(KStatusNotifierItem.ItemStatus.Passive)

    return indicator
