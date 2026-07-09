from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QLabel


class CameraViewWidget(QLabel):
    targetClicked = Signal(int, int)

    def __init__(self) -> None:
        super().__init__("WAITING FOR VISION FEED")
        self.image_width = 640
        self.image_height = 480
        self.setMinimumSize(640, 480)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 1px solid #00E5FF; background: #02040D; color: #8FA6C8;")
        self.setScaledContents(True)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            x = int(event.position().x() * self.image_width / max(1, self.width()))
            y = int(event.position().y() * self.image_height / max(1, self.height()))
            self.targetClicked.emit(x, y)
        super().mousePressEvent(event)

    def set_frame_size(self, width: int, height: int) -> None:
        self.image_width = width
        self.image_height = height
