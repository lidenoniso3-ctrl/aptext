"""
Text to Voice — Desktop App (v2.1)
- إضافة gTTS كخيار احتياطي تلقائي عند فشل edge-tts
"""
import sys
import os
import re
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

import edge_tts
from gtts import gTTS  # الخيار الاحتياطي

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLineEdit, QTextEdit, QPlainTextEdit, QPushButton,
    QLabel, QProgressBar, QFileDialog, QMessageBox, QComboBox,
    QSlider, QSpinBox, QTabWidget
)
from PySide6.QtCore import (
    QThread, Signal, Qt, QSettings, QUrl
)
from PySide6.QtGui import (
    QDesktopServices, QFont, QColor, QTextCursor
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


# ============================================================
# قائمة الأصوات
# ============================================================

VOICES = {
    "🇺🇸 Aria (Female - American)": "en-US-AriaNeural",
    "🇺🇸 Guy (Male - American)": "en-US-GuyNeural",
    "🇺🇸 Jenny (Female - American)": "en-US-JennyNeural",
    "🇺🇸 Monica (Female - American)": "en-US-MonicaNeural",
    "🇬🇧 Libby (Female - British)": "en-GB-LibbyNeural",
    "🇬🇧 Sonia (Female - British)": "en-GB-SoniaNeural",
    "🇬🇧 Ryan (Male - British)": "en-GB-RyanNeural",
    "🇸🇦 حامد (ذكر - سعودي)": "ar-SA-HamedNeural",
    "🇸🇦 زريّة (أنثى - سعودي)": "ar-SA-ZariyahNeural",
    "🇪🇬 شاكر (ذكر - مصري)": "ar-EG-ShakirNeural",
    "🇪🇬 سلمى (أنثى - مصري)": "ar-EG-SalmaNeural",
    "🇩🇿 أمينة (أنثى - جزائري)": "ar-DZ-AminaNeural",
    "🇩🇿 إسماعيل (ذكر - جزائري)": "ar-DZ-IsmaelNeural",
    "🇲🇦 Jamal (Male - Moroccan)": "ar-MA-JamalNeural",
    "🇲🇦 Mouna (Female - Moroccan)": "ar-MA-MounaNeural",
    "🇫🇷 Denise (Female)": "fr-FR-DeniseNeural",
    "🇫🇷 Henri (Male)": "fr-FR-HenriNeural",
    "🇪🇸 Elvira (Female)": "es-ES-ElviraNeural",
    "🇪🇸 Alvaro (Male)": "es-ES-AlvaroNeural",
    "🇩🇪 Katja (Female)": "de-DE-KatjaNeural",
    "🇩🇪 Conrad (Male)": "de-DE-ConradNeural",
    "🇮🇹 Elsa (Female)": "it-IT-ElsaNeural",
    "🇮🇹 Diego (Male)": "it-IT-DiegoNeural",
    "🇹🇷 Emel (Female)": "tr-TR-EmelNeural",
    "🇹🇷 Ahmet (Male)": "tr-TR-AhmetNeural",
    "🇷🇺 Svetlana (Female)": "ru-RU-SvetlanaNeural",
    "🇷🇺 Dmitry (Male)": "ru-RU-DmitryNeural",
    "🇯🇵 Nanami (Female)": "ja-JP-NanamiNeural",
    "🇯🇵 Keita (Male)": "ja-JP-KeitaNeural",
    "🇨🇳 Xiaoxiao (Female)": "zh-CN-XiaoxiaoNeural",
    "🇨🇳 Yunxi (Male)": "zh-CN-YunxiNeural",
}

DEFAULT_VOICE = "🇺🇸 Aria (Female - American)"


# ============================================================
# Worker Thread
# ============================================================

class TTSWorker(QThread):
    msg = Signal(str)
    pct = Signal(int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, mode: str, source: str, output: str,
                 voice: str, rate: str, pitch: str, volume: str,
                 pause_ms: int = 500):
        super().__init__()
        self.mode = mode
        self.source = source
        self.output = output
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.pause_ms = pause_ms
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.msg.emit("⛔ Cancelling...")

    def _check_cancel(self):
        if self._cancelled or self.isInterruptionRequested():
            raise InterruptedError("Cancelled by user")

    def _emit(self, m: str, p: int):
        self.msg.emit(m)
        self.pct.emit(p)

    def run(self):
        try:
            asyncio.run(self._run())
        except InterruptedError as e:
            self.error.emit(str(e))
        except Exception as e:
            import traceback
            self.error.emit(f"Unexpected error: {e}\n{traceback.format_exc(limit=5)}")

    async def _run(self):
        self._check_cancel()
        if self.mode == "text":
            await self._text_to_speech(self.source, self.output)
        elif self.mode == "txt":
            await self._txt_to_speech(self.source, self.output)
        elif self.mode == "srt":
            await self._srt_to_speech(self.source, self.output)
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

    async def _text_to_speech(self, text: str, output_file: str) -> bool:
        self._emit(f"🎙️ Generating voice...", 10)
        self._check_cancel()

        if not text.strip():
            raise ValueError("Text is empty")

        self._emit(f"   Voice: {self.voice}", 30)
        self._emit(f"   Length: {len(text)} chars", 40)
        self._check_cancel()

        # محاولة edge-tts أولاً، ثم gTTS عند الفشل
        try:
            comm = edge_tts.Communicate(
                text, self.voice,
                rate=self.rate, pitch=self.pitch, volume=self.volume
            )
            await comm.save(output_file)
            
            if not (os.path.exists(output_file) and os.path.getsize(output_file) > 1000):
                raise RuntimeError("Edge-TTS output empty")
                
        except Exception as e:
            self._emit(f"⚠️ Edge-TTS failed ({str(e)[:50]}), falling back to gTTS...", 50)
            # استخراج كود اللغة من الصوت (مثال: ar-SA-HamedNeural -> ar)
            lang_code = self.voice.split("-")[0]
            tts = gTTS(text=text, lang=lang_code, slow=False)
            await asyncio.to_thread(tts.save, output_file)

        self._check_cancel()
        if not (os.path.exists(output_file) and os.path.getsize(output_file) > 1000):
            raise RuntimeError("Output file is empty or missing")

        size_kb = os.path.getsize(output_file) / 1024
        self._emit(f"✅ Saved: {output_file} ({size_kb:.1f} KB)", 100)
        self.finished.emit(output_file)
        return True

    async def _txt_to_speech(self, input_file: str, output_file: str) -> bool:
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"File not found: {input_file}")

        with open(input_file, "r", encoding="utf-8") as f:
            text = f.read().strip()

        if not text:
            raise ValueError(f"File is empty: {input_file}")

        self._emit(f"📄 Loaded file: {Path(input_file).name}", 5)
        return await self._text_to_speech(text, output_file)

    async def _srt_to_speech(self, srt_file: str, output_file: str) -> bool:
        from pydub import AudioSegment
        import shutil

        if not os.path.exists(srt_file):
            raise FileNotFoundError(f"SRT file not found: {srt_file}")

        with open(srt_file, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        texts = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if re.match(r"^\d+$", line):
                continue
            if "-->" in line:
                continue
            texts.append(line)

        if not texts:
            raise ValueError("No text found in SRT file")

        self._emit(f"📝 Extracted {len(texts)} lines from SRT", 5)

        temp_dir = Path(tempfile.gettempdir()) / f"tts_srt_{datetime.now():%Y%m%d_%H%M%S}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        audio_segments = []
        silence = AudioSegment.silent(duration=self.pause_ms)
        lang_code = self.voice.split("-")[0]

        try:
            for i, text in enumerate(texts):
                self._check_cancel()
                temp_mp3 = temp_dir / f"line_{i:04d}.mp3"
                pct = 5 + int(85 * (i + 1) / len(texts))
                self._emit(f"   [{i+1}/{len(texts)}] {text[:50]}...", pct)

                # محاولة Edge-TTS أولاً
                success = False
                try:
                    comm = edge_tts.Communicate(
                        text, self.voice,
                        rate=self.rate, pitch=self.pitch, volume=self.volume
                    )
                    await comm.save(str(temp_mp3))
                    if temp_mp3.exists() and temp_mp3.stat().st_size > 500:
                        success = True
                except Exception:
                    pass

                # إذا فشل Edge-TTS، استخدم gTTS كخيار احتياطي
                if not success:
                    self._emit(f"   🔄 Fallback to gTTS for line {i+1}", pct)
                    try:
                        tts = gTTS(text=text, lang=lang_code, slow=False)
                        await asyncio.to_thread(tts.save, str(temp_mp3))
                        if temp_mp3.exists() and temp_mp3.stat().st_size > 500:
                            success = True
                    except Exception as ge:
                        self._emit(f"   ⚠️ gTTS also failed for line {i+1}: {str(ge)[:40]}", pct)

                if success:
                    try:
                        seg = AudioSegment.from_file(str(temp_mp3))
                        audio_segments.append(seg)
                        if i < len(texts) - 1:
                            audio_segments.append(silence)
                    except Exception as e:
                        self._emit(f"   ⚠️ Failed to load audio for line {i+1}: {e}", pct)

                # تأخير بسيط
                await asyncio.sleep(1.0)

            if not audio_segments:
                raise RuntimeError("No audio was generated from SRT")

            self._emit(f"🔗 Merging {len(audio_segments)} segments...", 92)
            self._check_cancel()

            combined = audio_segments[0]
            for seg in audio_segments[1:]:
                combined += seg

            combined.export(output_file, format="mp3")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self._emit(f"✅ Saved: {output_file}", 100)
        self.finished.emit(output_file)
        return True


# ============================================================
# Main Window (بدون تغيير في الواجهة)
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎙️ Text to Voice — Desktop App (v2.1)")
        self.setMinimumSize(900, 750)
        self.worker = None
        self.settings = QSettings("TextToVoiceApp", "Main")
        self._last_output = ""
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        c = QWidget()
        self.setCentralWidget(c)
        main_layout = QVBoxLayout(c)

        tabs = QTabWidget()
        main_layout.addWidget(tabs, 1)

        # --- Tab 1: Text Input ---
        text_tab = QWidget()
        text_l = QVBoxLayout(text_tab)
        text_l.addWidget(QLabel("📝 أدخل النص أو الصق محتوى SRT:"))
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText(
            "Hello, this is a test of text to speech.\n"
            "أو الصق نصاً عربياً هنا...\n"
            "أو الصق محتوى ملف SRT كاملاً وسيتعرف عليه تلقائياً")
        self.text_input.setFont(QFont("Consolas", 11))
        text_l.addWidget(self.text_input, 1)

        load_l = QHBoxLayout()
        load_txt_btn = QPushButton("📄 تحميل ملف .txt")
        load_txt_btn.clicked.connect(self._load_txt)
        load_l.addWidget(load_txt_btn)
        load_srt_btn = QPushButton("🎬 تحميل ملف .srt")
        load_srt_btn.clicked.connect(self._load_srt)
        load_l.addWidget(load_srt_btn)
        clear_btn = QPushButton("🧹 مسح")
        clear_btn.clicked.connect(lambda: self.text_input.clear())
        load_l.addWidget(clear_btn)
        load_l.addStretch()
        self.char_count = QLabel("0 حرف")
        self.char_count.setStyleSheet("color: gray;")
        load_l.addWidget(self.char_count)
        text_l.addLayout(load_l)
        self.text_input.textChanged.connect(self._update_char_count)
        tabs.addTab(text_tab, "📝 Text Input")

        # --- Tab 2: Settings ---
        settings_tab = QWidget()
        settings_l = QGridLayout(settings_tab)
        r = 0
        settings_l.addWidget(QLabel("🎙️ الصوت:"), r, 0)
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(list(VOICES.keys()))
        self.voice_combo.setCurrentText(DEFAULT_VOICE)
        self.voice_combo.setMinimumWidth(300)
        settings_l.addWidget(self.voice_combo, r, 1, 1, 3)
        r += 1
        # ... (باقي إعدادات الواجهة كما هي)
        settings_l.addWidget(QLabel("⚡ السرعة:"), r, 0)
        speed_l = QHBoxLayout()
        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(-100, 100)
        self.rate_spin.setValue(0)
        self.rate_spin.setSuffix(" %")
        speed_l.addWidget(self.rate_spin)
        self.rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rate_slider.setRange(-100, 100)
        self.rate_slider.setValue(0)
        self.rate_slider.valueChanged.connect(self.rate_spin.setValue)
        self.rate_spin.valueChanged.connect(self.rate_slider.setValue)
        speed_l.addWidget(self.rate_slider, 1)
        settings_l.addLayout(speed_l, r, 1, 1, 3)
        r += 1

        settings_l.addWidget(QLabel("🎵 النبرة:"), r, 0)
        pitch_l = QHBoxLayout()
        self.pitch_spin = QSpinBox()
        self.pitch_spin.setRange(-50, 50)
        self.pitch_spin.setValue(0)
        self.pitch_spin.setSuffix(" Hz")
        pitch_l.addWidget(self.pitch_spin)
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(-50, 50)
        self.pitch_slider.setValue(0)
        self.pitch_slider.valueChanged.connect(self.pitch_spin.setValue)
        self.pitch_spin.valueChanged.connect(self.pitch_slider.setValue)
        pitch_l.addWidget(self.pitch_slider, 1)
        settings_l.addLayout(pitch_l, r, 1, 1, 3)
        r += 1

        settings_l.addWidget(QLabel("🔊 مستوى الصوت:"), r, 0)
        vol_l = QHBoxLayout()
        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(-100, 100)
        self.volume_spin.setValue(0)
        self.volume_spin.setSuffix(" %")
        vol_l.addWidget(self.volume_spin)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(-100, 100)
        self.volume_slider.setValue(0)
        self.volume_slider.valueChanged.connect(self.volume_spin.setValue)
        self.volume_spin.valueChanged.connect(self.volume_slider.setValue)
        vol_l.addWidget(self.volume_slider, 1)
        settings_l.addLayout(vol_l, r, 1, 1, 3)
        r += 1

        settings_l.addWidget(QLabel("⏸️ فاصل الصمت (SRT):"), r, 0)
        pause_l = QHBoxLayout()
        self.pause_spin = QSpinBox()
        self.pause_spin.setRange(0, 5000)
        self.pause_spin.setValue(500)
        self.pause_spin.setSuffix(" ms")
        self.pause_spin.setSingleStep(100)
        pause_l.addWidget(self.pause_spin)
        pause_l.addWidget(QLabel("(بين كل سطر من SRT)"))
        pause_l.addStretch()
        settings_l.addLayout(pause_l, r, 1, 1, 3)
        r += 1

        settings_l.addWidget(QLabel("💾 مجلد الحفظ:"), r, 0)
        out_l = QHBoxLayout()
        self.out_input = QLineEdit()
        self.out_input.setText(os.path.join(str(Path.home()), "Music", "tts_output"))
        out_l.addWidget(self.out_input, 1)
        out_btn = QPushButton("...")
        out_btn.setMaximumWidth(40)
        out_btn.clicked.connect(self._pick_out)
        out_l.addWidget(out_btn)
        settings_l.addLayout(out_l, r, 1, 1, 3)
        settings_l.setRowStretch(r, 1)
        tabs.addTab(settings_tab, "⚙️ Settings")

        # --- Tab 3: Player ---
        player_tab = QWidget()
        player_l = QVBoxLayout(player_tab)
        player_l.addWidget(QLabel("🎧 معاينة الصوت:"))
        player_l.addStretch()
        self.player_status = QLabel("لا يوجد ملف بعد")
        self.player_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_status.setStyleSheet("font-size: 16px; color: gray; padding: 20px;")
        player_l.addWidget(self.player_status)
        player_l.addStretch()
        ctrl_l = QHBoxLayout()
        ctrl_l.addStretch()
        self.play_btn = QPushButton("▶️ تشغيل")
        self.play_btn.setMinimumWidth(120)
        self.play_btn.clicked.connect(self._toggle_play)
        ctrl_l.addWidget(self.play_btn)
        self.stop_btn = QPushButton("⏹️ إيقاف")
        self.stop_btn.setMinimumWidth(120)
        self.stop_btn.clicked.connect(self._stop_play)
        ctrl_l.addWidget(self.stop_btn)
        self.open_btn = QPushButton("📂 فتح المجلد")
        self.open_btn.setMinimumWidth(120)
        self.open_btn.clicked.connect(self._open_output_folder)
        ctrl_l.addWidget(self.open_btn)
        ctrl_l.addStretch()
        player_l.addLayout(ctrl_l)
        player_l.addStretch()
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.playbackStateChanged.connect(self._on_playback_state)
        tabs.addTab(player_tab, "🎧 Player")

        # --- Tab 4: Log ---
        log_tab = QWidget()
        log_l = QVBoxLayout(log_tab)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setMaximumBlockCount(2000)
        log_l.addWidget(self.log_text)
        log_btns = QHBoxLayout()
        clear_log_btn = QPushButton("🧹 مسح السجل")
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_btns.addWidget(clear_log_btn)
        save_log_btn = QPushButton("💾 حفظ السجل")
        save_log_btn.clicked.connect(self._save_log)
        log_btns.addWidget(save_log_btn)
        log_btns.addStretch()
        log_l.addLayout(log_btns)
        tabs.addTab(log_tab, "📋 Log")

        # Progress Bar
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        main_layout.addWidget(self.bar)

        self.status = QLabel("جاهز")
        self.status.setStyleSheet("padding: 5px;")
        main_layout.addWidget(self.status)

        # Buttons
        btn_l = QHBoxLayout()
        self.generate_btn = QPushButton("🎙️ توليد الصوت")
        self.generate_btn.setStyleSheet(
            "QPushButton { font-size: 16px; font-weight: bold; "
            "padding: 14px; background-color: #2E7D32; color: white; "
            "border-radius: 6px; }")
        self.generate_btn.clicked.connect(self._on_generate)
        btn_l.addWidget(self.generate_btn, 3)
        self.cancel_btn = QPushButton("⛔ إلغاء")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet(
            "QPushButton { padding: 14px; background-color: #B71C1C; "
            "color: white; border-radius: 6px; }")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_l.addWidget(self.cancel_btn, 1)
        main_layout.addLayout(btn_l)

    # ------------------ الوظائف ------------------
    def _update_char_count(self):
        text = self.text_input.toPlainText()
        words = len(text.split())
        self.char_count.setText(f"{len(text)} حرف • {words} كلمة")

    def _load_txt(self):
        p, _ = QFileDialog.getOpenFileName(self, "اختر ملف نصي", "", "Text Files (*.txt);;All Files (*)")
        if p:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    self.text_input.setPlainText(f.read())
                self._log(f"📄 Loaded: {Path(p).name}", "#4CAF50")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل تحميل الملف:\n{e}")

    def _load_srt(self):
        p, _ = QFileDialog.getOpenFileName(self, "اختر ملف SRT", "", "SRT Files (*.srt);;All Files (*)")
        if p:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    self.text_input.setPlainText(f.read())
                self._log(f"🎬 Loaded SRT: {Path(p).name}", "#4CAF50")
                self.status.setText("✅ ملف SRT محمّل — سيتم تحويله كاملاً")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل تحميل الملف:\n{e}")

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "اختر مجلد الحفظ")
        if d:
            self.out_input.setText(d)

    def _log(self, msg: str, color: str = ""):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if color:
            fmt = cursor.charFormat()
            fmt.setForeground(QColor(color))
            cursor.setCharFormat(fmt)
        cursor.insertText(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()
        fmt = cursor.charFormat()
        fmt.setForeground(QColor("#FFFFFF"))
        cursor.setCharFormat(fmt)

    def _save_log(self):
        p, _ = QFileDialog.getSaveFileName(self, "حفظ السجل", f"tts_log_{datetime.now():%Y%m%d_%H%M%S}.txt", "Text Files (*.txt)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.log_text.toPlainText())
            QMessageBox.information(self, "تم", f"تم حفظ السجل:\n{p}")

    def _on_generate(self):
        content = self.text_input.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "تنبيه", "أدخل نصاً أو حمّل ملفاً أولاً")
            return

        preview = content[:500]
        is_srt = bool(re.search(r"\d+\s*\n\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->", preview))

        if is_srt:
            mode = "srt"
            temp_srt = os.path.join(tempfile.gettempdir(), f"inline_srt_{datetime.now():%Y%m%d_%H%M%S}.srt")
            try:
                with open(temp_srt, "w", encoding="utf-8") as f:
                    f.write(content)
                source = temp_srt
                self._log(f"📝 Detected SRT content ({content.count('-->')} lines)", "#2196F3")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل حفظ SRT مؤقت:\n{e}")
                return
        else:
            mode = "text"
            source = content

        out_dir = self.out_input.text().strip()
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(out_dir, f"tts_{stamp}.mp3")

        voice_label = self.voice_combo.currentText()
        voice_id = VOICES.get(voice_label, "en-US-AriaNeural")

        rate_val = self.rate_spin.value()
        rate_str = f"{'+' if rate_val >= 0 else ''}{rate_val}%"
        pitch_val = self.pitch_spin.value()
        pitch_str = f"{'+' if pitch_val >= 0 else ''}{pitch_val}Hz"
        volume_val = self.volume_spin.value()
        volume_str = f"{'+' if volume_val >= 0 else ''}{volume_val}%"
        pause_ms = self.pause_spin.value()

        self._save_settings()
        self.generate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.bar.setValue(0)
        self.log_text.clear()

        self._log(f"🚀 Starting TTS ({mode})...", "#4CAF50")
        self._log(f"   Voice: {voice_label}", "#2196F3")
        self._log(f"   Rate: {rate_str} | Pitch: {pitch_str} | Volume: {volume_str}")
        self._log(f"   Output: {output_file}")

        self.worker = TTSWorker(
            mode=mode, source=source, output=output_file, voice=voice_id,
            rate=rate_str, pitch=pitch_str, volume=volume_str, pause_ms=pause_ms,
        )
        self.worker.msg.connect(self._on_worker_msg)
        self.worker.pct.connect(self.bar.setValue)
        self.worker.finished.connect(self._on_ok)
        self.worker.error.connect(self._on_err)
        self.worker.start()

    def _on_worker_msg(self, msg: str):
        self.status.setText(msg)
        color = ""
        if msg.startswith("✅"): color = "#4CAF50"
        elif msg.startswith("❌") or msg.startswith("⛔"): color = "#F44336"
        elif msg.startswith("⚠️"): color = "#FF9800"
        elif msg.startswith("🚀"): color = "#2196F3"
        self._log(msg, color)

    def _on_cancel(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)

    def _on_ok(self, path: str):
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.bar.setValue(100)
        self.status.setText(f"✅ تم: {path}")
        self._last_output = path
        self._log(f"✅ Output: {path}", "#4CAF50")
        self.media_player.setSource(QUrl.fromLocalFile(path))
        self.player_status.setText(f"🎵 {Path(path).name}")
        QMessageBox.information(self, "نجاح", f"✅ تم إنشاء الملف الصوتي!\n\n{path}")

    def _on_err(self, m: str):
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status.setText("❌ فشل")
        self._log(f"❌ {m}", "#F44336")
        QMessageBox.critical(self, "خطأ", m)

    def _toggle_play(self):
        if not self._last_output or not os.path.exists(self._last_output):
            QMessageBox.warning(self, "تنبيه", "لا يوجد ملف صوتي بعد")
            return
        state = self.media_player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            if self.media_player.source() != QUrl.fromLocalFile(self._last_output):
                self.media_player.setSource(QUrl.fromLocalFile(self._last_output))
            self.media_player.play()

    def _stop_play(self):
        self.media_player.stop()

    def _on_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸️ إيقاف مؤقت")
        else:
            self.play_btn.setText("▶️ تشغيل")

    def _open_output_folder(self):
        folder = self.out_input.text().strip()
        if os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            QMessageBox.warning(self, "تنبيه", "المجلد غير موجود")

    def _save_settings(self):
        s = self.settings
        s.setValue("voice", self.voice_combo.currentText())
        s.setValue("rate", self.rate_spin.value())
        s.setValue("pitch", self.pitch_spin.value())
        s.setValue("volume", self.volume_spin.value())
        s.setValue("pause", self.pause_spin.value())
        s.setValue("out_dir", self.out_input.text())

    def _load_settings(self):
        s = self.settings
        self.voice_combo.setCurrentText(s.value("voice", DEFAULT_VOICE, type=str))
        self.rate_spin.setValue(s.value("rate", 0, type=int))
        self.pitch_spin.setValue(s.value("pitch", 0, type=int))
        self.volume_spin.setValue(s.value("volume", 0, type=int))
        self.pause_spin.setValue(s.value("pause", 500, type=int))
        self.out_input.setText(s.value("out_dir", os.path.join(str(Path.home()), "Music", "tts_output"), type=str))


# ============================================================
# نقطة الدخول
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())