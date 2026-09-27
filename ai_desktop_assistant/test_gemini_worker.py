"""
GeminiWorker'in akis (streaming) mantigi icin testler: parca parca gelen
yanitin biriktirilip yayinlanmasi, ilk-parca-eager-cekme ile retry/fallback,
ve akis ortasinda hata olursa (retry yerine) dogrudan hataya dusme.

test_main.py'nin aksine burada gercek bir QApplication (QThread'in QObject
altyapisi icin) ve mss/google-genai mock'lari kullanilir - CI'da
QT_QPA_PLATFORM=offscreen zaten ayarli oldugu icin ekransiz calisir.
GeminiWorker.run() dogrudan (start()/thread olmadan, ayni thread'de
senkron) cagrilir, boylece sinyaller sirali ve deterministik gelir.

Calistirmak icin:
    pip install -r requirements.txt -r requirements-dev.txt
    pytest test_gemini_worker.py
"""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

from main import GeminiWorker


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeChunk:
    def __init__(self, text):
        self.text = text


def _fake_mss_capture():
    """mss.mss()/mss.tools.to_png cagrilarini, gercek bir ekran olmadan
    sahte bir PNG donduren bir context'e sahteler."""
    fake_sct = MagicMock()
    fake_sct.monitors = [{"left": 0, "top": 0, "width": 1, "height": 1}]
    fake_shot = MagicMock()
    fake_shot.rgb = b"\x00" * 3
    fake_shot.size = (1, 1)
    fake_sct.grab.return_value = fake_shot
    mss_cm = MagicMock()
    mss_cm.__enter__.return_value = fake_sct
    mss_cm.__exit__.return_value = False
    return patch("mss.mss", return_value=mss_cm), patch(
        "mss.tools.to_png", return_value=b"fake-png-bytes"
    )


def _make_client(stream_results):
    """[stream_results]: generate_content_stream'in ardisik cagrilarinda
    ne olacagini belirleyen bir liste - her eleman bir chunk-metni listesi
    (basarili bir akis) ya da bir Exception (o cagri patlar)."""
    client = MagicMock()
    calls = []

    def side_effect(*, model, contents, config):
        calls.append(model)
        result = stream_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return iter([_FakeChunk(t) for t in result])

    client.models.generate_content_stream.side_effect = side_effect
    return client, calls


def _run_worker(client, **kwargs):
    worker = GeminiWorker(
        api_key="test-key",
        model_name=kwargs.pop("model_name", "gemini-flash-latest"),
        question="soru",
        character_name="Fuff",
        **kwargs,
    )
    chunks = []
    results = {}
    worker.chunk_received.connect(chunks.append)
    worker.finished_ok.connect(lambda text: results.__setitem__("ok", text))
    worker.finished_error.connect(lambda text: results.__setitem__("error", text))

    mss_patch, png_patch = _fake_mss_capture()
    with mss_patch, png_patch, patch("google.genai.Client", return_value=client):
        worker.run()
    return chunks, results


class TestGeminiWorkerStreaming:
    def test_basit_akis_parca_parca_yayinlanir_ve_birikir(self):
        client, calls = _make_client([["Merhaba", ", ", "dunya!"]])
        chunks, results = _run_worker(client)
        assert chunks == ["Merhaba", ", ", "dunya!"]
        assert results == {"ok": "Merhaba, dunya!"}
        assert calls == ["gemini-flash-latest"]

    def test_bos_akis_bos_yanit_dondu_mesaji_verir(self):
        client, _ = _make_client([[]])
        chunks, results = _run_worker(client)
        assert chunks == []
        assert results == {"ok": "(Bos yanit dondu)"}

    def test_ilk_parcada_asiri_yuklenme_hatasi_ayni_modelde_tekrar_dener(self):
        client, calls = _make_client(
            [
                Exception("503 UNAVAILABLE overloaded"),
                ["ikinci denemede basarili"],
            ]
        )
        with patch("time.sleep"):
            chunks, results = _run_worker(client)
        assert chunks == ["ikinci denemede basarili"]
        assert results == {"ok": "ikinci denemede basarili"}
        assert calls == ["gemini-flash-latest", "gemini-flash-latest"]

    def test_ana_model_tukenince_yedek_modele_gecer(self):
        # OVERLOAD_RETRY_DELAYS = (2, 4) -> ana modelde 3 deneme hakki var,
        # ucu de 503 verirse yedek modele (FALLBACK_MODEL) geciliyor.
        client, calls = _make_client(
            [
                Exception("503 overloaded"),
                Exception("503 overloaded"),
                Exception("503 overloaded"),
                ["yedek modelden yanit"],
            ]
        )
        with patch("time.sleep"):
            chunks, results = _run_worker(client)
        assert chunks == ["yedek modelden yanit"]
        assert results == {"ok": "yedek modelden yanit"}
        assert calls[-1] == "gemini-3.6-flash"  # FALLBACK_MODEL

    def test_akis_ortasinda_hata_retry_denemez_zaten_gosterileni_hata_yapar(self):
        def broken_stream():
            yield _FakeChunk("kismi ")
            yield _FakeChunk("cevap ")
            raise RuntimeError("baglanti koptu")

        client = MagicMock()
        calls = []

        def side_effect(*, model, contents, config):
            calls.append(model)
            return broken_stream()

        client.models.generate_content_stream.side_effect = side_effect

        chunks, results = _run_worker(client)
        # Ilk iki parca zaten yayinlanmis olmali - akis ortasindaki hatada
        # bastan baska bir modelle denenmez (tekrarlanan/yarim bir metin
        # gostermemek icin), dogrudan hata bildirilir.
        assert chunks == ["kismi ", "cevap "]
        assert "error" in results
        assert "yarida kesildi" in results["error"]
        assert calls == ["gemini-flash-latest"]  # fallback denenmedi

    def test_modelin_kaldirilmasi_hatasinda_da_yedek_modele_gecer(self):
        client, calls = _make_client(
            [
                Exception("404 NOT_FOUND: model no longer available"),
                ["yedek modelden yanit"],
            ]
        )
        chunks, results = _run_worker(client)
        assert chunks == ["yedek modelden yanit"]
        assert calls == ["gemini-flash-latest", "gemini-3.6-flash"]

    def test_asiri_yuklenme_disi_hata_hemen_fallback_denemeden_hata_verir(self):
        client, calls = _make_client([Exception("400 Bad Request: gecersiz istek")])
        chunks, results = _run_worker(client)
        assert chunks == []
        assert "error" in results
        assert calls == ["gemini-flash-latest"]
