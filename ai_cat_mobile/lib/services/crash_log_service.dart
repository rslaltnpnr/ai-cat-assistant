import 'dart:io';

import 'package:path_provider/path_provider.dart';

const crashLogFileName = 'crash.log';

/// Bir defada dosyada tutulacak en fazla kayit sayisi - mobil cihazlarda
/// depolama sinirli oldugu icin gunluk sinirsizca buyumez.
const crashLogMaxEntries = 20;

/// Bir cokme kaydini crash.log'a eklenecek tek bir metin blogu haline
/// getirir - masaustu suruumundeki crash.log formatiyla (zaman damgasi +
/// hata + yigin izi) benzer, saf bir fonksiyon oldugu icin dosya sistemine
/// dokunmadan test edilebilir.
String formatCrashLogEntry(DateTime time, Object error, StackTrace stack) {
  final buffer = StringBuffer()
    ..writeln('--- ${time.toIso8601String()} ---')
    ..writeln(error.toString())
    ..writeln(stack.toString());
  return buffer.toString();
}

/// [content] icindeki kayitlari ("--- " ile baslayan satirlar yeni bir
/// kaydin basi sayilir) en fazla [maxEntries] tanesi kalacak sekilde
/// (en eskiler atilarak) budar. Tutulan kisim orijinal metnin dogrudan bir
/// dilimi oldugu icin (satir satir yeniden birlestirme yapilmaz) kayip
/// olusmaz - orn. son satirin sonundaki yeni satir karakteri korunur.
String trimCrashLog(String content, {int maxEntries = crashLogMaxEntries}) {
  if (content.isEmpty) return '';
  final markerOffsets = <int>[];
  var offset = 0;
  for (final line in content.split('\n')) {
    if (line.startsWith('--- ')) markerOffsets.add(offset);
    offset += line.length + 1; // +1: split'in yuttugu '\n'
  }
  if (markerOffsets.length <= maxEntries) return content;
  final startOffset = markerOffsets[markerOffsets.length - maxEntries];
  return content.substring(startOffset);
}

/// Beklenmeyen hatalari cihazda kalici bir dosyaya (crash.log) kaydeder -
/// masaustu suruumundeki install_crash_handler() ile AYNI amac: bir cokme
/// sessizce kaybolup gitmez, sonradan incelenebilir. main.dart, Flutter'in
/// kendi hata yollarini (FlutterError.onError / platformDispatcher.onError)
/// buraya baglar.
class CrashLogService {
  static final CrashLogService instance = CrashLogService._();
  CrashLogService._();

  Future<File> _logFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/$crashLogFileName');
  }

  Future<void> log(Object error, StackTrace stack) async {
    try {
      final file = await _logFile();
      final existing = await file.exists() ? await file.readAsString() : '';
      final updated = existing + formatCrashLogEntry(DateTime.now(), error, stack);
      await file.writeAsString(trimCrashLog(updated), flush: true);
    } catch (_) {
      // Gunluk yazilamazsa (orn. disk dolu) sessizce yoksay - bir hata
      // isleyicisinin kendisi yeni bir hataya yol acmamali.
    }
  }

  /// crash.log'un en son degistirildigi zaman - hic yoksa null. Kullanici
  /// bu zaman damgasini gormus mu diye SettingsService.lastSeenCrash ile
  /// karsilastirilir (bkz. HomeScreen._maybeShowCrashNotice).
  Future<DateTime?> lastCrashTime() async {
    try {
      final file = await _logFile();
      if (!await file.exists()) return null;
      return await file.lastModified();
    } catch (_) {
      return null;
    }
  }

  Future<String> readLog() async {
    try {
      final file = await _logFile();
      if (!await file.exists()) return '';
      return await file.readAsString();
    } catch (_) {
      return '';
    }
  }
}
