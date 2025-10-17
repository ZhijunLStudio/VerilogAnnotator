# main.py
import sys
from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow # 注意导入路径变了

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())