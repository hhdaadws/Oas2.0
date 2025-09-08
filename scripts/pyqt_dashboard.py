"""
PyQt 窗口，内嵌浏览器访问本地前端 Dashboard。

使用方式：
  1) 安装依赖（任选其一）
     - PyQt5: pip install PyQt5 PyQtWebEngine
     - PyQt6: pip install PyQt6 PyQt6-WebEngine
  2) 运行：python scripts/pyqt_dashboard.py

默认地址：http://localhost:9000/dashboard （Vite dev 服务端口为 9000）
"""
import sys

URL = "http://localhost:9000/dashboard"


def run_pyqt5():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QUrl
    from PyQt5.QtWebEngineWidgets import QWebEngineView

    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.setWindowTitle("Dashboard")
    view.resize(1280, 800)
    view.load(QUrl(URL))
    view.show()
    try:
        sys.exit(app.exec())
    except AttributeError:
        sys.exit(app.exec_())


def run_pyqt6():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    app = QApplication(sys.argv)
    view = QWebEngineView()
    view.setWindowTitle("Dashboard")
    view.resize(1280, 800)
    view.load(QUrl(URL))
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        run_pyqt5()
    except Exception:
        # 回退到 PyQt6
        run_pyqt6()

