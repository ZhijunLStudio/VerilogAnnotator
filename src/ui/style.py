# src/ui/style.py
DARK_THEME = """
    QMainWindow, QToolBar, QDialog {
        background-color: #2b2b2b;
        color: #eeeeee;
    }
    QListWidget {
        background-color: #3c3f41;
        border: 1px solid #555555;
        font-size: 13px;
        color: #eeeeee;
        padding: 4px;
    }
    QListWidget::item {
        padding: 6px;
        border-radius: 3px;
    }
    QListWidget::item:selected {
        background-color: #4b6eaf;
    }
    QListWidget::item:hover {
        background-color: #4a4a4a;
    }
    QTreeWidget {
        background-color: #3c3f41;
        border: 1px solid #555555;
        font-size: 13px;
        color: #eeeeee;
    }
    QTreeWidget::item {
        padding: 4px;
    }
    QTreeWidget::item:selected {
        background-color: #4b6eaf;
    }
    QLabel {
        font-size: 13px;
        color: #bbbbbb;
    }
    QPushButton, QToolButton {
        background-color: #4b4b4b;
        border: 1px solid #5a5a5a;
        padding: 6px 12px;
        color: #eeeeee;
        font-size: 12px;
        border-radius: 3px;
    }
    QPushButton:hover, QToolButton:hover {
        background-color: #5a5a5a;
        border-color: #6a6a6a;
    }
    QPushButton:pressed, QToolButton:pressed {
        background-color: #3a3a3a;
    }
    QPushButton:disabled {
        background-color: #3a3a3a;
        color: #888888;
    }
    QStatusBar {
        background-color: #2b2b2b;
        color: #999999;
        border-top: 1px solid #3a3a3a;
    }
    QGroupBox {
        border: 1px solid #555555;
        margin-top: 12px;
        font-size: 13px;
        font-weight: bold;
        color: #eeeeee;
        padding-top: 8px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 8px;
        color: #bbbbbb;
    }
    QSplitter::handle {
        background-color: #3a3a3a;
    }
    QSplitter::handle:horizontal {
        width: 4px;
    }
    QSplitter::handle:vertical {
        height: 4px;
    }
    QMenu {
        background-color: #3c3f41;
        border: 1px solid #555555;
        color: #eeeeee;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 24px;
    }
    QMenu::item:selected {
        background-color: #4b6eaf;
    }
    QMenu::separator {
        height: 1px;
        background-color: #555555;
        margin: 4px 8px;
    }
    QInputDialog, QMessageBox {
        background-color: #2b2b2b;
    }
    QLineEdit {
        background-color: #3c3f41;
        border: 1px solid #555555;
        color: #eeeeee;
        padding: 4px;
        font-size: 13px;
    }
    QLineEdit:focus {
        border-color: #4b6eaf;
    }
    QComboBox {
        background-color: #3c3f41;
        border: 1px solid #555555;
        color: #eeeeee;
        padding: 4px;
        font-size: 13px;
    }
    QComboBox:focus {
        border-color: #4b6eaf;
    }
    QComboBox::drop-down {
        border: none;
        padding-right: 8px;
    }
    QComboBox QAbstractItemView {
        background-color: #3c3f41;
        border: 1px solid #555555;
        color: #eeeeee;
        selection-background-color: #4b6eaf;
    }
    QGraphicsView {
        border: 1px solid #3a3a3a;
        background-color: #1e1e1e;
    }
"""
