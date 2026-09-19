import 'dart:async';

import 'package:ai_cat_mobile/widgets/cat_sprite.dart';

/// Widget testleri baslamadan once calisir (Flutter test framework'unun
/// standart mekanizmasi). CatSprite'in "norm" durumundaki surekli yuruyus
/// Timer'i kapatilir - aksi halde RoamingCat mounted iken herhangi bir
/// `pumpAndSettle()` cagrisi hic "durulmaz" ve timeout ile patlar (Timer
/// her 90ms'de bir setState tetikleyip yeni kare planladigi icin).
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  CatSprite.walkAnimationEnabled = false;
  await testMain();
}
