"""Zentrales Farbschema für ein modernes, dunkles UI."""

BG = "#14161c"
BG_ELEVATED = "#1c1f28"
CARD = "#20232e"
CARD_HOVER = "#272b38"
BORDER = "#2e3240"
ACCENT = "#00c2ff"          # GoPro-blau
ACCENT_DARK = "#0090c2"
ACCENT_SOFT = "rgba(0, 194, 255, 0.15)"
TEXT_PRIMARY = "#f2f4f8"
TEXT_SECONDARY = "#9aa1b2"
SUCCESS = "#3ddc84"
DANGER = "#ff5c72"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
    font-size: 14px;
}}

QTabWidget::pane {{
    border: none;
    background-color: {BG};
    top: 8px;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    padding: 10px 22px;
    margin-right: 4px;
    font-weight: 600;
    font-size: 14px;
    border-bottom: 3px solid transparent;
}}

QTabBar::tab:selected {{
    color: {TEXT_PRIMARY};
    border-bottom: 3px solid {ACCENT};
}}

QTabBar::tab:hover:!selected {{
    color: {TEXT_PRIMARY};
}}

QPushButton {{
    background-color: {ACCENT};
    color: #06121a;
    border: none;
    border-radius: 10px;
    padding: 12px 22px;
    font-weight: 700;
    font-size: 14px;
}}

QPushButton:hover {{
    background-color: {ACCENT_DARK};
}}

QPushButton:disabled {{
    background-color: {CARD};
    color: {TEXT_SECONDARY};
}}

QPushButton#secondary {{
    background-color: {CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
}}

QPushButton#secondary:hover {{
    background-color: {CARD_HOVER};
}}

QPushButton#iconButton {{
    background-color: transparent;
    border-radius: 20px;
    padding: 6px;
}}

QPushButton#iconButton:hover {{
    background-color: {CARD_HOVER};
}}

QLabel#heading {{
    font-size: 22px;
    font-weight: 800;
    color: {TEXT_PRIMARY};
}}

QLabel#subheading {{
    color: {TEXT_SECONDARY};
    font-size: 13px;
}}

QLabel#pathLabel {{
    color: {TEXT_SECONDARY};
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 14px;
}}

QFrame#card {{
    background-color: {CARD};
    border-radius: 18px;
    border: 1px solid {BORDER};
}}

QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}

QListWidget::item {{
    background-color: {CARD};
    border-radius: 14px;
    margin: 8px;
    padding: 0px;
}}

QListWidget::item:selected {{
    background-color: {CARD_HOVER};
    border: 1px solid {ACCENT};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}

QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}

QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 10px;
}}

QComboBox {{
    background-color: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 12px;
    color: {TEXT_PRIMARY};
}}

QToolTip {{
    background-color: {CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    padding: 6px;
    border-radius: 6px;
}}
"""
