import 'dart:async';

import 'package:ai_cat_mobile/screens/home_screen.dart';

/// Testler icin genel kurulum: HomeScreen'in ilk-calistirma sihirbazini
/// otomatik acma davranisini kapatir (bkz. HomeScreen.onboardingCheckEnabled).
/// Acik kalsaydi, bos SharedPreferences ile pompalanan her tam-uygulama
/// testinde OnboardingWizard modali beklenmedik sekilde ekrani kaplayip
/// diger etkilesimleri (orn. Ayarlar simgesine dokunma) engellerdi.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  HomeScreen.onboardingCheckEnabled = false;
  await testMain();
}
