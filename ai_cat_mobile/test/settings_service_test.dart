import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_cat_mobile/services/settings_service.dart';

void main() {
  group('SettingsService.onboardingCompleted', () {
    test('yeni kurulumda (hic ayar yok) varsayilan false', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final settings = SettingsService(prefs);
      expect(settings.onboardingCompleted, isFalse);
    });

    test(
      'sihirbazdan once var olan (karakter adi kayitli) kurulum otomatik tamamlanmis sayilir',
      () async {
        SharedPreferences.setMockInitialValues({'character_name': 'Pati'});
        final prefs = await SharedPreferences.getInstance();
        final settings = SettingsService(prefs);
        expect(settings.onboardingCompleted, isTrue);
      },
    );

    test(
      'sihirbazdan once var olan (API anahtari kayitli) kurulum otomatik tamamlanmis sayilir',
      () async {
        SharedPreferences.setMockInitialValues({'gemini_api_key': 'gizli'});
        final prefs = await SharedPreferences.getInstance();
        final settings = SettingsService(prefs);
        expect(settings.onboardingCompleted, isTrue);
      },
    );

    test('acikca false olarak kaydedilmis kurulum false kalir', () async {
      SharedPreferences.setMockInitialValues({
        'character_name': 'Pati',
        'onboarding_completed': false,
      });
      final prefs = await SharedPreferences.getInstance();
      final settings = SettingsService(prefs);
      expect(settings.onboardingCompleted, isFalse);
    });

    test('true olarak yazilinca kalici olarak true doner', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final settings = SettingsService(prefs);
      expect(settings.onboardingCompleted, isFalse);
      settings.onboardingCompleted = true;
      expect(settings.onboardingCompleted, isTrue);
    });
  });
}
