"""Main window for the IVY voice client."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from concurrent.futures import CancelledError as FutureCancelledError
from typing import Callable

from PySide6.QtCore import Q_ARG, Qt, QMetaObject, QTimer, Slot
from PySide6.QtGui import QAction, QColor, QKeySequence, QShortcut, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QGraphicsDropShadowEffect,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from httpx import HTTPStatusError

from ..config.paths import models_dir
from ..config.store import load_settings, save_settings
from ..config.settings import AppSettings
from ..runtime.controller import VoiceController
from ..services.api import IvyAPI
from ..services.schemas import ChatMessage, CommandRisk, SystemCommand, TranscriptEvent
from ..state.app_state import AppState, ConversationEntry
from ..utils.dpapi import protect


class WaveformWidget(QWidget):
    """Dual waveform showing microphone input (blue) and TTS playback (amber)."""

    def __init__(self, parent: QWidget | None = None, samples: int = 48) -> None:
        super().__init__(parent)
        self._samples = max(24, samples)
        self._input_values: deque[float] = deque([0.0] * self._samples, maxlen=self._samples)
        self._output_values: deque[float] = deque([0.0] * self._samples, maxlen=self._samples)
        self._speaking = False
        self.setMinimumHeight(70)
        self.setMaximumHeight(90)

    def add_input(self, value: float) -> None:
        self._input_values.append(max(0.0, min(value, 1.0)))
        self.update()

    def add_output(self, value: float) -> None:
        self._output_values.append(max(0.0, min(value, 1.0)))
        self.update()

    def reset_output(self) -> None:
        self._output_values = deque([0.0] * self._samples, maxlen=self._samples)
        self.update()

    def set_speaking(self, speaking: bool) -> None:
        self._speaking = speaking
        if not speaking:
            self.reset_output()
        else:
            self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        rect = self.rect()
        painter.fillRect(rect, QBrush(QColor(8, 9, 22)))
        width = rect.width()
        height = rect.height()
        if not self._input_values:
            return
        count = len(self._input_values)
        bar_width = max(2, width // count)
        gap = max(1, int(bar_width * 0.2))
        bar_width = max(1, bar_width - gap)
        base_pen = QPen(QColor(90, 152, 255), 1)
        painter.setPen(base_pen)
        inputs = list(self._input_values)
        outputs = list(self._output_values)
        for idx in range(count):
            mic_value = inputs[idx] if idx < len(inputs) else 0.0
            mic_height = height * max(0.02, mic_value)
            x = idx * (bar_width + gap)
            y = height - mic_height
            gradient = QColor(120, 170, 255)
            gradient.setAlpha(80 + int(150 * mic_value))
            painter.fillRect(x, y, bar_width, mic_height, gradient)
            if idx < len(outputs):
                out_value = outputs[idx]
                if out_value <= 0.0:
                    continue
                out_height = height * max(0.02, out_value) * 0.9
                out_y = height - out_height
                overlay = QColor(255, 180, 90 if self._speaking else 60)
                overlay.setAlpha(90 + int(120 * out_value))
                painter.fillRect(x, out_y, bar_width, out_height, overlay)


class _ChatBubble(QWidget):
    """Small widget used to render a chat entry with optional feedback buttons."""

    def __init__(self, role: str, text: str, *, align_right: bool = False) -> None:
        super().__init__()
        self._role = role
        self._feedback_handler: Callable[[bool], None] | None = None
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self._frame = QFrame()
        self._frame.setObjectName("chatBubble")
        self._frame.setProperty("bubbleRole", "user" if align_right else "ivy")
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(12, 8, 12, 8)
        frame_layout.setSpacing(6)

        header = QLabel(role)
        header.setStyleSheet("font-weight: 600; font-size: 14px; letter-spacing: 0.04em;")
        frame_layout.addWidget(header)

        self._text_label = QLabel(text)
        self._text_label.setWordWrap(True)
        frame_layout.addWidget(self._text_label)

        self._meta_label = QLabel("")
        self._meta_label.setStyleSheet("font-size: 12px; color: #cfd8ff;")
        self._meta_label.hide()
        frame_layout.addWidget(self._meta_label)

        self._feedback_widget = QWidget()
        feedback_layout = QHBoxLayout(self._feedback_widget)
        feedback_layout.setContentsMargins(0, 0, 0, 0)
        feedback_layout.setSpacing(8)
        self._helpful_btn = QPushButton("Pertinent")
        self._helpful_btn.setProperty("cssClass", "chatFeedback")
        self._helpful_btn.clicked.connect(lambda: self._emit_feedback(True))
        self._not_helpful_btn = QPushButton("A retravailler")
        self._not_helpful_btn.setProperty("cssClass", "chatFeedback")
        self._not_helpful_btn.clicked.connect(lambda: self._emit_feedback(False))
        feedback_layout.addWidget(self._helpful_btn)
        feedback_layout.addWidget(self._not_helpful_btn)
        self._feedback_widget.hide()
        frame_layout.addWidget(self._feedback_widget)

        if align_right:
            outer.addStretch(1)
            outer.addWidget(self._frame, 0, Qt.AlignmentFlag.AlignRight)
        else:
            outer.addWidget(self._frame, 0, Qt.AlignmentFlag.AlignLeft)
            outer.addStretch(1)

    def text(self) -> str:
        return self._text_label.text()

    def set_text(self, text: str) -> None:
        self._text_label.setText(text)

    def set_pending(self, pending: bool) -> None:
        if pending:
            self._meta_label.setText("Réponse en cours...")
            self._meta_label.show()
        else:
            self._meta_label.hide()

    def show_helper(self, message: str | None) -> None:
        if message:
            self._meta_label.setText(message)
            self._meta_label.show()
        else:
            self._meta_label.hide()

    def enable_feedback(self, handler: Callable[[bool], None]) -> None:
        self._feedback_handler = handler
        self._helpful_btn.setEnabled(True)
        self._not_helpful_btn.setEnabled(True)
        self._feedback_widget.show()
        self.show_helper("Votre avis aide à entraîner IVY.")

    def feedback_enabled(self) -> bool:
        return self._feedback_widget.isVisible()

    def set_feedback_pending(self) -> None:
        self.show_helper("Envoi du feedback...")
        self._helpful_btn.setEnabled(False)
        self._not_helpful_btn.setEnabled(False)

    def mark_feedback_result(self, success: bool, message: str) -> None:
        info = message or ("Merci pour le retour !" if success else "Réessayer plus tard.")
        self.show_helper(info)
        self._helpful_btn.setEnabled(False)
        self._not_helpful_btn.setEnabled(False)

    def _emit_feedback(self, helpful: bool) -> None:
        if self._feedback_handler is None:
            return
        self.set_feedback_pending()
        try:
            self._feedback_handler(helpful)
        except Exception:
            self.mark_feedback_result(False, "Erreur lors de l'envoi.")


def _list_tts_presets() -> list[tuple[str, str]]:
    """Return the set of installed Piper voices relative to models_dir/tts."""
    presets: list[tuple[str, str]] = []
    base = models_dir() / "tts"
    if not base.exists():
        return presets
    seen: set[str] = set()
    for onnx in sorted(base.rglob("*.onnx")):
        parent = onnx.parent
        try:
            rel = parent.relative_to(base)
        except ValueError:
            continue
        value = str(rel).replace("\\", "/")
        if value in seen:
            continue
        seen.add(value)
        label = " / ".join(part for part in value.split("/") if part)
        presets.append((label or value, value))
    return sorted(presets, key=lambda item: item[0].lower())


class VoiceMainWindow(QMainWindow):
    """High level window driving the voice assistant workflow."""

    _ASR_SLOW_THRESHOLD = 9.0
    _ASR_FAST_THRESHOLD = 3.0

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("IVY Voice Console")
        self.setMinimumSize(960, 600)

        self.state = AppState(settings=load_settings())
        self.controller = VoiceController(self.state)
        self.api = IvyAPI(self.state.settings)
        audio = self.state.settings.audio
        gpu_status = "on" if audio.enable_gpu else "off"
        print(f"[voice] ASR model: {audio.asr_model} (GPU {gpu_status})")
        print(f"[voice] TTS voice: {audio.tts_voice}")
        self._record_started_at: float | None = None
        self._last_transcription_duration: float | None = None
        self._llm_started_at: float | None = None
        self._last_llm_duration: float | None = None
        self._speaking_started_at: float | None = None
        self._last_tts_duration: float | None = None
        self._pipeline_started_at: float | None = None
        self._last_total_duration: float | None = None
        self._last_transcript_raw: str = ""
        self._gpu_available = self._detect_gpu()
        self._last_transcript_raw: str = ""
        self._auto_switch_done = audio.asr_model == "faster-whisper-tiny"
        self._recent_asr_latencies: deque[float] = deque(maxlen=5)
        if audio.enable_gpu and self._gpu_available is False:
            print("[voice] info: torch.cuda.is_available() est False ; verifiez la configuration GPU.")

        self._login_in_progress = False
        self._activity_value = 0.0
        self._transcript_anim_buffer = ""
        self._transcript_anim_index = 0
        self._pending_transcript_text = ""
        self._transcript_waiting = False
        self._awaiting_response = False
        self._last_metadata = {}
        self._pending_metadata = {}
        self._displayed_command_ids: set[str] = set()
        self._topic_counts: dict[str, int] = {}
        self._suggested_topics: set[str] = set()
        self.controller.set_activity_callback(self._handle_activity_level)
        self.controller.set_speech_callback(self._handle_speaking_state)
        self.controller.set_tts_activity_callback(self._handle_tts_activity_level)
        self.controller.set_metadata_callback(self._handle_metadata)
        self._shortcut_toggle_listen = QShortcut(QKeySequence("Ctrl+Space"), self)
        self._shortcut_toggle_listen.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut_toggle_listen.activated.connect(self._on_toggle_listen_shortcut)
        self._shortcut_toggle_eco = QShortcut(QKeySequence("Ctrl+E"), self)
        self._shortcut_toggle_eco.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._shortcut_toggle_eco.activated.connect(self._on_toggle_eco_shortcut)

        self._status_label = QLabel("Statut : initialisation...")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._transcript_label = QLabel("Transcription : ...")
        self._transcript_label.setWordWrap(True)
        self._transcript_label.setObjectName("transcriptLabel")
        self._waveform = WaveformWidget(self)
        self._search_label = QLabel("")
        self._search_label.setWordWrap(True)
        self._search_label.setObjectName("searchLabel")
        self._search_label.hide()
        self._chat_label = QLabel("Discussion vocale")
        self._chat_label.setObjectName("chatTitle")
        self._chat_list = QListWidget()
        self._chat_list.setObjectName("chatList")
        self._chat_list.setSpacing(6)
        self._chat_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._chat_list.setAlternatingRowColors(False)
        self._chat_list.setMinimumHeight(220)

        self._activity_indicator = QLabel("Activite micro : 00%")
        self._activity_indicator.setObjectName("activityIndicator")
        self._activity_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._activity_shadow = QGraphicsDropShadowEffect(self)
        self._activity_shadow.setBlurRadius(24)
        self._activity_shadow.setYOffset(10)
        self._activity_shadow.setXOffset(0)
        self._activity_shadow.setColor(QColor(92, 124, 250, 90))
        self._activity_indicator.setGraphicsEffect(self._activity_shadow)

        self._listen_button = QPushButton("Maintenir pour parler")
        self._listen_button.pressed.connect(self._on_listen_pressed)
        self._listen_button.released.connect(self._on_listen_released)
        self._listen_button.setEnabled(False)

        self._active_assistant_item: tuple[QListWidgetItem, "_ChatBubble"] | None = None
        self._last_answer_bubble: "_ChatBubble" | None = None
        self._last_user_message: str = ""
        self._pending_feedback_question: str = ""

        self._build_layout()
        self._apply_theme()
        self._refresh_activity_indicator()
        self._build_menu()

        self._activity_decay_timer = QTimer(self)
        self._activity_decay_timer.setInterval(150)
        self._activity_decay_timer.timeout.connect(self._decay_activity)
        self._activity_decay_timer.start()

        self._transcript_anim_timer = QTimer(self)
        self._transcript_anim_timer.setInterval(35)
        self._transcript_anim_timer.timeout.connect(self._advance_transcript_animation)

        self._transcript_timeout = QTimer(self)
        self._transcript_timeout.setSingleShot(True)
        self._transcript_timeout.setInterval(2500)
        self._transcript_timeout.timeout.connect(self._handle_transcript_timeout)

        if self._ensure_credentials():
            self._attempt_login()
        else:
            self._set_status_text("Statut : authentification requise")
            self._listen_button.setEnabled(False)

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_layout(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        layout.addWidget(self._status_label)
        layout.addWidget(self._waveform)
        layout.addWidget(self._activity_indicator)
        layout.addWidget(self._transcript_label)
        layout.addWidget(self._chat_label)
        layout.addWidget(self._chat_list)
        layout.addWidget(self._search_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        button_row.addWidget(self._listen_button)
        layout.addLayout(button_row)
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.setCentralWidget(container)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()
        settings_menu = menu_bar.addMenu("Parametrages")
        audio_action = QAction("Audio / ASR...", self)
        audio_action.triggered.connect(self._open_settings_dialog)
        settings_menu.addAction(audio_action)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #060710;
                color: #e9edff;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
            QMainWindow {
                background: qlineargradient(
                    spread:pad,
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(36, 43, 94, 180),
                    stop:1 rgba(12, 13, 26, 220)
                );
            }
            QLabel {
                font-size: 16px;
            }
            QLabel#statusLabel {
                font-size: 18px;
                font-weight: 600;
                padding: 14px;
                border-radius: 16px;
                background: rgba(92, 124, 250, 0.16);
                border: 1px solid rgba(92, 124, 250, 0.35);
                color: #ced8ff;
            }
            QLabel#activityIndicator {
                padding: 10px 16px;
                border-radius: 14px;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                font-size: 14px;
                letter-spacing: 0.08em;
            }
            QLabel#transcriptLabel,
            QLabel#chatTitle {
                padding: 12px 16px;
                border-radius: 14px;
                background: rgba(12, 18, 38, 0.65);
                border: 1px solid rgba(255, 255, 255, 0.04);
            }
            QListWidget#chatList {
                background: rgba(12, 18, 38, 0.5);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 6px;
            }
            QFrame#chatBubble {
                border-radius: 16px;
                padding: 12px 14px;
                border: 1px solid rgba(255, 255, 255, 0.05);
                background: rgba(255, 255, 255, 0.03);
            }
            QFrame#chatBubble[bubbleRole="ivy"] {
                background: rgba(90, 124, 250, 0.12);
                border-color: rgba(90, 124, 250, 0.3);
            }
            QFrame#chatBubble[bubbleRole="user"] {
                background: rgba(76, 201, 240, 0.12);
                border-color: rgba(76, 201, 240, 0.28);
            }
            QPushButton[cssClass="chatFeedback"] {
                border-radius: 12px;
                padding: 6px 12px;
                font-size: 13px;
                background: rgba(255, 255, 255, 0.08);
                color: #f4f6ff;
            }
            QPushButton[cssClass="chatFeedback"]:hover {
                background: rgba(255, 255, 255, 0.15);
            }
            QPushButton {
                border: none;
                border-radius: 18px;
                padding: 12px 24px;
                font-size: 15px;
                font-weight: 600;
                color: #eef2ff;
                background: qradialgradient(
                    cx:0.5, cy:0.5, radius:0.75,
                    fx:0.45, fy:0.4,
                    stop:0 rgba(92, 124, 250, 0.95),
                    stop:1 rgba(76, 201, 240, 0.85)
                );
            }
            QPushButton:hover {
                background: qradialgradient(
                    cx:0.5, cy:0.5, radius:0.75,
                    fx:0.48, fy:0.42,
                    stop:0 rgba(98, 126, 255, 0.98),
                    stop:1 rgba(84, 206, 245, 0.9)
                );
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.08);
                color: rgba(255, 255, 255, 0.45);
            }
            """
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setYOffset(12)
        shadow.setXOffset(0)
        shadow.setColor(QColor(92, 124, 250, 90))
        self._listen_button.setGraphicsEffect(shadow)

    # ------------------------------------------------------------------ #
    # Authentication helpers
    # ------------------------------------------------------------------ #
    def _attempt_login(self) -> None:
        if self._login_in_progress:
            return
        self._login_in_progress = True
        try:
            future = asyncio.run_coroutine_threadsafe(self.api.login(), self.controller.loop)
            future.result()
        except RuntimeError as exc:
            self._handle_login_failure(str(exc), reset_credentials=True)
        except HTTPStatusError as exc:
            if exc.response.status_code == 401:
                self._handle_login_failure("Identifiants invalides.", reset_credentials=True)
            elif exc.response.status_code == 429:
                self._set_status_text("Statut : trop de tentatives, nouvel essai dans 3 s...")
                self._listen_button.setEnabled(False)
                self._login_in_progress = False
                QTimer.singleShot(3000, self._attempt_login)
            else:
                self._handle_login_failure(f"Erreur HTTP {exc.response.status_code}")
        except Exception as exc:  # pragma: no cover - reseau imprevisible
            self._handle_login_failure(str(exc))
        else:
            self.controller.attach_api(
                self.api,
                on_transcript=self._handle_transcript,
                on_response=self._handle_response,
                on_error=self._handle_error,
            )
            self._awaiting_response = False
            self._listen_button.setText("Maintenir pour parler")
            self._listen_button.setEnabled(True)
            self._persist_credentials()
            self._update_idle_status()
        finally:
            self._login_in_progress = False

    def _handle_login_failure(self, message: str, *, reset_credentials: bool = False) -> None:
        QMessageBox.warning(self, "Connexion IVY", message)
        if reset_credentials:
            server = self.state.settings.server
            server.password_plaintext = None
            server.password_encrypted = None
            save_settings(self.state.settings)
        if self._prompt_credentials():
            self._attempt_login()
        else:
            self._set_status_text("Statut : authentification requise")
            self._listen_button.setEnabled(False)
            self._awaiting_response = False

    def _ensure_credentials(self) -> bool:
        server = self.state.settings.server
        if server.password_plaintext or server.password_encrypted:
            return True
        return self._prompt_credentials()

    def _prompt_credentials(self) -> bool:
        server = self.state.settings.server
        username, ok = QInputDialog.getText(
            self,
            "Connexion IVY",
            "Nom d'utilisateur :",
            text=server.username,
        )
        if not ok or not username.strip():
            return False
        password, ok = QInputDialog.getText(
            self,
            "Connexion IVY",
            "Mot de passe :",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not password:
            return False
        server.username = username.strip()
        server.password_plaintext = password
        return True

    def _handle_activity_level(self, level: float) -> None:
        level = max(0.0, min(level, 1.0))
        if level > self._activity_value:
            self._activity_value = level
        else:
            self._activity_value = self._activity_value * 0.85 + level * 0.15
        QMetaObject.invokeMethod(self, "_refresh_activity_indicator", Qt.QueuedConnection)

    def _handle_tts_activity_level(self, level: float) -> None:
        level = max(0.0, min(level, 1.0))
        QMetaObject.invokeMethod(
            self,
            "_apply_tts_activity",
            Qt.QueuedConnection,
            Q_ARG(float, level),
        )

    @Slot()
    def _decay_activity(self) -> None:
        self._activity_value *= 0.75
        if self._activity_value < 0.01:
            self._activity_value = 0.0
        self._refresh_activity_indicator()

    @Slot()
    def _refresh_activity_indicator(self) -> None:
        level = max(0.0, min(self._activity_value, 1.0))
        percent = min(100, int(level * 100))
        self._activity_indicator.setText(f"Activite micro : {percent:02d}%")
        alpha = min(220, 40 + int(180 * level))
        border = min(255, 80 + int(120 * level))
        self._activity_indicator.setStyleSheet(
            f"background-color: rgba(92, 124, 250, {alpha});"
            f"border: 1px solid rgba(92, 124, 250, {border});"
            "color: #e9edff;"
        )

        if hasattr(self, "_activity_shadow"):
            shadow_color = QColor(92, 124, 250)
            shadow_color.setAlpha(alpha)
            self._activity_shadow.setColor(shadow_color)
            self._activity_shadow.setBlurRadius(24 + 36 * level)
            self._activity_shadow.setYOffset(8 + 6 * level)
        if hasattr(self, "_waveform"):
            self._waveform.add_input(level)

    @Slot(float)
    def _apply_tts_activity(self, level: float) -> None:
        if hasattr(self, "_waveform"):
            self._waveform.add_output(level)
    @Slot()
    def _start_transcript_animation(self) -> None:
        buffer = self._transcript_anim_buffer
        if not buffer:
            self._transcript_label.setText("Transcription : ...")
            return
        self._transcript_anim_timer.stop()
        self._transcript_anim_index = 1 if len(buffer) > 1 else len(buffer)
        self._transcript_label.setText(buffer[: self._transcript_anim_index])
        if self._transcript_anim_index < len(buffer):
            self._transcript_anim_timer.start()

    @Slot()
    def _advance_transcript_animation(self) -> None:
        buffer = self._transcript_anim_buffer
        if not buffer:
            self._transcript_anim_timer.stop()
            self._transcript_label.setText("Transcription : ...")
            return
        if self._transcript_anim_index >= len(buffer):
            self._transcript_anim_timer.stop()
            self._transcript_label.setText(buffer)
            return
        self._transcript_anim_index += 1
        self._transcript_label.setText(buffer[: self._transcript_anim_index])

    def _persist_credentials(self) -> None:
        server = self.state.settings.server
        if server.password_plaintext:
            try:
                encrypted = protect(server.password_plaintext.encode('utf-8'))
            except Exception as exc:  # pragma: no cover
                QMessageBox.warning(
                    self,
                    'Chiffrement',
                    f"Impossible de chiffrer le mot de passe (conservation en clair) : {exc}",
                )
                encrypted = b''
            if encrypted:
                server.password_encrypted = encrypted
                server.password_plaintext = None
        save_settings(self.state.settings)

    # ------------------------------------------------------------------ #
    # Button callbacks
    # ------------------------------------------------------------------ #
    def _on_listen_pressed(self) -> None:
        if self._login_in_progress or not self.api.is_authenticated:
            return
        self._transcript_timeout.stop()
        self._pending_transcript_text = ""
        self._transcript_waiting = False
        self._last_transcript_raw = ""
        if self.controller.state.speaking:
            self.controller.stop_playback()
            self._listen_button.setDown(False)
            self._listen_button.setText("Maintenir pour parler")
            self._awaiting_response = False
            self._pending_metadata = {}
            self._last_metadata = {}
            self._record_started_at = None
            self._last_transcription_duration = None
            self._llm_started_at = None
            self._last_llm_duration = None
            if self._speaking_started_at is not None:
                elapsed = time.perf_counter() - self._speaking_started_at
                self._last_tts_duration = elapsed
                print(f"[voice] TTS stopped after {elapsed:.2f}s")
            self._speaking_started_at = None
            enabled = self.api.is_authenticated and not self._login_in_progress
            self._listen_button.setEnabled(enabled)
            self._update_idle_status()
            self._log_pipeline_summary("cancelled")
            return
        if self.controller.state.listening:
            return
        try:
            self.controller.start_listening()
        except Exception as exc:  # pragma: no cover
            QMessageBox.warning(self, "Audio", f"Impossible de demarrer l'ecoute : {exc}")
            return
        self._pipeline_started_at = time.perf_counter()
        self._record_started_at = self._pipeline_started_at
        self._last_transcription_duration = None
        self._llm_started_at = None
        self._last_llm_duration = None
        self._speaking_started_at = None
        self._last_tts_duration = None
        self._last_total_duration = None
        print("[voice] capture started")
        self._listen_button.setText("Relacher pour arreter")
        self._listen_button.setDown(True)
        self._set_status_text("Statut : ecoute en cours... (maintenir)")
        self._activity_value = 0.0
        self._refresh_activity_indicator()
        self._set_transcript("Transcription : (en attente)")

    def _on_listen_released(self) -> None:
        if not self.controller.state.listening:
            self._listen_button.setText("Maintenir pour parler")
            self._listen_button.setDown(False)
            enabled = self.api.is_authenticated and not self._login_in_progress
            self._listen_button.setEnabled(enabled)
            if enabled:
                self._update_idle_status()
            return
        self.controller.stop_listening()
        self._listen_button.setDown(False)
        self._listen_button.setText("Maintenir pour parler")
        self._enter_processing_state("Statut : transcription en cours...")
        self._transcript_timeout.start()

    def _on_toggle_listen_shortcut(self) -> None:
        if self._login_in_progress or not self.api.is_authenticated:
            return
        if self.controller.state.listening:
            self._on_listen_released()
        else:
            self._on_listen_pressed()

    def _on_toggle_eco_shortcut(self) -> None:
        settings = self.state.settings
        settings.audio.eco_mode = not settings.audio.eco_mode
        save_settings(settings)
        self.controller.state.settings = settings
        self.controller.apply_audio_settings()
        status = "activé" if settings.audio.eco_mode else "désactivé"
        self._set_status_text(f"Statut : mode éco {status}.")

    # ------------------------------------------------------------------ #
    # Controller callbacks (thread safe updates)
    # ------------------------------------------------------------------ #
    def _handle_speaking_state(self, speaking: bool) -> None:
        QMetaObject.invokeMethod(
            self,
            "_apply_speaking_state",
            Qt.QueuedConnection,
            Q_ARG(bool, speaking),
        )

    def _handle_transcript(self, event: TranscriptEvent) -> None:
        raw_text = (event.text or "").strip()
        if not event.final:
            if raw_text:
                self._pending_transcript_text = raw_text
            if not self._transcript_waiting:
                self._transcript_waiting = True
                QMetaObject.invokeMethod(
                    self._transcript_label,
                    "setText",
                    Qt.QueuedConnection,
                    Q_ARG(str, "Transcription : en cours..."),
                )
            return
        self._transcript_timeout.stop()
        self._transcript_waiting = False
        final_text = raw_text or self._pending_transcript_text
        self._pending_transcript_text = ""
        normalized = final_text.strip()
        if not normalized:
            normalized = "[aucune transcription]"
        self._last_transcript_raw = normalized
        if normalized and not normalized.startswith("[aucune"):
            QMetaObject.invokeMethod(
                self,
                "_apply_user_transcript",
                Qt.QueuedConnection,
                Q_ARG(str, normalized),
            )
        self._transcript_anim_buffer = f"Transcription : {normalized}"
        self._transcript_anim_index = 0
        QMetaObject.invokeMethod(self, "_start_transcript_animation", Qt.QueuedConnection)
        QMetaObject.invokeMethod(
            self,
            "_on_transcript_finalized",
            Qt.QueuedConnection,
            Q_ARG(str, normalized),
        )

    @Slot()
    def _handle_transcript_timeout(self) -> None:
        if self.controller.state.listening:
            return
        if self._record_started_at is None or not self._awaiting_response:
            return
        self._transcript_timeout.stop()
        candidate = (self._pending_transcript_text or "").strip()
        normalized = candidate or "[aucune transcription]"
        self._pending_transcript_text = ""
        self._transcript_waiting = False
        self._last_transcript_raw = normalized
        print("[voice] info: transcription timeout, finalisation forcee")
        self._set_transcript(f"Transcription : {normalized}")
        self._on_transcript_finalized(normalized)

    def _handle_response(self, text: str, is_final: bool) -> None:
        content = text.strip() or "..."
        QMetaObject.invokeMethod(
            self,
            "_update_chat_response",
            Qt.QueuedConnection,
            Q_ARG(str, content),
            Q_ARG(bool, is_final),
        )
        if is_final and content.strip():
            self._append_history_entry("IVY", content.strip())
        QMetaObject.invokeMethod(
            self,
            "_apply_response_state",
            Qt.QueuedConnection,
            Q_ARG(bool, is_final),
        )

    def _handle_metadata(self, data: dict) -> None:
        merged = dict(self._last_metadata or {})
        for key, value in (data or {}).items():
            if value in (None, False) and key in {"thinking"}:
                merged.pop(key, None)
            elif value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        self._pending_metadata = merged
        QMetaObject.invokeMethod(
            self,
            "_apply_metadata",
            Qt.QueuedConnection,
        )

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, (asyncio.CancelledError, FutureCancelledError)):
            return
        self._record_started_at = None
        message = str(exc) or exc.__class__.__name__
        QMetaObject.invokeMethod(
            self,
            "_apply_error_state",
            Qt.QueuedConnection,
            Q_ARG(str, message),
        )

    @Slot(str)
    def _apply_error_state(self, message: str) -> None:
        self._listen_button.setDown(False)
        if not self.controller.state.listening:
            self._listen_button.setText("Maintenir pour parler")
        enabled = self.api.is_authenticated and not self._login_in_progress and not self.controller.state.speaking
        self._listen_button.setEnabled(enabled)
        self._set_status_text(f"Statut : erreur ({message})")
        QMessageBox.warning(self, "Erreur", message)
        self._awaiting_response = False
        self._log_pipeline_summary("error")

    @Slot(str)
    def _on_transcript_finalized(self, _: str) -> None:
        if self._record_started_at is not None:
            duration = time.perf_counter() - self._record_started_at
            self._last_transcription_duration = duration
            print(f"[voice] ASR completed in {duration:.2f}s")
            self._record_started_at = None
        else:
            self._last_transcription_duration = None
        raw_text = (self._last_transcript_raw or "").strip()
        if not raw_text or raw_text.startswith('[aucune transcription]') or raw_text.startswith('[ASR indisponible]'):
            self._awaiting_response = False
            self._llm_started_at = None
            self._last_llm_duration = None
            self._last_tts_duration = None
            self._speaking_started_at = None
            self._last_transcript_raw = ''
            self._listen_button.setDown(False)
            self._listen_button.setText("Maintenir pour parler")
            enabled = self.api.is_authenticated and not self._login_in_progress
            self._listen_button.setEnabled(enabled)
            self._update_idle_status()
            self._log_pipeline_summary('silence')
            return
        if self._last_transcription_duration is not None:
            self._maybe_autoswitch_asr(self._last_transcription_duration)
        self._llm_started_at = time.perf_counter()
        self._enter_processing_state("Statut : question envoyee, attente reponse...")

    @Slot()
    def _apply_metadata(self) -> None:
        self._last_metadata = dict(self._pending_metadata) if self._pending_metadata else {}
        self._pending_metadata = {}
        self._update_search_results()
        self._maybe_present_commands()
        self._maybe_attach_feedback()
        if self._last_metadata.get("thinking"):
            self._set_status_text("Statut : réflexion en cours...")
            return
        if not self.controller.state.listening and not self._awaiting_response and not self.controller.state.speaking:
            self._update_idle_status()

    def _append_history_entry(self, role: str, content: str) -> None:
        text = (content or "").strip()
        if not text or text.startswith("[aucune transcription]"):
            return
        entry = ConversationEntry(
            message=ChatMessage(role=role.lower(), content=text),
            source="voice",
        )
        self.state.history.append(entry)
        if len(self.state.history) > 100:
            self.state.history.pop(0)
        if role.lower().startswith("vous"):
            self._last_user_message = text
            self._pending_feedback_question = text

    def _maybe_present_commands(self) -> None:
        commands_payload = self._last_metadata.get("commands")
        if not isinstance(commands_payload, list):
            return
        for raw in commands_payload:
            if not isinstance(raw, dict):
                continue
            try:
                command = SystemCommand.from_payload(raw)
            except Exception:
                continue
            if command.id in self._displayed_command_ids:
                continue
            self._displayed_command_ids.add(command.id)
            self._present_command_prompt(command)

    def _present_command_prompt(self, command: SystemCommand) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Commande système")
        if command.risk_level == CommandRisk.HIGH:
            box.setIcon(QMessageBox.Warning)
        elif command.risk_level == CommandRisk.MEDIUM:
            box.setIcon(QMessageBox.Information)
        else:
            box.setIcon(QMessageBox.Question)
        name = command.display_name or command.action or command.id
        box.setText(name or "Commande inconnue")
        box.setInformativeText(self._format_command_details(command))
        execute_btn = box.addButton("Exécuter", QMessageBox.AcceptRole)
        learn_btn = box.addButton("Apprentissage", QMessageBox.ActionRole)
        ignore_btn = box.addButton("Ignorer", QMessageBox.RejectRole)
        box.setDefaultButton(execute_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is execute_btn:
            self.controller.execute_command(command, status="accepted")
            self._set_status_text(f"Statut : commande {command.id} exécutée.")
        elif clicked is learn_btn:
            note, ok = QInputDialog.getText(
                self,
                "Apprentissage commande",
                "Décrivez l'action pour l'ajouter au moteur :",
            )
            if ok:
                note_value = note.strip()
                self.controller.report_command(command, note=note_value or None)
                self.controller.execute_command(command, status="rejected", note=note_value or None)
                self._set_status_text("Statut : commande envoyée pour apprentissage.")
            else:
                self.controller.execute_command(command, status="ignored")
        else:
            self.controller.execute_command(command, status="ignored")
            self._set_status_text("Statut : commande ignorée.")

    def _format_command_details(self, command: SystemCommand) -> str:
        args = " ".join(command.args or [])
        lines = [
            f"Action : {command.action or 'n/a'} {args}".strip(),
            f"Type : {command.type.value}",
            f"Risque : {command.risk_level.value}",
        ]
        if command.require_confirm:
            lines.append("Confirmation requise.")
        if command.fallback_hint:
            lines.append(f"Indice : {command.fallback_hint}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Chat rendering helpers
    # ------------------------------------------------------------------ #
    def _render_user_message(self, text: str) -> None:
        bubble = _ChatBubble("Vous", text, align_right=True)
        self._insert_chat_bubble(bubble)
        normalized = " ".join(text.lower().split())
        if normalized:
            self._topic_counts[normalized] = self._topic_counts.get(normalized, 0) + 1
            self._record_profile_topic(normalized)
            self._maybe_prompt_job_suggestion(text, normalized)
        self._active_assistant_item = None
        self._last_answer_bubble = None

    def _ensure_assistant_bubble(self) -> _ChatBubble:
        if self._active_assistant_item is not None:
            return self._active_assistant_item[1]
        item, bubble = self._insert_chat_bubble(_ChatBubble("IVY", "", align_right=False))
        self._active_assistant_item = (item, bubble)
        return bubble

    def _insert_chat_bubble(self, bubble: "_ChatBubble") -> tuple[QListWidgetItem, "_ChatBubble"]:
        item = QListWidgetItem()
        item.setSizeHint(bubble.sizeHint())
        self._chat_list.addItem(item)
        self._chat_list.setItemWidget(item, bubble)
        self._chat_list.scrollToBottom()
        self._prune_chat_list()
        return item, bubble

    def _record_profile_topic(self, normalized: str) -> None:
        profile = getattr(self.state.settings, "profile", None)
        if profile is None:
            return
        favorites = profile.favorite_topics
        favorites[normalized] = favorites.get(normalized, 0) + 1
        if len(favorites) > 25:
            least = min(favorites.items(), key=lambda item: item[1])[0]
            favorites.pop(least, None)
        profile.last_suggestion_topic = normalized
        save_settings(self.state.settings)

    def _maybe_prompt_job_suggestion(self, question: str, normalized: str) -> None:
        count = self._topic_counts.get(normalized, 0)
        if count < 3 or normalized in self._suggested_topics:
            return
        self._suggested_topics.add(normalized)
        box = QMessageBox(self)
        box.setWindowTitle("Suggestion IVY")
        box.setIcon(QMessageBox.Information)
        box.setText("Cette question revient souvent. Créer un job dédié ou mémoriser la réponse ?")
        box.setInformativeText(question)
        create_btn = box.addButton("Oui, me le rappeler", QMessageBox.AcceptRole)
        box.addButton("Plus tard", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == create_btn:
            QMessageBox.information(
                self,
                "Astuce",
                "Ouvrez la page 'Tâches & Programmation' pour planifier un job ou ajoutez ce prompt aux favoris.",
            )

    def _prune_chat_list(self) -> None:
        limit = 60
        while self._chat_list.count() > limit:
            self._chat_list.takeItem(0)

    @Slot(str, bool)
    def _update_chat_response(self, content: str, is_final: bool) -> None:
        bubble = self._ensure_assistant_bubble()
        bubble.set_text(content)
        bubble.set_pending(not is_final)
        if is_final:
            bubble.show_helper(None)
            self._last_answer_bubble = bubble
            self._active_assistant_item = None
            self._maybe_attach_feedback()

    def _maybe_attach_feedback(self) -> None:
        bubble = self._last_answer_bubble
        if bubble is None or bubble.feedback_enabled():
            return
        metadata = self._last_metadata if isinstance(self._last_metadata, dict) else {}
        qa_id = metadata.get("qa_id")
        if qa_id is None:
            return
        try:
            qa_value = int(qa_id)
        except (TypeError, ValueError):
            return
        question = self._pending_feedback_question or self._last_user_message
        answer = bubble.text()
        if not question or not answer:
            return
        bubble.enable_feedback(
            lambda helpful, q=question, a=answer, qa=qa_value, b=bubble: self._send_feedback(qa, q, a, helpful, b)
        )
        self._pending_feedback_question = ""

    def _send_feedback(
        self,
        qa_id: int,
        question: str,
        answer: str,
        helpful: bool,
        bubble: "_ChatBubble",
    ) -> None:
        comment = "voice_helpful" if helpful else "voice_flagged"

        async def _runner() -> None:
            await self.api.send_feedback(
                qa_id=qa_id,
                question=question,
                answer=answer,
                helpful=helpful,
                comment=comment,
            )

        future = asyncio.run_coroutine_threadsafe(_runner(), self.controller.loop)

        def _done(task: asyncio.Future) -> None:
            success = True
            message = "Merci pour le retour !" if helpful else "Suggestion transmise."
            try:
                task.result()
            except Exception as exc:
                success = False
                message = str(exc)
            QMetaObject.invokeMethod(
                self,
                "_apply_feedback_result",
                Qt.QueuedConnection,
                Q_ARG(object, bubble),
                Q_ARG(bool, success),
                Q_ARG(str, message),
            )

        future.add_done_callback(_done)

    @Slot(object, bool, str)
    def _apply_feedback_result(self, bubble_obj: object, success: bool, message: str) -> None:
        bubble = bubble_obj if isinstance(bubble_obj, _ChatBubble) else None
        if bubble is None:
            return
        bubble.mark_feedback_result(success, message)

    @Slot(str)
    def _apply_user_transcript(self, text: str) -> None:
        self._append_history_entry("Vous", text)
        self._render_user_message(text)

    @Slot(bool)
    def _apply_response_state(self, is_final: bool) -> None:
        self._listen_button.setEnabled(False)
        if is_final:
            self._awaiting_response = False
            self._listen_button.setDown(False)
            if self._llm_started_at is not None:
                llm_duration = time.perf_counter() - self._llm_started_at
                self._last_llm_duration = llm_duration
                print(f"[voice] LLM answered in {llm_duration:.2f}s")
                self._llm_started_at = None
            else:
                self._last_llm_duration = None
            if self.controller.state.speaking:
                self._set_status_text("Statut : synthese en cours...")
            else:
                self._update_idle_status()
                self._listen_button.setText("Maintenir pour parler")
                enabled = self.api.is_authenticated and not self._login_in_progress
                self._listen_button.setEnabled(enabled)
        else:
            self._set_status_text("Statut : reponse en cours...")

    @Slot(bool)
    def _apply_speaking_state(self, speaking: bool) -> None:
        self._waveform.set_speaking(speaking)
        if speaking:
            self._speaking_started_at = time.perf_counter()
            self._listen_button.setDown(False)
            self._listen_button.setText("Arreter lecture")
            self._listen_button.setEnabled(True)
            self._set_status_text("Statut : synthese en cours...")
            return
        if self._speaking_started_at is not None:
            duration = time.perf_counter() - self._speaking_started_at
            self._last_tts_duration = duration
            print(f"[voice] TTS playback finished in {duration:.2f}s")
            self._speaking_started_at = None
        self._listen_button.setDown(False)
        self._listen_button.setText("Maintenir pour parler")
        enabled = self.api.is_authenticated and not self._login_in_progress
        if self._awaiting_response:
            self._listen_button.setEnabled(False)
        else:
            self._listen_button.setEnabled(enabled)
            if not self.controller.state.listening:
                self._update_idle_status()
                self._log_pipeline_summary("complete")

    # ------------------------------------------------------------------ #
    # Utilities
    # ------------------------------------------------------------------ #
    def _set_status_text(self, text: str) -> None:
        self._status_label.setText(text)

    def _update_idle_status(self) -> None:
        text = "Statut : connecte (inactif)"
        metadata = self._format_metadata()
        if metadata:
            text += f" [{metadata}]"
        audio_info = self._format_audio_status()
        if audio_info:
            text += f" | {audio_info}"
        self._status_label.setText(text)

    def _format_metadata(self) -> str:
        if not self._last_metadata:
            return ""
        parts: list[str] = []
        classification = self._last_metadata.get("classification") or {}
        category = classification.get("category")
        if isinstance(category, str) and category:
            parts.append(f"classe={category}")
        match = self._last_metadata.get("match")
        if isinstance(match, dict):
            score = match.get("score")
            try:
                if score is not None:
                    parts.append(f"match={float(score):.2f}")
            except (TypeError, ValueError):
                pass
        if self._last_metadata.get("speculative"):
            parts.append("speculative")
        search_count = self._last_metadata.get("search_results_count")
        if isinstance(search_count, int) and search_count > 0:
            parts.append(f"web={search_count}")
        elif isinstance(self._last_metadata.get("search_results"), list):
            try:
                count = len(self._last_metadata["search_results"])
                if count:
                    parts.append(f"web={count}")
            except TypeError:
                pass
        latency = self._last_metadata.get("latency_ms")
        try:
            if latency is not None:
                parts.append(f"{int(latency)} ms")
        except (TypeError, ValueError):
            pass
        return " / ".join(parts)

    def _log_pipeline_summary(self, reason: str) -> None:
        if self._pipeline_started_at is None:
            return
        total = time.perf_counter() - self._pipeline_started_at
        self._last_total_duration = total
        self._pipeline_started_at = None
        self._last_transcript_raw = ''
        parts = [f'total={total:.2f}s']
        parts.append(self._fmt_duration('asr', self._last_transcription_duration))
        parts.append(self._fmt_duration('llm', self._last_llm_duration))
        parts.append(self._fmt_duration('tts', self._last_tts_duration))
        print('[voice] pipeline {reason}: '.format(reason=reason) + ' | '.join(filter(None, parts)))
        self._maybe_auto_adjust_tts()

    def _fmt_duration(self, label: str, value: float | None) -> str:
        if value is None:
            return f'{label}=NA'
        return f'{label}={value:.2f}s'

    def _maybe_auto_adjust_tts(self) -> None:
        audio = self.state.settings.audio
        if not getattr(audio, "auto_optimize_tts", True):
            return
        duration = self._last_tts_duration
        if duration is None:
            return
        delta = 0.0
        if duration > 7.0:
            delta = -0.02
        elif duration < 3.5:
            delta = 0.02
        if delta == 0.0:
            return
        new_scale = round(max(0.7, min(1.1, audio.tts_length_scale + delta)), 2)
        if abs(new_scale - audio.tts_length_scale) < 0.01:
            return
        audio.tts_length_scale = new_scale
        save_settings(self.state.settings)
        self.controller.apply_audio_settings()
        self.controller.refresh_tts_voice()
        print(f"[voice] auto-optimisation TTS -> {audio.tts_length_scale:.2f}")

    def _maybe_autoswitch_asr(self, duration: float) -> None:
        self._recent_asr_latencies.append(duration)
        avg = sum(self._recent_asr_latencies) / len(self._recent_asr_latencies)
        audio = self.state.settings.audio
        slow_threshold = self._ASR_SLOW_THRESHOLD
        fast_threshold = self._ASR_FAST_THRESHOLD
        fast_model = getattr(audio, "asr_fast_model", None)

        if duration >= slow_threshold and audio.asr_model != "faster-whisper-tiny":
            self._switch_asr_model("faster-whisper-tiny", duration)
            return

        if (
            fast_model
            and audio.asr_model == "faster-whisper-tiny"
            and len(self._recent_asr_latencies) == self._recent_asr_latencies.maxlen
            and avg <= fast_threshold
        ):
            self._switch_asr_model(fast_model, avg)

    def _switch_asr_model(self, model: str, metric: float) -> None:
        audio = self.state.settings.audio
        if audio.asr_model == model:
            return
        audio.asr_model = model
        save_settings(self.state.settings)
        self.controller.state.settings = self.state.settings
        self.controller.apply_audio_settings()
        self._auto_switch_done = model == "faster-whisper-tiny"
        print(f"[voice] ASR auto-switch vers {model} ({metric:.2f}s).")
        self._update_idle_status()

    def _format_audio_status(self) -> str:
        audio = self.state.settings.audio
        parts = [f"ASR={audio.asr_model}"]
        gpu_flag = "on" if audio.enable_gpu else "off"
        if audio.enable_gpu and self._gpu_available is False:
            gpu_flag = "off*"
        elif audio.enable_gpu and self._gpu_available is None:
            gpu_flag = "on?"
        parts.append(f"GPU={gpu_flag}")
        vad_flag = "off"
        if audio.eco_mode:
            level_map = {0: "L0", 1: "L1", 2: "L2", 3: "L3"}
            vad_flag = level_map.get(audio.vad_aggressiveness, f"L{audio.vad_aggressiveness}")
        parts.append(f"VAD={vad_flag}")
        if self._last_transcription_duration is not None:
            parts.append(f"time={self._last_transcription_duration:.1f}s")
        if self._last_llm_duration is not None:
            parts.append(f"llm={self._last_llm_duration:.1f}s")
        if self._last_tts_duration is not None:
            parts.append(f"tts={self._last_tts_duration:.1f}s")
        if self._last_total_duration is not None:
            parts.append(f"total={self._last_total_duration:.1f}s")
        return " ".join(parts)

    def _detect_gpu(self) -> bool | None:
        try:
            import torch  # type: ignore import-error
        except Exception:
            return None
        try:
            return bool(torch.cuda.is_available())  # type: ignore[attr-defined]
        except Exception:
            return None

    def _enter_processing_state(self, status: str) -> None:
        self._awaiting_response = True
        self._listen_button.setEnabled(False)
        self._set_status_text(status)

    def _update_search_results(self) -> None:
        results = self._last_metadata.get("search_results")
        if not isinstance(results, list) or not results:
            self._search_label.hide()
            self._search_label.setText("")
            return
        lines: list[str] = []
        for idx, item in enumerate(results[:3]):
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip() or "Sans titre"
            body = (item.get("body") or "").strip()
            if body:
                snippet = body[:160] + ("..." if len(body) > 160 else "")
                lines.append(f"{idx + 1}. {title} - {snippet}")
            else:
                lines.append(f"{idx + 1}. {title}")
        if not lines:
            self._search_label.hide()
            self._search_label.setText("")
            return
        query = (self._last_metadata.get("search_query") or "").strip()
        header = "Résultats web"
        if query:
            header = f'{header} pour "{query}"'
        self._search_label.setText(header + "\n" + "\n".join(lines))
        self._search_label.show()

    def _set_transcript(self, text: str) -> None:
        self._transcript_anim_timer.stop()
        self._transcript_anim_buffer = text
        self._transcript_anim_index = len(text)
        self._transcript_label.setText(text)

    # ------------------------------------------------------------------ #
    # Qt event overrides
    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            future = asyncio.run_coroutine_threadsafe(self.api.close(), self.controller.loop)
            future.result(timeout=2)
        except Exception:
            pass
        self.controller.shutdown()
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    # Settings dialog
    # ------------------------------------------------------------------ #
    def _open_settings_dialog(self) -> None:
        dialog = _AudioSettingsDialog(self.state.settings, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.apply(self.state.settings):
            save_settings(self.state.settings)
            audio = self.state.settings.audio
            self.controller.apply_audio_settings()
            if dialog.tts_changed:
                self.controller.refresh_tts_voice()
                print(
                    f"[voice] TTS mis a jour: longueur={audio.tts_length_scale:.2f}, "
                    f"pitch={audio.tts_pitch:.2f}"
                )
            self._gpu_available = self._detect_gpu()
            gpu_status = "on" if audio.enable_gpu else "off"
            vad_status = "on" if audio.eco_mode else "off"
            print(
                f"[voice] settings updated: ASR {audio.asr_model} "
                f"(GPU {gpu_status}, VAD {vad_status}, VAD-level {audio.vad_aggressiveness})"
            )
            if audio.enable_gpu and self._gpu_available is False:
                print("[voice] attention: GPU demande mais aucun dispositif CUDA detecte.")
            self._update_idle_status()


class _AudioSettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Parametrages audio")
        self.setModal(True)
        self.tts_changed = False

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Modele de transcription (ASR) :"))
        self._model_combo = QComboBox()
        models = [
            ("Faster Whisper - Tiny (CPU rapide)", "faster-whisper-tiny"),
            ("Faster Whisper - Small", "faster-whisper-small"),
            ("Faster Whisper - Medium", "faster-whisper-medium"),
            ("Faster Whisper - Large v3 (qualite maximale)", "faster-whisper-large-v3"),
        ]
        current_model = settings.audio.asr_model
        values = [value for _, value in models]
        for label, value in models:
            self._model_combo.addItem(label, userData=value)
        if current_model not in values:
            self._model_combo.addItem(f"Autre : {current_model}", userData=current_model)
        index = self._model_combo.findData(current_model)
        if index >= 0:
            self._model_combo.setCurrentIndex(index)
        layout.addWidget(self._model_combo)

        layout.addWidget(QLabel("Modele ASR rapide (auto-switch) :"))
        self._fast_model_combo = QComboBox()
        fast_model = getattr(settings.audio, "asr_fast_model", "faster-whisper-small")
        for label, value in models:
            self._fast_model_combo.addItem(label, userData=value)
        if fast_model not in values:
            self._fast_model_combo.addItem(f"Autre : {fast_model}", userData=fast_model)
        fast_index = self._fast_model_combo.findData(fast_model)
        if fast_index >= 0:
            self._fast_model_combo.setCurrentIndex(fast_index)
        layout.addWidget(self._fast_model_combo)

        self._gpu_checkbox = QCheckBox("Activer l'acceleration GPU (si disponible)")
        self._gpu_checkbox.setChecked(settings.audio.enable_gpu)
        layout.addWidget(self._gpu_checkbox)

        self._vad_checkbox = QCheckBox("Filtrer les silences automatiquement (VAD)")
        self._vad_checkbox.setChecked(settings.audio.eco_mode)
        self._vad_checkbox.stateChanged.connect(self._toggle_vad_controls)
        layout.addWidget(self._vad_checkbox)

        layout.addWidget(QLabel("Sensibilite du VAD :"))
        self._vad_level_combo = QComboBox()
        for label, value in [
            ("0 - tres sensible", 0),
            ("1 - sensible", 1),
            ("2 - equilibre", 2),
            ("3 - strict", 3),
        ]:
            self._vad_level_combo.addItem(label, userData=value)
        current_level = max(0, min(3, getattr(settings.audio, "vad_aggressiveness", 2)))
        index = self._vad_level_combo.findData(current_level)
        if index >= 0:
            self._vad_level_combo.setCurrentIndex(index)
        layout.addWidget(self._vad_level_combo)
        self._toggle_vad_controls()

        layout.addWidget(QLabel("Vitesse de la voix (1.0 = normal, plus petit = plus rapide) :"))
        self._tts_speed_spin = QDoubleSpinBox()
        self._tts_speed_spin.setRange(0.5, 1.5)
        self._tts_speed_spin.setSingleStep(0.05)
        self._tts_speed_spin.setDecimals(2)
        self._tts_speed_spin.setValue(getattr(settings.audio, "tts_length_scale", 0.92))
        layout.addWidget(self._tts_speed_spin)

        layout.addWidget(QLabel("Hauteur / expressivite (par defaut 0.85) :"))
        self._tts_pitch_spin = QDoubleSpinBox()
        self._tts_pitch_spin.setRange(0.2, 2.0)
        self._tts_pitch_spin.setSingleStep(0.05)
        self._tts_pitch_spin.setDecimals(2)
        self._tts_pitch_spin.setValue(getattr(settings.audio, "tts_pitch", 0.85))
        layout.addWidget(self._tts_pitch_spin)
        self._auto_tts_checkbox = QCheckBox("Optimiser automatiquement la vitesse TTS")
        self._auto_tts_checkbox.setChecked(getattr(settings.audio, "auto_optimize_tts", True))
        layout.addWidget(self._auto_tts_checkbox)
        layout.addWidget(QLabel("Voix TTS installee :"))
        self._tts_voice_combo = QComboBox()
        available_voices = _list_tts_presets()
        current_voice = getattr(settings.audio, "tts_voice", "fr-FR-piper-high/fr/fr_FR/upmc/medium")
        if not available_voices:
            self._tts_voice_combo.addItem("Aucune voix detectee (installez les ressources)", userData=current_voice)
        else:
            for label, value in available_voices:
                self._tts_voice_combo.addItem(label, userData=value)
        voice_index = self._tts_voice_combo.findData(current_voice)
        if voice_index < 0:
            self._tts_voice_combo.addItem(f"Actuel : {current_voice}", userData=current_voice)
            voice_index = self._tts_voice_combo.findData(current_voice)
        if voice_index >= 0:
            self._tts_voice_combo.setCurrentIndex(voice_index)
        layout.addWidget(self._tts_voice_combo)

        self._info_label = QLabel(
            "Astuce : utilisez scripts/install_voice_resources.py --asr pour telecharger un modele manquant."
        )
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self, settings: AppSettings) -> bool:
        self.tts_changed = False
        changed = False
        model = self._model_combo.currentData()
        if model and settings.audio.asr_model != model:
            settings.audio.asr_model = model
            changed = True
        fast_model = self._fast_model_combo.currentData()
        if fast_model and getattr(settings.audio, "asr_fast_model", None) != fast_model:
            settings.audio.asr_fast_model = fast_model
            changed = True
        gpu_enabled = self._gpu_checkbox.isChecked()
        if settings.audio.enable_gpu != gpu_enabled:
            settings.audio.enable_gpu = gpu_enabled
            changed = True
        eco_mode = self._vad_checkbox.isChecked()
        if settings.audio.eco_mode != eco_mode:
            settings.audio.eco_mode = eco_mode
            changed = True
        level = self._vad_level_combo.currentData()
        if level is not None and settings.audio.vad_aggressiveness != level:
            settings.audio.vad_aggressiveness = level
            changed = True
        tts_speed = round(float(self._tts_speed_spin.value()), 2)
        if getattr(settings.audio, "tts_length_scale", 0.92) != tts_speed:
            settings.audio.tts_length_scale = tts_speed
            changed = True
            self.tts_changed = True
        tts_pitch = round(float(self._tts_pitch_spin.value()), 2)
        if getattr(settings.audio, "tts_pitch", 0.85) != tts_pitch:
            settings.audio.tts_pitch = tts_pitch
            changed = True
            self.tts_changed = True
        auto_opt = self._auto_tts_checkbox.isChecked()
        if getattr(settings.audio, "auto_optimize_tts", True) != auto_opt:
            settings.audio.auto_optimize_tts = auto_opt
            changed = True
        voice_choice = self._tts_voice_combo.currentData()
        if isinstance(voice_choice, str) and voice_choice and settings.audio.tts_voice != voice_choice:
            settings.audio.tts_voice = voice_choice
            changed = True
            self.tts_changed = True
        return changed

    def _toggle_vad_controls(self) -> None:
        enabled = self._vad_checkbox.isChecked()
        self._vad_level_combo.setEnabled(enabled)





