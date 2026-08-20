from pathlib import Path

from PySide6.QtGui import QPixmap
from KStatusNotifierItem import KStatusNotifierItem


def create_indicator(icon_dir: Path) -> KStatusNotifierItem:
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
