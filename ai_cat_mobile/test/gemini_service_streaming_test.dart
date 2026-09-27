import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:ai_cat_mobile/services/gemini_service.dart';

/// Gemini SDK'sinin akis istekleri Server-Sent Events (?alt=sse) formati
/// kullanir: her satir "data: {json}\n\n" seklinde bir GenerateContentResponse
/// parcasi tasir (bkz. google_generative_ai paketinin client.dart'i). Bu
/// sahte istemci, gercek ag olmadan bu formati taklit ederek
/// GeminiService.askStream'in retry/fallback/mid-stream-hata mantigini
/// gercekten HTTP katmaninda dogrular.
class _ScriptedHttpClient extends http.BaseClient {
  final List<Object> _script;
  int _index = 0;
  final List<String> capturedModels = [];

  _ScriptedHttpClient(this._script);

  static String _sseChunk(String text) {
    final json = jsonEncode({
      'candidates': [
        {
          'content': {
            'parts': [
              {'text': text},
            ],
            'role': 'model',
          },
        },
      ],
    });
    return 'data: $json\n\n';
  }

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final match = RegExp(r'models/([^:]+):').firstMatch(request.url.path);
    capturedModels.add(match?.group(1) ?? '?');

    final entry = _script[_index++];

    if (entry is _ErrorScript) {
      final body = jsonEncode({
        'error': {'message': entry.message},
      });
      return http.StreamedResponse(
        Stream.value(utf8.encode(body)),
        entry.statusCode,
      );
    }

    if (entry is _MidStreamErrorScript) {
      final controller = StreamController<List<int>>();
      controller.add(utf8.encode(_sseChunk(entry.firstText)));
      // Bozuk bir satir (gecerli olmayan JSON) - SDK'nin satir okuma
      // dongusunde bir FormatException firlatarak baglanti kopmasini
      // taklit eder (bkz. streamRequest, LineSplitter uzerinden gecen her
      // satir jsonDecode edilir).
      controller.add(utf8.encode('data: {bozuk-json\n\n'));
      controller.close();
      return http.StreamedResponse(controller.stream, 200);
    }

    final texts = entry as List<String>;
    final body = texts.map(_sseChunk).join();
    return http.StreamedResponse(Stream.value(utf8.encode(body)), 200);
  }
}

class _ErrorScript {
  final int statusCode;
  final String message;
  _ErrorScript(this.statusCode, this.message);
}

class _MidStreamErrorScript {
  final String firstText;
  _MidStreamErrorScript(this.firstText);
}

Future<({List<String> chunks, String? answer, Object? error})> _collect(
  Stream<String> stream,
) async {
  final chunks = <String>[];
  try {
    await for (final piece in stream) {
      chunks.add(piece);
    }
    return (chunks: chunks, answer: chunks.join(), error: null);
  } catch (exc) {
    return (chunks: chunks, answer: null, error: exc);
  }
}

void main() {
  group('GeminiService.askStream (gercek SSE HTTP katmani)', () {
    test('basit akis parca parca birikir', () async {
      final client = _ScriptedHttpClient([
        ['Merhaba', ', ', 'dunya!'],
      ]);
      final service = GeminiService(httpClient: client);
      final result = await _collect(
        service.askStream(
          apiKey: 'test-key',
          modelName: 'gemini-flash-latest',
          characterName: 'Fuff',
          question: 'soru',
        ),
      );
      expect(result.chunks, ['Merhaba', ', ', 'dunya!']);
      expect(result.answer, 'Merhaba, dunya!');
      expect(client.capturedModels, ['gemini-flash-latest']);
    });

    test('ilk parcada asiri yuklenme hatasi ayni modelde tekrar dener', () async {
      final client = _ScriptedHttpClient([
        _ErrorScript(503, '503 UNAVAILABLE: model overloaded'),
        ['ikinci denemede basarili'],
      ]);
      final service = GeminiService(httpClient: client);
      final result = await _collect(
        service.askStream(
          apiKey: 'test-key',
          modelName: 'gemini-flash-latest',
          characterName: 'Fuff',
          question: 'soru',
        ),
      );
      expect(result.answer, 'ikinci denemede basarili');
      expect(client.capturedModels, [
        'gemini-flash-latest',
        'gemini-flash-latest',
      ]);
    });

    test('ana model tukenince yedek modele gecer', () async {
      final client = _ScriptedHttpClient([
        _ErrorScript(503, '503 overloaded'),
        _ErrorScript(503, '503 overloaded'),
        _ErrorScript(503, '503 overloaded'),
        ['yedek modelden yanit'],
      ]);
      final service = GeminiService(httpClient: client);
      final result = await _collect(
        service.askStream(
          apiKey: 'test-key',
          modelName: 'gemini-flash-latest',
          characterName: 'Fuff',
          question: 'soru',
        ),
      );
      expect(result.answer, 'yedek modelden yanit');
      expect(client.capturedModels.last, GeminiService.fallbackModel);
    });

    test('model kaldirilmis (404) hatasinda da yedek modele gecer', () async {
      final client = _ScriptedHttpClient([
        _ErrorScript(404, '404 NOT_FOUND: model no longer available'),
        ['yedek modelden yanit'],
      ]);
      final service = GeminiService(httpClient: client);
      final result = await _collect(
        service.askStream(
          apiKey: 'test-key',
          modelName: 'gemini-flash-latest',
          characterName: 'Fuff',
          question: 'soru',
        ),
      );
      expect(result.answer, 'yedek modelden yanit');
      expect(client.capturedModels, [
        'gemini-flash-latest',
        GeminiService.fallbackModel,
      ]);
    });

    test(
      'akis basladiktan sonraki hata yeniden denenmez, dogrudan hata verir',
      () async {
        final client = _ScriptedHttpClient([
          _MidStreamErrorScript('kismi cevap '),
        ]);
        final service = GeminiService(httpClient: client);
        final result = await _collect(
          service.askStream(
            apiKey: 'test-key',
            modelName: 'gemini-flash-latest',
            characterName: 'Fuff',
            question: 'soru',
          ),
        );
        // Ilk parca zaten yayinlanmis olmali.
        expect(result.chunks, ['kismi cevap ']);
        expect(result.error, isA<GeminiRequestException>());
        // Fallback modele GECILMEDI - sadece 1 istek atildi.
        expect(client.capturedModels, ['gemini-flash-latest']);
      },
    );

    test('asiri yuklenme disi hata (400) hemen hata verir, fallback denenmez', () async {
      final client = _ScriptedHttpClient([
        _ErrorScript(400, 'Bad Request: gecersiz istek'),
      ]);
      final service = GeminiService(httpClient: client);
      final result = await _collect(
        service.askStream(
          apiKey: 'test-key',
          modelName: 'gemini-flash-latest',
          characterName: 'Fuff',
          question: 'soru',
        ),
      );
      expect(result.chunks, isEmpty);
      expect(result.error, isA<GeminiRequestException>());
      expect(client.capturedModels, ['gemini-flash-latest']);
    });
  });
}
