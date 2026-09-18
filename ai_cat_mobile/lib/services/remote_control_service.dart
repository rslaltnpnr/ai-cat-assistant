import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// Bilgisayardaki ai_desktop_assistant uygulamasina yerel ag uzerinden
/// gonderilen bir istegin basarisiz olma nedenini kullanici dostu bir
/// mesajla tasir.
class RemoteControlException implements Exception {
  final String message;

  /// true ise hata baglanti kurulamamasindan (ag erisilemez, zaman asimi)
  /// kaynaklanir - PIN hatasi, sunucu reddi ya da sertifika uyusmazligi
  /// gibi "bilgisayara ulasildi ama istek reddedildi" durumlarindan farkli
  /// olarak, bu tur hatalar cevrimdisi komut kuyruguna alinabilir aday
  /// olaylardir (bkz. CommandQueueService) - baglanti kurulamadiginda
  /// tekrar denemek anlamli, ama yanlis PIN'i "kuyruga alip beklemek"
  /// anlamsizdir.
  final bool isNetworkError;

  RemoteControlException(this.message, {this.isNetworkError = false});

  @override
  String toString() => message;
}

/// Bir uzaktan komut isteginin basarili sonucu. `fingerprint`, sunucunun
/// TLS sertifikasinin bu istekte gorulen SHA-256 parmak izidir - cagiran
/// taraf bunu (ilk baglantida guven / TOFU) kaydedip sonraki isteklerde
/// tekrar gonderir.
class RemoteControlResult {
  final String fingerprint;

  const RemoteControlResult(this.fingerprint);
}

/// [fetchScreenshot] sonucu: parmak izinin yani sira indirilen goruntu
/// (JPEG) baytlarini da tasir.
class ScreenshotResult {
  final String fingerprint;
  final Uint8List imageBytes;

  const ScreenshotResult(this.fingerprint, this.imageBytes);
}

/// [fetchHistory] sonucu: parmak izinin yani sira bilgisayardaki sohbet
/// gecmisi kayitlarini (ham JSON haritalari - cagiran taraf kendi
/// ChatEntry modeline cevirir) tasir.
class HistoryFetchResult {
  final String fingerprint;
  final List<Map<String, dynamic>> entries;

  const HistoryFetchResult(this.fingerprint, this.entries);
}

/// [fetchPendingFiles] sonucu: parmak izinin yani sira, bilgisayarda
/// "Kediyle Gönder" (sag tik menusu) ile kuyruga alinmis, henuz telefona
/// inmemis dosyalari (her biri {"filename", "content_base64"}) tasir.
class PendingFilesResult {
  final String fingerprint;
  final List<Map<String, dynamic>> files;

  const PendingFilesResult(this.fingerprint, this.files);
}

/// [fetchClipboard] sonucu: parmak izinin yani sira bilgisayarin panosundaki
/// metni tasir.
class ClipboardFetchResult {
  final String fingerprint;
  final String text;

  const ClipboardFetchResult(this.fingerprint, this.text);
}

/// [fetchAlerts] sonucu: parmak izinin yani sira `since_id`'den sonraki
/// hata/uyari kayitlarini (id, time, message) tasir.
class AlertsFetchResult {
  final String fingerprint;
  final List<Map<String, dynamic>> alerts;

  const AlertsFetchResult(this.fingerprint, this.alerts);
}

/// [pushHistory] sonucu: parmak izinin yani sira bilgisayarda gercekten
/// yeni eklenen (zaten var olmayan) kayit sayisini tasir.
class HistoryPushResult {
  final String fingerprint;
  final int added;

  const HistoryPushResult(this.fingerprint, this.added);
}

/// [fetchAutomationRules] sonucu: parmak izinin yani sira bilgisayarda
/// tanimli otomasyon kurallarinin (name, trigger_type, trigger_value,
/// action_type, action_value, enabled) tam listesini tasir - salt okunur,
/// bu ekrandan duzenlenemez (bkz. masaustu uygulamasinin "Otomasyon
/// Kurallari" penceresi).
class AutomationFetchResult {
  final String fingerprint;
  final List<Map<String, dynamic>> rules;

  const AutomationFetchResult(this.fingerprint, this.rules);
}

/// [teleportFile] sonucu: parmak izinin yani sira bilgisayarda dosyanin
/// gercekten kaydedildigi ad (ayni adda dosya zaten varsa " (2)" gibi bir
/// sayacla degismis olabilir).
class FileTeleportResult {
  final String fingerprint;
  final String savedAs;

  const FileTeleportResult(this.fingerprint, this.savedAs);
}

class _RawResponse {
  final int statusCode;
  final String body;
  final String fingerprint;

  const _RawResponse(this.statusCode, this.body, this.fingerprint);
}

/// Bilgisayardaki kedi uygulamasinin sag tik menusunde acilan yerel HTTPS
/// sunucusuna (bkz. ai_desktop_assistant/main.py - RemoteCommandServer)
/// komut gonderir: /open (baglanti ac), /media (medya tuslari), /power
/// (kilit/uyku), /screenshot (ekran goruntusu). Ikisi de ayni Wi-Fi agina
/// bagli olmalidir; kimlik dogrulama bir PIN ile yapilir.
///
/// Sunucu kendinden imzali bir TLS sertifikasi kullandigi icin isletim
/// sisteminin guvenilir sertifika zincirinde bulunmaz. Bunun yerine SSH
/// host key'lerine benzer bir "ilk baglantida guven" (TOFU) modeli
/// uygulanir: ilk baglantida sertifikanin SHA-256 parmak izi kaydedilir
/// (kullanicinin bilgisayardaki "Uzaktan Kumanda Bilgisi" penceresinden
/// gorup dogrulayabilecegi degerle ayni olmalidir); sonraki baglantilarda
/// parmak izi degismisse istek reddedilir (olasi araya girme/MITM saldirisi).
class RemoteControlService {
  Future<_RawResponse> _post({
    required String ip,
    required int port,
    required String path,
    required Map<String, dynamic> body,
    required String pinnedFingerprint,
    Duration connectTimeout = const Duration(seconds: 5),
    Duration sendTimeout = const Duration(seconds: 8),
    Duration responseTimeout = const Duration(seconds: 8),
  }) async {
    final Uri uri;
    try {
      uri = Uri.parse('https://${ip.trim()}:$port$path');
    } catch (_) {
      throw RemoteControlException('IP adresi veya port gecersiz.');
    }

    String? observedFingerprint;
    var fingerprintMismatch = false;

    final client = HttpClient();
    client.connectionTimeout = connectTimeout;
    client.badCertificateCallback = (cert, host, certPort) {
      final fingerprint = sha256.convert(cert.der).toString();
      observedFingerprint = fingerprint;
      if (pinnedFingerprint.isEmpty || fingerprint == pinnedFingerprint) {
        return true;
      }
      fingerprintMismatch = true;
      return false;
    };

    try {
      final encodedBody = utf8.encode(jsonEncode(body));
      final request = await client.postUrl(uri).timeout(connectTimeout);
      request.headers.set('Content-Type', 'application/json');
      request.headers.set('Content-Length', encodedBody.length.toString());
      request.add(encodedBody);
      final response = await request.close().timeout(sendTimeout);
      final responseBody = await response
          .transform(utf8.decoder)
          .join()
          .timeout(responseTimeout);

      return _RawResponse(
        response.statusCode,
        responseBody,
        observedFingerprint ?? pinnedFingerprint,
      );
    } on RemoteControlException {
      rethrow;
    } catch (_) {
      if (fingerprintMismatch) {
        throw RemoteControlException(
          'DIKKAT: Bilgisayarin guvenlik sertifikasi kayitli olandan '
          'farkli! Bu bir araya girme (MITM) saldirisi belirtisi olabilir '
          '- ya da bilgisayar uygulamasi yeniden kuruldu. Emin degilseniz '
          'baglanmayin; eminseniz eslestirmeyi sifirlayip tekrar deneyin.',
        );
      }
      throw RemoteControlException(
        'Bilgisayara ulasilamadi. Ayni Wi-Fi agina bagli oldugunuzdan ve '
        'IP/portun dogru oldugundan emin olun.',
        isNetworkError: true,
      );
    } finally {
      client.close(force: true);
    }
  }

  void _throwForCommonErrors(_RawResponse response) {
    if (response.statusCode == 200) return;
    if (response.statusCode == 401) {
      throw RemoteControlException('PIN yanlis.');
    }
    if (response.statusCode == 429) {
      throw RemoteControlException(
        '${_serverErrorMessage(response.body) ?? 'Cok fazla yanlis deneme yapildi'}. '
        'Biraz bekleyip tekrar dene.',
      );
    }
    final detail = _serverErrorMessage(response.body);
    throw RemoteControlException(
      detail != null
          ? 'Bilgisayar istegi reddetti: $detail'
          : 'Bilgisayar istegi reddetti (kod ${response.statusCode}).',
    );
  }

  Future<RemoteControlResult> openUrl({
    required String ip,
    required int port,
    required String pin,
    required String url,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    if (url.trim().isEmpty) {
      throw RemoteControlException('Acilacak bir baglanti yaz.');
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/open',
      body: {'pin': pin, 'url': url.trim()},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    return RemoteControlResult(response.fingerprint);
  }

  Future<RemoteControlResult> sendMedia({
    required String ip,
    required int port,
    required String pin,
    required String action,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/media',
      body: {'pin': pin, 'action': action},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    return RemoteControlResult(response.fingerprint);
  }

  Future<RemoteControlResult> sendPower({
    required String ip,
    required int port,
    required String pin,
    required String action,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/power',
      body: {'pin': pin, 'action': action},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    return RemoteControlResult(response.fingerprint);
  }

  Future<ScreenshotResult> fetchScreenshot({
    required String ip,
    required int port,
    required String pin,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/screenshot',
      body: {'pin': pin},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    try {
      final data = jsonDecode(response.body);
      final imageBytes = base64Decode(data['image_base64'] as String);
      return ScreenshotResult(response.fingerprint, imageBytes);
    } catch (_) {
      throw RemoteControlException('Ekran goruntusu okunamadi.');
    }
  }

  Future<HistoryFetchResult> fetchHistory({
    required String ip,
    required int port,
    required String pin,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/history',
      body: {'pin': pin},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    try {
      final data = jsonDecode(response.body);
      final entries = List<Map<String, dynamic>>.from(data['entries'] as List);
      return HistoryFetchResult(response.fingerprint, entries);
    } catch (_) {
      throw RemoteControlException('Geçmiş okunamadı.');
    }
  }

  Future<AutomationFetchResult> fetchAutomationRules({
    required String ip,
    required int port,
    required String pin,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/automation',
      body: {'pin': pin},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    try {
      final data = jsonDecode(response.body);
      final rules = List<Map<String, dynamic>>.from(data['rules'] as List);
      return AutomationFetchResult(response.fingerprint, rules);
    } catch (_) {
      throw RemoteControlException('Otomasyon kurallari okunamadi.');
    }
  }

  /// Telefondaki sohbet gecmisi kayitlarini bilgisayara gonderir; bilgisayar
  /// zaten sahip oldugu (ayni zaman/soru/cevap ucluesune sahip) kayitlari
  /// kendisi atlar (bkz. main.py - merge_history_entries), bu yuzden burada
  /// tum [entries] listesi gonderilebilir.
  Future<HistoryPushResult> pushHistory({
    required String ip,
    required int port,
    required String pin,
    required List<Map<String, dynamic>> entries,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/history/import',
      body: {'pin': pin, 'entries': entries},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    try {
      final data = jsonDecode(response.body);
      final added = (data['added'] as num?)?.toInt() ?? 0;
      return HistoryPushResult(response.fingerprint, added);
    } catch (_) {
      throw RemoteControlException('Sunucu yaniti okunamadı.');
    }
  }

  Future<AlertsFetchResult> fetchAlerts({
    required String ip,
    required int port,
    required String pin,
    required String pinnedFingerprint,
    required int sinceId,
  }) async {
    final response = await _post(
      ip: ip,
      port: port,
      path: '/alerts',
      body: {'pin': pin, 'since_id': sinceId},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    try {
      final data = jsonDecode(response.body);
      final alerts = List<Map<String, dynamic>>.from(data['alerts'] as List);
      return AlertsFetchResult(response.fingerprint, alerts);
    } catch (_) {
      throw RemoteControlException('Uyarılar okunamadı.');
    }
  }

  Future<RemoteControlResult> pushClipboard({
    required String ip,
    required int port,
    required String pin,
    required String text,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/clipboard',
      body: {'pin': pin, 'action': 'push', 'text': text},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    return RemoteControlResult(response.fingerprint);
  }

  Future<ClipboardFetchResult> pullClipboard({
    required String ip,
    required int port,
    required String pin,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/clipboard',
      body: {'pin': pin, 'action': 'pull'},
      pinnedFingerprint: pinnedFingerprint,
    );
    _throwForCommonErrors(response);
    try {
      final data = jsonDecode(response.body);
      return ClipboardFetchResult(response.fingerprint, data['text'] as String? ?? '');
    } catch (_) {
      throw RemoteControlException('Pano okunamadı.');
    }
  }

  /// "Dosya Teleport": secilen dosyayi bilgisayara gonderir - bilgisayar
  /// tarafinda hep AYNI sabit klasore (bkz. main.py -
  /// received_files_dir()) kaydedilir, her seferinde nereye kaydedilecegi
  /// sorulmaz. Buyuk dosyalar (fotograf/belge) icin diger komutlardan daha
  /// uzun zaman asimlari kullanilir.
  Future<FileTeleportResult> teleportFile({
    required String ip,
    required int port,
    required String pin,
    required String filename,
    required Uint8List bytes,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/file',
      body: {
        'pin': pin,
        'filename': filename,
        'content_base64': base64Encode(bytes),
      },
      pinnedFingerprint: pinnedFingerprint,
      connectTimeout: const Duration(seconds: 8),
      sendTimeout: const Duration(seconds: 60),
      responseTimeout: const Duration(seconds: 30),
    );
    _throwForCommonErrors(response);
    try {
      final data = jsonDecode(response.body);
      return FileTeleportResult(
        response.fingerprint,
        data['saved_as'] as String? ?? filename,
      );
    } catch (_) {
      throw RemoteControlException('Sunucu yaniti okunamadı.');
    }
  }

  /// "Kediyle Gönder" ile bilgisayarda kuyruga alinmis dosyalari yoklar -
  /// bir sonucu olan her dosya bilgisayar tarafinda kuyruktan SILINIR
  /// (yalnizca bir kez teslim edilir), bu yuzden bu metod cagrildiginda
  /// donen dosyalar mutlaka kaydedilmelidir (bkz. IncomingFileService).
  Future<PendingFilesResult> fetchPendingFiles({
    required String ip,
    required int port,
    required String pin,
    required String pinnedFingerprint,
  }) async {
    if (ip.trim().isEmpty) {
      throw RemoteControlException(
        'Once bilgisayarin IP adresini ve PIN kodunu gir.',
      );
    }
    final response = await _post(
      ip: ip,
      port: port,
      path: '/file/pending',
      body: {'pin': pin},
      pinnedFingerprint: pinnedFingerprint,
      connectTimeout: const Duration(seconds: 8),
      sendTimeout: const Duration(seconds: 30),
      responseTimeout: const Duration(seconds: 30),
    );
    _throwForCommonErrors(response);
    try {
      final data = jsonDecode(response.body);
      final files = List<Map<String, dynamic>>.from(data['files'] as List);
      return PendingFilesResult(response.fingerprint, files);
    } catch (_) {
      throw RemoteControlException('Bekleyen dosyalar okunamadı.');
    }
  }

  String? _serverErrorMessage(String body) {
    try {
      final data = jsonDecode(body);
      if (data is Map && data['error'] is String) {
        return data['error'] as String;
      }
    } catch (_) {
      // govde JSON degilse yok say, jenerik mesaj kullanilir
    }
    return null;
  }
}
