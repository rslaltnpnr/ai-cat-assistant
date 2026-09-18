import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_overlay_window/flutter_overlay_window.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'l10n/app_strings.dart';
import 'overlay/screen_watch_overlay_app.dart';
import 'screens/app_lock_screen.dart';
import 'screens/home_screen.dart';
import 'services/auto_theme.dart';
import 'services/crash_log_service.dart';
import 'services/screen_watch_overlay_service.dart';
import 'services/settings_service.dart';
import 'theme/app_colors.dart';

/// Masaustu suruumundeki install_crash_handler() ile AYNI amac: beklenmeyen
/// bir hata sessizce kaybolmasin, cihazda kalici bir dosyaya (crash.log)
/// yazilsin ve bir sonraki acilista kullaniciya bildirilsin (bkz.
/// HomeScreen._maybeShowCrashNotice). Iki ayri Flutter hata yolu var:
/// FlutterError.onError widget agacinda (build/layout/paint) yakalanan
/// hatalar icin, platformDispatcher.onError ise bunlarin disinda kalan
/// (orn. bir Future icinde yakalanmamis) hatalar icindir - ikisi birden
/// baglanmazsa bir sinif hata sessizce atlanir.
void _installCrashHandler() {
  FlutterError.onError = (FlutterErrorDetails details) {
    FlutterError.presentError(details);
    CrashLogService.instance.log(
      details.exception,
      details.stack ?? StackTrace.current,
    );
  };
  WidgetsBinding.instance.platformDispatcher.onError = (error, stack) {
    CrashLogService.instance.log(error, stack);
    return true;
  };
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  _installCrashHandler();
  runApp(const AiCatApp());
}

/// "Ekranda Gez" kayan balonu icin ayri giris noktasi - main() ile AYNI
/// process ama TAMAMEN farkli bir Flutter motoru/isolate'ta calisir
/// (flutter_overlay_window paketi bunu bir on plan servisinden baslatir).
/// @pragma olmadan derleyici "kullanilmiyor" diye bu fonksiyonu budar;
/// native taraf ismiyle (overlayMain) cagirdigi icin Dart kodundan hic
/// cagirilmasa bile kalmasi gerekir.
@pragma('vm:entry-point')
void overlayMain() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ScreenWatchOverlayApp());
}

class AiCatApp extends StatefulWidget {
  const AiCatApp({super.key});

  @override
  State<AiCatApp> createState() => _AiCatAppState();
}

class _AiCatAppState extends State<AiCatApp> {
  ThemeMode _themeMode = ThemeMode.dark; // ilk yuklenene kadarki varsayilan
  SettingsService? _settings;
  Timer? _autoThemeTimer;
  StreamSubscription? _overlaySubscription;

  @override
  void initState() {
    super.initState();
    _loadSettings();
    _listenForOverlayCloseRequests();
  }

  @override
  void dispose() {
    _autoThemeTimer?.cancel();
    _overlaySubscription?.cancel();
    super.dispose();
  }

  /// "Ekranda Gez" balonu KENDI (ayri) Flutter motorunda calistigi icin
  /// FlutterOverlayWindow.closeOverlay()'i dogrudan cagiramaz - bu metod
  /// yalnizca ANA uygulamanin motoruna kayitli bir kanal kullanir (bkz.
  /// screen_watch_overlay_app.dart._dismiss). Panelin "Kapat" (X)
  /// butonu bu yuzden shareData() ile buraya bir istek yolluyor; kanalin
  /// gercek sahibi olan biz burada closeOverlay()'i cagirip ayari da
  /// kapatiyoruz - boylece uygulama bir dahaki acilista balonu otomatik
  /// geri getirmez (bkz. _restoreScreenWatchOverlayIfEnabled). Bu koprü
  /// yalnizca ana uygulama calisirken islevlidir; uygulama tamamen
  /// kapatilmisken balonu kapatmanin yolu Ayarlar'daki anahtaridir.
  void _listenForOverlayCloseRequests() {
    _overlaySubscription = FlutterOverlayWindow.overlayListener.listen((event) {
      if (event is Map && event['cmd'] == 'close_overlay') {
        _handleOverlayCloseRequest();
      }
    });
  }

  Future<void> _handleOverlayCloseRequest() async {
    await FlutterOverlayWindow.closeOverlay();
    final prefs = await SharedPreferences.getInstance();
    SettingsService(prefs).screenWatchOverlayEnabled = false;
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    final settings = SettingsService(prefs);
    setState(() {
      _settings = settings;
      _themeMode = settings.themeMode;
    });
    _applyAutoThemeIfEnabled();
    // Masaustu suruumundeki AUTOMATION_TICK_INTERVAL_MS ile ayni fikir:
    // dakikada bir kontrol yeterli, gunun saatine bagli bir gecis icin
    // daha sik kontrol gereksiz.
    _autoThemeTimer = Timer.periodic(
      const Duration(minutes: 1),
      (_) => _applyAutoThemeIfEnabled(),
    );
    _restoreScreenWatchOverlayIfEnabled(settings);
  }

  /// Kullanici daha once "Ekranda Gez"i actiysa (ve izin hala gecerliyse)
  /// balonu otomatik yeniden gosterir - uygulama surecinin oldurulup
  /// yeniden baslatilmasi (telefonu yeniden baslatma, "Son Uygulamalar"
  /// listesinden kapatma) balonu da beraberinde oldurur, bu olmadan
  /// kullanici her seferinde ayarlara girip yeniden acmak zorunda kalirdi.
  Future<void> _restoreScreenWatchOverlayIfEnabled(
    SettingsService settings,
  ) async {
    if (!settings.screenWatchOverlayEnabled) return;
    final overlay = ScreenWatchOverlayService();
    if (!await overlay.isPermissionGranted()) return;
    if (await overlay.isActive()) return;
    final dpr = WidgetsBinding.instance.platformDispatcher.views.first
        .devicePixelRatio;
    await overlay.showBubble(devicePixelRatio: dpr);
  }

  void _applyAutoThemeIfEnabled() {
    final settings = _settings;
    if (settings == null || !settings.autoThemeEnabled) return;
    final desired = resolveAutoThemeMode(
      DateTime.now(),
      dayStart: settings.autoThemeDayStart,
      nightStart: settings.autoThemeNightStart,
    );
    if (desired != _themeMode) {
      settings.themeMode = desired;
      setState(() => _themeMode = desired);
    }
  }

  void _onThemeModeChanged(ThemeMode mode) {
    setState(() => _themeMode = mode);
  }

  void _onLanguageCodeChanged(String languageCode) {
    setState(() => _settings?.languageCode = languageCode);
  }

  /// 'system' iken cihazin dilini kullanir (desteklenmiyorsa Turkce'ye
  /// duser); aksi halde kullanicinin acikca sectigi dili kullanir.
  String _resolveLanguageCode() {
    final stored = _settings?.languageCode ?? 'system';
    if (stored != 'system') return resolveSupportedLanguageCode(stored);
    final deviceLanguage =
        WidgetsBinding.instance.platformDispatcher.locale.languageCode;
    return resolveSupportedLanguageCode(deviceLanguage);
  }

  @override
  Widget build(BuildContext context) {
    final languageCode = _resolveLanguageCode();
    return MaterialApp(
      title: 'AI Kedi Asistani',
      debugShowCheckedModeBanner: false,
      themeMode: _themeMode,
      locale: Locale(languageCode),
      theme: ThemeData(
        brightness: Brightness.light,
        useMaterial3: true,
        scaffoldBackgroundColor: AppColors.light.scaffoldBackground,
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.light.accent,
          brightness: Brightness.light,
        ),
        extensions: const [AppColors.light],
      ),
      darkTheme: ThemeData(
        brightness: Brightness.dark,
        useMaterial3: true,
        scaffoldBackgroundColor: AppColors.dark.scaffoldBackground,
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.dark.accent,
          brightness: Brightness.dark,
        ),
        extensions: const [AppColors.dark],
      ),
      home: _settings == null
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : AppStringsScope(
              strings: AppStrings(languageCode),
              child: _AppLockGate(
                settings: _settings!,
                child: HomeScreen(
                  onThemeModeChanged: _onThemeModeChanged,
                  onLanguageCodeChanged: _onLanguageCodeChanged,
                ),
              ),
            ),
    );
  }
}

/// [settings].appLockEnabled acikken [child]'i bir PIN ekraninin
/// arkasina gizler - ilk acilista VE uygulama arka plana gidip geri
/// donduğunde (bkz. didChangeAppLifecycleState) tekrar kilitlenir, boylece
/// telefonu birakip donen biri kilidi atlayamaz. Kilit kapaliysa (varsayilan)
/// bu widget tamamen seffaftir, [child]'i dogrudan gosterir.
class _AppLockGate extends StatefulWidget {
  final SettingsService settings;
  final Widget child;

  const _AppLockGate({required this.settings, required this.child});

  @override
  State<_AppLockGate> createState() => _AppLockGateState();
}

class _AppLockGateState extends State<_AppLockGate>
    with WidgetsBindingObserver {
  late bool _locked = widget.settings.appLockEnabled &&
      (widget.settings.appLockPin?.isNotEmpty ?? false);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final pin = widget.settings.appLockPin;
    if (widget.settings.appLockEnabled &&
        (pin?.isNotEmpty ?? false) &&
        state == AppLifecycleState.paused) {
      setState(() => _locked = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pin = widget.settings.appLockPin;
    if (!_locked || !widget.settings.appLockEnabled || pin == null || pin.isEmpty) {
      return widget.child;
    }
    return AppLockScreen(
      expectedPin: pin,
      onUnlocked: () => setState(() => _locked = false),
    );
  }
}
