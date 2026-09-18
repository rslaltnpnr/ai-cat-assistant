"""
main.py icindeki saf mantik fonksiyonlari icin testler (surum
karsilastirma, release secimi, SSRF korumasi). GUI/PyQt widget'lari
olusturmaz - main() cagirilmadigi surece QApplication hic acilmaz, bu
yuzden bu testler ekransiz (headless) CI'da da calisir.

Calistirmak icin:
    pip install -r requirements.txt -r requirements-dev.txt
    pytest
"""

import tempfile
from datetime import datetime, timedelta

import pytest

from main import (
    ConfigManager,
    DEFAULT_QUICK_QUESTIONS,
    HISTORY_ENTRY_MAX_FIELD_LENGTH,
    PERSONALITY_PRESETS,
    PROFILE_EXPORT_KEYS,
    ScreenshotHistoryLog,
    SecureNotepadService,
    WrongPasswordError,
    _parse_version,
    append_access_log,
    apply_settings_profile,
    build_pairing_uri,
    build_persona_prompt,
    build_settings_profile,
    compute_usage_stats,
    describe_automation_rule,
    find_release_with_asset,
    format_access_log_line,
    format_automation_rules,
    format_history_entries,
    format_notifications,
    format_recent_connections,
    format_relative_time,
    format_screenshot_history,
    format_usage_stats,
    is_newer_version,
    is_url_safe_to_open,
    live_coords_to_pixels,
    merge_history_entries,
    normalize_live_key_name,
    normalize_live_mouse_button,
    parse_hh_mm,
    parse_send_file_arg,
    prune_old_backups,
    record_connection,
    resolve_auto_theme_mode,
    sanitize_teleport_filename,
    select_context_turns,
    send_with_cat_command_line,
    should_fire_rule,
    should_run_auto_backup,
    tail_access_log,
    unique_teleport_destination,
    validate_custom_command,
)


class TestParseVersion:
    def test_basit_surum(self):
        assert _parse_version("v1.2.3") == (1, 2, 3)

    def test_v_onekisiz(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_eksik_parca_sifir_sayilir(self):
        assert _parse_version("v1.2") == (1, 2)

    def test_sayisal_olmayan_parca_sifir_sayilir(self):
        assert _parse_version("vabc.2.3") == (0, 2, 3)


class TestIsNewerVersion:
    def test_daha_yuksek_patch_daha_yeni(self):
        assert is_newer_version("v1.1.1", "1.1.0") is True

    def test_daha_yuksek_minor_daha_yeni(self):
        assert is_newer_version("v1.2.0", "1.1.9") is True

    def test_ayni_surum_daha_yeni_degil(self):
        assert is_newer_version("v1.1.1", "1.1.1") is False

    def test_daha_eski_surum_daha_yeni_degil(self):
        assert is_newer_version("v1.0.0", "1.1.0") is False

    def test_cift_haneli_parcalar_sozluksel_degil(self):
        assert is_newer_version("v1.10.0", "1.9.0") is True

    def test_gecersiz_girdi_false_doner(self):
        assert is_newer_version(None, "1.0.0") is False


class TestFindReleaseWithAsset:
    def test_depo_release_listesini_masaustu_ve_mobil_karisikken_dogru_ayiklar(self):
        # Gercek senaryo: mobil daha yeni bir release yayinladi (sadece
        # .apk), masaustunun kendi surumu listede daha asagida. Ham
        # /releases/latest kullansaydik yanlislikla mobil release'ini
        # bulurduk.
        releases = [
            {
                "tag_name": "v1.0.1",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "ai-kedi-asistani.apk"}],
            },
            {
                "tag_name": "v1.2.1",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "AI-Kedi-Asistani.exe"}],
            },
        ]
        found = find_release_with_asset(releases, "AI-Kedi-Asistani.exe")
        assert found is not None
        assert found["tag_name"] == "v1.2.1"

    def test_taslak_release_atlanir(self):
        releases = [
            {
                "tag_name": "v2.0.0",
                "draft": True,
                "prerelease": False,
                "assets": [{"name": "AI-Kedi-Asistani.exe"}],
            },
            {
                "tag_name": "v1.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "AI-Kedi-Asistani.exe"}],
            },
        ]
        found = find_release_with_asset(releases, "AI-Kedi-Asistani.exe")
        assert found["tag_name"] == "v1.0.0"

    def test_on_surum_atlanir(self):
        releases = [
            {
                "tag_name": "v2.0.0-beta",
                "draft": False,
                "prerelease": True,
                "assets": [{"name": "AI-Kedi-Asistani.exe"}],
            },
            {
                "tag_name": "v1.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "AI-Kedi-Asistani.exe"}],
            },
        ]
        found = find_release_with_asset(releases, "AI-Kedi-Asistani.exe")
        assert found["tag_name"] == "v1.0.0"

    def test_eslesen_asset_yoksa_none_doner(self):
        releases = [
            {
                "tag_name": "v1.0.1",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "ai-kedi-asistani.apk"}],
            }
        ]
        assert find_release_with_asset(releases, "AI-Kedi-Asistani.exe") is None

    def test_bos_liste_none_doner(self):
        assert find_release_with_asset([], "AI-Kedi-Asistani.exe") is None


class TestIsUrlSafeToOpen:
    """IP literalleriyle test edilir - getaddrinfo bunlari gercek bir DNS
    sorgusu yapmadan yerel olarak cozer, bu yuzden testler ag erisimi
    gerektirmez ve CI'da guvenilir sekilde calisir."""

    def test_genel_ip_izinli(self):
        assert is_url_safe_to_open("http://8.8.8.8/x") is True

    def test_loopback_reddedilir(self):
        assert is_url_safe_to_open("http://127.0.0.1/x") is False

    def test_ozel_ag_reddedilir(self):
        assert is_url_safe_to_open("http://192.168.1.1/x") is False
        assert is_url_safe_to_open("http://10.0.0.1/x") is False
        assert is_url_safe_to_open("http://172.16.0.1/x") is False

    def test_link_local_reddedilir(self):
        assert is_url_safe_to_open("http://169.254.1.1/x") is False

    def test_localhost_hostname_reddedilir(self):
        assert is_url_safe_to_open("http://localhost/x") is False

    def test_gecersiz_sema_reddedilir(self):
        assert is_url_safe_to_open("ftp://8.8.8.8/x") is False
        assert is_url_safe_to_open("file:///etc/passwd") is False

    def test_cozulemeyen_host_reddedilir(self):
        assert is_url_safe_to_open("http://bu-host-kesinlikle-yok.invalid/x") is False


class TestValidateCustomCommand:
    def test_gecerli_isim_ve_baglanti_kabul_edilir(self):
        assert validate_custom_command("Haberler", "http://8.8.8.8/x") is None

    def test_bos_isim_reddedilir(self):
        assert validate_custom_command("  ", "http://8.8.8.8/x") is not None

    def test_bos_baglanti_reddedilir(self):
        assert validate_custom_command("Haberler", "  ") is not None

    def test_guvensiz_baglanti_reddedilir(self):
        error = validate_custom_command("Router", "http://192.168.1.1/x")
        assert error is not None
        assert "http(s)" in error.lower() or "http" in error.lower()

    def test_bos_isim_once_kontrol_edilir(self):
        # Hem isim hem baglanti gecersizse, once isim hatasi donmeli.
        error = validate_custom_command("", "")
        assert error == "Bir isim yaz."


class TestBuildPairingUri:
    def test_semayi_ve_yolu_icerir(self):
        uri = build_pairing_uri("192.168.1.5", 8765, "123456", "AA:BB")
        assert uri.startswith("aikedi://pair?")

    def test_tum_alanlar_sorgu_dizesinde_bulunur(self):
        uri = build_pairing_uri("192.168.1.5", 8765, "123456", "AA:BB:CC")
        assert "ip=192.168.1.5" in uri
        assert "port=8765" in uri
        assert "pin=123456" in uri
        # ':' url-encode edilir (%3A).
        assert "fp=AA%3ABB%3ACC" in uri

    def test_ozel_karakterler_dogru_kacirilir(self):
        uri = build_pairing_uri("10.0.0.1", 8765, "111111", "AA:BB & CC")
        assert "AA:BB & CC" not in uri
        assert "%26" in uri or "+" in uri or "%20" in uri


class TestComputeUsageStats:
    def test_bos_verilerle_tum_sayaclar_sifir(self):
        stats = compute_usage_stats([], [], [], [], {}, datetime(2026, 1, 10))
        assert stats["total_questions"] == 0
        assert stats["questions_today"] == 0
        assert stats["questions_this_week"] == 0
        assert stats["error_count"] == 0
        assert stats["favorite_count"] == 0
        assert stats["notification_count"] == 0
        assert stats["automation_rule_count"] == 0
        assert stats["custom_command_count"] == 0
        assert stats["connected_device_count"] == 0
        assert stats["first_question_at"] is None

    def test_toplam_soru_hatalilar_dahil_sayilir(self):
        now = datetime(2026, 1, 10, 12, 0)
        entries = [
            {"time": "2026-01-10 11:00", "question": "q1", "answer": "a1", "is_error": False},
            {"time": "2026-01-10 11:30", "question": "q2", "answer": "hata", "is_error": True},
        ]
        stats = compute_usage_stats(entries, [], [], [], {}, now)
        assert stats["total_questions"] == 2
        assert stats["error_count"] == 1

    def test_bugun_ve_bu_hafta_sayaclari_dogru_ayrilir(self):
        now = datetime(2026, 1, 10, 12, 0)
        entries = [
            {"time": "2026-01-10 09:00", "question": "bugun", "answer": "a", "is_error": False},
            {"time": "2026-01-07 09:00", "question": "hafta-ici", "answer": "a", "is_error": False},
            {"time": "2025-12-01 09:00", "question": "eski", "answer": "a", "is_error": False},
        ]
        stats = compute_usage_stats(entries, [], [], [], {}, now)
        assert stats["questions_today"] == 1
        assert stats["questions_this_week"] == 2
        assert stats["total_questions"] == 3

    def test_favori_sayisi_dogru(self):
        now = datetime(2026, 1, 10)
        entries = [
            {"time": "2026-01-01 10:00", "question": "q1", "answer": "a1", "favorite": True},
            {"time": "2026-01-01 10:00", "question": "q2", "answer": "a2", "favorite": False},
        ]
        stats = compute_usage_stats(entries, [], [], [], {}, now)
        assert stats["favorite_count"] == 1

    def test_bozuk_zaman_damgasi_atlanir(self):
        now = datetime(2026, 1, 10)
        entries = [{"time": "gecersiz", "question": "q1", "answer": "a1"}]
        stats = compute_usage_stats(entries, [], [], [], {}, now)
        assert stats["total_questions"] == 1
        assert stats["questions_today"] == 0
        assert stats["first_question_at"] is None

    def test_en_eski_kayit_first_question_at_olarak_donduruluyor(self):
        now = datetime(2026, 1, 10)
        entries = [
            {"time": "2026-01-05 10:00", "question": "yeni", "answer": "a"},
            {"time": "2025-01-01 10:00", "question": "eski", "answer": "a"},
        ]
        stats = compute_usage_stats(entries, [], [], [], {}, now)
        assert stats["first_question_at"] == datetime(2025, 1, 1, 10, 0)

    def test_diger_listelerin_uzunluklari_dogrudan_sayilir(self):
        now = datetime(2026, 1, 10)
        stats = compute_usage_stats(
            [],
            [{"time": "x", "title": "t", "message": "m"}] * 2,
            [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            [{"id": "1"}],
            {"1.2.3.4": {}, "5.6.7.8": {}},
            now,
        )
        assert stats["notification_count"] == 2
        assert stats["automation_rule_count"] == 3
        assert stats["custom_command_count"] == 1
        assert stats["connected_device_count"] == 2


class TestFormatUsageStats:
    def test_ilk_soru_yoksa_tire_gosterilir(self):
        stats = compute_usage_stats([], [], [], [], {}, datetime(2026, 1, 10))
        text = format_usage_stats(stats)
        assert "İlk soru tarihi: -" in text

    def test_sayaclar_metinde_gorunur(self):
        now = datetime(2026, 1, 10)
        entries = [{"time": "2026-01-10 09:00", "question": "q", "answer": "a"}]
        stats = compute_usage_stats(entries, [], [], [], {}, now)
        text = format_usage_stats(stats)
        assert "Toplam soru: 1" in text
        assert "Bugün sorulan: 1" in text


class TestMergeHistoryEntries:
    def test_yeni_kayitlar_eklenir(self):
        existing = [
            {"time": "2026-01-01 10:00", "question": "q1", "answer": "a1", "is_error": False}
        ]
        new = [
            {"time": "2026-01-01 11:00", "question": "q2", "answer": "a2", "is_error": False}
        ]
        added = merge_history_entries(existing, new)
        assert added == 1
        assert len(existing) == 2
        assert existing[1]["question"] == "q2"

    def test_ayni_zaman_soru_cevap_uclusu_tekrar_eklenmez(self):
        existing = [
            {"time": "2026-01-01 10:00", "question": "q1", "answer": "a1", "is_error": False}
        ]
        new = [
            {"time": "2026-01-01 10:00", "question": "q1", "answer": "a1", "is_error": False}
        ]
        added = merge_history_entries(existing, new)
        assert added == 0
        assert len(existing) == 1

    def test_ayni_liste_icindeki_tekrarlar_da_bir_kez_eklenir(self):
        existing = []
        new = [
            {"time": "2026-01-01 10:00", "question": "q1", "answer": "a1"},
            {"time": "2026-01-01 10:00", "question": "q1", "answer": "a1"},
        ]
        added = merge_history_entries(existing, new)
        assert added == 1
        assert len(existing) == 1

    def test_zaman_veya_soru_bos_kayit_atlanir(self):
        existing = []
        new = [
            {"time": "", "question": "q1", "answer": "a1"},
            {"time": "2026-01-01 10:00", "question": "", "answer": "a1"},
        ]
        added = merge_history_entries(existing, new)
        assert added == 0
        assert existing == []

    def test_dict_olmayan_kayit_atlanir(self):
        existing = []
        added = merge_history_entries(existing, ["gecersiz", 42, None])
        assert added == 0
        assert existing == []

    def test_alanlar_maksimum_uzunluga_kesilir(self):
        existing = []
        long_text = "x" * (HISTORY_ENTRY_MAX_FIELD_LENGTH + 100)
        new = [{"time": "2026-01-01 10:00", "question": long_text, "answer": long_text}]
        merge_history_entries(existing, new)
        assert len(existing[0]["question"]) == HISTORY_ENTRY_MAX_FIELD_LENGTH
        assert len(existing[0]["answer"]) == HISTORY_ENTRY_MAX_FIELD_LENGTH

    def test_eksik_is_error_false_varsayilir(self):
        existing = []
        new = [{"time": "2026-01-01 10:00", "question": "q1", "answer": "a1"}]
        merge_history_entries(existing, new)
        assert existing[0]["is_error"] is False


class TestSelectContextTurns:
    def test_kapaliysa_bos_liste_doner(self):
        entries = [{"question": "q1", "answer": "a1", "is_error": False}]
        assert select_context_turns(entries, enabled=False) == []

    def test_acikken_soru_cevaplar_donusturulur(self):
        entries = [
            {"question": "q1", "answer": "a1", "is_error": False},
            {"question": "q2", "answer": "a2", "is_error": False},
        ]
        result = select_context_turns(entries, enabled=True)
        assert result == [
            {"question": "q1", "answer": "a1"},
            {"question": "q2", "answer": "a2"},
        ]

    def test_hatali_kayitlar_haric_tutulur(self):
        entries = [
            {"question": "q1", "answer": "a1", "is_error": False},
            {"question": "q2", "answer": "hata mesaji", "is_error": True},
            {"question": "q3", "answer": "a3", "is_error": False},
        ]
        result = select_context_turns(entries, enabled=True)
        assert result == [
            {"question": "q1", "answer": "a1"},
            {"question": "q3", "answer": "a3"},
        ]

    def test_sadece_son_max_turns_kadar_alinir(self):
        entries = [
            {"question": f"q{i}", "answer": f"a{i}", "is_error": False}
            for i in range(10)
        ]
        result = select_context_turns(entries, enabled=True, max_turns=3)
        assert [t["question"] for t in result] == ["q7", "q8", "q9"]

    def test_gecmis_bossa_bos_liste_doner(self):
        assert select_context_turns([], enabled=True) == []


class TestFormatHistoryEntries:
    def test_en_yeni_en_ustte(self):
        entries = [
            {"time": "2026-01-01 10:00", "question": "q1", "answer": "a1"},
            {"time": "2026-01-01 11:00", "question": "q2", "answer": "a2"},
        ]
        text = format_history_entries(entries)
        assert text.index("q2") < text.index("q1")

    def test_hata_isaretiyle_isaretlenir(self):
        entries = [
            {"time": "2026-01-01 10:00", "question": "q1", "answer": "hata!", "is_error": True}
        ]
        text = format_history_entries(entries)
        assert "⚠ hata!" in text

    def test_bos_liste_bos_metin_doner(self):
        assert format_history_entries([]) == ""


class TestRecordConnection:
    def test_yeni_ip_eklenir(self):
        conns = {}
        record_connection(conns, "1.2.3.4", "/open", 1000.0, max_connections=5)
        assert conns["1.2.3.4"]["count"] == 1
        assert conns["1.2.3.4"]["last_endpoint"] == "/open"
        assert conns["1.2.3.4"]["last_seen_epoch"] == 1000.0

    def test_ayni_ip_tekrar_gelince_sayac_artar_ve_guncellenir(self):
        conns = {}
        record_connection(conns, "1.2.3.4", "/open", 1000.0, max_connections=5)
        record_connection(conns, "1.2.3.4", "/media", 1010.0, max_connections=5)
        assert conns["1.2.3.4"]["count"] == 2
        assert conns["1.2.3.4"]["last_endpoint"] == "/media"
        assert conns["1.2.3.4"]["last_seen_epoch"] == 1010.0

    def test_kapasite_asilinca_en_eski_ip_cikarilir(self):
        conns = {}
        record_connection(conns, "1.1.1.1", "/open", 1000.0, max_connections=2)
        record_connection(conns, "2.2.2.2", "/open", 2000.0, max_connections=2)
        record_connection(conns, "3.3.3.3", "/open", 3000.0, max_connections=2)
        assert "1.1.1.1" not in conns
        assert set(conns) == {"2.2.2.2", "3.3.3.3"}

    def test_kapasite_doluyken_mevcut_ip_guncellenmesi_baskasini_cikarmaz(self):
        conns = {}
        record_connection(conns, "1.1.1.1", "/open", 1000.0, max_connections=2)
        record_connection(conns, "2.2.2.2", "/open", 2000.0, max_connections=2)
        record_connection(conns, "1.1.1.1", "/media", 3000.0, max_connections=2)
        assert set(conns) == {"1.1.1.1", "2.2.2.2"}
        assert conns["1.1.1.1"]["count"] == 2


class TestFormatRelativeTime:
    def test_bir_dakikadan_az_az_once_doner(self):
        now = datetime(2024, 1, 1, 12, 0, 30)
        assert format_relative_time("2024-01-01 12:00", now) == "az once"

    def test_dakika_cinsinden(self):
        now = datetime(2024, 1, 1, 12, 5, 0)
        assert format_relative_time("2024-01-01 12:00", now) == "5 dakika once"

    def test_saat_cinsinden(self):
        now = datetime(2024, 1, 1, 15, 0, 0)
        assert format_relative_time("2024-01-01 12:00", now) == "3 saat once"

    def test_gun_cinsinden(self):
        now = datetime(2024, 1, 3, 12, 0, 0)
        assert format_relative_time("2024-01-01 12:00", now) == "2 gun once"

    def test_ayristirilamayan_deger_oldugu_gibi_doner(self):
        assert format_relative_time("gecersiz", datetime(2024, 1, 1)) == "gecersiz"
        assert format_relative_time(None, datetime(2024, 1, 1)) == "None"


class TestFormatRecentConnections:
    def test_bos_sozluk_icin_mesaj_doner(self):
        assert format_recent_connections({}, datetime(2024, 1, 1)) == "Son baglanan cihaz yok."

    def test_en_yeni_en_ustte_ve_goreli_sure_icerir(self):
        now = datetime(2024, 1, 1, 12, 10, 0)
        connections = {
            "1.1.1.1": {
                "count": 3,
                "last_seen_epoch": 1000,
                "last_seen": "2024-01-01 12:00",
                "last_endpoint": "/open",
            },
            "2.2.2.2": {
                "count": 1,
                "last_seen_epoch": 2000,
                "last_seen": "2024-01-01 12:05",
                "last_endpoint": "/screenshot",
            },
        }
        text = format_recent_connections(connections, now)
        lines = text.split("\n")
        assert "2.2.2.2" in lines[1]
        assert "5 dakika once" in lines[1]
        assert "1.1.1.1" in lines[2]
        assert "10 dakika once" in lines[2]


class TestShouldRunAutoBackup:
    def test_hic_yedek_yoksa_true_doner(self):
        assert should_run_auto_backup(None, datetime(2026, 1, 2)) is True
        assert should_run_auto_backup("", datetime(2026, 1, 2)) is True

    def test_gecersiz_tarih_true_doner(self):
        assert should_run_auto_backup("gecersiz-tarih", datetime(2026, 1, 2)) is True

    def test_interval_dolmamissa_false_doner(self):
        last = datetime(2026, 1, 1, 10, 0).isoformat()
        now = datetime(2026, 1, 1, 20, 0)  # 10 saat sonra
        assert should_run_auto_backup(last, now, interval_days=1) is False

    def test_interval_dolmussa_true_doner(self):
        last = datetime(2026, 1, 1, 10, 0).isoformat()
        now = datetime(2026, 1, 2, 11, 0)  # 25 saat sonra
        assert should_run_auto_backup(last, now, interval_days=1) is True

    def test_tam_interval_sinirinda_true_doner(self):
        last = datetime(2026, 1, 1, 10, 0)
        now = last + timedelta(days=1)
        assert should_run_auto_backup(last.isoformat(), now, interval_days=1) is True


class TestParseHhMm:
    def test_gecerli_saat_normallestirilir(self):
        assert parse_hh_mm("9:5") == "09:05"
        assert parse_hh_mm(" 18:30 ") == "18:30"
        assert parse_hh_mm("00:00") == "00:00"
        assert parse_hh_mm("23:59") == "23:59"

    def test_iki_parca_degilse_none_doner(self):
        assert parse_hh_mm("1830") is None
        assert parse_hh_mm("18:30:00") is None

    def test_sayi_degilse_none_doner(self):
        assert parse_hh_mm("ab:cd") is None

    def test_aralik_disinda_none_doner(self):
        assert parse_hh_mm("24:00") is None
        assert parse_hh_mm("12:60") is None
        assert parse_hh_mm("-1:00") is None


class TestResolveAutoThemeMode:
    def test_gunduz_araliginda_light_doner(self):
        now = datetime(2024, 1, 1, 12, 0)
        assert resolve_auto_theme_mode(now, "07:00", "19:00") == "light"

    def test_gece_araliginda_dark_doner(self):
        now = datetime(2024, 1, 1, 22, 0)
        assert resolve_auto_theme_mode(now, "07:00", "19:00") == "dark"

    def test_gunduz_baslangicinda_tam_olarak_light_doner(self):
        now = datetime(2024, 1, 1, 7, 0)
        assert resolve_auto_theme_mode(now, "07:00", "19:00") == "light"

    def test_gece_baslangicinda_tam_olarak_dark_doner(self):
        now = datetime(2024, 1, 1, 19, 0)
        assert resolve_auto_theme_mode(now, "07:00", "19:00") == "dark"

    def test_gecersiz_saatler_varsayilana_duser(self):
        now = datetime(2024, 1, 1, 12, 0)
        assert resolve_auto_theme_mode(now, "gecersiz", "gecersiz") == "light"

    def test_gunduz_araligi_gece_yarisini_geciyorsa(self):
        # gunduz baslangici gece baslangicindan sonraysa (orn. vardiyali
        # kullanim) - gece yarisini gecen araliktaki saatler de light olmali
        now = datetime(2024, 1, 1, 23, 0)
        assert resolve_auto_theme_mode(now, "20:00", "06:00") == "light"
        now = datetime(2024, 1, 1, 10, 0)
        assert resolve_auto_theme_mode(now, "20:00", "06:00") == "dark"


class TestShouldFireRule:
    def test_devre_disi_kural_hicbir_zaman_ateslenmez(self):
        rule = {"enabled": False, "trigger_type": "time_daily", "trigger_value": "10:00"}
        now = datetime(2026, 1, 1, 10, 0)
        assert should_fire_rule(rule, now, idle_seconds=0) is False

    def test_gunluk_saat_tutmuyorsa_ateslenmez(self):
        rule = {"trigger_type": "time_daily", "trigger_value": "10:00"}
        now = datetime(2026, 1, 1, 9, 59)
        assert should_fire_rule(rule, now, idle_seconds=0) is False

    def test_gunluk_saat_tutunca_ilk_kez_ateslenir(self):
        rule = {"trigger_type": "time_daily", "trigger_value": "10:00", "last_fired": None}
        now = datetime(2026, 1, 1, 10, 0)
        assert should_fire_rule(rule, now, idle_seconds=0) is True

    def test_gunluk_kural_bugun_zaten_ateslendiyse_tekrar_ateslenmez(self):
        rule = {
            "trigger_type": "time_daily",
            "trigger_value": "10:00",
            "last_fired": datetime(2026, 1, 1, 10, 0).isoformat(),
        }
        now = datetime(2026, 1, 1, 10, 0)
        assert should_fire_rule(rule, now, idle_seconds=0) is False

    def test_gunluk_kural_ertesi_gun_tekrar_ateslenir(self):
        rule = {
            "trigger_type": "time_daily",
            "trigger_value": "10:00",
            "last_fired": datetime(2026, 1, 1, 10, 0).isoformat(),
        }
        now = datetime(2026, 1, 2, 10, 0)
        assert should_fire_rule(rule, now, idle_seconds=0) is True

    def test_hareketsizlik_esigi_asilmamissa_ateslenmez(self):
        rule = {"trigger_type": "idle_minutes", "trigger_value": 30, "last_fired": None}
        now = datetime(2026, 1, 1, 10, 0)
        assert should_fire_rule(rule, now, idle_seconds=29 * 60) is False

    def test_hareketsizlik_esigi_asilinca_ateslenir(self):
        rule = {"trigger_type": "idle_minutes", "trigger_value": 30, "last_fired": None}
        now = datetime(2026, 1, 1, 10, 0)
        assert should_fire_rule(rule, now, idle_seconds=30 * 60) is True

    def test_hareketsizlikte_ayni_pencerede_tekrar_ateslenmez(self):
        rule = {
            "trigger_type": "idle_minutes",
            "trigger_value": 30,
            "last_fired": datetime(2026, 1, 1, 10, 0).isoformat(),
        }
        now = datetime(2026, 1, 1, 10, 20)  # sadece 20 dk sonra, esik 30 dk
        assert should_fire_rule(rule, now, idle_seconds=50 * 60) is False

    def test_hareketsizlik_esigi_yeniden_asilinca_tekrar_ateslenir(self):
        rule = {
            "trigger_type": "idle_minutes",
            "trigger_value": 30,
            "last_fired": datetime(2026, 1, 1, 10, 0).isoformat(),
        }
        now = datetime(2026, 1, 1, 10, 35)  # 35 dk sonra, esik 30 dk asildi
        assert should_fire_rule(rule, now, idle_seconds=60 * 60) is True

    def test_bilinmeyen_tetikleyici_turu_false_doner(self):
        rule = {"trigger_type": "bilinmeyen", "trigger_value": "x"}
        assert should_fire_rule(rule, datetime(2026, 1, 1), idle_seconds=999999) is False


class TestDescribeAndFormatAutomationRules:
    def test_aktif_kural_ozeti(self):
        rule = {
            "name": "Ise gec kalma",
            "trigger_type": "time_daily",
            "trigger_value": "18:00",
            "action_type": "notify",
            "action_value": "Eve gitme zamani!",
            "enabled": True,
        }
        desc = describe_automation_rule(rule)
        assert "Ise gec kalma" in desc
        assert "18:00" in desc
        assert "Eve gitme zamani!" in desc
        assert "devre disi" not in desc

    def test_devre_disi_kural_ozetinde_belirtilir(self):
        rule = {
            "name": "Test",
            "trigger_type": "idle_minutes",
            "trigger_value": 30,
            "action_type": "lock",
            "enabled": False,
        }
        assert "[devre disi]" in describe_automation_rule(rule)

    def test_format_bos_listede_bos_metin_doner(self):
        assert format_automation_rules([]) == ""

    def test_format_numaralandirir(self):
        rules = [
            {"name": "A", "trigger_type": "time_daily", "trigger_value": "09:00",
             "action_type": "lock", "enabled": True},
            {"name": "B", "trigger_type": "idle_minutes", "trigger_value": 5,
             "action_type": "sleep", "enabled": True},
        ]
        text = format_automation_rules(rules)
        lines = text.split("\n")
        assert lines[0].startswith("1. ")
        assert lines[1].startswith("2. ")


class TestDefaultQuickQuestions:
    def test_bos_degil(self):
        assert len(DEFAULT_QUICK_QUESTIONS) > 0

    def test_tum_ogeler_bos_olmayan_metin(self):
        for question in DEFAULT_QUICK_QUESTIONS:
            assert isinstance(question, str)
            assert question.strip()

    def test_tekrar_eden_soru_yok(self):
        assert len(DEFAULT_QUICK_QUESTIONS) == len(set(DEFAULT_QUICK_QUESTIONS))


class TestScreenshotHistoryLog:
    def test_yeni_kayit_dosyaya_yazilir(self, tmp_path):
        log = ScreenshotHistoryLog(str(tmp_path / "screenshot_history.json"))
        log.add("Telefon (192.168.1.5)")
        assert len(log.entries) == 1
        assert log.entries[0]["source"] == "Telefon (192.168.1.5)"
        assert "time" in log.entries[0]

    def test_kalicidir(self, tmp_path):
        path = str(tmp_path / "screenshot_history.json")
        log = ScreenshotHistoryLog(path)
        log.add("Telefon (192.168.1.5)")
        reloaded = ScreenshotHistoryLog(path)
        assert len(reloaded.entries) == 1

    def test_maksimum_kayit_sayisini_asmaz(self, tmp_path):
        log = ScreenshotHistoryLog(str(tmp_path / "screenshot_history.json"))
        for i in range(60):
            log.add(f"Telefon ({i})")
        assert len(log.entries) == 50
        assert log.entries[-1]["source"] == "Telefon (59)"

    def test_clear_tum_kayitlari_siler(self, tmp_path):
        log = ScreenshotHistoryLog(str(tmp_path / "screenshot_history.json"))
        log.add("Telefon (192.168.1.5)")
        log.clear()
        assert log.entries == []


class TestFormatScreenshotHistory:
    def test_bos_liste_bos_metin_dondurur(self):
        assert format_screenshot_history([]) == ""

    def test_en_yeni_en_ustte(self):
        entries = [
            {"time": "2024-01-01 10:00", "source": "Telefon (a)"},
            {"time": "2024-01-02 10:00", "source": "Telefon (b)"},
        ]
        lines = format_screenshot_history(entries).split("\n")
        assert "Telefon (b)" in lines[0]
        assert "Telefon (a)" in lines[1]


class TestBuildPersonaPrompt:
    def test_karakter_adi_yer_alir(self):
        assert "Fuff" in build_persona_prompt("Fuff", "Varsayilan")

    def test_her_kisilik_farkli_ton_uretir(self):
        prompts = {
            personality: build_persona_prompt("Fuff", personality)
            for personality in PERSONALITY_PRESETS
        }
        assert len(set(prompts.values())) == len(PERSONALITY_PRESETS)

    def test_bilinmeyen_kisilik_varsayilana_duser(self):
        assert build_persona_prompt("Fuff", "olmayan-kisilik") == build_persona_prompt(
            "Fuff", "Varsayilan"
        )

    def test_model_kimligi_asla_soylenmez_talimati_her_zaman_var(self):
        for personality in PERSONALITY_PRESETS:
            prompt = build_persona_prompt("Fuff", personality)
            assert "asla soyleme" in prompt


class TestBuildSettingsProfile:
    def test_yalnizca_bilinen_anahtarlari_alir(self):
        config_data = dict(
            {key: "x" for key in PROFILE_EXPORT_KEYS},
            gemini_api_key="gizli-anahtar",
            remote_pin="123456",
            pos_x=100,
        )
        profile = build_settings_profile(config_data)
        assert set(profile.keys()) == set(PROFILE_EXPORT_KEYS)
        assert "gemini_api_key" not in profile
        assert "remote_pin" not in profile
        assert "pos_x" not in profile

    def test_eksik_anahtarlari_atlar(self):
        profile = build_settings_profile({"character_name": "Fuff"})
        assert profile == {"character_name": "Fuff"}


class TestApplySettingsProfile:
    def _config(self, tmp_path):
        return ConfigManager(str(tmp_path / "config.json"))

    def test_bilinen_anahtarlar_uygulanir(self, tmp_path):
        config = self._config(tmp_path)
        applied = apply_settings_profile(config, {"character_name": "Pati", "scale_percent": 150})
        assert config.get("character_name") == "Pati"
        assert config.get("scale_percent") == 150
        assert set(applied) == {"character_name", "scale_percent"}

    def test_bilinmeyen_anahtarlar_yok_sayilir(self, tmp_path):
        config = self._config(tmp_path)
        original_pin = config.get("remote_pin")
        applied = apply_settings_profile(
            config, {"gemini_api_key": "gizli", "remote_pin": "000000", "unknown_key": "x"}
        )
        assert applied == []
        assert config.get("gemini_api_key") == ""
        assert config.get("remote_pin") == original_pin

    def test_dict_olmayan_veri_hicbir_sey_uygulamaz(self, tmp_path):
        config = self._config(tmp_path)
        assert apply_settings_profile(config, ["not", "a", "dict"]) == []
        assert apply_settings_profile(config, None) == []

    def test_disa_ice_aktarma_yuvarlanabilir(self, tmp_path):
        source = ConfigManager(str(tmp_path / "source.json"))
        source.set("character_name", "Pati")
        source.set("theme_mode", "light")
        profile = build_settings_profile(source.data)

        dest = ConfigManager(str(tmp_path / "dest.json"))
        apply_settings_profile(dest, profile)
        assert dest.get("character_name") == "Pati"
        assert dest.get("theme_mode") == "light"


class TestSecureNotepadService:
    """Dusuk bir PBKDF2 iterasyon sayisiyla calisir - varsayilan 200k
    iterasyon test suitini gereksiz yavaslatir, ayni kod yolunu daha
    hizli sinamak icin."""

    def _service(self, tmp_path):
        return SecureNotepadService(
            path=str(tmp_path / "secure_notepad.dat"), pbkdf2_iterations=100
        )

    def test_kurulmadan_once_is_set_up_false(self, tmp_path):
        assert self._service(tmp_path).is_set_up() is False

    def test_set_up_sonrasi_is_set_up_true(self, tmp_path):
        service = self._service(tmp_path)
        service.set_up("dogru-sifre")
        assert service.is_set_up() is True

    def test_set_up_sonrasi_dogru_sifreyle_bos_liste_acilir(self, tmp_path):
        service = self._service(tmp_path)
        service.set_up("dogru-sifre")
        _, notes = service.unlock("dogru-sifre")
        assert notes == []

    def test_yanlis_sifre_wrongpassworderror_firlatir(self, tmp_path):
        service = self._service(tmp_path)
        service.set_up("dogru-sifre")
        with pytest.raises(WrongPasswordError):
            service.unlock("yanlis-sifre")

    def test_save_edilen_notlar_dogru_sifreyle_geri_yuklenir(self, tmp_path):
        service = self._service(tmp_path)
        key = service.set_up("dogru-sifre")
        notes = [{"id": "1", "title": "Banka PIN", "body": "gizli", "updated_at": "x"}]
        service.save(key, notes)

        _, loaded = service.unlock("dogru-sifre")
        assert loaded == notes

    def test_kaydedilen_dosyada_duz_metin_gorunmez(self, tmp_path):
        service = self._service(tmp_path)
        key = service.set_up("dogru-sifre")
        service.save(key, [{"id": "1", "title": "gizli-baslik-xyz", "body": "gizli-govde-abc", "updated_at": "x"}])

        raw = (tmp_path / "secure_notepad.dat").read_text()
        assert "gizli-baslik-xyz" not in raw
        assert "gizli-govde-abc" not in raw

    def test_reset_sonrasi_yeniden_kurulabilir(self, tmp_path):
        service = self._service(tmp_path)
        service.set_up("eski-sifre")
        service.reset()
        assert service.is_set_up() is False

        service.set_up("yeni-sifre")
        _, notes = service.unlock("yeni-sifre")
        assert notes == []

    def test_ardisik_save_farkli_sifreli_metin_uretir(self, tmp_path):
        service = self._service(tmp_path)
        key = service.set_up("dogru-sifre")
        path = tmp_path / "secure_notepad.dat"

        service.save(key, [])
        first = path.read_text()
        service.save(key, [])
        second = path.read_text()
        assert first != second


class TestPruneOldBackups:
    def test_dizin_yoksa_hicbir_sey_yapmaz(self, tmp_path):
        missing = tmp_path / "yok"
        prune_old_backups(str(missing), keep_count=3)  # patlamamali

    def test_fazla_dosyalar_en_eskiden_baslayarak_silinir(self, tmp_path):
        names = [
            "otomatik-yedek-2026-01-01-000000.json",
            "otomatik-yedek-2026-01-02-000000.json",
            "otomatik-yedek-2026-01-03-000000.json",
        ]
        for name in names:
            (tmp_path / name).write_text("{}")
        prune_old_backups(str(tmp_path), keep_count=2)
        remaining = sorted(p.name for p in tmp_path.iterdir())
        assert remaining == names[1:]

    def test_kapasitenin_altindaysa_hicbir_sey_silinmez(self, tmp_path):
        (tmp_path / "otomatik-yedek-2026-01-01-000000.json").write_text("{}")
        prune_old_backups(str(tmp_path), keep_count=5)
        assert len(list(tmp_path.iterdir())) == 1

    def test_ilgisiz_dosyalara_dokunmaz(self, tmp_path):
        (tmp_path / "baska-dosya.txt").write_text("x")
        for i in range(3):
            (tmp_path / f"otomatik-yedek-2026-01-0{i + 1}-000000.json").write_text("{}")
        prune_old_backups(str(tmp_path), keep_count=1)
        remaining = sorted(p.name for p in tmp_path.iterdir())
        assert "baska-dosya.txt" in remaining
        assert len(remaining) == 2  # baska-dosya.txt + tutulan 1 yedek


class TestFormatAccessLogLine:
    def test_detay_olmadan(self):
        line = format_access_log_line("2026-01-01 10:00:00", "1.2.3.4", "istek")
        assert line == "2026-01-01 10:00:00\t1.2.3.4\tistek"

    def test_detayla(self):
        line = format_access_log_line("2026-01-01 10:00:00", "1.2.3.4", "istek", "/open")
        assert line == "2026-01-01 10:00:00\t1.2.3.4\tistek\t/open"


class TestAppendAccessLog:
    def test_dosya_yoksa_olusturur_ve_yazar(self, tmp_path):
        path = str(tmp_path / "log.txt")
        append_access_log(path, "satir1", max_bytes=1_000_000)
        append_access_log(path, "satir2", max_bytes=1_000_000)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == "satir1\nsatir2\n"

    def test_boyut_asilinca_en_eski_yari_atilir(self, tmp_path):
        path = str(tmp_path / "log.txt")
        # Her satir yaklasik ayni uzunlukta - dosyayi max_bytes'i asacak
        # sekilde doldurup rotasyonun tetiklendigini dogruluyoruz.
        for i in range(20):
            append_access_log(path, f"satir-{i:03d}", max_bytes=100)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) < 20  # eski satirlarin bir kismi atilmis olmali
        assert lines[-1].strip() == "satir-019"  # en yenisi hep korunur


class TestTailAccessLog:
    def test_dosya_yoksa_bos_liste_doner(self, tmp_path):
        assert tail_access_log(str(tmp_path / "yok.txt")) == []

    def test_son_n_satiri_dondurur(self, tmp_path):
        path = str(tmp_path / "log.txt")
        with open(path, "w", encoding="utf-8") as f:
            for i in range(10):
                f.write(f"satir-{i}\n")
        result = tail_access_log(path, max_lines=3)
        assert result == ["satir-7", "satir-8", "satir-9"]

    def test_dosya_max_lines_altindaysa_hepsini_doner(self, tmp_path):
        path = str(tmp_path / "log.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("tek-satir\n")
        assert tail_access_log(path, max_lines=50) == ["tek-satir"]


class TestFormatNotifications:
    def test_en_yeni_en_ustte(self):
        entries = [
            {"time": "2026-01-01 10:00", "title": "Baslik1", "message": "Mesaj1"},
            {"time": "2026-01-01 11:00", "title": "Baslik2", "message": "Mesaj2"},
        ]
        text = format_notifications(entries)
        assert text.index("Baslik2") < text.index("Baslik1")

    def test_baslik_ve_mesaj_icerir(self):
        entries = [{"time": "2026-01-01 10:00", "title": "T", "message": "M"}]
        text = format_notifications(entries)
        assert "[2026-01-01 10:00] T" in text
        assert "M" in text

    def test_bos_liste_bos_metin_doner(self):
        assert format_notifications([]) == ""


class TestLiveCoordsToPixels:
    """"Canlı Kontrol" sekmesinden gelen normallestirilmis (0..1) dokunma
    konumunun gercek ekran pikseline cevrilmesi (bkz.
    RemoteLiveControlServer)."""

    def test_orta_nokta_dogru_hesaplanir(self):
        assert live_coords_to_pixels(0.5, 0.5, 1920, 1080) == (960, 540)

    def test_kose_noktalar_dogru_hesaplanir(self):
        assert live_coords_to_pixels(0.0, 0.0, 1920, 1080) == (0, 0)
        assert live_coords_to_pixels(1.0, 1.0, 1920, 1080) == (1920, 1080)

    def test_sinir_disi_degerler_kirpilir(self):
        assert live_coords_to_pixels(-0.5, 2.0, 1920, 1080) == (0, 1080)


class TestNormalizeLiveKeyName:
    def test_ozel_tus_adi_kucuk_harfe_cevrilip_doner(self):
        assert normalize_live_key_name("Enter") == "enter"
        assert normalize_live_key_name("ESC") == "esc"

    def test_tek_karakter_oldugu_gibi_doner(self):
        assert normalize_live_key_name("a") == "a"
        assert normalize_live_key_name("3") == "3"

    def test_bos_veya_none_none_doner(self):
        assert normalize_live_key_name("") is None
        assert normalize_live_key_name(None) is None

    def test_taninmayan_coklu_karakter_none_doner(self):
        assert normalize_live_key_name("garip_komut") is None


class TestNormalizeLiveMouseButton:
    def test_gecerli_degerler_oldugu_gibi_doner(self):
        assert normalize_live_mouse_button("right") == "right"
        assert normalize_live_mouse_button("MIDDLE") == "middle"

    def test_gecersiz_veya_bos_deger_left_e_duser(self):
        assert normalize_live_mouse_button("") == "left"
        assert normalize_live_mouse_button(None) == "left"
        assert normalize_live_mouse_button("garip") == "left"


class TestSanitizeTeleportFilename:
    """"Dosya Teleport" ile telefondan gelen dosya adinin guvenli hale
    getirilmesi (bkz. RemoteCommandServer'in /file uc noktasi)."""

    def test_normal_ad_oldugu_gibi_doner(self):
        assert sanitize_teleport_filename("tatil_fotografi.jpg") == "tatil_fotografi.jpg"

    def test_yol_bilesenleri_atilir(self):
        assert sanitize_teleport_filename("../../gizli/parola.txt") == "parola.txt"
        assert sanitize_teleport_filename("C:\\Windows\\System32\\evil.exe") == "evil.exe"

    def test_bos_veya_sadece_nokta_varsayilan_ada_duser(self):
        assert sanitize_teleport_filename("") == "dosya"
        assert sanitize_teleport_filename(None) == "dosya"
        assert sanitize_teleport_filename("..") == "dosya"
        assert sanitize_teleport_filename(".") == "dosya"


class TestUniqueTeleportDestination:
    """Ayni adli dosya zaten varsa " (2)", " (3)" ile benzersiz bir hedef
    yol uretilmesi - telefondan arka arkaya gonderilen ayni isimli
    dosyalarin birbirinin uzerine yazilmamasi icin."""

    def test_dosya_yoksa_ad_degismez(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            destination = unique_teleport_destination(tmp_dir, "rapor.pdf")
            assert destination.endswith("rapor.pdf")

    def test_ayni_ad_varsa_sayac_eklenir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = unique_teleport_destination(tmp_dir, "rapor.pdf")
            with open(first, "w", encoding="utf-8") as f:
                f.write("x")
            second = unique_teleport_destination(tmp_dir, "rapor.pdf")
            assert second != first
            assert second.endswith("rapor (2).pdf")

    def test_uzanti_korunur(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = unique_teleport_destination(tmp_dir, "not.txt")
            with open(first, "w", encoding="utf-8") as f:
                f.write("x")
            second = unique_teleport_destination(tmp_dir, "not.txt")
            assert second.endswith(".txt")


class TestParseSendFileArg:
    """"Kediyle Gönder" - Windows Gezgini sag tik menusunden "--send-file
    <yol>" ile baslatildiginda argv'den dosya yolunun cikarilmasi."""

    def test_arg_varsa_yolu_doner(self):
        argv = ["AI-Kedi-Asistani.exe", "--send-file", "C:\\Users\\biri\\rapor.pdf"]
        assert parse_send_file_arg(argv) == "C:\\Users\\biri\\rapor.pdf"

    def test_arg_yoksa_none_doner(self):
        assert parse_send_file_arg(["AI-Kedi-Asistani.exe"]) is None

    def test_arg_son_elemansa_deger_eksikse_none_doner(self):
        assert parse_send_file_arg(["AI-Kedi-Asistani.exe", "--send-file"]) is None


class TestSendWithCatCommandLine:
    def test_exe_yolunu_tirnak_icine_alir_ve_percent1_kullanir(self):
        command = send_with_cat_command_line("C:\\Program Files\\AI-Kedi-Asistani.exe")
        assert command == (
            '"C:\\Program Files\\AI-Kedi-Asistani.exe" --send-file "%1"'
        )
