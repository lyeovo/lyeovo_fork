from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget


class MissionStatusBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        self.title = QLabel("ORBITAL SNAKE ROBOT MISSION CONTROL")
        self.state = QLabel("Camera: STARTING | Vision: RUNNING | Bridge: FILE MODE | Robot: IDLE | E-STOP: SAFE")
        self.title.setStyleSheet("font-size: 18px; font-weight: 700; color: #00E5FF;")
        self.state.setStyleSheet("color: #2EEA8A; font-family: Consolas;")
        layout.addWidget(self.title)
        layout.addStretch()
        layout.addWidget(self.state)

    def set_state(self, text: str, danger: bool = False) -> None:
        self.state.setText(text)
        self.state.setStyleSheet(f"color: {'#FF4D5A' if danger else '#2EEA8A'}; font-family: Consolas;")
