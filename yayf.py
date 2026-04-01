#!/usr/bin/env python3

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader


if __name__ == "__main__":
    app = QApplication([])
    loader = QUiLoader()
    file = QFile("gui.ui")

    window = loader.load(file)
    window.setWindowTitle("Yet Another yt-dlp Frontend")
    file.close()

    import functions

    functions.setLoader(loader)
    functions.setWindow(window)
    functions.setDefaultQuality()

    window.link_line.setFocus()
    window.add_button.clicked.connect(
        lambda: functions.addToQ(window.quality_cb.currentText())
    )
    window.download_button.clicked.connect(lambda: functions.download(False))
    window.startAll_button.clicked.connect(functions.downloadAll)
    window.q_tableWidget.itemDoubleClicked.connect(functions.openOutputWindow)
    window.stopall_button.clicked.connect(functions.stopall)
    window.remove_button.clicked.connect(functions.remove)
    window.up_button.clicked.connect(functions.up)
    window.down_button.clicked.connect(functions.down)
    window.custom_button.clicked.connect(functions.openListFormats)
    window.link_line.returnPressed.connect(functions.pressedEnter)
    window.options_button.clicked.connect(functions.openOptions)

    window.show()
    app.exec()
