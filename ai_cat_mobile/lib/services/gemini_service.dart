import 'dart:async';
import 'dart:typed_data';

import 'package:google_generative_ai/google_generative_ai.dart';
import 'package:http/http.dart' as http;

/// Gemini isteklerinde olusan hatalari kullanici dostu, kisa bir Turkce
/// mesaja cevirir; sohbet panelinde ham SDK/HTTP hatasi yerine bu
/// gosterilir.
class GeminiRequestException implements Exception {
  final String message;

  GeminiRequestException(this.message);

  @override
  String toString() => message;
}

/// Google Gemini'ye ekran/galeri goruntusu + soru gonderir.
///
/// Gecici asiri yuklenme (503) hatalarinda kisa bir bekleme ile tekrar
/// dener; ana model kaldirilmis/bulunamiyorsa (404) veya ucretsiz kota
/// (429) doluysa otomatik olarak yedek modele gecer. Kota hatasinda
/// Gemini'nin "Please retry in Ns" mesajindaki bekleme suresi kullanilir.
/// Tum denemeler basarisiz olursa ham hata yerine kisa, okunakli bir
/// mesaj firlatilir.
class GeminiService {
  static const fallbackModel = 'gemini-3.6-flash';
  static const _defaultQuotaWait = Duration(seconds: 5);
  static const _maxQuotaWait = Duration(seconds: 20);

  static final RegExp _retryAfterPattern = RegExp(
    r'retry in ([\d.]+)\s*s',
    caseSensitive: false,
  );

  /// Yalnizca testler icin: verilirse GenerativeModel'e gercek ag yerine
  /// bu http.Client enjekte edilir (bkz. test/gemini_service_test.dart).
  /// Normal kullanimda null kalir, SDK kendi varsayilan istemcisini kurar.
  final http.Client? httpClient;

  GeminiService({this.httpClient});

  Future<String> ask({
    required String apiKey,
    required String modelName,
    required String characterName,
    required String question,
    Uint8List? imageBytes,
  }) async {
    final persona = _persona(characterName);
    final content = _content(question, imageBytes);

    Object finalError;
    try {
      final response = await _generateWithRetry(
        apiKey: apiKey,
        modelName: modelName,
        systemInstruction: persona,
        content: content,
        maxAttempts: 3,
      );
      return _extractText(response);
    } catch (primaryError) {
      finalError = primaryError;
      final shouldFallback = modelName != fallbackModel &&
          (_isOverloadError(primaryError) ||
              _isModelRetiredError(primaryError) ||
              _isQuotaError(primaryError));
      if (shouldFallback) {
        try {
          final response = await _generateWithRetry(
            apiKey: apiKey,
            modelName: fallbackModel,
            systemInstruction: persona,
            content: content,
            maxAttempts: 2,
          );
          return _extractText(response);
        } catch (fallbackError) {
          finalError = fallbackError;
        }
      }
    }
    throw GeminiRequestException(_friendlyMessage(finalError));
  }

  /// [ask] ile ayni istegi, yaniti tek seferde beklemek yerine parca parca
  /// (Gemini'nin akis API'siyle) yayinlar. Ilk parca alinana kadar olan
  /// hatalarda [ask] ile ayni yeniden deneme/yedek model mantigi gecerlidir;
  /// akis BASLADIKTAN SONRA (en az bir parca yayinlandiktan sonra) olusan
  /// bir hata ASLA yeniden denenmez - kismen gosterilmis bir yanitin
  /// bastan, hatta baska bir modelden tekrarlanmasi kullaniciyi
  /// sasirtirdi; bunun yerine akis doğrudan hata firlatarak sonlanir.
  ///
  /// Not: Dart'ta `try { yield* altAkis(); } catch (e) {}` altAkis'in
  /// firlattigi hatalari YAKALAMAZ (dogrulanmis dil davranisi) - bu yuzden
  /// burada `yield*` hic kullanilmiyor; akis dogrudan `yield` ile, tek
  /// seviyeli ve tek bir try/catch icinde uretiliyor.
  Stream<String> askStream({
    required String apiKey,
    required String modelName,
    required String characterName,
    required String question,
    Uint8List? imageBytes,
  }) async* {
    final persona = _persona(characterName);
    final content = _content(question, imageBytes);

    StreamIterator<GenerateContentResponse>? iterator;
    var obtained = false;
    Object? finalError;
    try {
      iterator = await _obtainStreamIterator(
        apiKey: apiKey,
        modelName: modelName,
        systemInstruction: persona,
        content: content,
        maxAttempts: 3,
      );
      obtained = true;
    } catch (primaryError) {
      finalError = primaryError;
      final shouldFallback = modelName != fallbackModel &&
          (_isOverloadError(primaryError) ||
              _isModelRetiredError(primaryError) ||
              _isQuotaError(primaryError));
      if (shouldFallback) {
        try {
          iterator = await _obtainStreamIterator(
            apiKey: apiKey,
            modelName: fallbackModel,
            systemInstruction: persona,
            content: content,
            maxAttempts: 2,
          );
          obtained = true;
          finalError = null;
        } catch (fallbackError) {
          finalError = fallbackError;
        }
      }
    }

    if (!obtained) {
      throw GeminiRequestException(_friendlyMessage(finalError!));
    }
    if (iterator == null) {
      return; // bos akis
    }

    try {
      final firstText = iterator.current.text ?? '';
      if (firstText.isNotEmpty) yield firstText;
      while (await iterator.moveNext()) {
        final text = iterator.current.text ?? '';
        if (text.isNotEmpty) yield text;
      }
    } catch (exc) {
      throw GeminiRequestException(_friendlyMessage(exc));
    }
  }

  Content _persona(String characterName) => Content.system(
        "Senin adin '$characterName'. Kullanicinin telefonunda yasayan, "
        "gonderdigi gorselleri gorebilen sevimli bir kedi yapay zeka "
        "asistanisin. Kendini her zaman bu isimle tanit; Google tarafindan "
        "gelistirilmis bir dil modeli oldugunu veya hangi sirkete/modele ait "
        "oldugunu asla soyleme. Kisa, samimi ve yardimsever konus.",
      );

  List<Content> _content(String question, Uint8List? imageBytes) {
    final parts = <Part>[TextPart(question)];
    if (imageBytes != null) {
      parts.add(DataPart('image/jpeg', imageBytes));
    }
    return [Content.multi(parts)];
  }

  String _extractText(GenerateContentResponse response) {
    final text = response.text?.trim();
    return (text == null || text.isEmpty) ? '(Bos yanit dondu)' : text;
  }

  /// Bir model icin akis baslatmayi dener; ilk parca alinana kadar olan
  /// hatalarda (asiri yuklenme/kota) yeniden dener. Akis bossa null
  /// doner; basarili olursa ilk parcaya konumlanmis (moveNext zaten bir
  /// kez cagrilmis) bir StreamIterator doner - cagiran taraf `.current`
  /// ile ilk parcayi okuyup sonra `moveNext()` ile devam eder.
  Future<StreamIterator<GenerateContentResponse>?> _obtainStreamIterator({
    required String apiKey,
    required String modelName,
    required Content systemInstruction,
    required List<Content> content,
    required int maxAttempts,
  }) async {
    final model = GenerativeModel(
      model: modelName,
      apiKey: apiKey,
      systemInstruction: systemInstruction,
      httpClient: httpClient,
    );

    for (var attempt = 0; attempt < maxAttempts; attempt++) {
      final candidate = StreamIterator(model.generateContentStream(content));
      try {
        if (!await candidate.moveNext()) {
          return null; // bos akis
        }
        return candidate;
      } catch (exc) {
        final isLastAttempt = attempt == maxAttempts - 1;
        if (isLastAttempt) rethrow;
        if (_isOverloadError(exc)) {
          await Future.delayed(Duration(seconds: 2 * (attempt + 1)));
          continue;
        }
        if (_isQuotaError(exc)) {
          await Future.delayed(_parseRetryAfter(exc) ?? _defaultQuotaWait);
          continue;
        }
        rethrow;
      }
    }
    return null;
  }

  Future<GenerateContentResponse> _generateWithRetry({
    required String apiKey,
    required String modelName,
    required Content systemInstruction,
    required List<Content> content,
    required int maxAttempts,
  }) async {
    final model = GenerativeModel(
      model: modelName,
      apiKey: apiKey,
      systemInstruction: systemInstruction,
      httpClient: httpClient,
    );

    for (var attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        return await model.generateContent(content);
      } catch (exc) {
        final isLastAttempt = attempt == maxAttempts - 1;
        if (isLastAttempt) rethrow;

        if (_isOverloadError(exc)) {
          await Future.delayed(Duration(seconds: 2 * (attempt + 1)));
          continue;
        }
        if (_isQuotaError(exc)) {
          await Future.delayed(_parseRetryAfter(exc) ?? _defaultQuotaWait);
          continue;
        }
        rethrow;
      }
    }
    throw StateError('generateContent hicbir deneme yapmadan basarisiz oldu.');
  }

  String _friendlyMessage(Object exc) {
    if (_isQuotaError(exc)) {
      return 'Şu an çok fazla istek yapıldı ve ücretsiz kullanım kotası '
          'doldu. Birkaç saniye bekleyip tekrar dener misin?';
    }
    if (_isOverloadError(exc)) {
      return 'Google\'ın sunucuları şu an yoğun. Birazdan tekrar dener misin?';
    }
    if (_isModelRetiredError(exc)) {
      return 'Kullanılan yapay zeka modeli güncellenmiş görünüyor. '
          'Lütfen tekrar dener misin?';
    }
    if (_isNetworkError(exc)) {
      return 'İnternet bağlantısı kurulamadı. Bağlantını kontrol edip '
          'tekrar dener misin?';
    }
    return 'Bir şeyler ters gitti, tekrar dener misin?';
  }

  bool _isOverloadError(Object exc) {
    final text = exc.toString().toLowerCase();
    return text.contains('503') ||
        text.contains('unavailable') ||
        text.contains('overloaded');
  }

  bool _isModelRetiredError(Object exc) {
    final text = exc.toString().toLowerCase();
    return text.contains('404') ||
        text.contains('not_found') ||
        text.contains('no longer available');
  }

  bool _isQuotaError(Object exc) {
    final text = exc.toString().toLowerCase();
    return text.contains('429') ||
        text.contains('quota') ||
        text.contains('resource_exhausted');
  }

  bool _isNetworkError(Object exc) {
    final text = exc.toString().toLowerCase();
    return text.contains('socketexception') ||
        text.contains('failed host lookup') ||
        text.contains('network is unreachable') ||
        text.contains('connection refused') ||
        text.contains('connection closed');
  }

  Duration? _parseRetryAfter(Object exc) {
    final match = _retryAfterPattern.firstMatch(exc.toString());
    if (match == null) return null;
    final seconds = double.tryParse(match.group(1)!);
    if (seconds == null) return null;
    final capped = seconds.clamp(1.0, _maxQuotaWait.inSeconds.toDouble());
    return Duration(milliseconds: (capped * 1000).round());
  }
}
