from PySide6.QtWidgets import QMessageBox, QTableWidgetItem, QMainWindow
from PySide6.QtCore import QFile, QProcess, Qt
from PySide6.QtUiTools import QUiLoader
from queue import Queue
import os
import requests
import json
import platform
import locale
from hashlib import sha256


def getSettings():
    if not os.path.exists("settings.ini"):
        with open("settings.ini", "w") as file:
            s = {
                "DOWNLOAD_LOCATION": "/DEFAULT/",
                "PROXY": False,
                "USER": "",
                "PASSWORD": "",
                "ADDRESS": "",
                "PROTOCOL": "None",
                "DEFAULT_QUALITY": "720p",
            }
            file.write(json.dumps(s))
            return s
    with open("settings.ini", "r") as file:
        s = json.loads(file.read())
        return s


def getYTDLP():
    system = platform.system()
    if system == "Windows":
        return "yt-dlp.exe"
    elif system == "Linux":
        return "./yt-dlp_linux"
    elif system == "Darwin":
        return "./yt-dlp_macos"
    else:
        raise Exception("System not supported")


YTDLP = getYTDLP()
SETTINGS = getSettings()
FORMATLIST = Queue()
processes = []
outputWindows = []
optWindows = []
formatsWindows = []
loader = QUiLoader()
window = QMainWindow()


def setDefaultQuality():
    window.quality_cb.setCurrentText(SETTINGS["DEFAULT_QUALITY"])


def setLoader(ld):
    global loader
    loader = ld


def setWindow(wd):
    global window
    window = wd


def handle_stdout(process, quality):
    encoding = locale.getpreferredencoding(False)
    data = process.readAllStandardOutput().data().decode(encoding, errors="replace")
    q = Queue(maxsize=10)
    index = -1
    for ps in processes:
        if process in ps:
            q = ps[1]
            index = ps[2]
            break
    if q.full():
        q.get()
    q.put(data.strip())
    out = data.strip()
    if out:
        if "%" in out:
            out = out.split()
            # Format --> ['[download]', '34.2%', 'of', '2.55MiB', 'at', '202.40KiB/s', 'ETA', '00:08']
            if "%" in out[1] and ":" in out[7]:
                percent = float(out[1][:-1])
                if percent < ps[4]:
                    ps[3] = not ps[3]
                ps[4] = percent
                if not ps[3] and quality != "ba":
                    window.q_tableWidget.setItem(
                        # Percent
                        index,
                        2,
                        QTableWidgetItem(f"Video ({out[1]})"),
                    )
                else:
                    window.q_tableWidget.setItem(
                        # Percent
                        index,
                        2,
                        QTableWidgetItem(f"Audio ({out[1]})"),
                    )
                window.q_tableWidget.setItem(
                    index, 4, QTableWidgetItem(out[5])
                )  # Speed
                window.q_tableWidget.setItem(
                    index, 5, QTableWidgetItem(out[7])
                )  # Remaining
        for i in range(2, 6):
            window.q_tableWidget.item(index, i).setTextAlignment(Qt.AlignCenter)
        for win in outputWindows:
            if not win.isVisible():
                outputWindows.remove(win)
                continue
            row = win.windowTitle().split("--->")[1]
            if (int(row) - 1) == index:
                while not q.empty():
                    win.output_plainTextEdit.appendPlainText(q.get())


def handle_list_stdout(process):
    encoding = locale.getpreferredencoding(False)
    data = process.readAllStandardOutput().data().decode(encoding, errors="replace")
    global FORMATLIST
    out = data.strip()
    if out:
        FORMATLIST.put(out)


# List Output Format
# 1 [info] Available formats for hc8hW26vuI4:
# 2 ID  EXT   RESOLUTION FPS CH |  FILESIZE   TBR PROTO | VCODEC          VBR ACODEC      ABR ASR MORE INFO
# 3 ----------------------------------------------------------------------------------------------------------------
# 4 251 webm  audio only      2 |   3.70MiB  126k https | audio only          opus       126k 48k medium, webm_dash
# 5 160 mp4   256x144     30    |   2.11MiB   72k https | avc1.4d400c     72k video only          144p, mp4_dash
# 6 278 webm  256x144     30    |   2.26MiB   77k https | vp9             77k video only          144p, webm_dash
#    1   2      3          4  5 6      7       8    9   10  11            12     13        14  15   16   17


def list_finished(process, lfwin):
    global FORMATLIST
    lfwin.label.setText("Double Click the Format to Add it to the Queue")
    while not FORMATLIST.empty():
        line = FORMATLIST.get()
    lfwin.listWidget.addItems(line.split("\n"))


def process_finished(exit_code, process):
    p = []
    for ps in processes:
        if process in ps:
            p = ps
            break
    window.q_tableWidget.setItem(p[2], 4, QTableWidgetItem("-----B/S"))  # Speed
    window.q_tableWidget.item(p[2], 4).setTextAlignment(Qt.AlignCenter)
    window.q_tableWidget.setItem(p[2], 5, QTableWidgetItem("--:--"))  # Remaining
    window.q_tableWidget.item(p[2], 5).setTextAlignment(Qt.AlignCenter)
    progress = window.q_tableWidget.item(p[2], 2).text()
    if progress == "Downloading":
        progress = ""
    if exit_code == 1:  # general error
        window.q_tableWidget.setItem(
            p[2], 2, QTableWidgetItem("Error (" + progress + ")")
        )
        msg = "Download Error on element " + str(p[2] + 1) + ":<br>"
        q = p[1]
        while not q.empty():
            msg += q.get() + "<br>"
        QMessageBox.information(window, "Alert", msg)
    elif exit_code == 0:  # succesful
        window.q_tableWidget.setItem(p[2], 2, QTableWidgetItem("Finished"))
        window.q_tableWidget.item(p[2], 2).setTextAlignment(Qt.AlignCenter)
        processes.remove(p)
        download(True)
        return
    else:  # terminate
        window.q_tableWidget.setItem(
            p[2], 2, QTableWidgetItem("Stopped (" + progress + ")")
        )
    for i in range(2, 6):
        window.q_tableWidget.item(p[2], i).setTextAlignment(Qt.AlignCenter)
    processes.remove(p)


def download(qFlag):
    if not os.path.exists(YTDLP):
        return QMessageBox.information(
            window, "Alert", "yt-dlp not found, download it from the settings"
        )
    if SETTINGS["DOWNLOAD_LOCATION"] == "/DEFAULT/":
        return QMessageBox.information(
            window, "Alert", "Download location not set, please check the settings"
        )

    link = ""
    index = -1
    for i in range(window.q_tableWidget.rowCount()):
        status = window.q_tableWidget.item(i, 2).text()
        if status == "Added" or "Stopped" in status or "Error" in status:
            link = window.q_tableWidget.item(i, 0).text().split("//--//")
            link = link[0] if len(link) == 1 else link[1]
            index = i
            break
    if link == "" and len(processes) == 0:
        if qFlag:
            return QMessageBox.information(window, "Alert", "Queue Finished")
        return QMessageBox.information(window, "Alert", "Empty Queue")
    if index != -1:
        quality = format_quality(window.q_tableWidget.item(index, 1).text())
        process = QProcess()

        # Array Format -> [process, outputs, row, DlAudio, percent, videoSize]
        processes.append([process, Queue(maxsize=10), index, False, 0, -1])
        process.setProgram(YTDLP)
        proxyData = getProxyData() if SETTINGS["PROXY"] else ""
        nameFormat = f"%(title)s [{quality[0]}].%(ext)s"
        if "&list" in link:
            nameFormat = "%(playlist_index)s-" + nameFormat
        if quality[1] == "ba":
            process.setArguments(
                [
                    link,
                    "--extract-audio",
                    "--audio-format",
                    "mp3",
                    "-o",
                    nameFormat,
                    "--embed-thumbnail",
                    "--convert-thumbnails",
                    "jpg",
                    "--embed-chapters",
                    "-P",
                    SETTINGS["DOWNLOAD_LOCATION"],
                    "--proxy",
                    proxyData,
                ]
            )
        else:
            process.setArguments(
                [
                    link,
                    "-f",
                    quality[1],
                    "-o",
                    nameFormat,
                    "--embed-thumbnail",
                    "--convert-thumbnails",
                    "jpg",
                    "--embed-chapters",
                    "-P",
                    SETTINGS["DOWNLOAD_LOCATION"],
                    "--proxy",
                    proxyData,
                ]
            )
        process.readyReadStandardOutput.connect(
            lambda: handle_stdout(process, quality[1])
        )
        process.finished.connect(lambda code: process_finished(code, process))
        process.start()
        window.q_tableWidget.setItem(index, 2, QTableWidgetItem("Downloading"))
        window.q_tableWidget.item(index, 2).setTextAlignment(Qt.AlignCenter)


def getProxyData():
    user = SETTINGS["USER"]
    passw = SETTINGS["PASSWORD"]
    protocol = SETTINGS["PROTOCOL"].lower()
    address = SETTINGS["ADDRESS"]
    if user != "":
        user = f"{user}:{passw}@"

    data = f"{protocol}://{user}{address}"
    return data


def downloadAll():
    for i in range(window.q_tableWidget.rowCount()):
        status = window.q_tableWidget.item(i, 2).text()
        if status == "Added" or "Stopped" in status or "Error" in status:
            download(False)


def format_quality(quality):
    q = [quality, quality]  # quality pre and post format
    presetQ = ["Only Audio", "Best Quality", "240p", "360p", "480p", "720p", "1080p"]
    if quality in presetQ:
        if quality[-1] == "p":
            q[1] = f"bv*[height<={quality[:-1]}]+ba"
        elif quality == "Only Audio":
            q[1] = "ba"
        elif quality == "Best Quality":
            q[1] = "bv+ba"
    return q


def openOutputWindow(item):
    row = item.row()
    outFile = QFile("output.ui")
    outWindow = loader.load(outFile)
    outWindow.setWindowTitle("stdout from row --->" + str(row + 1))
    outFile.close()
    outWindow.output_plainTextEdit.setReadOnly(True)
    outWindow.show()
    outputWindows.append(outWindow)


def openOptions():
    optFile = QFile("settings.ui")
    optWindow = loader.load(optFile)
    optWindow.setWindowTitle("Settings")
    optFile.close()
    if not SETTINGS["PROXY"]:
        optWindow.protocol_comboBox.addItem("None")
        optWindow.user_lineEdit.setEnabled(False)
        optWindow.pass_lineEdit.setEnabled(False)
        optWindow.address_lineEdit.setEnabled(False)
        optWindow.protocol_comboBox.setEnabled(False)
    optWindow.dlocation_lineEdit.setText(SETTINGS["DOWNLOAD_LOCATION"])
    optWindow.proxy_checkBox.setChecked(SETTINGS["PROXY"])
    optWindow.user_lineEdit.setText(SETTINGS["USER"])
    optWindow.pass_lineEdit.setText(SETTINGS["PASSWORD"])
    optWindow.address_lineEdit.setText(SETTINGS["ADDRESS"])
    optWindow.protocol_comboBox.setCurrentText(SETTINGS["PROTOCOL"])
    optWindow.quality_cb.setCurrentText(SETTINGS["DEFAULT_QUALITY"])
    optWindow.save_button.clicked.connect(lambda: saveOptions(optWindow))
    optWindow.proxy_checkBox.stateChanged.connect(lambda: toggleProxy(optWindow))
    optWindow.update_label.setAlignment(Qt.AlignRight)
    optWindow.download_lineEdit.setReadOnly(True)
    optWindow.download_button.clicked.connect(lambda: download_yt_dlp(optWindow, False))
    optWindow.checkUpdate_pushButton.clicked.connect(
        lambda: download_yt_dlp(optWindow, True)
    )
    optWindow.show()
    optWindows.append(optWindow)


def toggleProxy(optwin):
    proxy = optwin.proxy_checkBox.isChecked()
    if proxy:
        optwin.user_lineEdit.setEnabled(True)
        optwin.pass_lineEdit.setEnabled(True)
        optwin.address_lineEdit.setEnabled(True)
        optwin.protocol_comboBox.setEnabled(True)
        optwin.protocol_comboBox.setCurrentText("HTTP")
        optwin.protocol_comboBox.removeItem(4)
    else:
        optwin.user_lineEdit.setEnabled(False)
        optwin.user_lineEdit.setText("")
        optwin.pass_lineEdit.setEnabled(False)
        optwin.pass_lineEdit.setText("")
        optwin.address_lineEdit.setEnabled(False)
        optwin.address_lineEdit.setText("")
        optwin.protocol_comboBox.setEnabled(False)
        optwin.protocol_comboBox.addItem("None")
        optwin.protocol_comboBox.setCurrentText("None")


def saveOptions(optwin):
    location = optwin.dlocation_lineEdit.text()
    proxy = optwin.proxy_checkBox.isChecked()
    user = optwin.user_lineEdit.text()
    passw = optwin.pass_lineEdit.text()
    address = optwin.address_lineEdit.text()
    protocol = optwin.protocol_comboBox.currentText()
    defaultQ = optwin.quality_cb.currentText()
    with open("settings.ini", "w") as file:
        s = {
            "DOWNLOAD_LOCATION": location,
            "PROXY": proxy,
            "USER": user,
            "PASSWORD": passw,
            "ADDRESS": address,
            "PROTOCOL": protocol,
            "DEFAULT_QUALITY": defaultQ,
        }
        file.write(json.dumps(s))
    global SETTINGS
    SETTINGS = s
    setDefaultQuality()
    optwin.close()


def openListFormats():
    if window.link_line.text() == "":
        return
    lfFile = QFile("list_formats.ui")
    lfWindow = loader.load(lfFile)
    lfWindow.setWindowTitle("List of Formats")
    lfFile.close()
    lfWindow.label.setAlignment(Qt.AlignCenter)
    lfWindow.listWidget.itemDoubleClicked.connect(
        lambda item: addCustomToQ(item, lfWindow)
    )
    lfWindow.close_button.clicked.connect(lfWindow.close)
    lfWindow.show()
    formatsWindows.append(lfWindow)

    link = window.link_line.text()
    proc = QProcess()
    proc.setProgram(YTDLP)
    proxyData = getProxyData() if SETTINGS["PROXY"] else ""
    proc.setArguments([link, "-F", "--proxy", proxyData])
    proc.readyReadStandardOutput.connect(lambda: handle_list_stdout(proc))
    proc.finished.connect(lambda: list_finished(proc, lfWindow))
    proc.start()


def stopall():
    for ps in processes:
        ps[0].terminate()
        if not ps[0].waitForFinished(1000):
            ps[0].kill()


def remove():
    a = window.q_tableWidget.selectedIndexes()
    rows = sorted(set(i.row() for i in a), reverse=True)
    if rows:
        top = rows[0]
        for r in rows:
            window.q_tableWidget.removeRow(r)
        if top < window.q_tableWidget.rowCount():
            window.q_tableWidget.selectRow(top)
        elif top > 0:
            window.q_tableWidget.selectRow(top - 1)


def up():
    a = window.q_tableWidget.selectedIndexes()
    rows = sorted(set(i.row() for i in a))
    for r in rows:
        temp = ""
        if r > 0:
            for ps in processes:
                if ps[2] == r:
                    ps[2] = r - 1
                elif ps[2] == r - 1:
                    ps[2] = r
            for i in range(window.q_tableWidget.columnCount()):
                temp = window.q_tableWidget.item(r - 1, i).text()
                window.q_tableWidget.setItem(
                    r - 1, i, QTableWidgetItem(window.q_tableWidget.item(r, i).text())
                )
                window.q_tableWidget.setItem(r, i, QTableWidgetItem(temp))
            window.q_tableWidget.selectRow(r - 1)


def down():
    a = window.q_tableWidget.selectedIndexes()
    rows = sorted(set(i.row() for i in a), reverse=True)
    for r in rows:
        temp = ""
        if r < window.q_tableWidget.rowCount() - 1:
            for ps in processes:
                if ps[2] == r:
                    ps[2] = r + 1
                elif ps[2] == r + 1:
                    ps[2] = r
            for i in range(window.q_tableWidget.columnCount()):
                temp = window.q_tableWidget.item(r + 1, i).text()
                window.q_tableWidget.setItem(
                    r + 1, i, QTableWidgetItem(window.q_tableWidget.item(r, i).text())
                )
                window.q_tableWidget.setItem(r, i, QTableWidgetItem(temp))
            window.q_tableWidget.selectRow(r + 1)


def download_yt_dlp(optwin, check):

    url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
    response = requests.get(url)
    release = response.json()
    download_link = ""
    sha = ""
    for asset in release["assets"]:
        if asset["name"] == YTDLP:
            download_link = asset["browser_download_url"]
            sha = asset["digest"].split(":")[1]
            break
    # Checks the sha256 of the latest release with the one in the folder
    if os.path.exists(YTDLP):
        with open(YTDLP, "rb") as file:
            s = sha256(file.read())
            if s.hexdigest() == sha:
                optwin.update_label.setText("Already have the latest version")
                return
            elif check:
                optwin.update_label.setText("Newer version available")
    elif check:
        optwin.update_label.setText("yt-dlp not found in the folder")
        return

    proc = QProcess()
    proc.setProgram("curl")
    proc.setArguments(["-LO", download_link])
    proc.readyReadStandardError.connect(lambda: handle_yt_download(proc, optwin))
    proc.finished.connect(lambda code: download_finished(code, optwin))
    proc.start()


# Curl Format
#  % Total    % Received % Xferd  Average Speed  Time    Time    Time   Current
#                                 Dload  Upload  Total   Spent   Left   Speed
#  0      0   0      0   0      0      0      0                              0
# 25 34.43M  25  8.66M   0      0 372.1k      0   01:34   00:23   01:11 394.6k


def handle_yt_download(process, optwin):
    encoding = locale.getpreferredencoding(False)
    data = process.readAllStandardError().data().decode(encoding, errors="replace")
    out = data.strip()
    if out:
        out = out.split()
        if len(out) == 12:
            optwin.download_lineEdit.setText(
                f"Downloading || {out[0]}% of {out[1]} at {out[11]}/s, remaining {
                    out[10]
                } ||"
            )


def download_finished(exit_code, optwin):
    if exit_code != 0:
        optwin.download_lineEdit.setText("Error")
    else:
        optwin.download_lineEdit.setText("Finished")
        os.chmod(YTDLP, 0o755)


def addToQ(quality, custom=False):
    link = window.link_line.text()
    if link == "":
        return
    add_row([link, quality, "Added", "-----MB", "-----B/S", "--:--"])
    window.link_line.clear()

    proc1 = QProcess()
    proc1.setProgram(YTDLP)
    proxyData = getProxyData() if SETTINGS["PROXY"] else ""
    quality = format_quality(quality)[1]
    if quality != "ba" and not custom:
        quality = quality[:-3]
        proc1.setArguments(
            [
                link,
                "-f",
                "ba",
                "--print",
                "%(title)s//--//%(filesize)s",
                "--proxy",
                proxyData,
            ]
        )
        proc1.readyReadStandardOutput.connect(lambda: handle_name_size(proc1))
        proc1.readyReadStandardError.connect(lambda: handle_name_size_error(proc1))
        proc1.finished.connect(lambda code: update_name_size_finished(code, proc1))
        processes.append(
            [proc1, Queue(maxsize=10), window.q_tableWidget.rowCount() - 1]
        )
        proc1.start()

    proc2 = QProcess()
    proc2.setProgram(YTDLP)
    proc2.setArguments(
        [
            link,
            "-f",
            quality,
            "--print",
            "%(title)s//--//%(filesize)s",
            "--proxy",
            proxyData,
        ]
    )
    proc2.readyReadStandardOutput.connect(lambda: handle_name_size(proc2))
    proc2.readyReadStandardError.connect(lambda: handle_name_size_error(proc2))
    proc2.finished.connect(lambda code: update_name_size_finished(code, proc2))
    processes.append([proc2, Queue(maxsize=10), window.q_tableWidget.rowCount() - 1])
    proc2.start()


def addCustomToQ(item, lfwin):
    id = item.text().split()[0]
    addToQ(id, custom=True)
    lfwin.close()


def update_name_size_finished(code, process):
    for ps in processes:
        if process in ps:
            processes.remove(ps)
            break


def handle_name_size_error(process):
    encoding = locale.getpreferredencoding(False)
    data = process.readAllStandardError().data().decode(encoding, errors="replace")
    if data.strip():
        print(data.strip())


def handle_name_size(process):
    encoding = locale.getpreferredencoding(False)
    data = process.readAllStandardOutput().data().decode(encoding, errors="replace")
    index = -1
    for ps in processes:
        if process in ps:
            index = ps[2]
    out = data.strip()
    if out:
        out = out.split("//--//")
        link = window.q_tableWidget.item(index, 0).text()
        if "//--//" not in link:
            window.q_tableWidget.setItem(
                # column 0 -> name
                index,
                0,
                QTableWidgetItem(f"{out[0]}//--//{link}"),
            )
        if out[1] != "NA":
            size = formatBytes(float(out[1]))
            tableSize = window.q_tableWidget.item(index, 3).text()
            if tableSize != "-----MB":
                size = formatBytes(size, True) + formatBytes(tableSize, inversed=True)
                size = formatBytes(size)
            window.q_tableWidget.setItem(
                index, 3, QTableWidgetItem(size)
            )  # column 3 -> size
    window.q_tableWidget.item(index, 3).setTextAlignment(Qt.AlignCenter)


def formatBytes(n, inversed=False):  # if inversed then is to convert to bytes
    sizes = ["B", "KiB", "MiB", "GiB"]
    if not inversed:
        count = 0
        while n >= 1024:
            n /= 1024
            count += 1
        return "{:.2f}".format(n) + sizes[count]
    count = sizes.index(n[-3:])
    n = float(n[:-3])
    while count > 0:
        n *= 1024
        count -= 1
    return n


def pressedEnter():
    if window.link_line.text() == "":
        download(False)
    else:
        addToQ(window.quality_cb.currentText())


def add_row(data):  # size 6 array
    row = window.q_tableWidget.rowCount()
    window.q_tableWidget.insertRow(row)
    for i in range(window.q_tableWidget.columnCount()):
        window.q_tableWidget.setItem(row, i, QTableWidgetItem(data[i]))
        window.q_tableWidget.item(row, i).setTextAlignment(Qt.AlignCenter)
