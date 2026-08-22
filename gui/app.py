"""Main window: wires the tabs to the background pipeline worker."""

import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
)

from . import theme
from .chat_tab import ChatTab
from .voices_tab import VoicesTab
from .worker import PipelineWorker


class MainWindow(QMainWindow):
    # UI-thread -> worker requests (delivered as queued calls across threads).
    request_turn = Signal(object)          # wav bytes
    request_create = Signal(str, str, str)  # name, wav path, prompt
    request_switch = Signal(str)            # profile name

    def __init__(self):
        super().__init__()
        self.setWindowTitle(theme.APP_TITLE)
        self.resize(920, 640)

        self.chat_tab = ChatTab(self)
        self.voices_tab = VoicesTab(self)

        tabs = QTabWidget()
        tabs.addTab(self.chat_tab, "Chat")
        tabs.addTab(self.voices_tab, "Voices")
        self.setCentralWidget(tabs)

        self.statusBar().showMessage("Starting...")

        self._start_worker()

    # ------------------------------------------------------------ worker
    def _start_worker(self) -> None:
        self.thread = QThread(self)
        self.worker = PipelineWorker()
        self.worker.moveToThread(self.thread)

        # Requests -> worker slots
        self.request_turn.connect(self.worker.process_turn)
        self.request_create.connect(self.worker.create_voice)
        self.request_switch.connect(self.worker.switch_voice)

        # Worker signals -> UI
        self.worker.load_started.connect(
            lambda: self.statusBar().showMessage("Loading models...")
        )
        self.worker.loaded.connect(self._on_loaded)
        self.worker.load_failed.connect(self._on_load_failed)
        self.worker.status.connect(self.statusBar().showMessage)

        self.worker.transcribed.connect(self.chat_tab.append_user)
        self.worker.turn_done.connect(self._on_turn_done)
        self.worker.turn_empty.connect(self.chat_tab.on_turn_empty)
        self.worker.turn_failed.connect(self.chat_tab.on_turn_failed)

        self.worker.voice_created.connect(self.voices_tab.on_voice_created)
        self.worker.voice_create_failed.connect(
            self.voices_tab.on_voice_create_failed
        )
        self.worker.voice_switched.connect(self.voices_tab.on_voice_switched)
        self.worker.voice_switch_failed.connect(
            lambda msg: self.statusBar().showMessage(f"Voice switch failed: {msg}")
        )

        # Kick off loading once the thread is running.
        self.thread.started.connect(self.worker.load)
        self.thread.start()

    # ------------------------------------------------------------ handlers
    def _on_loaded(self, voices, current, has_api_key) -> None:
        self.chat_tab.set_ready(True)
        self.chat_tab.set_api_key_warning(not has_api_key)
        self.voices_tab.set_ready(True)
        self.voices_tab.set_voices(voices, current=current)
        self.statusBar().showMessage(f"Ready. Active voice: {current}")

    def _on_load_failed(self, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        self.statusBar().showMessage("Failed to load pipeline.")
        QMessageBox.critical(self, "Startup error", message)

    def _on_turn_done(self, transcript: str, response: str) -> None:
        self.chat_tab.append_assistant(response)
        self.chat_tab.set_processing(False)

    # ------------------------------------------------------------ shutdown
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.thread.quit()
        self.thread.wait(3000)
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(theme.APP_TITLE)
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
