# main.py
import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox

# 确保能找到 src 目录
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ui.main_window import MainWindow

# === 关键：定义全局异常捕获函数 ===
def exception_hook(exctype, value, tb):
    """当程序崩溃时，捕获错误并弹窗显示，而不是直接闪退"""
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(error_msg) # 如果有黑框，也会打印出来
    
    app = QApplication.instance()
    if app:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("程序崩溃了 (Crash Report)")
        msg.setText("发生了一个错误，导致程序无法继续运行。")
        msg.setInformativeText(str(value)) # 简短错误信息
        msg.setDetailedText(error_msg)     # 详细堆栈信息
        msg.exec()
    sys.exit(1)

if __name__ == '__main__':
    # 挂载异常捕获钩子
    sys.excepthook = exception_hook
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())