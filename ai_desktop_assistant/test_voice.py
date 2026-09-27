"""
Sesli sohbet ozelligi icin testler: mikrofon dinleme/metne cevirme
(SpeechToTextWorker), cevabi sesle okuma (TextToSpeechWorker) ve
ChatBubble'daki mikrofon dugmesinin bu worker'lari dogru sekilde tetikleyip
sonuclarini isleyip islemedigi.

test_gemini_worker.py ile ayni yaklasim: gercek bir QApplication (QThread
altyapisi icin) kullanilir, worker'lar .run() ile senkron cagrilir
(start()/thread olmadan), speech_recognition/pyttsx3 tamamen mock'lanir -
gercek bir mikrofon/hoparlor gerekmez, CI'da (ses aygiti olmayan bir
runner'da da) calisir.

Calistirmak icin:
    pip install -r requirements.txt -r requirements-dev.txt
    pytest test_voice.py
"""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

from main import ChatBubble, SpeechToTextWorker, TextToSpeechWorker


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeSrModule:
    """speech_recognition modulunun testler icin sahtesi - gercek bir
    mikrofon/ag baglantisi olmadan Recognizer/Microphone/hata siniflarini
    taklit eder."""

    class WaitTimeoutError(Exception):
        pass

    class UnknownValueError(Exception):
        pass

    class RequestError(Exception):
        pass

    def __init__(self, audio="fake-audio", recognized_text="merhaba", raise_on=None):
        self._audio = audio
        self._recognized_text = recognized_text
        self._raise_on = raise_on  # ("listen"|"recognize", ExceptionInstance)

        recognizer = MagicMock()
        recognizer.adjust_for_ambient_noise = MagicMock()

        def listen(source, timeout=None, phrase_time_limit=None):
            if self._raise_on and self._raise_on[0] == "listen":
                raise self._raise_on[1]
            return self._audio

        def recognize_google(audio_data, language="en-US"):
            if self._raise_on and self._raise_on[0] == "recognize":
                raise self._raise_on[1]
            return self._recognized_text

        recognizer.listen.side_effect = listen
        recognizer.recognize_google.side_effect = recognize_google
        self.Recognizer = MagicMock(return_value=recognizer)
        self.recognizer_instance = recognizer

        mic_cm = MagicMock()
        mic_cm.__enter__.return_value = MagicMock()
        mic_cm.__exit__.return_value = False
        self.Microphone = MagicMock(return_value=mic_cm)


def _run_stt_worker(fake_sr_module):
    worker = SpeechToTextWorker()
    recognized = []
    failed = []
    worker.recognized.connect(recognized.append)
    worker.failed.connect(failed.append)
    with patch.dict("sys.modules", {"speech_recognition": fake_sr_module}):
        worker.run()
    return recognized, failed


class TestSpeechToTextWorker:
    def test_basarili_taninma_recognized_sinyalini_yayinlar(self):
        fake_sr = _FakeSrModule(recognized_text="ekranda ne var")
        recognized, failed = _run_stt_worker(fake_sr)
        assert recognized == ["ekranda ne var"]
        assert failed == []
        fake_sr.recognizer_instance.recognize_google.assert_called_once()
        _, kwargs = fake_sr.recognizer_instance.recognize_google.call_args
        assert kwargs.get("language") == "tr-TR"

    def test_sessizlikte_zaman_asimi_dostane_hata_verir(self):
        fake_sr = _FakeSrModule(raise_on=("listen", _FakeSrModule.WaitTimeoutError()))
        recognized, failed = _run_stt_worker(fake_sr)
        assert recognized == []
        assert len(failed) == 1
        assert "duyulmadi" in failed[0].lower()

    def test_anlasilmayan_konusmada_dostane_hata_verir(self):
        fake_sr = _FakeSrModule(raise_on=("recognize", _FakeSrModule.UnknownValueError()))
        recognized, failed = _run_stt_worker(fake_sr)
        assert recognized == []
        assert "anlayamadim" in failed[0].lower()

    def test_servis_hatasinda_dostane_hata_verir(self):
        fake_sr = _FakeSrModule(
            raise_on=("recognize", _FakeSrModule.RequestError("baglanti yok"))
        )
        recognized, failed = _run_stt_worker(fake_sr)
        assert recognized == []
        assert "ses tanima servisine" in failed[0].lower()

    def test_bos_metin_donerse_hata_olarak_ele_alinir(self):
        fake_sr = _FakeSrModule(recognized_text="   ")
        recognized, failed = _run_stt_worker(fake_sr)
        assert recognized == []
        assert len(failed) == 1

    def test_kutuphane_kurulu_degilse_dostane_hata_verir(self):
        worker = SpeechToTextWorker()
        failed = []
        worker.failed.connect(failed.append)
        with patch.dict("sys.modules", {"speech_recognition": None}):
            worker.run()
        assert len(failed) == 1
        assert "kurulu degil" in failed[0].lower()


class _FakeVoice:
    def __init__(self, id_, name):
        self.id = id_
        self.name = name


class _FakePyttsx3Module:
    def __init__(self, voices=None, init_raises=None):
        self._init_raises = init_raises
        engine = MagicMock()
        engine.getProperty.return_value = voices or []
        self.engine = engine

        def init():
            if self._init_raises:
                raise self._init_raises
            return engine

        self.init = MagicMock(side_effect=init)


def _run_tts_worker(fake_pyttsx3_module, text="merhaba dunya"):
    worker = TextToSpeechWorker(text)
    failed = []
    worker.failed.connect(failed.append)
    with patch.dict("sys.modules", {"pyttsx3": fake_pyttsx3_module}):
        worker.run()
    return failed


class TestTextToSpeechWorker:
    def test_basarili_okuma_say_ve_runandwait_cagirir(self):
        fake = _FakePyttsx3Module()
        failed = _run_tts_worker(fake, text="merhaba dunya")
        assert failed == []
        fake.engine.say.assert_called_once_with("merhaba dunya")
        fake.engine.runAndWait.assert_called_once()

    def test_turkce_ses_varsa_secilir(self):
        voices = [
            _FakeVoice("com.apple.speech.synthesis.voice.Alex", "Alex"),
            _FakeVoice("com.microsoft.tr-TR.Turkish", "Microsoft Turkish"),
        ]
        fake = _FakePyttsx3Module(voices=voices)
        _run_tts_worker(fake)
        fake.engine.setProperty.assert_called_once_with(
            "voice", "com.microsoft.tr-TR.Turkish"
        )

    def test_turkce_ses_yoksa_setproperty_cagrilmaz(self):
        voices = [_FakeVoice("com.apple.speech.synthesis.voice.Alex", "Alex")]
        fake = _FakePyttsx3Module(voices=voices)
        _run_tts_worker(fake)
        fake.engine.setProperty.assert_not_called()

    def test_motor_baslatilamazsa_dostane_hata_verir(self):
        fake = _FakePyttsx3Module(init_raises=RuntimeError("eSpeak yok"))
        failed = _run_tts_worker(fake)
        assert len(failed) == 1
        assert "sesli okuma hatasi" in failed[0].lower()

    def test_kutuphane_kurulu_degilse_dostane_hata_verir(self):
        worker = TextToSpeechWorker("merhaba")
        failed = []
        worker.failed.connect(failed.append)
        with patch.dict("sys.modules", {"pyttsx3": None}):
            worker.run()
        assert len(failed) == 1
        assert "kurulu degil" in failed[0].lower()


class TestChatBubbleMicButton:
    def test_mikrofon_basarili_tanimada_sesle_soruldu_isaretler_ve_ask_requested_yayinlar(self):
        bubble = ChatBubble("Fuff")
        asked = []
        bubble.ask_requested.connect(asked.append)
        assert bubble.last_ask_was_voice is False

        bubble._on_voice_recognized("ekranda ne var")

        assert bubble.last_ask_was_voice is True
        assert asked == ["ekranda ne var"]
        assert bubble.input_field.text() == "ekranda ne var"
        assert bubble.mic_button.isEnabled() is True

    def test_metinle_soru_sormak_sesle_soruldu_bayragini_temizler(self):
        bubble = ChatBubble("Fuff")
        bubble._on_voice_recognized("onceki sesli soru")
        assert bubble.last_ask_was_voice is True

        bubble.input_field.setText("yeni yazili soru")
        bubble._on_ask()

        assert bubble.last_ask_was_voice is False

    def test_mikrofon_hatasinda_hata_gosterilir_ask_requested_yayinlanmaz(self):
        bubble = ChatBubble("Fuff")
        asked = []
        bubble.ask_requested.connect(asked.append)

        bubble._on_voice_failed("Bir sey duyulmadi, tekrar dener misin?")

        assert asked == []
        assert bubble.last_ask_was_voice is False
        assert "duyulmadi" in bubble.response_area.toPlainText().lower()
        assert bubble.mic_button.isEnabled() is True

    def test_mikrofon_calismiyorken_tiklaninca_yeni_worker_baslatilir(self):
        bubble = ChatBubble("Fuff")
        mock_worker = MagicMock()
        with patch("main.SpeechToTextWorker", return_value=mock_worker) as MockWorker:
            bubble._on_mic_clicked()

        MockWorker.assert_called_once_with(bubble)
        mock_worker.recognized.connect.assert_called_once_with(bubble._on_voice_recognized)
        mock_worker.failed.connect.assert_called_once_with(bubble._on_voice_failed)
        mock_worker.start.assert_called_once()
        assert bubble.mic_button.isEnabled() is False

    def test_mikrofon_calisirken_tekrar_tiklamak_yeni_worker_baslatmaz(self):
        bubble = ChatBubble("Fuff")
        running_worker = MagicMock()
        running_worker.isRunning.return_value = True
        bubble._stt_worker = running_worker

        with patch("main.SpeechToTextWorker") as MockWorker:
            bubble._on_mic_clicked()

        MockWorker.assert_not_called()
