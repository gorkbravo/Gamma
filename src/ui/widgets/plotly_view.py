from __future__ import annotations

import os
import tempfile
import webbrowser

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QStackedLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
import plotly.graph_objects as go
import plotly.io as pio


class PlotlyView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(240)
        self._force_static = os.getenv("PLOTLY_STATIC_RENDER", "0") == "1"
        self._auto_fallback = os.getenv("MQW_AUTO_FALLBACK", "0") == "1"
        self._config = {
            "displayModeBar": False,
            "responsive": True,
            "scrollZoom": False,
        }
        self._last_error_message: str | None = None
        self._last_fig: go.Figure | None = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._rerender_static)

        self._web = QWebEngineView()
        self._web.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._web.loadFinished.connect(self._on_load_finished)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignCenter)
        self._image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._image.setStyleSheet("QLabel { color: #666; }")
        self._image.setScaledContents(False)

        self._stack = QStackedLayout()
        self._stack.addWidget(self._web)
        self._stack.addWidget(self._image)
        self.setLayout(self._stack)

    def set_figure(self, fig: go.Figure) -> None:
        self._last_fig = fig
        if self._force_static:
            self._render_static(fig)
            return

        html = pio.to_html(fig, include_plotlyjs="inline", full_html=False, config=self._config)
        wrapped = (
            "<!DOCTYPE html>"
            "<html><head><meta charset='utf-8' />"
            "<style>"
            "html, body { margin:0; padding:0; width:100%; height:100%; }"
            "body { background:transparent; }"
            ".plotly-graph-div { width:100% !important; height:100% !important; }"
            "</style></head><body>"
            f"{html}"
            "</body></html>"
        )
        self._last_error_message = None
        self._stack.setCurrentWidget(self._web)
        self._web.setHtml(wrapped, QUrl("file:///"))

    def open_in_browser(self, title: str = "Chart") -> None:
        if self._last_fig is None:
            return
        html = pio.to_html(self._last_fig, include_plotlyjs="cdn", full_html=True, config=self._config)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", prefix="mqw_chart_") as tmp:
            tmp.write(html.encode("utf-8"))
            path = tmp.name
        webbrowser.open(f"file:///{path}", new=2)

    def show_message(self, message: str) -> None:
        fig = go.Figure()
        fig.add_annotation(text=message, x=0.5, y=0.5, showarrow=False, font=dict(size=14))
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        fig.update_layout(margin=dict(l=20, r=20, t=20, b=20))
        self.set_figure(fig)

    def _on_load_finished(self, ok: bool) -> None:
        if ok or self._last_error_message:
            return
        if not self._auto_fallback:
            self._show_text(
                "Chart failed to load. Try: MQW_WEBENGINE_SOFTWARE=1 or PLOTLY_STATIC_RENDER=1"
            )
            return
        self._last_error_message = "Chart failed to load"
        if self._last_fig is not None:
            self._render_static(self._last_fig)
        else:
            self._show_text("Chart failed to load")

    def _render_static(self, fig: go.Figure) -> None:
        width = max(self.width(), 320)
        height = max(self.height(), 240)
        try:
            png = pio.to_image(fig, format="png", width=width, height=height, scale=1)
        except Exception:
            self._show_text("Chart failed to load")
            return
        image = QImage.fromData(png)
        if image.isNull():
            self._show_text("Chart failed to load")
            return
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(self._image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._image.setPixmap(scaled)
        self._stack.setCurrentWidget(self._image)

    def _show_text(self, message: str) -> None:
        self._image.setText(message)
        self._stack.setCurrentWidget(self._image)

    def _rerender_static(self) -> None:
        if self._last_fig is None:
            return
        if not self._force_static and self._stack.currentWidget() is self._web:
            return
        self._render_static(self._last_fig)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._stack.currentWidget() is self._image:
            self._resize_timer.start(150)
