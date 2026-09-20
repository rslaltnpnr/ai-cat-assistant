import 'package:flutter/material.dart';

enum CatState { norm, zzz, smile, stern, fear }

/// Durum bazinda kedi gorseli. assets/cat/ altinda ilgili PNG yoksa
/// (masaustu surumundeki gibi) basit bir yer tutucu daire cizer, boylece
/// gercek gorseller eklenmeden once de uygulama sorunsuz calisir.
class CatSprite extends StatelessWidget {
  final CatState state;
  final double size;
  final String skinFolder;

  const CatSprite({
    super.key,
    required this.state,
    required this.size,
    this.skinFolder = 'assets/cat',
  });

  String get _fileName {
    switch (state) {
      case CatState.norm:
        return 'fuff_norm.png';
      case CatState.zzz:
        return 'fuff_zzz.png';
      case CatState.smile:
        return 'fuff_smile.png';
      case CatState.stern:
        return 'fuff_stern.png';
      case CatState.fear:
        return 'fuff_fear.png';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      '$skinFolder/$_fileName',
      width: size,
      height: size,
      errorBuilder: (context, error, stackTrace) => _placeholder(),
    );
  }

  Widget _placeholder() {
    return Container(
      width: size,
      height: size,
      decoration: const BoxDecoration(
        color: Color(0xFF5AAAFF),
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Text(
        state.name,
        textAlign: TextAlign.center,
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.bold,
          fontSize: 10,
        ),
      ),
    );
  }
}
