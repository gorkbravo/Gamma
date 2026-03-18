from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.models.app_mode import AppMode


class LandingPage(QWidget):
    mode_selected = Signal(str)
    connect_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.addStretch(1)

        card = QFrame()
        card.setObjectName("landingCard")
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(14)

        title = QLabel("Gamma")
        title.setObjectName("landingTitle")
        subtitle = QLabel("Research-first quant workstation for portfolio monitoring, risk, and volatility analysis.")
        subtitle.setObjectName("landingSubtitle")
        subtitle.setWordWrap(True)

        self.connection_status_label = QLabel("Status: Disconnected")
        self.connection_status_label.setObjectName("landingStatus")
        self.connection_status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.connect_btn = QPushButton("Connect to IBKR")
        self.connect_btn.setObjectName("landingConnectButton")
        self.connect_btn.clicked.connect(self.connect_requested.emit)

        connect_row = QHBoxLayout()
        connect_row.addWidget(self.connection_status_label)
        connect_row.addStretch()
        connect_row.addWidget(self.connect_btn)

        buttons = QHBoxLayout()
        portfolio_btn = QPushButton("Portfolio View")
        portfolio_btn.clicked.connect(lambda: self.mode_selected.emit(AppMode.PORTFOLIO.value))
        research_btn = QPushButton("Research View")
        research_btn.clicked.connect(lambda: self.mode_selected.emit(AppMode.RESEARCH.value))
        buttons.addWidget(portfolio_btn)
        buttons.addWidget(research_btn)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addLayout(connect_row)
        card_layout.addLayout(buttons)
        card.setLayout(card_layout)

        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(card)
        wrap.addStretch(1)
        root.addLayout(wrap)
        root.addStretch(1)
        self.setLayout(root)

    def set_connection_state(self, status_text: str, action_text: str, enabled: bool) -> None:
        self.connection_status_label.setText(status_text)
        self.connect_btn.setText(action_text)
        self.connect_btn.setEnabled(enabled)
