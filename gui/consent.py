"""Voice-cloning consent gate and audit log.

Cloning a person's voice without their knowledge is the central ethical risk of
this app. Every clone created through the GUI MUST pass through
:class:`ConsentDialog`, which forces the operator to affirm two independent
facts before the *Create Voice* button is enabled:

  (a) the person has been informed, and
  (b) the person has personally consented.

The acknowledgment is persisted to an append-only audit log
(``consent_log.jsonl`` at the repo root) via :func:`record_consent` so there is
a durable trail of who was cloned and when.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ova.profiles import REPO_ROOT

CONSENT_LOG = REPO_ROOT / "consent_log.jsonl"

CONSENT_QUESTION = (
    "Has the person in this recording been informed and personally consented "
    "to their voice being cloned and used by this app?"
)


def record_consent(profile_name: str, source_audio: str) -> dict:
    """Append a consent acknowledgment to the audit log and return the entry.

    Called only after both consent checkboxes have been ticked and confirmed.
    The log is append-only JSON Lines so entries are never overwritten.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profile": profile_name,
        "source_audio": source_audio,
        "informed": True,
        "consented": True,
        "acknowledgment": CONSENT_QUESTION,
    }
    with CONSENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


class ConsentDialog(QDialog):
    """Modal consent gate. Accepts only when BOTH checkboxes are ticked.

    The *Create Voice* button stays disabled until both boxes are checked, so
    there is no code path that accepts the dialog without consent. Closing the
    dialog any other way (Cancel, Escape, window close) rejects it and blocks
    the clone.
    """

    def __init__(self, profile_name: str, source_audio: str, parent=None):
        super().__init__(parent)
        self.profile_name = profile_name
        self.source_audio = source_audio

        self.setWindowTitle("Voice cloning consent required")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Consent required before cloning")
        title.setObjectName("h1")
        layout.addWidget(title)

        question = QLabel(CONSENT_QUESTION)
        question.setWordWrap(True)
        layout.addWidget(question)

        target = QLabel(
            f'You are about to clone the voice in "{source_audio}" into a new '
            f'profile named "{profile_name}".'
        )
        target.setObjectName("muted")
        target.setWordWrap(True)
        layout.addWidget(target)

        self.informed_box = QCheckBox("The person has been informed")
        self.consented_box = QCheckBox("The person has personally consented")
        layout.addWidget(self.informed_box)
        layout.addWidget(self.consented_box)

        note = QLabel(
            "This acknowledgment is recorded, with a timestamp, to the consent "
            "audit log."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(Qt.Horizontal)
        cancel_btn = buttons.addButton("Cancel", QDialogButtonBox.RejectRole)
        self.create_btn: QPushButton = buttons.addButton(
            "Create Voice", QDialogButtonBox.AcceptRole
        )
        self.create_btn.setObjectName("primary")
        self.create_btn.setEnabled(False)  # gated until both boxes are ticked
        layout.addWidget(buttons)

        cancel_btn.clicked.connect(self.reject)
        self.create_btn.clicked.connect(self._on_accept)
        self.informed_box.toggled.connect(self._refresh_gate)
        self.consented_box.toggled.connect(self._refresh_gate)

    def _refresh_gate(self) -> None:
        both = self.informed_box.isChecked() and self.consented_box.isChecked()
        self.create_btn.setEnabled(both)

    def _on_accept(self) -> None:
        # Belt-and-braces: never accept unless both boxes are genuinely ticked,
        # even if some future change re-enables the button by mistake.
        if not (self.informed_box.isChecked() and self.consented_box.isChecked()):
            return
        self.accept()

    def consent_entry(self) -> dict:
        """Record and return the audit-log entry. Call only after accept()."""
        return record_consent(self.profile_name, self.source_audio)
