class WindowsController:
    """Track live Dofus windows and the currently active window."""

    def __init__(self):
        self._windows: list[str] = []
        self._active_window: str | None = None

    @property
    def windows(self) -> list[str]:
        return list(self._windows)

    @property
    def active_window(self) -> str | None:
        return self._active_window

    def update_windows(self, windows: list[str]) -> None:
        self._windows = list(windows)

    def update_active_window(self, uuid: str) -> None:
        self._active_window = uuid
