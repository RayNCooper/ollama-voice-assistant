"""Settings tab: set the Ollama Cloud API key from inside the app.

The key is saved via :mod:`gui.settings` (a gitignored local file) and pushed
into ``os.environ`` so ``ova.pipeline.chat`` picks it up on the next turn — no
restart required.
"""

import os

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import settings


class SettingsTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel("Settings")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "The assistant's replies run on Ollama Cloud. Paste your API key "
            "here to enable them. It is stored locally and takes effect "
            "immediately - no restart needed."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        root.addWidget(QLabel("Ollama Cloud API key"))
        key_row = QHBoxLayout()
        self.key_field = QLineEdit()
        self.key_field.setEchoMode(QLineEdit.Password)
        self.key_field.setPlaceholderText("Paste your OLLAMA_API_KEY")
        self.key_field.setText(settings.load_api_key())
        key_row.addWidget(self.key_field, stretch=1)

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._on_save)
        key_row.addWidget(self.save_btn)
        root.addLayout(key_row)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        root.addStretch(1)

    def _on_save(self) -> None:
        key = self.key_field.text().strip()
        settings.save_api_key(key)
        os.environ["OLLAMA_API_KEY"] = key
        # Clear/re-show the "missing key" banner on the Chat tab.
        self.controller.on_api_key_changed(bool(key))
        self.status.setText(
            "API key saved." if key else "API key cleared."
        )
