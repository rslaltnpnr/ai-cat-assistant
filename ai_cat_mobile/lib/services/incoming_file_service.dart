import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// "Kediyle Gönder" (masaüstü sağ tık menüsü) ile bilgisayardan gelen
/// dosyaların kaydedildiği sabit klasör adı - masaüstündeki
/// received_files_dir() ile SİMETRİK, ama TERS yön (bilgisayar -> telefon).
const incomingFilesDirName = 'Bilgisayardan Gelenler';

/// [existingNames] içinde [filename] zaten varsa üzerine yazmak yerine
/// " (2)", " (3)" gibi bir sayaç ekleyerek benzersiz bir ad üretir -
/// masaüstündeki unique_teleport_destination() ile aynı mantık, saf/test
/// edilebilir bir fonksiyon.
String uniqueIncomingFileName(Set<String> existingNames, String filename) {
  if (!existingNames.contains(filename)) return filename;
  final dotIndex = filename.lastIndexOf('.');
  final hasExtension = dotIndex > 0 && dotIndex < filename.length - 1;
  final base = hasExtension ? filename.substring(0, dotIndex) : filename;
  final ext = hasExtension ? filename.substring(dotIndex) : '';
  var counter = 2;
  var candidate = '$base ($counter)$ext';
  while (existingNames.contains(candidate)) {
    counter++;
    candidate = '$base ($counter)$ext';
  }
  return candidate;
}

/// [RemoteControlService.fetchPendingFiles] ile alınan dosyaları cihaza
/// kaydeder - `getExternalStorageDirectory()` altına (bir dosya
/// yöneticisinden erişilebilir, uygulamanın özel/gizli deposu değil).
class IncomingFileService {
  Future<Directory> _targetDir() async {
    final base = await getExternalStorageDirectory() ??
        await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/$incomingFilesDirName');
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  /// [files] (her biri {"filename", "content_base64"}) içindekileri diske
  /// yazar, başarıyla kaydedilenlerin (olası çakışma sonrası) gerçek
  /// dosya adlarının listesini döner.
  Future<List<String>> saveAll(List<Map<String, dynamic>> files) async {
    if (files.isEmpty) return [];
    final dir = await _targetDir();
    final existing = (await dir.list().toList())
        .whereType<File>()
        .map((f) => f.uri.pathSegments.last)
        .toSet();
    final saved = <String>[];
    for (final entry in files) {
      final rawName = entry['filename'] as String? ?? 'dosya';
      final contentB64 = entry['content_base64'] as String?;
      if (contentB64 == null) continue;
      try {
        final bytes = base64Decode(contentB64);
        final name = uniqueIncomingFileName(existing, rawName);
        existing.add(name);
        await File('${dir.path}/$name').writeAsBytes(bytes, flush: true);
        saved.add(name);
      } catch (_) {
        // Bozuk bir kayit varsa yoksay, digerlerini kaydetmeye devam et.
      }
    }
    return saved;
  }
}
