import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:ai_cat_mobile/services/settings_service.dart';
import 'package:ai_cat_mobile/theme/app_colors.dart';
import 'package:ai_cat_mobile/widgets/onboarding_wizard.dart';

Future<SettingsService> _openWizard(WidgetTester tester) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final settings = SettingsService(prefs);

  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData(extensions: const [AppColors.dark]),
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () => showDialog(
              context: context,
              barrierDismissible: false,
              builder: (_) => OnboardingWizard(settings: settings),
            ),
            child: const Text('Aç'),
          ),
        ),
      ),
    ),
  );

  await tester.tap(find.text('Aç'));
  await tester.pumpAndSettle();
  return settings;
}

void main() {
  testWidgets('ilk sayfada hos geldin metni ve adim 1/4 gorunur', (
    tester,
  ) async {
    await _openWizard(tester);
    expect(find.text('Merhaba!'), findsOneWidget);
    expect(find.text('Adım 1/4'), findsOneWidget);
    expect(find.text('Daha Sonra'), findsOneWidget);
  });

  testWidgets(
    '"Daha Sonra" hicbir adimi tamamlamadan sihirbazi kapatir ve tamamlanmis isaretler',
    (tester) async {
      final settings = await _openWizard(tester);
      expect(settings.onboardingCompleted, isFalse);

      await tester.tap(find.text('Daha Sonra'));
      await tester.pumpAndSettle();

      expect(settings.onboardingCompleted, isTrue);
      expect(find.text('Merhaba!'), findsNothing);
    },
  );

  testWidgets(
    'Ileri ile son adima kadar gidilebilir ve Baslat ismi/API anahtarini kaydeder',
    (tester) async {
      final settings = await _openWizard(tester);

      // Sayfa 1 (Hos Geldin) -> 2 (Isim)
      await tester.tap(find.text('İleri'));
      await tester.pumpAndSettle();
      expect(find.text('İsim'), findsOneWidget);

      await tester.enterText(find.byType(TextField).first, 'Pati');

      // Sayfa 2 -> 3 (API Key)
      await tester.tap(find.text('İleri'));
      await tester.pumpAndSettle();
      expect(find.text('Gemini API Anahtarı'), findsOneWidget);

      await tester.enterText(find.byType(TextField).first, 'gizli-anahtar');

      // Sayfa 3 -> 4 (Hazirsin)
      await tester.tap(find.text('İleri'));
      await tester.pumpAndSettle();
      expect(find.text('Hazırsın!'), findsOneWidget);
      expect(find.text('Başla'), findsOneWidget);

      await tester.tap(find.text('Başla'));
      await tester.pumpAndSettle();

      expect(settings.characterName, 'Pati');
      expect(settings.apiKey, 'gizli-anahtar');
      expect(settings.onboardingCompleted, isTrue);
    },
  );

  testWidgets('Geri butonu bir onceki adima doner', (tester) async {
    await _openWizard(tester);

    await tester.tap(find.text('İleri'));
    await tester.pumpAndSettle();
    expect(find.text('İsim'), findsOneWidget);

    await tester.tap(find.text('Geri'));
    await tester.pumpAndSettle();
    expect(find.text('Merhaba!'), findsOneWidget);
  });
}
