import 'dart:async';
import 'dart:io' show File;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:home_widget/home_widget.dart';
import 'package:receive_sharing_intent/receive_sharing_intent.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/chat_entry.dart';
import '../models/remote_profile.dart';
import '../services/backup_service.dart';
import '../services/command_queue_service.dart';
import '../services/crash_log_service.dart';
import '../services/incoming_file_service.dart';
import '../services/gemini_service.dart';
import '../services/history_service.dart';
import '../services/notification_history_service.dart';
import '../services/reminder_service.dart';
import '../services/remote_control_service.dart';
import '../services/settings_service.dart';
import '../services/widget_service.dart';
import '../theme/app_colors.dart';
import '../widgets/cat_sprite.dart';
import '../widgets/chat_sheet.dart';
import '../widgets/notification_history_sheet.dart';
import '../widgets/reminder_dialog.dart';
import '../widgets/remote_control_sheet.dart';
import '../widgets/roaming_cat.dart';
import '../widgets/secure_notepad_sheet.dart';
import '../widgets/settings_dialog.dart';
import '../widgets/usage_stats_sheet.dart';

class HomeScreen extends StatefulWidget {
  final ValueChanged<ThemeMode> onThemeModeChanged;
  final ValueChanged<String> onLanguageCodeChanged;

  const HomeScreen({
    super.key,
    required this.onThemeModeChanged,
    required this.onLanguageCodeChanged,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const _sleepAfter = Duration(minutes: 3);
  static const _revertAfter = Duration(seconds: 4);
  static const _catSize = 96.0;

  static const _alertPollInterval = Duration(seconds: 45);

  final _gemini = GeminiService();
  final _remoteService = RemoteControlService();
  final _notifications = ReminderService();
  final _notificationHistory = NotificationHistoryService();
  final _incomingFiles = IncomingFileService();
  final _commandQueue = CommandQueueService();

  SettingsService? _settings;
  HistoryService? _history;

  CatState _catState = CatState.norm;
  DateTime _lastActivity = DateTime.now();
  Timer? _sleepCheckTimer;
  Timer? _revertTimer;
  Timer? _alertPollTimer;
  bool _polling = false;
  StreamSubscription<List<SharedMediaFile>>? _shareSub;
  StreamSubscription<Uri?>? _widgetSub;
  String? _pendingSharedUrl;
  String? _pendingRestoreFilePath;
  WidgetLaunchAction? _pendingWidgetAction;

  // Ana ekrandaki aktif profil gostergesi icin - ana ekran widget'ina
  // gonderilenle ayni degerler (bkz. _updateWidgetStatus), ama uygulama
  // icinde de gorunur olmasi icin ayrica burada tutulur. null = henuz
  // yoklanmadi (uygulama daha yeni acildi).
  String? _activeProfileName;
  bool? _connected;

  @override
  void initState() {
    super.initState();
    _init();
    _sleepCheckTimer = Timer.periodic(
      const Duration(seconds: 5),
      (_) => _checkSleep(),
    );
    _initShareIntent();
    _initHomeWidget();
    _alertPollTimer = Timer.periodic(
      _alertPollInterval,
      (_) => _pollForDesktopAlerts(),
    );
  }

  Future<void> _init() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _settings = SettingsService(prefs);
      _history = HistoryService(prefs);
    });
    // Ana ekran widget'indaki baglanti durumu satirinin ilk 45sn'lik
    // periyodik yoklamayi beklemeden hemen tazelenmesi icin.
    _pollForDesktopAlerts();
    // Masaustu suruumundeki gunluk otomatik yedeklemenin mobil karsiligi -
    // burada gercek bir arka plan zamanlayicisi yok, bu yuzden yalnizca
    // uygulama her acildiginda (foreground) firsatci sekilde kontrol
    // edilir; ayarlar > "Otomatik Yedekleme" ile kapatilabilir.
    final settingsForBackup = _settings;
    if (settingsForBackup != null) {
      BackupService().maybeAutoBackup(settingsForBackup);
      _maybeShowCrashNotice(settingsForBackup);
    }
    final pendingUrl = _pendingSharedUrl;
    if (pendingUrl != null) {
      _pendingSharedUrl = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _openRemoteControl(initialUrl: pendingUrl);
      });
    }
    final pendingRestorePath = _pendingRestoreFilePath;
    if (pendingRestorePath != null) {
      _pendingRestoreFilePath = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _confirmAndRestoreBackup(pendingRestorePath);
      });
    }
    final pendingWidgetAction = _pendingWidgetAction;
    if (pendingWidgetAction != null) {
      _pendingWidgetAction = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _handleWidgetAction(pendingWidgetAction);
      });
    }
  }

  /// Masaustu suruumunun crash.log'una benzer sekilde: gecen seferki bir
  /// cokme (varsa) sessizce kaybolmaz, acik bir bildirimle gosterilir.
  /// CrashLogService (main.dart'taki genel hata yakalayicilarla beslenir)
  /// ile SettingsService.lastSeenCrash karsilastirilir - boylece AYNI
  /// cokme her acilista tekrar tekrar bildirilmez.
  Future<void> _maybeShowCrashNotice(SettingsService settings) async {
    final crashTime = await CrashLogService.instance.lastCrashTime();
    if (crashTime == null) return;
    final lastSeen = DateTime.tryParse(settings.lastSeenCrash ?? '');
    if (lastSeen != null && !crashTime.isAfter(lastSeen)) return;
    settings.lastSeenCrash = crashTime.toIso8601String();
    if (!mounted) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Önceki oturumda beklenmeyen bir hata oluştu, günlüğe kaydedildi.',
          ),
          duration: Duration(seconds: 6),
        ),
      );
    });
  }

  /// Ana ekran widget'indaki "Sohbet"/"Kumanda" dugmelerinden biriyle
  /// uygulama acildiysa (soguk baslatma ya da uygulama zaten acikken)
  /// ilgili paneli dogrudan acar.
  void _initHomeWidget() {
    HomeWidget.initiallyLaunchedFromHomeWidget().then(_handleWidgetUri);
    _widgetSub = HomeWidget.widgetClicked.listen(
      _handleWidgetUri,
      onError: (_) {},
    );
  }

  void _handleWidgetUri(Uri? uri) {
    final action = WidgetService.actionFromUri(uri);
    if (action == null) return;
    if (_settings != null && mounted) {
      _handleWidgetAction(action);
    } else {
      _pendingWidgetAction = action;
    }
  }

  void _handleWidgetAction(WidgetLaunchAction action) {
    switch (action) {
      case WidgetLaunchAction.chat:
        _openChat();
        break;
      case WidgetLaunchAction.remoteControl:
        _openRemoteControl();
        break;
      case WidgetLaunchAction.reminder:
        _openReminderDialog();
        break;
      case WidgetLaunchAction.secureNotepad:
        _openSecureNotepad();
        break;
    }
  }

  /// Baska bir uygulamadan (orn. YouTube) "Paylas" ile bir link
  /// gonderildiginde "Bilgisayarda Ac" panelini linkle dolu acar.
  void _initShareIntent() {
    _shareSub = ReceiveSharingIntent.instance.getMediaStream().listen(
      _handleSharedFiles,
      onError: (_) {},
    );
    ReceiveSharingIntent.instance.getInitialMedia().then((files) {
      _handleSharedFiles(files);
      ReceiveSharingIntent.instance.reset();
    });
  }

  void _handleSharedFiles(List<SharedMediaFile> files) {
    if (files.isEmpty) return;

    final backupFile = files.cast<SharedMediaFile?>().firstWhere(
      (f) =>
          f!.mimeType == 'application/json' ||
          f.path.toLowerCase().endsWith('.json'),
      orElse: () => null,
    );
    if (backupFile != null) {
      if (_settings != null && mounted) {
        _confirmAndRestoreBackup(backupFile.path);
      } else {
        _pendingRestoreFilePath = backupFile.path;
      }
      return;
    }

    final shared = files.firstWhere(
      (f) => f.type == SharedMediaType.text || f.type == SharedMediaType.url,
      orElse: () => files.first,
    );
    final text = shared.path.trim();
    if (text.isEmpty) return;
    final match = RegExp(r'https?://\S+').firstMatch(text);
    final url = match?.group(0) ?? text;
    if (_settings != null && mounted) {
      _openRemoteControl(initialUrl: url);
    } else {
      _pendingSharedUrl = url;
    }
  }

  /// Bir dosya yoneticisinden "Paylas" ile gonderilen bir yedek (.json)
  /// dosyasini onay aldiktan sonra geri yukler; ayarlar, uzaktan kumanda
  /// profilleri ve sohbet gecmisi (hepsi ayni SharedPreferences deposunda)
  /// yedekteki degerlerle degistirilir.
  Future<void> _confirmAndRestoreBackup(String filePath) async {
    _registerActivity();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Yedekten Geri Yükle'),
        content: const Text(
          'Bu yedek dosyası; ayarlarınızın, uzaktan kumanda profillerinizin '
          've sohbet geçmişinizin üzerine yazılacak. Devam etmek istiyor '
          'musunuz?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('İptal'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Geri Yükle'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    try {
      final content = await File(filePath).readAsString();
      final count = await BackupService().importBackup(content);
      final prefs = await SharedPreferences.getInstance();
      if (!mounted) return;
      setState(() {
        _settings = SettingsService(prefs);
        _history = HistoryService(prefs);
      });
      widget.onThemeModeChanged(_settings!.themeMode);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Yedek geri yüklendi ($count ayar).')),
      );
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Geri yükleme başarısız: $exc')),
      );
    }
  }

  @override
  void dispose() {
    _sleepCheckTimer?.cancel();
    _revertTimer?.cancel();
    _alertPollTimer?.cancel();
    _shareSub?.cancel();
    _widgetSub?.cancel();
    super.dispose();
  }

  /// Eslesik (aktif) bilgisayarda bir hata/uyari olustuysa yerel bildirim
  /// olarak gosterir. Yalnizca uygulama acikken calisir (bulut/Firebase
  /// push gerektirmez) - bilgisayara ulasilamazsa sessizce yok sayar,
  /// boylece bilgisayar kapaliyken/ag disindayken kullaniciyi rahatsiz
  /// eden tekrarlayan hatalar gostermez.
  Future<void> _pollForDesktopAlerts() async {
    if (_polling) return;
    final settings = _settings;
    if (settings == null) return;
    final profiles = settings.remoteProfiles;
    if (profiles.isEmpty) {
      await _updateWidgetStatus(profileName: null, connected: false);
      return;
    }
    final activeId = settings.activeProfileId;
    final profile = profiles.firstWhere(
      (p) => p.id == activeId,
      orElse: () => profiles.first,
    );
    if (profile.ip.isEmpty || profile.pin.isEmpty) {
      await _updateWidgetStatus(profileName: profile.name, connected: false);
      return;
    }

    _polling = true;
    try {
      final result = await _remoteService.fetchAlerts(
        ip: profile.ip,
        port: profile.port,
        pin: profile.pin,
        pinnedFingerprint: profile.certFingerprint,
        sinceId: profile.lastAlertId,
      );
      var maxId = profile.lastAlertId;
      for (final alert in result.alerts) {
        final id = alert['id'] as int? ?? maxId;
        if (id > maxId) maxId = id;
        final message = alert['message'] as String? ?? '';
        if (message.isEmpty) continue;
        final alertTitle = '${profile.name} - Uyarı';
        await _notifications.showAlert(title: alertTitle, message: message);
        await _notificationHistory.add(title: alertTitle, message: message);
      }
      final updatedProfile = profile.copyWith(
        certFingerprint: result.fingerprint,
        lastAlertId: maxId,
      );
      settings.remoteProfiles = profiles
          .map((p) => p.id == profile.id ? updatedProfile : p)
          .toList();
      await _updateWidgetStatus(profileName: profile.name, connected: true);
      await _flushQueuedCommands(updatedProfile);
      await _checkPendingFiles(updatedProfile);
    } catch (_) {
      // bilgisayar kapali/ag disinda olabilir - sessizce yok say
      await _updateWidgetStatus(profileName: profile.name, connected: false);
    } finally {
      _polling = false;
    }
  }

  /// [profile]'a baglanti kurulabildigi her onaylandiginda (basarili bir
  /// /alerts yoklamasi sonrasi) cagrilir - bu profil icin kuyrukta bekleyen
  /// varsa (bkz. CommandQueueService, RemoteControlSheet._send) gonderilmeye
  /// calisilir. Basariyla gonderilenler icin yerel bildirim gosterilir,
  /// boylece uygulamayi acmadan da "kuyruktaki linkiniz gonderildi"
  /// bilgisini alirsiniz.
  Future<void> _flushQueuedCommands(RemoteProfile profile) async {
    final settings = _settings;
    if (settings == null) return;
    final sentCount = await _commandQueue.flushFor(
      profile: profile,
      sendOpenUrl: _remoteService.openUrl,
      onFingerprintUpdate: (fingerprint) {
        settings.remoteProfiles = settings.remoteProfiles
            .map(
              (p) => p.id == profile.id
                  ? p.copyWith(certFingerprint: fingerprint)
                  : p,
            )
            .toList();
      },
    );
    if (sentCount == 0) return;
    final title = '${profile.name} - Kuyruklu Komutlar';
    final message = sentCount == 1
        ? 'Bekleyen 1 bağlantı gönderildi.'
        : 'Bekleyen $sentCount bağlantı gönderildi.';
    await _notifications.showAlert(title: title, message: message);
    await _notificationHistory.add(title: title, message: message);
  }

  /// Bilgisayarda "Kediyle Gönder" (sag tik menusu) ile kuyruga alinmis
  /// dosya var mi diye kontrol eder - varsa cihaza kaydedip (bkz.
  /// IncomingFileService) yerel bir bildirim gosterir. Her basarili
  /// /alerts yoklamasinin hemen ardindan (_flushQueuedCommands ile ayni
  /// yerde) cagrilir, boylece ayrica bir zamanlayiciya gerek kalmaz.
  Future<void> _checkPendingFiles(RemoteProfile profile) async {
    try {
      final result = await _remoteService.fetchPendingFiles(
        ip: profile.ip,
        port: profile.port,
        pin: profile.pin,
        pinnedFingerprint: profile.certFingerprint,
      );
      if (result.files.isEmpty) return;
      final saved = await _incomingFiles.saveAll(result.files);
      if (saved.isEmpty) return;
      final title = '${profile.name} - Kediyle Gönderildi';
      final message = saved.length == 1
          ? '"${saved.first}" bilgisayardan geldi.'
          : '${saved.length} dosya bilgisayardan geldi.';
      await _notifications.showAlert(title: title, message: message);
      await _notificationHistory.add(title: title, message: message);
    } catch (_) {
      // bilgisayar erisilemezse ya da ozellik henuz desteklenmiyorsa
      // (eski masaustu suruumu) sessizce yoksay - bu bir sonraki
      // yoklamada tekrar denenir.
    }
  }

  /// Ana ekran widget'indaki baglanti durumu satirini gunceller. Widget
  /// dinamik veri gostermedigi icin (updatePeriodMillis=0) bu cagri
  /// olmadan hicbir zaman yenilenmez - o yuzden her poll sonucunda
  /// (basarili/basarisiz) ve profil yoksa/eksikse de cagrilir.
  Future<void> _updateWidgetStatus({
    required String? profileName,
    required bool connected,
  }) async {
    if (mounted) {
      setState(() {
        _activeProfileName = profileName;
        _connected = connected;
      });
    }
    try {
      await HomeWidget.saveWidgetData<String>(
        'widget_profile_name',
        profileName,
      );
      await HomeWidget.saveWidgetData<String>(
        'widget_connection_status',
        connected ? 'connected' : 'disconnected',
      );
      final settings = _settings;
      if (settings != null) {
        await HomeWidget.saveWidgetData<String>(
          'widget_slot1_action',
          settings.widgetSlot1Action.uriValue,
        );
        await HomeWidget.saveWidgetData<String>(
          'widget_slot2_action',
          settings.widgetSlot2Action.uriValue,
        );
      }
      await HomeWidget.updateWidget(androidName: 'CatWidgetProvider');
    } catch (_) {
      // widget ana ekrana eklenmemis olabilir - onemli degil
    }
  }

  void _registerActivity() {
    _lastActivity = DateTime.now();
    if (_catState == CatState.zzz) {
      setState(() => _catState = CatState.norm);
    }
  }

  void _checkSleep() {
    if (_catState == CatState.stern || _catState == CatState.zzz) return;
    if (DateTime.now().difference(_lastActivity) >= _sleepAfter) {
      setState(() => _catState = CatState.zzz);
    }
  }

  void _scheduleRevert() {
    _revertTimer?.cancel();
    _revertTimer = Timer(_revertAfter, () {
      if (mounted) setState(() => _catState = CatState.norm);
    });
  }

  void _openChat() {
    _registerActivity();
    final settings = _settings;
    final history = _history;
    if (settings == null || history == null) return;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ChatSheet(
        settings: settings,
        history: history,
        onAsk: _handleQuestion,
      ),
    );
  }

  void _openSettings() {
    _registerActivity();
    final settings = _settings;
    if (settings == null) return;
    showDialog(
      context: context,
      builder: (_) => SettingsDialog(
        settings: settings,
        onThemeModeChanged: widget.onThemeModeChanged,
        onLanguageCodeChanged: widget.onLanguageCodeChanged,
      ),
    ).then(
      (_) => setState(() {}),
    ); // isim degismis olabilir, baslik guncellensin
  }

  void _openRemoteControl({String? initialUrl}) {
    _registerActivity();
    final settings = _settings;
    if (settings == null) return;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) =>
          RemoteControlSheet(settings: settings, initialUrl: initialUrl),
    ).then((_) {
      // Panelde profil degistirilmis/duzenlenmis olabilir - ana ekrandaki
      // gostergeyi hemen tazele, 45sn'lik periyodik yoklamayi bekleme.
      _pollForDesktopAlerts();
    });
  }

  /// Ana ekrandaki aktif profil gostergesine dokununca acilan hizli gecis
  /// menusu - RemoteControlSheet'i tamamen acmadan (baglanti bilgilerini
  /// duzenlemeden) profiller arasinda gecis yapmayi saglar.
  void _quickSwitchProfile(String profileId) {
    _registerActivity();
    final settings = _settings;
    if (settings == null || profileId == settings.activeProfileId) return;
    settings.activeProfileId = profileId;
    setState(() => _connected = null); // yeni profil icin durum bilinmiyor
    _pollForDesktopAlerts();
  }

  void _openNotificationHistory() {
    _registerActivity();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const NotificationHistorySheet(),
    );
  }

  void _openSecureNotepad() {
    _registerActivity();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const SecureNotepadSheet(),
    );
  }

  void _openUsageStats() {
    _registerActivity();
    final settings = _settings;
    final history = _history;
    if (settings == null || history == null) return;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => UsageStatsSheet(settings: settings, history: history),
    );
  }

  Future<void> _openReminderDialog() async {
    _registerActivity();
    final minutes = await showDialog<int>(
      context: context,
      builder: (_) => const ReminderDialog(),
    );
    if (minutes != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$minutes dakika sonra hatırlatılacak.')),
      );
    }
  }

  Future<String> _handleQuestion(String question, Uint8List? imageBytes) async {
    final settings = _settings!;
    final history = _history!;
    final apiKey = settings.apiKey;
    if (apiKey.isEmpty) {
      throw Exception(
        'Once ayarlardan Gemini API Key girin (kediyi uzun basip acabilirsiniz).',
      );
    }

    _registerActivity();
    _revertTimer?.cancel();
    setState(() => _catState = CatState.stern);

    try {
      final answer = await _gemini.ask(
        apiKey: apiKey,
        modelName: settings.modelName,
        characterName: settings.characterName,
        question: question,
        imageBytes: imageBytes,
      );
      history.add(
        ChatEntry(
          time: DateTime.now(),
          question: question,
          answer: answer,
          isError: false,
        ),
      );
      if (mounted) setState(() => _catState = CatState.smile);
      _scheduleRevert();
      return answer;
    } catch (exc) {
      final message = exc.toString();
      history.add(
        ChatEntry(
          time: DateTime.now(),
          question: question,
          answer: message,
          isError: true,
        ),
      );
      if (mounted) setState(() => _catState = CatState.fear);
      _scheduleRevert();
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_settings == null || _history == null) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return Stack(
              children: [
                Positioned.fill(
                  child: GestureDetector(
                    behavior: HitTestBehavior.translucent,
                    onTap: _registerActivity,
                  ),
                ),
                RoamingCat(
                  bounds: Size(constraints.maxWidth, constraints.maxHeight),
                  state: _catState,
                  size: _catSize,
                  onTap: _openChat,
                  onLongPress: _openSettings,
                ),
                Positioned(
                  top: 8,
                  right: 8,
                  child: IconButton(
                    icon: Icon(Icons.settings, color: context.colors.textMuted),
                    onPressed: _openSettings,
                  ),
                ),
                Positioned(
                  top: 8,
                  right: 48,
                  child: IconButton(
                    icon: Icon(
                      Icons.desktop_windows,
                      color: context.colors.textMuted,
                    ),
                    tooltip: 'Bilgisayarı Kumanda Et',
                    onPressed: _openRemoteControl,
                  ),
                ),
                Positioned(
                  top: 8,
                  right: 88,
                  child: IconButton(
                    icon: Icon(
                      Icons.alarm_add,
                      color: context.colors.textMuted,
                    ),
                    tooltip: 'Hatırlatıcı Kur',
                    onPressed: _openReminderDialog,
                  ),
                ),
                Positioned(
                  top: 8,
                  right: 128,
                  child: IconButton(
                    icon: Icon(
                      Icons.notifications_outlined,
                      color: context.colors.textMuted,
                    ),
                    tooltip: 'Bildirim Geçmişi',
                    onPressed: _openNotificationHistory,
                  ),
                ),
                Positioned(
                  top: 8,
                  right: 168,
                  child: IconButton(
                    icon: Icon(
                      Icons.lock_outline,
                      color: context.colors.textMuted,
                    ),
                    tooltip: 'Şifreli Not Defteri',
                    onPressed: _openSecureNotepad,
                  ),
                ),
                Positioned(
                  top: 8,
                  right: 208,
                  child: IconButton(
                    icon: Icon(
                      Icons.bar_chart,
                      color: context.colors.textMuted,
                    ),
                    tooltip: 'Kullanım İstatistikleri',
                    onPressed: _openUsageStats,
                  ),
                ),
                Positioned(
                  top: 12,
                  left: 16,
                  child: Text(
                    _settings!.characterName,
                    style: TextStyle(color: context.colors.textMuted, fontSize: 13),
                  ),
                ),
                Positioned(top: 32, left: 16, child: _buildProfileIndicator()),
              ],
            );
          },
        ),
      ),
    );
  }

  /// Aktif profili (varsa baglanti durumuyla birlikte) gosteren, dokununca
  /// hizli profil gecis menusu acan kucuk bir gosterge. Hic profil yoksa
  /// dogrudan "Bilgisayarı Kumanda Et" panelini acar (ilk kurulum).
  Widget _buildProfileIndicator() {
    final settings = _settings;
    if (settings == null) return const SizedBox.shrink();
    final profiles = settings.remoteProfiles;
    if (profiles.isEmpty) {
      return _ProfileChip(
        label: 'Bilgisayar eklenmedi',
        dotColor: Colors.transparent,
        onTap: _openRemoteControl,
      );
    }

    final activeId = settings.activeProfileId;
    final active = profiles.firstWhere(
      (p) => p.id == activeId,
      orElse: () => profiles.first,
    );
    final dotColor = switch (_connected) {
      true => const Color(0xFF8CFF8C),
      false => const Color(0xFF9A9AA5),
      null => Colors.transparent,
    };

    const manageSentinel = '__manage__';
    return PopupMenuButton<String>(
      tooltip: 'Bilgisayar değiştir',
      onSelected: (value) {
        if (value == manageSentinel) {
          _openRemoteControl();
        } else {
          _quickSwitchProfile(value);
        }
      },
      itemBuilder: (context) => [
        for (final RemoteProfile profile in profiles)
          PopupMenuItem(
            value: profile.id,
            child: Row(
              children: [
                if (profile.id == active.id)
                  const Icon(Icons.check, size: 16)
                else
                  const SizedBox(width: 16),
                const SizedBox(width: 8),
                Text(profile.name),
              ],
            ),
          ),
        const PopupMenuDivider(),
        const PopupMenuItem(
          value: manageSentinel,
          child: Text('Bilgisayarları Yönet...'),
        ),
      ],
      child: _ProfileChip(
        label: _activeProfileName ?? active.name,
        dotColor: dotColor,
      ),
    );
  }
}

class _ProfileChip extends StatelessWidget {
  final String label;
  final Color dotColor;
  final VoidCallback? onTap;

  const _ProfileChip({required this.label, required this.dotColor, this.onTap});

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final chip = Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: colors.panelTranslucent,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(color: colors.textMuted, fontSize: 11),
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
    return onTap == null ? chip : GestureDetector(onTap: onTap, child: chip);
  }
}
