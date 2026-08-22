"""Olio brand palette and Qt stylesheet.

Clean and restrained on purpose: real brand colours, no decorative chrome
(no pill badges, no invented geometry). See CLAUDE.md for the brand spec.
"""

# Olio brand colours
ACCENT = "#6366f1"        # indigo
ACCENT_HOVER = "#4f46e5"  # indigo, one step darker for hover
ACCENT_DOWN = "#4338ca"   # pressed
INK = "#1e293b"           # slate-800
MUTED = "#475569"         # slate-600
BORDER = "#e2e8f0"        # slate-200
SURFACE = "#ffffff"
PANEL = "#f8fafc"         # slate-50
DANGER = "#b91c1c"        # red-700 (used sparingly for warnings only)

APP_TITLE = "Ollama Voice Assistant by Olio Solutions"


STYLESHEET = f"""
QWidget {{
    background-color: {SURFACE};
    color: {INK};
    font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
}}

QLabel#h1 {{
    font-size: 20px;
    font-weight: 600;
    color: {INK};
}}
QLabel#subtitle {{
    color: {MUTED};
    font-size: 13px;
}}
QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {INK};
}}
QLabel#muted {{
    color: {MUTED};
}}
QLabel#warning {{
    color: {DANGER};
    font-weight: 600;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background: {PANEL};
    color: {MUTED};
    padding: 8px 20px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {INK};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT};
}}

QPushButton {{
    background-color: {SURFACE};
    color: {INK};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton:hover {{
    border-color: {ACCENT};
}}
QPushButton:disabled {{
    color: #94a3b8;
    border-color: {BORDER};
    background-color: {PANEL};
}}

QPushButton#primary {{
    background-color: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#primary:pressed {{
    background-color: {ACCENT_DOWN};
}}
QPushButton#primary:disabled {{
    background-color: #c7d2fe;
    border-color: #c7d2fe;
    color: white;
}}

QPushButton#record:checked {{
    background-color: {DANGER};
    color: white;
    border-color: {DANGER};
    font-weight: 600;
}}

QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}

QListWidget {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 8px;
    border-radius: 4px;
}}
QListWidget::item:selected {{
    background-color: {ACCENT};
    color: white;
}}

QCheckBox {{
    spacing: 8px;
    color: {INK};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {MUTED};
    border-radius: 4px;
    background: {SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}

QFrame#card {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QFrame#banner {{
    background-color: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 6px;
}}
"""
