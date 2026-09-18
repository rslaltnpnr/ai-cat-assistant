import 'package:flutter_test/flutter_test.dart';

import 'package:ai_cat_mobile/services/incoming_file_service.dart';

void main() {
  group('uniqueIncomingFileName', () {
    test('cakisma yoksa ad degismez', () {
      expect(uniqueIncomingFileName({}, 'rapor.pdf'), 'rapor.pdf');
    });

    test('cakisma varsa sayac eklenir, uzanti korunur', () {
      final existing = {'rapor.pdf'};
      expect(uniqueIncomingFileName(existing, 'rapor.pdf'), 'rapor (2).pdf');
    });

    test('birden fazla cakisma varsa sayac artar', () {
      final existing = {'rapor.pdf', 'rapor (2).pdf', 'rapor (3).pdf'};
      expect(uniqueIncomingFileName(existing, 'rapor.pdf'), 'rapor (4).pdf');
    });

    test('uzantisiz dosya adinda da calisir', () {
      final existing = {'notlar'};
      expect(uniqueIncomingFileName(existing, 'notlar'), 'notlar (2)');
    });

    test('nokta ile baslayan (gizli) dosya adinda uzanti sayilmaz', () {
      final existing = {'.gitignore'};
      expect(uniqueIncomingFileName(existing, '.gitignore'), '.gitignore (2)');
    });
  });
}
