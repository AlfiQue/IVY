"""Orchestrates audio capture, playback and interaction with IVY."""

from __future__ import annotations

import asyncio
from array import array
import contextlib
import re
import threading
from concurrent.futures import Future, CancelledError as FutureCancelledError
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

from ..audio.capture import CaptureConfig, MicrophoneCapture
from ..audio.playback import PlaybackConfig, SpeechPlayback
from ..audio.tts import PiperConfig, PiperTTS
from ..audio.vad import VADConfig, VoiceActivityDetector
from ..config.paths import models_dir
from ..services.api import IvyAPI
from ..services.schemas import ChatMessage, TranscriptEvent
from ..state.app_state import AppState


TranscriptCallback = Callable[[TranscriptEvent], None]
ResponseCallback = Callable[[str, bool], None]
MetadataCallback = Callable[[dict[str, Any]], None]
ErrorCallback = Callable[[Exception], None]


class VoiceController:
    """High-level coordinator for the voice client."""

    def __init__(
        self,
        state: AppState,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.state = state
        if loop is not None:
            self.loop = loop
            self._owns_loop = False
            self._loop_thread: Optional[threading.Thread] = None
        else:
            self.loop = asyncio.new_event_loop()
            self._owns_loop = True
            self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._loop_thread.start()

        audio_settings = state.settings.audio
        use_vad = audio_settings.eco_mode
        vad_config = VADConfig(aggressiveness=max(0, min(3, audio_settings.vad_aggressiveness)))
        self.vad = VoiceActivityDetector(vad_config) if use_vad else None
        capture_config = CaptureConfig(
            device_name=audio_settings.input_device,
            deliver_silence=not use_vad,
            frame_duration_ms=25 if use_vad else 20,
        )
        self.capture = MicrophoneCapture(config=capture_config, vad=self.vad)
        self.capture.bind(self._handle_frame)

        playback_config = PlaybackConfig(
            sample_rate=22_050,
            channels=1,
            device_name=state.settings.audio.output_device,
        )
        self.playback = SpeechPlayback(playback_config)

        self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=256)
        self._listening = False

        self._api: Optional[IvyAPI] = None
        self._transcript_callback: Optional[TranscriptCallback] = None
        self._response_callback: Optional[ResponseCallback] = None
        self._metadata_callback: Optional[MetadataCallback] = None
        self._error_callback: Optional[ErrorCallback] = None
        self._login_future: Optional[Future] = None
        self._stream_future: Optional[Future] = None
        self._response_task: Optional[asyncio.Task] = None

        self._debug_frame_counter = 0

        self._tts: Optional[PiperTTS] = None
        self._tts_lock = threading.Lock()
        self._activity_callback: Optional[Callable[[float], None]] = None
        self._speech_callback: Optional[Callable[[bool], None]] = None
        self._tts_activity_callback: Optional[Callable[[float], None]] = None
        self._speech_chunks: int = 0
        self._speech_tasks: set[asyncio.Task[Any]] = set()
        self._conversation_id: Optional[int] = None

        self._thinking_task: Optional[asyncio.Task[None]] = None
        self._thinking_delay = 1.2

        self.apply_audio_settings()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def attach_api(
        self,
        api: IvyAPI,
        *,
        on_transcript: TranscriptCallback,
        on_response: ResponseCallback,
        on_error: Optional[ErrorCallback] = None,
        auto_login: bool = False,
    ) -> None:
        """Attach the Ivy API client and callbacks."""
        self._api = api
        self._transcript_callback = on_transcript
        self._response_callback = on_response
        self._error_callback = on_error
        if auto_login and not api.is_authenticated:
            self._login_future = asyncio.run_coroutine_threadsafe(api.login(), self.loop)

    def set_activity_callback(self, callback: Optional[Callable[[float], None]]) -> None:
        """Register a callback receiving audio activity levels (0..1)."""
        self._activity_callback = callback

    def set_speech_callback(self, callback: Optional[Callable[[bool], None]]) -> None:
        """Register a callback triggered when TTS playback starts or stops."""
        self._speech_callback = callback

    def set_tts_activity_callback(self, callback: Optional[Callable[[float], None]]) -> None:
        """Register a callback receiving playback activity levels."""
        self._tts_activity_callback = callback

    def set_metadata_callback(self, callback: Optional[MetadataCallback]) -> None:
        """Register a callback to receive metadata from the LLM response."""
        self._metadata_callback = callback

    def start_listening(self) -> None:
        """Start microphone capture and feed the async queue."""
        if self._listening:
            return
        self._queue = asyncio.Queue(maxsize=8)
        self.capture.start()
        self.state.listening = True
        self._listening = True
        self._start_stream_task()

    def stop_listening(self) -> None:
        """Stop microphone capture and signal the streaming coroutine."""
        if not self._listening:
            return
        self.capture.stop()
        self.state.listening = False
        self._listening = False
        self.loop.call_soon_threadsafe(self._signal_stop_marker)

        future = self._stream_future
        if future is not None:
            def _cleanup(fut: Future) -> None:
                try:
                    fut.result()
                except asyncio.CancelledError:
                    return
                except FutureCancelledError:
                    return
                except Exception as exc:  # pragma: no cover - logged to UI
                    self._notify_error(exc)
                finally:
                    if self._stream_future is fut:
                        self._stream_future = None

            future.add_done_callback(_cleanup)

    async def frame_stream(self) -> AsyncIterator[bytes]:
        """Async generator yielding captured audio frames."""
        while True:
            frame = await self._queue.get()
            if frame is None:
                break
            yield frame

    def play_pcm(self, pcm_data: bytes) -> None:
        """Queue PCM data for playback."""
        self.playback.play(pcm_data)
        sample_rate = self.playback.config.sample_rate
        channels = self.playback.config.channels or 1
        length_bytes = len(pcm_data)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.loop.call_soon_threadsafe(
                self._register_speech_chunk,
                length_bytes,
                sample_rate,
                channels,
            )
        else:
            self._register_speech_chunk(length_bytes, sample_rate, channels)

    def stop_playback(self) -> None:
        """Stop playback."""
        self.playback.stop()
        self.state.speaking = False
        for task in list(self._speech_tasks):
            task.cancel()
        self._speech_tasks.clear()
        self._speech_chunks = 0
        self._emit_speaking(False)

    def pause_playback(self) -> None:
        """Pause playback."""
        self.playback.pause()

    def resume_playback(self) -> None:
        """Resume playback."""
        self.playback.resume()

    def shutdown(self) -> None:
        """Release audio resources."""
        if self._listening:
            self.stop_listening()
        self.stop_playback()
        if self._stream_future:
            self._stream_future.cancel()
        if self._response_task:
            self._response_task.cancel()
        if self._owns_loop and self._loop_thread:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._loop_thread.join(timeout=1)
            self._loop_thread = None

    def apply_audio_settings(self) -> None:
        """Refresh capture and playback devices based on current settings."""
        audio = self.state.settings.audio
        self.capture.config.device_name = audio.input_device
        self.playback.config.device_name = audio.output_device
        use_vad = audio.eco_mode
        self.capture.config.deliver_silence = not use_vad
        self.capture.config.frame_duration_ms = 25 if use_vad else 20
        level = max(0, min(3, getattr(audio, "vad_aggressiveness", 2)))
        if use_vad:
            if isinstance(self.capture.vad, VoiceActivityDetector):
                self.capture.vad.update_aggressiveness(level)
            else:
                self.capture.vad = VoiceActivityDetector(VADConfig(aggressiveness=level))
        else:
            self.capture.vad = None
        self.vad = self.capture.vad

    def refresh_tts_voice(self) -> None:
        """Invalidate the cached Piper voice so the next synthesis reloads it."""
        with self._tts_lock:
            self._tts = None

    def execute_command(self, command: SystemCommand, *, status: str = "accepted", note: str | None = None) -> None:
        """Send a command acknowledgement to the backend."""
        if self._api is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._api.execute_command(command, status=status, note=note),
            self.loop,
        )
        future.add_done_callback(self._handle_command_future)

    def report_command(self, command: SystemCommand, note: str | None = None) -> None:
        """Report a command for learning/confirmation."""
        if self._api is None:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._api.report_command(command, note=note),
            self.loop,
        )
        future.add_done_callback(self._handle_command_future)

    # ------------------------------------------------------------------ #
    # Internal streaming orchestration
    # ------------------------------------------------------------------ #
    def _start_stream_task(self) -> None:
        if self._api is None:
            return
        if self._stream_future is not None:
            if not self._stream_future.done():
                self._stream_future.cancel()
                try:
                    self._stream_future.result()
                except Exception:
                    pass
            self._stream_future = None
        if self._login_future:
            try:
                self._login_future.result()
            except Exception as exc:  # pragma: no cover - propagated to UI
                self._notify_error(exc)
                self._login_future = None
                return
            self._login_future = None
        coroutine = self._run_stream()
        self._stream_future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        self._stream_future.add_done_callback(lambda _: setattr(self, '_stream_future', None))

    def _stop_stream_task(self) -> None:
        if self._stream_future:
            self._stream_future.cancel()
            try:
                self._stream_future.result()
            except Exception:
                pass
            self._stream_future = None

    async def _run_stream(self) -> None:
        """Stream microphone frames to IVY and process transcription events."""
        if self._api is None:
            return
        try:
            async for event in self._api.stream_voice(
                self.frame_stream(),
                sample_rate=self.capture.config.sample_rate,
            ):
                self._emit_transcript(event)
                clean_text = event.text.strip()
                if event.final and clean_text and not clean_text.startswith('[aucune transcription]') and not clean_text.startswith('[ASR indisponible]'):
                    if self._response_task and not self._response_task.done():
                        self._response_task.cancel()
                    self._response_task = asyncio.create_task(self._handle_user_transcript(clean_text))
                    self._schedule_thinking_prompt()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover
            self._notify_error(exc)

    async def _handle_user_transcript(self, text: str) -> None:
        """Send the final user transcript to IVY and speak the reply."""
        if self._api is None:
            return
        metadata: dict[str, Any] = {}
        if self._conversation_id is not None:
            metadata["conversation_id"] = self._conversation_id
        message = ChatMessage(role="user", content=text, metadata=metadata)
        buffer = ""
        start_time = asyncio.get_running_loop().time()
        try:
            async for chunk in self._api.send_chat(message):
                if not chunk:
                    continue
                buffer += chunk
                self._emit_response(buffer, partial=True)
            final_text = buffer.strip()
            if final_text:
                elapsed = asyncio.get_running_loop().time() - start_time
                print(f"[voice] LLM API latency {elapsed:.2f}s")
                self._emit_response(final_text, partial=False)
                await self._speak_text(final_text)
                if self._api:
                    summary = self._build_search_summary(self._api.last_chat_metadata)
                    if summary:
                        await self._speak_text(summary)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover
            self._notify_error(exc)
        else:
            if self._api:
                new_conversation = self._api.last_conversation_id
                if new_conversation is not None:
                    self._conversation_id = new_conversation
                self._emit_metadata(self._api.last_chat_metadata)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _emit_transcript(self, event: TranscriptEvent) -> None:
        if self._transcript_callback:
            self._transcript_callback(event)

    def _emit_response(self, text: str, *, partial: bool) -> None:
        if self._response_callback:
            self._response_callback(text, not partial)

    def _emit_metadata(self, data: dict[str, Any]) -> None:
        if data and self._metadata_callback:
            self._metadata_callback(data)

    def _handle_command_future(self, future: Future[Any]) -> None:
        try:
            future.result()
        except Exception as exc:  # pragma: no cover - surfaced to UI
            self._notify_error(exc)

    def _notify_error(self, exc: Exception) -> None:
        if isinstance(exc, (asyncio.CancelledError, FutureCancelledError)):
            return
        try:
            print(f"[voice] error: {exc!r}")
        except Exception:
            pass
        if self._error_callback:
            self._error_callback(exc)

    # ------------------------------------------------------------------ #
    # TTS handling
    # ------------------------------------------------------------------ #
    async def _speak_text(self, text: str) -> None:
        """Convert text to audio with Piper and enqueue playback."""
        text = text.strip()
        if not text:
            return
        self._cancel_thinking_prompt()
        try:
            tts = self._ensure_tts()
        except FileNotFoundError as exc:  # pragma: no cover - missing assets
            self._notify_error(exc)
            return

        text = self._sanitize_tts_text(text)
        extracted = self._extract_sentences(text)
        sentences = [sentence.strip() for sentence, _length in extracted if sentence.strip()]
        if sentences:
            consumed = sum(length for _sentence, length in extracted)
            remainder = text[consumed:].strip()
            if remainder:
                sentences.append(remainder)
        else:
            sentences = [text]

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[tuple[bytes, int, int]]] = asyncio.Queue()

        def producer() -> None:
            try:
                for sentence in sentences:
                    for chunk in tts.synthesize_stream(sentence):
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except Exception as exc:  # pragma: no cover
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        producer_future = loop.run_in_executor(None, producer)
        total_bytes = 0
        sample_rate = self.playback.config.sample_rate
        channels = self.playback.config.channels or 1
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                pcm_bytes, chunk_rate, chunk_channels = item
                if not pcm_bytes:
                    continue
                if total_bytes == 0 and self._speech_chunks == 0:
                    self.state.speaking = True
                    self._emit_speaking(True)
                if self.playback.config.sample_rate != chunk_rate or self.playback.config.channels != chunk_channels:
                    self.playback.stop()
                    self.playback.config.sample_rate = chunk_rate
                    self.playback.config.channels = chunk_channels
                self.playback.play(pcm_bytes)
                self._emit_tts_activity(self._estimate_level(pcm_bytes))
                total_bytes += len(pcm_bytes)
                sample_rate = chunk_rate
                channels = chunk_channels
        except Exception as exc:  # pragma: no cover
            self._notify_error(exc)
        finally:
            with contextlib.suppress(Exception):
                await producer_future
        if total_bytes:
            self._register_speech_chunk(total_bytes, sample_rate, channels)
        self._emit_tts_activity(0.0)

    def _ensure_tts(self) -> PiperTTS:
        """Load the Piper voice if missing."""
        with self._tts_lock:
            if self._tts is not None:
                return self._tts
            audio_settings = self.state.settings.audio
            base = models_dir() / "tts" / audio_settings.tts_voice
            model_path = self._find_file(base, ".onnx")
            config_path = self._find_file(base, ".onnx.json")
            length_scale = max(0.5, min(2.0, getattr(audio_settings, "tts_length_scale", 0.92)))
            pitch = max(0.1, min(2.0, getattr(audio_settings, "tts_pitch", 0.85)))
            self._tts = PiperTTS(
                PiperConfig(
                    model_path=model_path,
                    config_path=config_path,
                    length_scale=length_scale,
                    noise_scale=pitch,
                )
            )
            return self._tts

    @staticmethod
    def _find_file(root: Path, extension: str) -> Path:
        for candidate in root.rglob(f"*{extension}"):
            return candidate
        raise FileNotFoundError(f"Impossible de trouver un fichier {extension} sous {root}")

    @staticmethod
    def _extract_sentences(buffer: str) -> list[tuple[str, int]]:
        sentences: list[tuple[str, int]] = []
        current = ""
        for char in buffer:
            current += char
            if char in ".?!":
                sentences.append((current.strip(), len(current)))
                current = ""
        return sentences

    @staticmethod
    def _sanitize_tts_text(text: str) -> str:
        cleaned = re.sub(r"[*_`#<>]", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    # ------------------------------------------------------------------ #
    # Capture callbacks / loop management
    # ------------------------------------------------------------------ #
    def _handle_frame(self, frame: bytes) -> None:
        """Receive audio frames from the capture callback (sounddevice thread)."""
        if not self._listening:
            return
        try:
            self.loop.call_soon_threadsafe(self._enqueue_frame, frame)
        except RuntimeError:  # pragma: no cover
            self._listening = False

    def _enqueue_frame(self, frame: bytes) -> None:
        """Push a frame into the async queue, dropping the oldest if full."""
        try:
            self._queue.put_nowait(frame)
            self._debug_frame_counter += 1
            if self._debug_frame_counter % 10 == 0:
                print(f"[voice] frames captured: {self._debug_frame_counter}")
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(frame)
                self._debug_frame_counter += 1
                if self._debug_frame_counter % 10 == 0:
                    print(f"[voice] frames captured: {self._debug_frame_counter}")
            except asyncio.QueueFull:
                # Still full: drop the frame silently.
                pass
        level = self._estimate_level(frame)
        self._emit_activity(level)

    def _emit_activity(self, level: float) -> None:
        if self._activity_callback:
            try:
                self._activity_callback(level)
            except Exception:
                pass

    def _emit_speaking(self, speaking: bool) -> None:
        if self._speech_callback:
            try:
                self._speech_callback(speaking)
            except Exception:
                pass

    def _emit_tts_activity(self, level: float) -> None:
        if self._tts_activity_callback:
            try:
                self._tts_activity_callback(level)
            except Exception:
                pass

    def _register_speech_chunk(self, length_bytes: int, sample_rate: int, channels: int) -> None:
        if length_bytes <= 0 or sample_rate <= 0 or channels <= 0:
            return
        channels = max(1, channels)
        bytes_per_sample = 2  # pcm_s16le
        duration = length_bytes / (sample_rate * channels * bytes_per_sample)
        if duration <= 0:
            return
        duration += 0.15  # guard to cover buffering jitter
        self._speech_chunks += 1
        self.state.speaking = True
        self._emit_speaking(True)

        task = asyncio.create_task(self._release_speech_after(duration))
        self._speech_tasks.add(task)
        task.add_done_callback(self._speech_tasks.discard)

    async def _release_speech_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        finally:
            self._speech_chunks = max(0, self._speech_chunks - 1)
            if self._speech_chunks == 0:
                self.state.speaking = False
                self._emit_speaking(False)

    @staticmethod
    def _estimate_level(frame: bytes) -> float:
        samples = array("h")
        samples.frombytes(frame)
        if not samples:
            return 0.0
        peak = max(abs(sample) for sample in samples)
        return min(1.0, peak / 32768.0)

    def _signal_stop_marker(self) -> None:
        """Insert a stop marker into the queue, handling saturation."""
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            # queue shouldn't be full, but ensure marker inserted
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def _run_loop(self) -> None:
        """Run the owned asyncio loop in a dedicated thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _schedule_thinking_prompt(self) -> None:
        if self._thinking_task and not self._thinking_task.done():
            return
        self._thinking_task = asyncio.create_task(self._delayed_thinking_prompt())

    def _cancel_thinking_prompt(self) -> None:
        if self._thinking_task and not self._thinking_task.done():
            self._thinking_task.cancel()
        self._thinking_task = None
        self._emit_metadata({"thinking": False})

    async def _delayed_thinking_prompt(self) -> None:
        try:
            await asyncio.sleep(self._thinking_delay)
            if self._response_task is None or self._response_task.done() or self.state.speaking:
                return
            self._emit_metadata({"thinking": True})
        except asyncio.CancelledError:
            return

    def _build_search_summary(self, meta: dict[str, Any]) -> str:
        results = meta.get("search_results")
        if not isinstance(results, list) or not results:
            return ""

        snippets: list[str] = []
        for item in results[:2]:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            body = (item.get("body") or item.get("text") or "").strip()
            body = body.replace("\n", " ")
            if body:
                body = body[:160].rstrip(" ,.;")
            if title and body:
                snippets.append(f"{title}: {body}")
            elif title:
                snippets.append(title)
            elif body:
                snippets.append(body)
        if not snippets:
            return ""
        joined = " Ensuite, ".join(snippets)
        query = (meta.get("search_query") or meta.get("query") or "").strip()
        if query:
            return f'Selon la recherche web pour "{query}", {joined}.'
        return f"Selon la recherche web, {joined}."

