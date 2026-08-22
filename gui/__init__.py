"""Cross-platform desktop GUI (PySide6/Qt) for the Ollama Voice Assistant.

Olio-branded desktop front-end that replaces the web UI for the primary
experience. It talks to :mod:`ova.pipeline` directly (single process) for voice
chat, and provides a voice-cloning workflow gated behind a mandatory consent
dialog.

Entry point: ``gui.py`` at the repo root (``python gui.py``).
"""
