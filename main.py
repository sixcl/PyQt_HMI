import sys
from PyQt5.QtWidgets import QApplication
from controllers.main_controller import MainController

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 启动控制器，由控制器负责组装 Model 和 View
    controller = MainController()
    sys.exit(app.exec_())