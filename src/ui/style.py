DARK_THEME = """
    QMainWindow, QToolBar, QDialog {
        background-color: #333;
        color: #EEE;
    }
    QListWidget {
        background-color: #444;
        border: 1px solid #555;
        font-size: 14px;
        color: #EEE;
    }
    QListWidget::item { padding: 5px; }
    QListWidget::item:selected { background-color: #0078D7; }
    QLabel { font-size: 14px; color: #DDD; }
    QPushButton, QToolButton {
        background-color: #555;
        border: 1px solid #666;
        padding: 6px;
        color: #EEE;
        font-size: 13px;
    }
    QPushButton:hover, QToolButton:hover { background-color: #666; }
    QPushButton:pressed, QToolButton:pressed { background-color: #444; }
    QStatusBar { background-color: #222; color: #AAA; }
    QGroupBox { border: 1px solid #555; margin-top: 10px; font-size: 14px; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 5px; }
"""