from PySide6.QtWidgets import QPlainTextEdit

from ..utils.logging_utils import ts


class LogConsole(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)

    def log(self, message: str) -> None:
        self.appendPlainText(f"[{ts()}] {message}")


LogConsoleWidget = LogConsole
