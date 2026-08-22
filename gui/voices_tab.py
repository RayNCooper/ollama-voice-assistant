"""Voices tab: list voices, pick the active one, and clone a new one.

Cloning always routes through :class:`gui.consent.ConsentDialog`. If the
operator does not tick both boxes, the dialog cannot be accepted and no clone
is created.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import voices as voice_lib
from .consent import ConsentDialog


class VoicesTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self._ready = False
        self._chosen_wav: Path | None = None
        self._current: str | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)

        root.addLayout(self._build_list_panel(), stretch=1)
        root.addWidget(self._build_create_panel(), stretch=1)

    # ------------------------------------------------------ list panel
    def _build_list_panel(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(10)

        title = QLabel("Voices")
        title.setObjectName("sectionTitle")
        col.addWidget(title)

        subtitle = QLabel("Select a voice and set it as the active one for chat.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        col.addWidget(subtitle)

        self.voice_list = QListWidget()
        self.voice_list.itemSelectionChanged.connect(self._refresh_use_button)
        col.addWidget(self.voice_list, stretch=1)

        self.use_btn = QPushButton("Use selected voice")
        self.use_btn.setObjectName("primary")
        self.use_btn.setEnabled(False)
        self.use_btn.clicked.connect(self._on_use_clicked)
        col.addWidget(self.use_btn)

        return col

    # ---------------------------------------------------- create panel
    def _build_create_panel(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        col = QVBoxLayout(card)
        col.setContentsMargins(16, 16, 16, 16)
        col.setSpacing(10)

        title = QLabel("Create a new cloned voice")
        title.setObjectName("sectionTitle")
        col.addWidget(title)

        subtitle = QLabel(
            "Clone a voice from a short (3-30s) reference .wav. You will be "
            "asked to confirm the person has consented before it is created."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        col.addWidget(subtitle)

        col.addWidget(QLabel("Voice name"))
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("e.g. my-voice")
        col.addWidget(self.name_field)

        col.addWidget(QLabel("Reference audio"))
        wav_row = QHBoxLayout()
        self.choose_btn = QPushButton("Choose .wav...")
        self.choose_btn.clicked.connect(self._on_choose_wav)
        wav_row.addWidget(self.choose_btn)
        self.wav_label = QLabel("No file chosen")
        self.wav_label.setObjectName("muted")
        wav_row.addWidget(self.wav_label, stretch=1)
        col.addLayout(wav_row)

        col.addWidget(QLabel("Assistant prompt"))
        self.prompt_field = QPlainTextEdit()
        self.prompt_field.setPlainText(voice_lib.DEFAULT_CLONE_PROMPT)
        col.addWidget(self.prompt_field, stretch=1)

        self.create_btn = QPushButton("Create Voice...")
        self.create_btn.setObjectName("primary")
        self.create_btn.setEnabled(False)
        self.create_btn.clicked.connect(self._on_create_clicked)
        col.addWidget(self.create_btn)

        return card

    # ------------------------------------------------------------ state
    def set_ready(self, ready: bool) -> None:
        self._ready = ready
        self.create_btn.setEnabled(ready and self._chosen_wav is not None)
        self.choose_btn.setEnabled(ready)
        self._refresh_use_button()

    def set_voices(self, voices: list[dict], current: str | None = None) -> None:
        if current is not None:
            self._current = current
        self.voice_list.clear()
        for v in voices:
            tags = []
            if v["cloned"]:
                tags.append("cloned")
            if v["name"] == self._current:
                tags.append("active")
            suffix = f"  ({', '.join(tags)})" if tags else ""
            item = QListWidgetItem(v["name"] + suffix)
            item.setData(Qt.UserRole, v["name"])
            self.voice_list.addItem(item)
        self._refresh_use_button()

    # ----------------------------------------------------------- use voice
    def _refresh_use_button(self) -> None:
        self.use_btn.setEnabled(self._ready and self.voice_list.currentItem() is not None)

    def _on_use_clicked(self) -> None:
        item = self.voice_list.currentItem()
        if item is None:
            return
        self.controller.request_switch.emit(item.data(Qt.UserRole))

    def on_voice_switched(self, name: str) -> None:
        self._current = name
        # Rebuild labels to move the "active" tag.
        names = [
            {
                "name": self.voice_list.item(i).data(Qt.UserRole),
                "cloned": "cloned" in self.voice_list.item(i).text(),
            }
            for i in range(self.voice_list.count())
        ]
        self.set_voices(names, current=name)

    # --------------------------------------------------------- create voice
    def _on_choose_wav(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose reference audio", "", "WAV audio (*.wav)"
        )
        if not path:
            return
        self._chosen_wav = Path(path)
        self.wav_label.setText(self._chosen_wav.name)
        self.create_btn.setEnabled(self._ready)

    def _on_create_clicked(self) -> None:
        # Validate before showing the consent gate so we don't ask for consent
        # on an input that can't work anyway.
        try:
            name = voice_lib.validate_new_name(self.name_field.text())
        except voice_lib.VoiceError as exc:
            QMessageBox.warning(self, "Invalid name", str(exc))
            return
        if self._chosen_wav is None:
            QMessageBox.warning(
                self, "No reference audio", "Choose a .wav file to clone first."
            )
            return

        # MANDATORY consent gate. Blocks unless both boxes are ticked.
        dialog = ConsentDialog(name, self._chosen_wav.name, parent=self)
        if dialog.exec() != ConsentDialog.Accepted:
            return  # consent not given -> clone is blocked

        # Record the acknowledgment to the audit log before any encoding.
        dialog.consent_entry()

        self.create_btn.setEnabled(False)
        self.controller.request_create.emit(
            name, str(self._chosen_wav), self.prompt_field.toPlainText()
        )

    def on_voice_created(self, name: str, voices: list[dict]) -> None:
        self.set_voices(voices)
        self.name_field.clear()
        self._chosen_wav = None
        self.wav_label.setText("No file chosen")
        self.prompt_field.setPlainText(voice_lib.DEFAULT_CLONE_PROMPT)
        self.create_btn.setEnabled(False)
        QMessageBox.information(
            self,
            "Voice created",
            f'Voice "{name}" was created. Select it and click '
            f'"Use selected voice" to chat with it.',
        )

    def on_voice_create_failed(self, message: str) -> None:
        self.create_btn.setEnabled(self._ready and self._chosen_wav is not None)
        QMessageBox.warning(self, "Could not create voice", message)
