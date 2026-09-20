import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/settings_service.dart';
import '../theme/app_colors.dart';

/// Ilk kurulumda HomeScreen tarafindan gosterilen kisa, adim adim kurulum
/// sihirbazi - masaustu suruumundeki OnboardingWizard (main.py) ile ayni
/// fikir: isim ve Gemini API key gibi ayarlar daha once yalnizca kediye
/// uzun basinca acilan Ayarlar penceresinde gomulu duruyordu, yeni bir
/// kullanici bunlari kesfetmeden once uygulamayla karsilasiyordu.
///
/// Yalnizca gercekten yeni bir kurulumda gorunur (bkz.
/// SettingsService.onboardingCompleted / HomeScreen._maybeShowOnboarding);
/// Ayarlar penceresindeki "Kurulum Sihirbazini Yeniden Baslat" ile de
/// istendigi zaman tekrar acilabilir.
class OnboardingWizard extends StatefulWidget {
  final SettingsService settings;

  const OnboardingWizard({super.key, required this.settings});

  @override
  State<OnboardingWizard> createState() => _OnboardingWizardState();
}

class _OnboardingWizardState extends State<OnboardingWizard> {
  static const _geminiApiKeyUrl = 'https://aistudio.google.com/apikey';
  static const _pageCount = 4;

  final _pageController = PageController();
  late final TextEditingController _nameController;
  late final TextEditingController _apiKeyController;
  int _pageIndex = 0;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.settings.characterName);
    _apiKeyController = TextEditingController(text: widget.settings.apiKey);
  }

  @override
  void dispose() {
    _pageController.dispose();
    _nameController.dispose();
    _apiKeyController.dispose();
    super.dispose();
  }

  void _goNext() {
    if (_pageIndex == _pageCount - 1) {
      _finish();
      return;
    }
    _pageController.nextPage(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  void _goBack() {
    _pageController.previousPage(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  void _finish() {
    final name = _nameController.text.trim();
    if (name.isNotEmpty) {
      widget.settings.characterName = name;
    }
    widget.settings.apiKey = _apiKeyController.text.trim();
    widget.settings.onboardingCompleted = true;
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final isLast = _pageIndex == _pageCount - 1;
    return PopScope(
      canPop: false,
      child: Dialog(
        backgroundColor: colors.panel,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: SizedBox(
          width: 400,
          height: 440,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Adım ${_pageIndex + 1}/$_pageCount',
                    style: TextStyle(color: colors.textMuted, fontSize: 11),
                  ),
                ),
              ),
              Expanded(
                child: PageView(
                  controller: _pageController,
                  physics: const NeverScrollableScrollPhysics(),
                  onPageChanged: (index) => setState(() => _pageIndex = index),
                  children: [
                    _buildWelcomePage(colors),
                    _buildIdentityPage(colors),
                    _buildApiKeyPage(colors),
                    _buildFinishPage(colors),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
                child: Row(
                  children: [
                    if (!isLast)
                      TextButton(
                        onPressed: _finish,
                        child: const Text('Daha Sonra'),
                      ),
                    const Spacer(),
                    if (_pageIndex > 0)
                      TextButton(onPressed: _goBack, child: const Text('Geri')),
                    FilledButton(
                      onPressed: _goNext,
                      child: Text(isLast ? 'Başla' : 'İleri'),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildWelcomePage(AppColors colors) {
    return _page(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Merhaba!',
            style: TextStyle(
              color: colors.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Telefon ekranında gezinen, Google Gemini destekli bir kedi '
            'asistanıyım. Sorularını yanıtlar, ekran görüntülerini '
            'yorumlar ve bilgisayarındaki eşimle konuşabiliriz.\n\n'
            'Başlamadan önce birkaç kısa adımı birlikte tamamlayalım.',
            style: TextStyle(color: colors.textSecondary, height: 1.4),
          ),
        ],
      ),
    );
  }

  Widget _buildIdentityPage(AppColors colors) {
    return _page(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'İsim',
            style: TextStyle(
              color: colors.textPrimary,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Text('Bana bir isim ver:', style: TextStyle(color: colors.textSecondary)),
          const SizedBox(height: 8),
          TextField(
            controller: _nameController,
            style: TextStyle(color: colors.textPrimary),
            decoration: const InputDecoration(border: OutlineInputBorder()),
          ),
        ],
      ),
    );
  }

  Widget _buildApiKeyPage(AppColors colors) {
    return _page(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Gemini API Anahtarı',
            style: TextStyle(
              color: colors.textPrimary,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Sorularını yanıtlayabilmem için ücretsiz bir Google Gemini '
            'API anahtarına ihtiyacım var. Aşağıdaki bağlantıdan birkaç '
            'saniyede alabilirsin; istersen bu adımı atlayıp daha sonra '
            'Ayarlar\'dan da girebilirsin.',
            style: TextStyle(color: colors.textSecondary, height: 1.4),
          ),
          const SizedBox(height: 8),
          InkWell(
            onTap: () => launchUrl(
              Uri.parse(_geminiApiKeyUrl),
              mode: LaunchMode.externalApplication,
            ),
            child: Text(
              'API Anahtarı Al (tarayıcıda açılır)',
              style: TextStyle(
                color: colors.accent,
                decoration: TextDecoration.underline,
              ),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _apiKeyController,
            obscureText: true,
            style: TextStyle(color: colors.textPrimary),
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: 'API anahtarını buraya yapıştır (opsiyonel)',
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFinishPage(AppColors colors) {
    return _page(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Hazırsın!',
            style: TextStyle(
              color: colors.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Ayarlarını istediğin zaman kediye uzun basıp açılan Ayarlar '
            'penceresinden değiştirebilirsin.',
            style: TextStyle(color: colors.textSecondary, height: 1.4),
          ),
        ],
      ),
    );
  }

  Widget _page({required Widget child}) {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: child,
    );
  }
}
