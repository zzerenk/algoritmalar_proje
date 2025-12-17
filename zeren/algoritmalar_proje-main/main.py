"""Application entry point."""

import sys
from PyQt6.QtWidgets import QApplication, QStyleFactory

from ui.main_window import OperationWindow


def main() -> None:
	app = QApplication(sys.argv)

	windows_style = QStyleFactory.create("Windows")
	if windows_style is not None:
		app.setStyle(windows_style)

	window = OperationWindow()
	window.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
