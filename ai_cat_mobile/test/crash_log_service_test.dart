import 'package:flutter_test/flutter_test.dart';

import 'package:ai_cat_mobile/services/crash_log_service.dart';

void main() {
  group('formatCrashLogEntry', () {
    test('zaman, hata ve yigin izini iceren bir blok uretir', () {
      final time = DateTime.utc(2026, 1, 2, 3, 4, 5);
      final entry = formatCrashLogEntry(
        time,
        Exception('bir seyler ters gitti'),
        StackTrace.fromString('#0 main (file.dart:1:1)'),
      );

      expect(entry, contains('--- ${time.toIso8601String()} ---'));
      expect(entry, contains('bir seyler ters gitti'));
      expect(entry, contains('#0 main (file.dart:1:1)'));
    });
  });

  group('trimCrashLog', () {
    String entryFor(int n) =>
        '--- 2026-01-0${n}T00:00:00.000Z ---\nhata $n\niz $n\n';

    test('sinirin altindaysa hicbir sey atilmaz', () {
      final content = entryFor(1) + entryFor(2);
      final trimmed = trimCrashLog(content, maxEntries: 5);
      expect(trimmed, content);
    });

    test('sinir asilirsa en eski kayitlar atilir, en yeniler kalir', () {
      final content = entryFor(1) + entryFor(2) + entryFor(3);
      final trimmed = trimCrashLog(content, maxEntries: 2);

      expect(trimmed, isNot(contains('hata 1')));
      expect(trimmed, contains('hata 2'));
      expect(trimmed, contains('hata 3'));
    });

    test('bos icerik icin bos doner', () {
      expect(trimCrashLog('', maxEntries: 5), '');
    });
  });
}
