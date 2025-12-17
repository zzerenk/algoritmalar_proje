from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QTextEdit,
    QStyleFactory,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Operasyon ve Analiz")
        self.resize(1200, 800)
        self.menuBar().setNativeMenuBar(False)

        self.stacked = QStackedWidget()
        self.setCentralWidget(self.stacked)

        self.operations_page = self._build_operations_page()
        self.analysis_page = self._build_analysis_page()

        self.stacked.addWidget(self.operations_page)
        self.stacked.addWidget(self.analysis_page)

        self._build_menu()

    def _build_menu(self) -> None:
        view_menu = self.menuBar().addMenu("Görünüm")

        operation_action = QAction("Operasyon", self)
        operation_action.triggered.connect(lambda: self.stacked.setCurrentIndex(0))
        view_menu.addAction(operation_action)

        analysis_action = QAction("Analiz", self)
        analysis_action.triggered.connect(lambda: self.stacked.setCurrentIndex(1))
        view_menu.addAction(analysis_action)

    def _build_operations_page(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left_panel = self._build_left_panel()
        right_panel = self._build_right_panel()

        layout.addWidget(left_panel)
        layout.addWidget(right_panel)
        layout.setStretch(0, 3)
        layout.setStretch(1, 1)

        return container

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        map_placeholder = QWidget()
        map_placeholder.setStyleSheet(
            "background-color: #f7f7f7; border: 1px solid #dcdcdc;"
        )

        log_view = QTextEdit()
        log_view.setReadOnly(True)

        vbox.addWidget(map_placeholder)
        vbox.addWidget(log_view)
        vbox.setStretch(0, 2)
        vbox.setStretch(1, 1)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addStretch()

        return panel

    def _build_analysis_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        label = QLabel("Analiz Verileri Buraya Gelecek")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        return container


def main() -> None:
    import sys

    app = QApplication(sys.argv)

    # Prefer simple Windows look for minimal, familiar visuals.
    windows_style = QStyleFactory.create("Windows")
    if windows_style is not None:
        app.setStyle(windows_style)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
