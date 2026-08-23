"""GUI settings shim.

The storage itself lives in :mod:`ova.settings` so the FastAPI backend and the
PySide6 GUI read and write the same file (``<REPO_ROOT>/.ova/api_key``).
"""

from ova.settings import load_api_key, mask_api_key, save_api_key

__all__ = ["load_api_key", "save_api_key", "mask_api_key"]
