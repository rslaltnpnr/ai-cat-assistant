import 'dart:async';

import 'package:ai_cat_mobile/screens/home_screen.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Testler icin genel kurulum.
///
/// 1) HomeScreen'in ilk-calistirma sihirbazini otomatik acma davranisini
///    kapatir (bkz. HomeScreen.onboardingCheckEnabled). Acik kalsaydi, bos
///    SharedPreferences ile pompalanan her tam-uygulama testinde
///    OnboardingWizard modali beklenmedik sekilde ekrani kaplayip diger
///    etkilesimleri (orn. Ayarlar simgesine dokunma) engellerdi.
///
/// 2) flutter_secure_storage'in platform kanalini (bkz.
///    SettingsService.apiKey) bellek-ici sahte bir kasayla mock'lar.
///    Gercek cihazda olmayan bir test ortaminda bu kanala yapilan
///    cagrilar hicbir zaman yanit vermez - mock olmadan
///    SettingsService.create() sonsuza kadar beklerdi (pumpAndSettle
///    timeout). Her test oncesi/sonrasi setUp/tearDown ile kaydedilip
///    kaldirilir, boylece testler arasinda sizinti olmaz.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  HomeScreen.onboardingCheckEnabled = false;
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('plugins.it_nomads.com/flutter_secure_storage');
  final store = <String, String>{};

  Future<Object?> handle(MethodCall call) async {
    final args = call.arguments as Map?;
    final key = args?['key'] as String?;
    switch (call.method) {
      case 'read':
        return store[key];
      case 'write':
        store[key!] = args!['value'] as String;
        return null;
      case 'delete':
        store.remove(key);
        return null;
      case 'containsKey':
        return store.containsKey(key);
      case 'readAll':
        return Map<String, String>.from(store);
      case 'deleteAll':
        store.clear();
        return null;
      default:
        return null;
    }
  }

  setUp(() {
    store.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, handle);
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  await testMain();
}
