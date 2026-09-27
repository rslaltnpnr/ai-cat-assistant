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

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

import main
from main import MAX_TOOL_CALL_ROUNDS, GeminiWorker


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeFunctionCall:
    """google.genai.types.FunctionCall'in testler icin sahtesi -
    GeminiWorker sadece .name ve .args okur."""

    def __init__(self, name, args=None):
        self.name = name
        self.args = args or {}


class _FakeChunk:
    """google.genai.types.GenerateContentResponse'un (bir akis parcasi)
    testler icin sahtesi - gercek SDK'daki .text/.function_calls/.parts
    property'lerini taklit eder (bkz. GeminiWorker.run()'daki kullanimlari)."""

    def __init__(self, text=None, function_calls=None):
        self.text = text
        self.function_calls = function_calls or None
        if function_calls:
            self.parts = list(function_calls)
        elif text:
            self.parts = [SimpleNamespace(text=text)]
        else:
            self.parts = []


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
    """[stream_results]: generate_content_stream'in ardisik cagrilarinda ne
    olacagini belirleyen bir liste - her eleman bir chunk listesi (basarili
    bir akis; ogeler metin string'i ya da bir _FakeFunctionCall olabilir)
    ya da bir Exception (o cagri patlar). configs listesi her cagrida
    gonderilen GenerateContentConfig'i biriktirir (tools icerigini kontrol
    etmek icin - bkz. tool-kombinasyonu-hatasi testi)."""
    client = MagicMock()
    calls = []
    configs = []

    def side_effect(*, model, contents, config):
        calls.append(model)
        configs.append(config)
        result = stream_results.pop(0)
        if isinstance(result, Exception):
            raise result
        chunks = []
        for item in result:
            if isinstance(item, _FakeFunctionCall):
                chunks.append(_FakeChunk(function_calls=[item]))
            else:
                chunks.append(_FakeChunk(text=item))
        return iter(chunks)

    client.models.generate_content_stream.side_effect = side_effect
    return client, calls, configs


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
    tool_calls = []
    worker.chunk_received.connect(chunks.append)
    worker.tool_used.connect(lambda name, summary: tool_calls.append((name, summary)))
    worker.finished_ok.connect(lambda text: results.__setitem__("ok", text))
    worker.finished_error.connect(lambda text: results.__setitem__("error", text))

    mss_patch, png_patch = _fake_mss_capture()
    with mss_patch, png_patch, patch("google.genai.Client", return_value=client):
        worker.run()
    return chunks, results, tool_calls


class TestGeminiWorkerStreaming:
    def test_basit_akis_parca_parca_yayinlanir_ve_birikir(self):
        client, calls, _configs = _make_client([["Merhaba", ", ", "dunya!"]])
        chunks, results, _tool_calls = _run_worker(client)
        assert chunks == ["Merhaba", ", ", "dunya!"]
        assert results == {"ok": "Merhaba, dunya!"}
        assert calls == ["gemini-flash-latest"]

    def test_bos_akis_bos_yanit_dondu_mesaji_verir(self):
        client, _, _configs = _make_client([[]])
        chunks, results, _tool_calls = _run_worker(client)
        assert chunks == []
        assert results == {"ok": "(Bos yanit dondu)"}

    def test_ilk_parcada_asiri_yuklenme_hatasi_ayni_modelde_tekrar_dener(self):
        client, calls, _configs = _make_client(
            [
                Exception("503 UNAVAILABLE overloaded"),
                ["ikinci denemede basarili"],
            ]
        )
        with patch("time.sleep"):
            chunks, results, _tool_calls = _run_worker(client)
        assert chunks == ["ikinci denemede basarili"]
        assert results == {"ok": "ikinci denemede basarili"}
        assert calls == ["gemini-flash-latest", "gemini-flash-latest"]

    def test_ana_model_tukenince_yedek_modele_gecer(self):
        # OVERLOAD_RETRY_DELAYS = (2, 4) -> ana modelde 3 deneme hakki var,
        # ucu de 503 verirse yedek modele (FALLBACK_MODEL) geciliyor.
        client, calls, _configs = _make_client(
            [
                Exception("503 overloaded"),
                Exception("503 overloaded"),
                Exception("503 overloaded"),
                ["yedek modelden yanit"],
            ]
        )
        with patch("time.sleep"):
            chunks, results, _tool_calls = _run_worker(client)
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

        chunks, results, _tool_calls = _run_worker(client)
        # Ilk iki parca zaten yayinlanmis olmali - akis ortasindaki hatada
        # bastan baska bir modelle denenmez (tekrarlanan/yarim bir metin
        # gostermemek icin), dogrudan hata bildirilir.
        assert chunks == ["kismi ", "cevap "]
        assert "error" in results
        assert "yarida kesildi" in results["error"]
        assert calls == ["gemini-flash-latest"]  # fallback denenmedi

    def test_modelin_kaldirilmasi_hatasinda_da_yedek_modele_gecer(self):
        client, calls, _configs = _make_client(
            [
                Exception("404 NOT_FOUND: model no longer available"),
                ["yedek modelden yanit"],
            ]
        )
        chunks, results, _tool_calls = _run_worker(client)
        assert chunks == ["yedek modelden yanit"]
        assert calls == ["gemini-flash-latest", "gemini-3.6-flash"]

    def test_asiri_yuklenme_disi_hata_hemen_fallback_denemeden_hata_verir(self):
        client, calls, _configs = _make_client([Exception("400 Bad Request: gecersiz istek")])
        chunks, results, _tool_calls = _run_worker(client)
        assert chunks == []
        assert "error" in results
        assert calls == ["gemini-flash-latest"]


class TestGeminiWorkerAgentTools:
    """GeminiWorker'in Gemini function-calling ile cagirabildigi yerel
    araclari (write_file, open_application) ve Google Arama grounding'ini
    kapsayan testler - bkz. main.py'deki AGENT_TOOL_DISPATCH/_build_agent_tools."""

    def test_write_file_araci_calisir_dosyayi_yazar_ve_akis_devam_eder(self, tmp_path):
        target = tmp_path / "hello.py"
        client, calls, _configs = _make_client(
            [
                [_FakeFunctionCall("write_file", {"path": str(target), "content": "print(1)"})],
                ["Dosyayi yazdim."],
            ]
        )
        chunks, results, tool_calls = _run_worker(client)

        assert target.read_text(encoding="utf-8") == "print(1)"
        assert chunks == ["Dosyayi yazdim."]
        assert results == {"ok": "Dosyayi yazdim."}
        assert len(tool_calls) == 1
        assert tool_calls[0][0] == "write_file"
        assert str(target) in tool_calls[0][1]
        # Arac calistirildiktan sonra dogal dil yaniti icin ikinci bir
        # istek daha atilmis olmali (ayni modelle).
        assert calls == ["gemini-flash-latest", "gemini-flash-latest"]

    def test_open_application_araci_calisir_ve_sonuc_modele_bildirilir(self):
        client, _calls, _configs = _make_client(
            [
                [_FakeFunctionCall("open_application", {"name": "hesap makinesi"})],
                ["Actim."],
            ]
        )
        with patch(
            "main._tool_open_application",
            return_value={"ok": True, "resolved": "calc.exe"},
        ) as mocked:
            chunks, results, tool_calls = _run_worker(client)

        mocked.assert_called_once_with("hesap makinesi")
        assert chunks == ["Actim."]
        assert results == {"ok": "Actim."}
        assert tool_calls == [("open_application", '"hesap makinesi" acildi.')]

    def test_bilinmeyen_arac_adi_hata_olarak_bildirilir_akis_devam_eder(self):
        client, _calls, _configs = _make_client(
            [
                [_FakeFunctionCall("sil_hepsini", {})],
                ["Bunu yapamam."],
            ]
        )
        chunks, results, tool_calls = _run_worker(client)

        assert results == {"ok": "Bunu yapamam."}
        assert tool_calls[0][0] == "sil_hepsini"
        assert "bilinmeyen arac" in tool_calls[0][1].lower()

    def test_cok_fazla_ardisik_arac_cagrisi_sinirlanir_ve_bosa_istek_atilmaz(self):
        # MAX_TOOL_CALL_ROUNDS kadar script - her biri yine bir arac cagrisi
        # donduruyor, hic biri metinle bitmiyor.
        script = [
            [_FakeFunctionCall("write_file", {"path": f"f{i}.txt", "content": "x"})]
            for i in range(MAX_TOOL_CALL_ROUNDS)
        ]
        client, calls, _configs = _make_client(script)
        with patch(
            "main._tool_write_file",
            return_value={"ok": True, "path": "f.txt", "bytes_written": 1},
        ):
            chunks, results, tool_calls = _run_worker(client)

        assert len(tool_calls) == MAX_TOOL_CALL_ROUNDS
        assert "ok" in results
        assert "cok fazla" in results["ok"].lower()
        # Son turdan sonra bosa bir istek daha atilmamis olmali.
        assert len(calls) == MAX_TOOL_CALL_ROUNDS

    def test_arama_ile_fonksiyon_araclari_cakisirsa_aramasiz_tekrar_dener(self):
        client, calls, configs = _make_client(
            [
                Exception(
                    "400 INVALID_ARGUMENT: google_search cannot be combined "
                    "with function calling tools."
                ),
                ["ikinci denemede basarili (aramasiz)"],
            ]
        )
        chunks, results, _tool_calls = _run_worker(client)

        assert results == {"ok": "ikinci denemede basarili (aramasiz)"}
        assert len(configs) == 2
        assert any(t.google_search is not None for t in configs[0].tools)
        assert all(t.google_search is None for t in configs[1].tools)
        assert any(t.function_declarations for t in configs[1].tools)
        assert calls == ["gemini-flash-latest", "gemini-flash-latest"]


class TestAgentToolFunctions:
    """write_file/open_application arac fonksiyonlarinin ve yardimci
    fonksiyonlarin (_agent_tool_summary, _is_tool_combination_error) dogrudan
    (Gemini/worker olmadan) testleri."""

    def test_write_file_klasor_yoksa_olusturur_ve_yazar(self, tmp_path):
        target = tmp_path / "alt_klasor" / "dosya.txt"
        result = main._tool_write_file(str(target), "merhaba")
        assert result["ok"] is True
        assert target.read_text(encoding="utf-8") == "merhaba"
        assert result["bytes_written"] == len("merhaba".encode("utf-8"))

    def test_write_file_gecersiz_yolda_hata_dondurur(self):
        # Bos bir yol gecersizdir (os.makedirs/open patlar).
        result = main._tool_write_file("", "x")
        assert result["ok"] is False
        assert "error" in result

    def test_open_application_path_te_bulunursa_dogrudan_calistirir(self):
        with patch("shutil.which", return_value="/usr/bin/calc"), patch(
            "subprocess.Popen"
        ) as mocked_popen:
            result = main._tool_open_application("calc")
        mocked_popen.assert_called_once_with(["/usr/bin/calc"])
        assert result == {"ok": True, "resolved": "/usr/bin/calc"}

    def test_open_application_popen_hatasinda_hata_dondurur(self):
        with patch("shutil.which", return_value=None), patch(
            "sys.platform", "linux"
        ), patch("subprocess.Popen", side_effect=OSError("bulunamadi")):
            result = main._tool_open_application("olmayan-uygulama")
        assert result["ok"] is False
        assert "error" in result

    def test_open_application_pathte_yoksa_windowsta_startfile_ile_acar(self):
        # PATH'te bulunamayan bir uygulama adi Windows'ta os.startfile'a
        # birakilir - shell=True/subprocess YOK, dogrudan ShellExecute
        # (bkz. _tool_open_application docstring'i: kabuk enjeksiyonu riski
        # bu yuzden yok).
        with patch("shutil.which", return_value=None), patch(
            "sys.platform", "win32"
        ), patch("os.startfile", create=True) as mocked_startfile:
            result = main._tool_open_application("chrome")
        mocked_startfile.assert_called_once_with("chrome")
        assert result == {"ok": True, "resolved": "chrome"}

    def test_agent_tool_summary_bilinmeyen_arac_basarisiz_ozet_verir(self):
        summary = main._agent_tool_summary(
            "gizemli_arac", {}, {"ok": False, "error": "cok kotu"}
        )
        assert "basarisiz" in summary.lower()
        assert "cok kotu" in summary

    def test_is_tool_combination_error_ilgisiz_hatada_false_doner(self):
        assert main._is_tool_combination_error(Exception("network timeout")) is False
