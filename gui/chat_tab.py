"""Chat tab: record the mic, run a turn through the pipeline, hear the reply."""

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .audio_io import AudioError, MicRecorder


class ChatTab(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.recorder = MicRecorder()
        self._ready = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel("Voice chat")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Hold a conversation: record your voice, and the assistant "
            "transcribes, replies, and speaks back."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # API-key warning banner (hidden unless the key is missing).
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        self.banner_label = QLabel(
            "No Ollama Cloud API key set. Speech recognition and playback work, "
            "but the assistant cannot reply until you add your key in the "
            "Settings tab (it takes effect right away - no restart needed)."
        )
        self.banner_label.setObjectName("warning")
        self.banner_label.setWordWrap(True)
        banner_layout.addWidget(self.banner_label)
        self.banner.setVisible(False)
        root.addWidget(self.banner)

        self.conversation = QTextEdit()
        self.conversation.setReadOnly(True)
        root.addWidget(self.conversation, stretch=1)

        controls = QHBoxLayout()
        self.record_btn = QPushButton("Record")
        self.record_btn.setObjectName("record")
        self.record_btn.setCheckable(True)
        self.record_btn.setEnabled(False)
        self.record_btn.toggled.connect(self._on_record_toggled)
        controls.addWidget(self.record_btn)

        self.hint = QLabel("Loading models...")
        self.hint.setObjectName("muted")
        controls.addWidget(self.hint)
        controls.addStretch(1)
        root.addLayout(controls)

    # ------------------------------------------------------------- state
    def set_ready(self, ready: bool) -> None:
        self._ready = ready
        self.record_btn.setEnabled(ready)
        if ready:
            self.hint.setText("Click Record, speak, then click again to send.")

    def set_api_key_warning(self, missing: bool) -> None:
        self.banner.setVisible(missing)

    def set_processing(self, processing: bool) -> None:
        # While a turn is in flight, block re-recording but keep the button
        # readable.
        if processing:
            self.record_btn.setEnabled(False)
            self.hint.setText("Working...")
        else:
            self.record_btn.setEnabled(self._ready)
            if self._ready:
                self.hint.setText("Click Record, speak, then click again to send.")

    # ------------------------------------------------------------- record
    def _on_record_toggled(self, checked: bool) -> None:
        if checked:
            try:
                self.recorder.start()
            except AudioError as exc:
                self.record_btn.setChecked(False)
                QMessageBox.warning(self, "Microphone unavailable", str(exc))
                return
            self.record_btn.setText("Stop & Send")
            self.hint.setText("Recording... click Stop & Send when done.")
        else:
            self.record_btn.setText("Record")
            try:
                wav_bytes = self.recorder.stop()
            except AudioError as exc:
                QMessageBox.warning(self, "Recording failed", str(exc))
                self.set_processing(False)
                return
            if not wav_bytes:
                self.hint.setText("Nothing recorded. Try again.")
                return
            self.set_processing(True)
            self.controller.request_turn.emit(wav_bytes)

    # -------------------------------------------------------- transcript
    def _append(self, who: str, text: str, color: str) -> None:
        self.conversation.append(
            f'<p style="margin:6px 0;"><b style="color:{color};">{who}:</b> '
            f'{_escape(text)}</p>'
        )

    def append_user(self, text: str) -> None:
        self._append("You", text, theme.MUTED)

    def append_assistant(self, text: str) -> None:
        self._append("Assistant", text, theme.ACCENT)

    def on_turn_empty(self) -> None:
        self.hint.setText("Didn't catch that - nothing was transcribed. Try again.")
        self.set_processing(False)

    def on_turn_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Chat failed", message)
        self.set_processing(False)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
