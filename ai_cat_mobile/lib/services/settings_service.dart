import 'dart:convert';

import 'package:flutter/material.dart' show ThemeMode;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/remote_profile.dart';
import 'vibration_pattern.dart';
import 'widget_service.dart';

/// Ayarlari (API anahtari, kedi ismi, model adi) cihazda saklar.
///
/// Not: shared_preferences duz metin olarak saklar (masaustu suruminin
/// config.json'u gibi) - sifrelenmis bir kasa degildir. Cihaz paylasiliyorsa
/// bunu goz onunde bulundurun.
class SettingsService {
  static const _keyApiKey = 'gemini_api_key';
  static const _keyCharacterName = 'character_name';
  static const _keyModelName = 'model_name';
  // Eski (tek bilgisayarli) uzaktan kumanda alanlari - artik dogrudan
  // kullanilmiyor, yalnizca ilk kez birden fazla bilgisayar profiline
  // gecerken tek seferlik gocu (migration) icin okunuyor.
  static const _keyDesktopIp = 'desktop_ip';
  static const _keyDesktopPort = 'desktop_port';
  static const _keyDesktopPin = 'desktop_pin';
  static const _keyDesktopCertFingerprint = 'desktop_cert_fingerprint';
  static const _keyRemoteProfiles = 'remote_profiles';
  static const _keyActiveProfileId = 'active_profile_id';
  static const _keyThemeMode = 'theme_mode';
  static const _keyAutoBackupEnabled = 'auto_backup_enabled';
  static const _keyAutoBackupLast = 'auto_backup_last';
  static const _keyWidgetSlot1Action = 'widget_slot1_action';
  static const _keyWidgetSlot2Action = 'widget_slot2_action';
  static const _keyAppLockEnabled = 'app_lock_enabled';
  static const _keyAppLockPin = 'app_lock_pin';
  static const _keyAutoThemeEnabled = 'auto_theme_enabled';
  static const _keyAutoThemeDayStart = 'auto_theme_day_start';
  static const _keyAutoThemeNightStart = 'auto_theme_night_start';
  static const _keyNotificationVibrationPattern =
      'notification_vibration_pattern';
  static const _keyLanguageCode = 'language_code';
  static const _keyScreenWatchOverlayEnabled = 'screen_watch_overlay_enabled';
  static const _keyLastSeenCrash = 'last_seen_crash';

  final SharedPreferences _prefs;

  SettingsService(this._prefs);

  String get apiKey => _prefs.getString(_keyApiKey) ?? '';
  set apiKey(String value) => _prefs.setString(_keyApiKey, value);

  String get characterName => _prefs.getString(_keyCharacterName) ?? 'Fuff';
  set characterName(String value) => _prefs.setString(_keyCharacterName, value);

  String get modelName =>
      _prefs.getString(_keyModelName) ?? 'gemini-flash-latest';
  set modelName(String value) => _prefs.setString(_keyModelName, value);

  /// Eslestirilmis bilgisayarlarin listesi (ev/is gibi birden fazla
  /// bilgisayarla eslesip aralarinda gecis yapilabilir). Ilk okumada,
  /// eski tek-bilgisayarli kurulumdan kalma alanlar varsa bunlari otomatik
  /// olarak tek bir profile donusturur.
  List<RemoteProfile> get remoteProfiles {
    final raw = _prefs.getString(_keyRemoteProfiles);
    if (raw == null) return _migrateLegacyProfile();
    try {
      final list = jsonDecode(raw) as List;
      return list
          .map((e) => RemoteProfile.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  set remoteProfiles(List<RemoteProfile> profiles) {
    _prefs.setString(
      _keyRemoteProfiles,
      jsonEncode(profiles.map((p) => p.toJson()).toList()),
    );
  }

  String? get activeProfileId => _prefs.getString(_keyActiveProfileId);

  set activeProfileId(String? id) {
    if (id == null) {
      _prefs.remove(_keyActiveProfileId);
    } else {
      _prefs.setString(_keyActiveProfileId, id);
    }
  }

  List<RemoteProfile> _migrateLegacyProfile() {
    final legacyIp = _prefs.getString(_keyDesktopIp) ?? '';
    if (legacyIp.isEmpty) return [];
    final profile = RemoteProfile(
      id: 'legacy',
      name: 'Bilgisayar',
      ip: legacyIp,
      port: _prefs.getInt(_keyDesktopPort) ?? 8765,
      pin: _prefs.getString(_keyDesktopPin) ?? '',
      certFingerprint: _prefs.getString(_keyDesktopCertFingerprint) ?? '',
    );
    final profiles = [profile];
    remoteProfiles = profiles;
    activeProfileId = profile.id;
    return profiles;
  }

  /// Varsayilan 'dark' - uygulamanin onceki (tek secenekli) koyu gorunumunu
  /// korur; kullanici acik moda ya da sistem temasina gecebilir.
  ThemeMode get themeMode {
    switch (_prefs.getString(_keyThemeMode)) {
      case 'light':
        return ThemeMode.light;
      case 'system':
        return ThemeMode.system;
      default:
        return ThemeMode.dark;
    }
  }

  set themeMode(ThemeMode mode) {
    final value = switch (mode) {
      ThemeMode.light => 'light',
      ThemeMode.system => 'system',
      ThemeMode.dark => 'dark',
    };
    _prefs.setString(_keyThemeMode, value);
  }

  /// Varsayilan true - masaustu suruumundeki ayni varsayilanla tutarli.
  bool get autoBackupEnabled => _prefs.getBool(_keyAutoBackupEnabled) ?? true;
  set autoBackupEnabled(bool value) =>
      _prefs.setBool(_keyAutoBackupEnabled, value);

  /// En son otomatik yedek alinan zaman (ISO 8601) - hic alinmadiysa null.
  String? get autoBackupLast => _prefs.getString(_keyAutoBackupLast);
  set autoBackupLast(String? value) {
    if (value == null) {
      _prefs.remove(_keyAutoBackupLast);
    } else {
      _prefs.setString(_keyAutoBackupLast, value);
    }
  }

  /// Kullaniciya en son gosterilen "gecen sefer coktu" bildiriminin zaman
  /// damgasi (ISO 8601) - CrashLogService.lastCrashTime() ile karsilastirilir,
  /// boylece ayni cokme her acilista tekrar tekrar bildirilmez (bkz.
  /// HomeScreen._maybeShowCrashNotice).
  String? get lastSeenCrash => _prefs.getString(_keyLastSeenCrash);
  set lastSeenCrash(String? value) {
    if (value == null) {
      _prefs.remove(_keyLastSeenCrash);
    } else {
      _prefs.setString(_keyLastSeenCrash, value);
    }
  }

  /// Ana ekran widget'inin iki butonuna atanan eylemler - varsayilan,
  /// widget'in tanitildigindaki sabit davranisiyla ayni (1. buton sohbet,
  /// 2. buton kumanda).
  WidgetLaunchAction get widgetSlot1Action =>
      WidgetLaunchAction.fromUriValue(_prefs.getString(_keyWidgetSlot1Action)) ??
      WidgetLaunchAction.chat;
  set widgetSlot1Action(WidgetLaunchAction action) =>
      _prefs.setString(_keyWidgetSlot1Action, action.uriValue);

  WidgetLaunchAction get widgetSlot2Action =>
      WidgetLaunchAction.fromUriValue(_prefs.getString(_keyWidgetSlot2Action)) ??
      WidgetLaunchAction.remoteControl;
  set widgetSlot2Action(WidgetLaunchAction action) =>
      _prefs.setString(_keyWidgetSlot2Action, action.uriValue);

  /// Uygulama acilisinda (ve arka plandan donuste) bir PIN isteyip
  /// istemeyecegi - bkz. AppLockScreen/main.dart'taki _AppLockGate. Bu,
  /// Şifreli Not Defteri'nin AES-256-GCM sifrelemesinden FARKLI bir seydir:
  /// burada veri sifrelenmez, yalnizca uygulamanin acilis ekrani bir PIN
  /// arkasina gizlenir (telefonu eline alan biri kilidi bilmeden sohbet/
  /// kumanda panellerini goremez) - PIN de diger ayarlar gibi duz metin
  /// saklanir (bkz. sinif dokumani), bu yuzden fiziksel cihaz erisimine
  /// karsi degil, hizli goz atmaya karsi bir engeldir.
  bool get appLockEnabled => _prefs.getBool(_keyAppLockEnabled) ?? false;
  set appLockEnabled(bool value) => _prefs.setBool(_keyAppLockEnabled, value);

  String? get appLockPin => _prefs.getString(_keyAppLockPin);
  set appLockPin(String? value) {
    if (value == null) {
      _prefs.remove(_keyAppLockPin);
    } else {
      _prefs.setString(_keyAppLockPin, value);
    }
  }

  /// Acikken, [themeMode] tercihini gunun saatine gore kendiliginden
  /// gunduz/gece arasinda degistirir (bkz. resolveAutoThemeMode,
  /// _AiCatAppState) - masaustu suruumundeki ayni ozelligin (auto_theme_
  /// enabled) mobil karsiligi.
  bool get autoThemeEnabled => _prefs.getBool(_keyAutoThemeEnabled) ?? false;
  set autoThemeEnabled(bool value) =>
      _prefs.setBool(_keyAutoThemeEnabled, value);

  String get autoThemeDayStart =>
      _prefs.getString(_keyAutoThemeDayStart) ?? '07:00';
  set autoThemeDayStart(String value) =>
      _prefs.setString(_keyAutoThemeDayStart, value);

  String get autoThemeNightStart =>
      _prefs.getString(_keyAutoThemeNightStart) ?? '19:00';
  set autoThemeNightStart(String value) =>
      _prefs.setString(_keyAutoThemeNightStart, value);

  /// Hatirlatici ve masaustu uyari bildirimlerinde kullanilacak titresim
  /// paterni - bkz. VibrationPatternOption/ReminderService.
  VibrationPatternOption get notificationVibrationPattern =>
      VibrationPatternOption.fromValue(
        _prefs.getString(_keyNotificationVibrationPattern),
      );
  set notificationVibrationPattern(VibrationPatternOption value) =>
      _prefs.setString(_keyNotificationVibrationPattern, value.value);

  /// 'system'/'tr'/'en' - bkz. AppStrings/resolveSupportedLanguageCode.
  /// Varsayilan 'system': cihazin dili desteklenen bir dilse (tr/en) o
  /// kullanilir, degilse Turkce'ye duser.
  String get languageCode => _prefs.getString(_keyLanguageCode) ?? 'system';
  set languageCode(String value) => _prefs.setString(_keyLanguageCode, value);

  /// "Ekranda Gez" kayan balonu acik mi - bkz. ScreenWatchOverlayService.
  /// Uygulama yeniden acildiginda (orn. islem oldurulup yeniden
  /// baslatildiginda) bu true ise ve izin hala verilmisse balon otomatik
  /// yeniden gosterilir (bkz. main.dart _loadSettings).
  bool get screenWatchOverlayEnabled =>
      _prefs.getBool(_keyScreenWatchOverlayEnabled) ?? false;
  set screenWatchOverlayEnabled(bool value) =>
      _prefs.setBool(_keyScreenWatchOverlayEnabled, value);
}
