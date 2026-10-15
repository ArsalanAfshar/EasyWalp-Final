"""Themes: Dark and Light, derived from the Wallify channel identity.

The logo is a deep-navy wall with the gradient "Wallify" wordmark running from
steel blue to bright cyan. EasyWalp mirrors that: navy surfaces in dark mode,
soft blue-tinted whites in light mode, and the bright cyan-blue as the accent.
QSS stylesheets apply at runtime; "follow system" re-evaluates on every apply.
"""
from __future__ import annotations

import sys

ACCENT = "#3d9bdb"
ACCENT_HOVER = "#54aee8"
ACCENT_PRESSED = "#2f82b8"

DARK = {
    "bg": "#0b1524",
    "bgAlt": "#0f1c30",
    "surface": "#13253d",
    "surfaceAlt": "#182e4a",
    "border": "#24405f",
    "text": "#e8f1fa",
    "textDim": "#9db4cc",
    "accent": ACCENT,
    "accentHover": ACCENT_HOVER,
    "accentPressed": ACCENT_PRESSED,
    "accentText": "#04101e",
    "danger": "#e05555",
    "success": "#4fc38a",
    "dropBorder": ACCENT,
}

LIGHT = {
    "bg": "#f2f6fb",
    "bgAlt": "#e9f0f8",
    "surface": "#ffffff",
    "surfaceAlt": "#f5f9fd",
    "border": "#c4d5e8",
    "text": "#122a44",
    "textDim": "#54718e",
    "accent": "#2380c4",
    "accentHover": "#3393d8",
    "accentPressed": "#1c6da6",
    "accentText": "#ffffff",
    "danger": "#c93a3a",
    "success": "#2e9e63",
    "dropBorder": "#2380c4",
}

FONT_FAMILY = "Vazirmatn"


def system_prefers_dark() -> bool:
    try:
        if sys.platform == "win32":
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
        if sys.platform == "darwin":
            import subprocess

            out = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True, check=False
            )
            return "Dark" in out.stdout
        # Linux and others: pick dark unless XDG says light.
        return "light" not in _linux_session_theme()
    except Exception:
        return True  # EasyWalp's identity is dark-first


def _linux_session_theme() -> str:
    import os

    return (os.getenv("XDG_CURRENT_DESKTOP", "") + os.getenv("GTK_THEME", "")).lower()


def resolve(theme_setting: str) -> dict:
    if theme_setting == "dark":
        return DARK
    if theme_setting == "light":
        return LIGHT
    return DARK if system_prefers_dark() else LIGHT


def stylesheet(palette: dict) -> str:
    p = palette
    return f"""
QWidget {{
    background: {p['bg']};
    color: {p['text']};
    font-family: "{FONT_FAMILY}", "Segoe UI";
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {p['bg']}; }}

 QLabel[h1="true"] {{ font-size: 21px; font-weight: 700; }}
 QLabel[h2="true"] {{ font-size: 15px; font-weight: 600; color: {p['text']}; }}
 QLabel[dim="true"] {{ color: {p['textDim']}; }}

QFrame[card="true"] {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 12px;
}}
QFrame[dropZone="true"] {{
    background: {p['surfaceAlt']};
    border: 2px dashed {p['border']};
    border-radius: 12px;
}}
QFrame[dropZone="true"][filled="true"] {{ border-style: solid; }}
QFrame[dropZone="true"][dragOver="true"] {{ border: 2px solid {p['dropBorder']}; background: {p['surface']}; }}

QPushButton {{
    background: {p['surfaceAlt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 7px 16px;
}}
QPushButton:hover {{ background: {p['surface']}; border-color: {p['accent']}; }}
QPushButton:pressed {{ background: {p['bgAlt']}; }}
QPushButton:disabled {{ color: {p['textDim']}; border-color: {p['border']}; }}
QPushButton[accent="true"] {{
    background: {p['accent']};
    color: {p['accentText']};
    border: none;
    font-weight: 600;
    padding: 10px 22px;
    font-size: 14px;
}}
QPushButton[accent="true"]:hover {{ background: {p['accentHover']}; }}
QPushButton[accent="true"]:pressed {{ background: {p['accentPressed']}; }}
QPushButton[accent="true"]:disabled {{ background: {p['border']}; color: {p['textDim']}; }}
QPushButton[flat="true"] {{ background: transparent; border: none; color: {p['textDim']}; }}
QPushButton[flat="true"]:hover {{ color: {p['text']}; }}
QPushButton[danger="true"] {{ color: {p['danger']}; }}

QLineEdit, QSpinBox, QComboBox {{
    background: {p['bgAlt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {p['accent']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    selection-background-color: {p['accent']};
    selection-color: {p['accentText']};
}}

QToggleButton, QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}

QProgressBar {{
    background: {p['bgAlt']};
    border: 1px solid {p['border']};
    border-radius: 7px;
    height: 14px;
    text-align: center;
    color: {p['textDim']};
}}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 6px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p['accent']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

QListWidget {{
    background: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 8px;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {p['accent']}; color: {p['accentText']}; }}

QToolTip {{
    background: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    padding: 4px 8px;
    border-radius: 6px;
}}

QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p['accent']}; color: {p['accentText']}; }}

QMessageBox {{ background: {p['bgAlt']}; }}
QDialogButtonBox QPushButton {{ min-width: 84px; }}

QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 8px; background: {p['surface']}; }}
QTabBar::tab {{
    background: transparent; color: {p['textDim']};
    padding: 8px 16px; border: none;
}}
QTabBar::tab:selected {{ color: {p['text']}; border-bottom: 2px solid {p['accent']}; }}

QSlider::groove:horizontal {{ height: 4px; background: {p['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -7px 0; border-radius: 8px; background: {p['accent']}; }}
"""
