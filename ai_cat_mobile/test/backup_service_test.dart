import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_cat_mobile/services/backup_service.dart';
import 'package:ai_cat_mobile/services/settings_service.dart';

void main() {
  group('BackupService.importBackup', () {
    test('gecerli bir yedegi ice aktarir ve tercihleri geri yukler', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      final backupJson = jsonEncode({
        'backup_version': 1,
        'preferences': {
          'character_name': 'Fuff',
          'gemini_api_key': 'test-key',
          'theme_mode': 'dark',
          'onboarded': true,
          'reminder_minutes': 30,
        },
      });

      final count = await BackupService().importBackup(backupJson);

      expect(count, 5);
      expect(prefs.getString('character_name'), 'Fuff');
      // API anahtari SharedPreferences'a duz metin YAZILMAZ - dogrudan
      // guvenli depoya tasinir (bkz. SettingsService.migrateLegacyApiKey).
      expect(prefs.containsKey('gemini_api_key'), isFalse);
      final settings = await SettingsService.create(prefs);
      expect(settings.apiKey, 'test-key');
      expect(prefs.getString('theme_mode'), 'dark');
      expect(prefs.getBool('onboarded'), true);
      expect(prefs.getInt('reminder_minutes'), 30);
    });

    test('gecersiz JSON FormatException firlatir', () async {
      SharedPreferences.setMockInitialValues({});
      await expectLater(
        () => BackupService().importBackup('bu gecerli bir json degil'),
        throwsA(isA<FormatException>()),
      );
    });

    test('preferences alani olmayan yedek FormatException firlatir', () async {
      SharedPreferences.setMockInitialValues({});
      await expectLater(
        () => BackupService().importBackup(jsonEncode({'foo': 'bar'})),
        throwsA(isA<FormatException>()),
      );
    });

    test('liste degerler stringlist olarak geri yuklenir', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      final backupJson = jsonEncode({
        'backup_version': 1,
        'preferences': {
          'remote_profile_ids': ['a', 'b', 'c'],
        },
      });

      final count = await BackupService().importBackup(backupJson);

      expect(count, 1);
      expect(prefs.getStringList('remote_profile_ids'), ['a', 'b', 'c']);
    });
  });

  group('shouldRunAutoBackup', () {
    test('hic yedek yoksa true doner', () {
      expect(shouldRunAutoBackup(null, DateTime(2026, 1, 2)), isTrue);
      expect(shouldRunAutoBackup('', DateTime(2026, 1, 2)), isTrue);
    });

    test('gecersiz tarih true doner', () {
      expect(
        shouldRunAutoBackup('gecersiz-tarih', DateTime(2026, 1, 2)),
        isTrue,
      );
    });

    test('interval dolmamissa false doner', () {
      final last = DateTime(2026, 1, 1, 10, 0).toIso8601String();
      final now = DateTime(2026, 1, 1, 20, 0); // 10 saat sonra
      expect(shouldRunAutoBackup(last, now, intervalDays: 1), isFalse);
    });

    test('interval dolmussa true doner', () {
      final last = DateTime(2026, 1, 1, 10, 0).toIso8601String();
      final now = DateTime(2026, 1, 2, 11, 0); // 25 saat sonra
      expect(shouldRunAutoBackup(last, now, intervalDays: 1), isTrue);
    });
  });

  group('autoBackupFilesToDelete', () {
    test('kapasitenin altindaysa hicbir sey silinmez', () {
      final result = autoBackupFilesToDelete([
        '${autoBackupPrefix}2026-01-01-000000.json',
      ], keepCount: 5);
      expect(result, isEmpty);
    });

    test('fazla dosyalar en eskiden baslayarak listelenir', () {
      final names = [
        '${autoBackupPrefix}2026-01-01-000000.json',
        '${autoBackupPrefix}2026-01-02-000000.json',
        '${autoBackupPrefix}2026-01-03-000000.json',
      ];
      final result = autoBackupFilesToDelete(names, keepCount: 2);
      expect(result, [names[0]]);
    });

    test('ilgisiz dosyalar goz ardi edilir', () {
      final result = autoBackupFilesToDelete([
        'baska-dosya.txt',
        '${autoBackupPrefix}2026-01-01-000000.json',
      ], keepCount: 0);
      expect(result, ['${autoBackupPrefix}2026-01-01-000000.json']);
    });
  });
}
