import 'package:flutter/material.dart';
import 'package:home_widget/home_widget.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/app_strings.dart';
import '../services/app_lock.dart';
import '../services/auto_theme.dart';
import '../services/backup_service.dart';
import '../services/screen_watch_overlay_service.dart';
import '../services/settings_service.dart';
import '../services/update_service.dart';
import '../services/vibration_pattern.dart';
import '../services/widget_service.dart';
import '../theme/app_colors.dart';
import 'about_dialog.dart';

/// Kediyi uzun basinca acilan ayarlar penceresi (masaustu surumundeki
/// sag tik menusunun "Kediye Isim Ver" + "Gemini API Key Ayarlari"
/// karsiligi).
class SettingsDialog extends StatefulWidget {
  final SettingsService settings;
  final ValueChanged<ThemeMode> onThemeModeChanged;
  final ValueChanged<String> onLanguageCodeChanged;

  const SettingsDialog({
    super.key,
    required this.settings,
    required this.onThemeModeChanged,
    required this.onLanguageCodeChanged,
  });

  @override
  State<SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<SettingsDialog> {
  late final TextEditingController _nameController;
  late final TextEditingController _apiKeyController;
  late ThemeMode _themeMode;
  late bool _autoBackupEnabled;
  late WidgetLaunchAction _widgetSlot1Action;
  late WidgetLaunchAction _widgetSlot2Action;
  late bool _appLockEnabled;
  late bool _autoThemeEnabled;
  late final TextEditingController _autoThemeDayStartController;
  late final TextEditingController _autoThemeNightStartController;
  late VibrationPatternOption _vibrationPattern;
  late String _languageCode;
  late bool _screenWatchOverlayEnabled;
  final _screenWatchOverlayService = ScreenWatchOverlayService();
  bool _obscureKey = true;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(
      text: widget.settings.characterName,
    );
    _apiKeyController = TextEditingController(text: widget.settings.apiKey);
    _themeMode = widget.settings.themeMode;
    _autoBackupEnabled = widget.settings.autoBackupEnabled;
    _widgetSlot1Action = widget.settings.widgetSlot1Action;
    _widgetSlot2Action = widget.settings.widgetSlot2Action;
    _appLockEnabled = widget.settings.appLockEnabled;
    _autoThemeEnabled = widget.settings.autoThemeEnabled;
    _autoThemeDayStartController =
        TextEditingController(text: widget.settings.autoThemeDayStart);
    _autoThemeNightStartController =
        TextEditingController(text: widget.settings.autoThemeNightStart);
    _vibrationPattern = widget.settings.notificationVibrationPattern;
    _languageCode = widget.settings.languageCode;
    _screenWatchOverlayEnabled = widget.settings.screenWatchOverlayEnabled;
  }

  @override
  void dispose() {
    _nameController.dispose();
    _apiKeyController.dispose();
    _autoThemeDayStartController.dispose();
    _autoThemeNightStartController.dispose();
    super.dispose();
  }

  void _save() {
    final name = _nameController.text.trim();
    if (name.isNotEmpty) {
      widget.settings.characterName = name;
    }
    widget.settings.apiKey = _apiKeyController.text.trim();
    widget.settings.themeMode = _themeMode;
    widget.settings.autoBackupEnabled = _autoBackupEnabled;
    widget.settings.autoThemeEnabled = _autoThemeEnabled;
    final dayStart = parseHhMm(_autoThemeDayStartController.text);
    if (dayStart != null) widget.settings.autoThemeDayStart = dayStart;
    final nightStart = parseHhMm(_autoThemeNightStartController.text);
    if (nightStart != null) widget.settings.autoThemeNightStart = nightStart;
    widget.settings.notificationVibrationPattern = _vibrationPattern;
    widget.settings.languageCode = _languageCode;
    widget.onLanguageCodeChanged(_languageCode);
    widget.settings.widgetSlot1Action = _widgetSlot1Action;
    widget.settings.widgetSlot2Action = _widgetSlot2Action;
    HomeWidget.saveWidgetData<String>(
      'widget_slot1_action',
      _widgetSlot1Action.uriValue,
    );
    HomeWidget.saveWidgetData<String>(
      'widget_slot2_action',
      _widgetSlot2Action.uriValue,
    );
    HomeWidget.updateWidget(androidName: 'CatWidgetProvider');
    widget.onThemeModeChanged(_themeMode);
    Navigator.of(context).pop();
  }

  /// [enable] true: yeni bir PIN belirlemesi istenir, gecerli bir PIN
  /// girilip onaylanmadan kilit acilmaz (iptal edilirse anahtar hic
  /// degismez). false: kilidi kapatir ve saklanan PIN'i siler - boylece
  /// tekrar acmak her zaman yeni bir PIN gerektirir, eski PIN'i "hatirlama"
  /// riski olmaz.
  Future<void> _toggleAppLock(bool enable) async {
    if (!enable) {
      widget.settings.appLockEnabled = false;
      widget.settings.appLockPin = null;
      setState(() => _appLockEnabled = false);
      return;
    }
    final pin = await _promptForNewPin();
    if (pin == null) return;
    widget.settings.appLockPin = pin;
    widget.settings.appLockEnabled = true;
    setState(() => _appLockEnabled = true);
  }

  Future<String?> _promptForNewPin() async {
    final pinController = TextEditingController();
    final confirmController = TextEditingController();
    String? error;
    return showDialog<String>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('Uygulama Kilidi PIN\'i'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: pinController,
                obscureText: true,
                keyboardType: TextInputType.number,
                autofocus: true,
                decoration: const InputDecoration(labelText: '4-6 haneli PIN'),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: confirmController,
                obscureText: true,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'PIN\'i tekrar yaz'),
              ),
              if (error != null) ...[
                const SizedBox(height: 8),
                Text(error!, style: const TextStyle(color: Colors.red)),
              ],
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('İptal'),
            ),
            ElevatedButton(
              onPressed: () {
                final pin = pinController.text;
                if (!isValidAppLockPin(pin)) {
                  setDialogState(() => error = 'PIN 4-6 haneli rakam olmalı.');
                  return;
                }
                if (pin != confirmController.text) {
                  setDialogState(() => error = 'PIN\'ler eşleşmiyor.');
                  return;
                }
                Navigator.of(dialogContext).pop(pin);
              },
              child: const Text('Kaydet'),
            ),
          ],
        ),
      ),
    );
  }

  /// [enable] true: sistem izni yoksa Android'in "diger uygulamalarin
  /// uzerinde goster" ayar sayfasini acar ve kullanicinin izin vermesini
  /// bekler; izin verilmezse balon acilmaz ve ayar kapali kalir. false:
  /// balonu kapatir. Balonun kendisi (bkz. ScreenWatchOverlayApp) ayri bir
  /// Flutter motorunda calisir, bu yuzden burada yalnizca goster/kapat
  /// cagirilir - ekran boyutu icin bir BuildContext gerekir, o da bu
  /// SettingsDialog'un context'inden alinir.
  Future<void> _toggleScreenWatchOverlay(bool enable) async {
    if (!enable) {
      widget.settings.screenWatchOverlayEnabled = false;
      await _screenWatchOverlayService.close();
      setState(() => _screenWatchOverlayEnabled = false);
      return;
    }
    var granted = await _screenWatchOverlayService.isPermissionGranted();
    if (!granted) {
      granted = await _screenWatchOverlayService.requestPermission();
    }
    if (!granted) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Ekranda gezinmesi icin "diger uygulamalarin uzerinde goster" '
            'izni gerekiyor.',
          ),
        ),
      );
      return;
    }
    if (!mounted) return;
    final dpr = MediaQuery.of(context).devicePixelRatio;
    await _screenWatchOverlayService.showBubble(devicePixelRatio: dpr);
    widget.settings.screenWatchOverlayEnabled = true;
    setState(() => _screenWatchOverlayEnabled = true);
  }

  Future<void> _shareBackup() async {
    try {
      await BackupService().shareBackup();
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Yedek oluşturulamadı: $exc')),
      );
    }
  }

  Future<void> _checkForUpdate() async {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(
      const SnackBar(content: Text('Güncellemeler kontrol ediliyor...')),
    );
    final info = await UpdateService().checkForUpdate();
    if (!mounted) return;
    if (info == null) {
      messenger.showSnackBar(
        const SnackBar(content: Text('Güncel sürümü kullanıyorsunuz.')),
      );
      return;
    }
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Yeni Sürüm Var'),
        content: Text('${info.tag} sürümü yayınlandı.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Kapat'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              launchUrl(
                Uri.parse(info.apkDownloadUrl ?? info.htmlUrl),
                mode: LaunchMode.externalApplication,
              );
            },
            child: const Text('İndir'),
          ),
        ],
      ),
    );
  }

  Future<void> _addHomeWidget() async {
    final messenger = ScaffoldMessenger.of(context);
    final requested = await WidgetService.requestPinWidget();
    if (!mounted) return;
    if (!requested) {
      messenger.showSnackBar(
        const SnackBar(
          content: Text(
            'Cihazınız/başlatıcınız widget eklemeyi desteklemiyor. Ana '
            'ekranda boş bir alana uzun basıp "Widget\'lar" menüsünden '
            'elle ekleyebilirsiniz.',
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final strings = AppStringsScope.of(context);
    return AlertDialog(
      backgroundColor: colors.panel,
      title: Text(strings.t('settings_title'),
          style: TextStyle(color: colors.textPrimary)),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _nameController,
              style: TextStyle(color: colors.textPrimary),
              decoration: InputDecoration(
                labelText: strings.t('settings_character_name'),
                labelStyle: TextStyle(color: colors.textSecondary),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _apiKeyController,
              obscureText: _obscureKey,
              style: TextStyle(color: colors.textPrimary),
              decoration: InputDecoration(
                labelText: strings.t('settings_api_key'),
                labelStyle: TextStyle(color: colors.textSecondary),
                suffixIcon: IconButton(
                  icon: Icon(
                    _obscureKey ? Icons.visibility : Icons.visibility_off,
                    color: colors.textSecondary,
                  ),
                  onPressed: () => setState(() => _obscureKey = !_obscureKey),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(strings.t('settings_theme'),
                  style: TextStyle(color: colors.textSecondary, fontSize: 12)),
            ),
            const SizedBox(height: 6),
            SegmentedButton<ThemeMode>(
              segments: [
                ButtonSegment(
                  value: ThemeMode.system,
                  label: Text(strings.t('settings_theme_system')),
                  icon: const Icon(Icons.brightness_auto),
                ),
                ButtonSegment(
                  value: ThemeMode.light,
                  label: Text(strings.t('settings_theme_light')),
                  icon: const Icon(Icons.light_mode),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  label: Text(strings.t('settings_theme_dark')),
                  icon: const Icon(Icons.dark_mode),
                ),
              ],
              selected: {_themeMode},
              onSelectionChanged: (selection) =>
                  setState(() => _themeMode = selection.first),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(strings.t('settings_language'),
                  style: TextStyle(color: colors.textSecondary, fontSize: 12)),
            ),
            const SizedBox(height: 6),
            SegmentedButton<String>(
              segments: [
                ButtonSegment(
                  value: 'system',
                  label: Text(strings.t('settings_language_system')),
                ),
                ButtonSegment(
                  value: 'tr',
                  label: Text(strings.t('settings_language_tr')),
                ),
                ButtonSegment(
                  value: 'en',
                  label: Text(strings.t('settings_language_en')),
                ),
              ],
              selected: {_languageCode},
              onSelectionChanged: (selection) =>
                  setState(() => _languageCode = selection.first),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(
                'Otomatik Gece/Gündüz Teması',
                style: TextStyle(color: colors.textPrimary, fontSize: 13),
              ),
              subtitle: Text(
                'Yukarıdaki seçimi yok sayıp temayı gunun saatine göre '
                'kendiliğinden değiştirir.',
                style: TextStyle(color: colors.textMuted, fontSize: 11),
              ),
              value: _autoThemeEnabled,
              onChanged: (value) => setState(() => _autoThemeEnabled = value),
            ),
            if (_autoThemeEnabled)
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _autoThemeDayStartController,
                      decoration: const InputDecoration(
                        labelText: 'Gündüz başlangıcı (SS:DD)',
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: TextField(
                      controller: _autoThemeNightStartController,
                      decoration: const InputDecoration(
                        labelText: 'Gece başlangıcı (SS:DD)',
                      ),
                    ),
                  ),
                ],
              ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Yedekleme',
                style: TextStyle(color: colors.textSecondary, fontSize: 12),
              ),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _shareBackup,
                    icon: const Icon(Icons.upload_file, size: 18),
                    label: const Text('Yedek Al'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _checkForUpdate,
                    icon: const Icon(Icons.system_update, size: 18),
                    label: const Text('Güncelleme Kontrol'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Geri yüklemek için yedek dosyasını bir dosya yöneticisinden '
                'bu uygulamaya "Paylaş" ile gönderin.',
                style: TextStyle(color: colors.textMuted, fontSize: 11),
              ),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(
                'Otomatik Yedekleme (Günlük)',
                style: TextStyle(color: colors.textPrimary, fontSize: 13),
              ),
              subtitle: Text(
                'Uygulama açıldığında, günde en fazla bir kez sessizce '
                'cihaza kaydedilir (paylaşım gerekmez).',
                style: TextStyle(color: colors.textMuted, fontSize: 11),
              ),
              value: _autoBackupEnabled,
              onChanged: (value) => setState(() => _autoBackupEnabled = value),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(
                'Uygulama Kilidi',
                style: TextStyle(color: colors.textPrimary, fontSize: 13),
              ),
              subtitle: Text(
                'Açılışta ve arka plandan dönüşte bir PIN sorulur.',
                style: TextStyle(color: colors.textMuted, fontSize: 11),
              ),
              value: _appLockEnabled,
              onChanged: (value) => _toggleAppLock(value),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: Text(
                'Ekranda Gez',
                style: TextStyle(color: colors.textPrimary, fontSize: 13),
              ),
              subtitle: Text(
                'Uygulama kapalıyken bile ekranda gezinen, dokununca '
                'bilgisayarın ekranını gösterip soru sorabildiğiniz bir '
                'balon açar. "Diğer uygulamaların üzerinde göster" izni '
                'ister.',
                style: TextStyle(color: colors.textMuted, fontSize: 11),
              ),
              value: _screenWatchOverlayEnabled,
              onChanged: (value) => _toggleScreenWatchOverlay(value),
            ),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Bildirim Titreşim Paterni',
                style: TextStyle(color: colors.textSecondary, fontSize: 12),
              ),
            ),
            const SizedBox(height: 6),
            DropdownButtonFormField<VibrationPatternOption>(
              initialValue: _vibrationPattern,
              items: VibrationPatternOption.values
                  .map(
                    (option) => DropdownMenuItem(
                      value: option,
                      child: Text(option.label),
                    ),
                  )
                  .toList(),
              onChanged: (value) {
                if (value != null) setState(() => _vibrationPattern = value);
              },
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Ana Ekran Widget\'ı',
                style: TextStyle(color: colors.textSecondary, fontSize: 12),
              ),
            ),
            const SizedBox(height: 6),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _addHomeWidget,
                icon: const Icon(Icons.widgets_outlined, size: 18),
                label: const Text('Ana Ekrana Widget Ekle'),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: _WidgetActionDropdown(
                    label: '1. Buton',
                    value: _widgetSlot1Action,
                    onChanged: (value) =>
                        setState(() => _widgetSlot1Action = value),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _WidgetActionDropdown(
                    label: '2. Buton',
                    value: _widgetSlot2Action,
                    onChanged: (value) =>
                        setState(() => _widgetSlot2Action = value),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          // HomeScreen._openSettings() bu ozel sonucu görüp sihirbazi
          // acar - dogrudan burada acmak, bu pencereyi kapatan
          // Navigator.pop() ile ayni anda calisirsa context gecersiz
          // kalabilir, bu yuzden karari cagirana birakiyoruz.
          onPressed: () => Navigator.of(context).pop('restart_onboarding'),
          child: const Text('Kurulum Sihirbazı'),
        ),
        TextButton(
          onPressed: () => showDialog(
            context: context,
            builder: (_) => const AboutAppDialog(),
          ),
          child: Text(strings.t('settings_about')),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(strings.t('settings_cancel')),
        ),
        ElevatedButton(onPressed: _save, child: Text(strings.t('settings_save'))),
      ],
    );
  }
}

/// Ana ekran widget'inin iki butonundan biri icin eylem secici
/// (Sohbet/Kumanda/Hatırlatıcı). SettingsDialog disinda kullanilmadigi
/// icin ozel (private) tutuluyor.
class _WidgetActionDropdown extends StatelessWidget {
  final String label;
  final WidgetLaunchAction value;
  final ValueChanged<WidgetLaunchAction> onChanged;

  const _WidgetActionDropdown({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return DropdownButtonFormField<WidgetLaunchAction>(
      initialValue: value,
      isExpanded: true,
      decoration: InputDecoration(
        labelText: label,
        labelStyle: TextStyle(color: colors.textMuted, fontSize: 11),
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 8,
          vertical: 4,
        ),
      ),
      style: TextStyle(color: colors.textPrimary, fontSize: 12),
      items: WidgetLaunchAction.values
          .map(
            (action) => DropdownMenuItem(
              value: action,
              child: Text(action.label),
            ),
          )
          .toList(),
      onChanged: (action) {
        if (action != null) onChanged(action);
      },
    );
  }
}
