from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget


class ConfigWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("dictado - Configuracion")
        self.resize(420, 220)

        label = QLabel("La configuracion completa llegara en la Fase 7.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
