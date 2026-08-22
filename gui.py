#!/usr/bin/env python3
"""Entry point for the Ollama Voice Assistant desktop GUI.

Run with::

    OLLAMA_API_KEY=your_key python gui.py

Requires the optional ``gui`` extra (PySide6 + sounddevice):

    pip install ".[gui]"

The GUI imports ``ova.pipeline`` directly and runs everything in one process:
local ASR + TTS, with the LLM on Ollama Cloud.
"""

import sys


def main() -> int:
    try:
        from gui.app import main as run
    except ImportError as exc:
        sys.stderr.write(
            f"Could not start the GUI ({exc}).\n"
            "Install the GUI extra first:\n\n"
            "    pip install \".[gui]\"\n\n"
        )
        return 1
    return run()


if __name__ == "__main__":
    sys.exit(main())
