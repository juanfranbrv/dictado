from __future__ import annotations

from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QLineEdit


class HotkeyInput(QLineEdit):
    """Small text field that can capture a key sequence or accept manual text."""

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        sequence = QKeySequence(event.modifiers().value | event.key()).toString(QKeySequence.SequenceFormat.PortableText)
        if sequence:
            self.setText(sequence.lower().replace("meta", "win"))
            event.accept()
            return
        super().keyPressEvent(event)
