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

  group('SettingsService.apiKey (guvenli depolama)', () {
    test('yeni kurulumda create() sonrasi bos doner', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final settings = await SettingsService.create(prefs);
      expect(settings.apiKey, '');
    });

    test('yazilan anahtar SharedPreferences\'a duz metin yazilmaz', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final settings = await SettingsService.create(prefs);
      settings.apiKey = 'gizli-anahtar';
      expect(settings.apiKey, 'gizli-anahtar');
      expect(prefs.containsKey('gemini_api_key'), isFalse);
    });

    test(
      'eski duz metin SharedPreferences degeri create() ile guvenli depoya tasinir',
      () async {
        SharedPreferences.setMockInitialValues({
          'character_name': 'Pati',
          'gemini_api_key': 'eski-anahtar',
        });
        final prefs = await SharedPreferences.getInstance();
        final settings = await SettingsService.create(prefs);
        expect(settings.apiKey, 'eski-anahtar');
        expect(prefs.containsKey('gemini_api_key'), isFalse);
        expect(prefs.getString('character_name'), 'Pati');
      },
    );

    test(
      'eski duz metin anahtar tasinirken onboarding otomatik tamamlanmis sayilir',
      () async {
        // character_name gibi baska hicbir "eski kurulum" isareti yok -
        // yalnizca API anahtari var. containsKey(gemini_api_key) migrasyon
        // sirasinda silinecegi icin _looksLikeExistingInstall bunu bir daha
        // yakalayamaz; onboarding_completed bu yuzden migrasyon SIRASINDA
        // aciktan yazilmali (bkz. SettingsService._loadApiKey).
        SharedPreferences.setMockInitialValues({'gemini_api_key': 'eski-anahtar'});
        final prefs = await SharedPreferences.getInstance();
        final settings = await SettingsService.create(prefs);
        expect(settings.apiKey, 'eski-anahtar');
        expect(settings.onboardingCompleted, isTrue);
      },
    );

    test('iki ayri instance ayni guvenli depoyu paylasir', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final first = await SettingsService.create(prefs);
      first.apiKey = 'paylasilan-anahtar';
      final second = await SettingsService.create(prefs);
      expect(second.apiKey, 'paylasilan-anahtar');
    });

    test(
      'migrateLegacyApiKey static yardimcisi SharedPreferences\'a dokunmadan guvenli depoya yazar',
      () async {
        SharedPreferences.setMockInitialValues({});
        final prefs = await SharedPreferences.getInstance();
        await SettingsService.migrateLegacyApiKey('yedekten-gelen-anahtar');
        final settings = await SettingsService.create(prefs);
        expect(settings.apiKey, 'yedekten-gelen-anahtar');
        expect(prefs.containsKey('gemini_api_key'), isFalse);
      },
    );
  });
}
