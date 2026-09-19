import 'dart:async';

import 'package:flutter/material.dart';

enum CatState { norm, zzz, smile, stern, fear }

/// Durum bazinda kedi gorseli. assets/cat/ altinda ilgili PNG yoksa
/// (masaustu surumundeki gibi) basit bir yer tutucu daire cizer, boylece
/// gercek gorseller eklenmeden once de uygulama sorunsuz calisir.
///
/// "norm" durumunda statik bir gorsel yerine gercek bir yuruyus kare
/// dizisi (fuff_walk_000.png, fuff_walk_001.png, ...) dondurulur - bkz.
/// masaustu surumundeki ayni mantik (main.py, CatCharacter._load_walk_frames).
class CatSprite extends StatefulWidget {
  /// Blender "Walk" action'inin render edildigi kare sayisi. Masaustu
  /// tarafiyla ayni kaynaktan uretildigi icin sabit kodlanmistir.
  static const int walkFrameCount = 28;
  static const Duration walkFrameInterval = Duration(milliseconds: 90);

  /// Widget testlerinde surekli/sonsuz bir Timer, `pumpAndSettle()`'in hic
  /// "durulmamasina" (timeout) yol acar - bu yuzden test/flutter_test_config.dart
  /// bunu false yapip yuruyus animasyonunu test suresince kapatir. Normal
  /// calismada her zaman true'dur.
  static bool walkAnimationEnabled = true;

  final CatState state;
  final double size;
  final String skinFolder;

  const CatSprite({
    super.key,
    required this.state,
    required this.size,
    this.skinFolder = 'assets/cat',
  });

  @override
  State<CatSprite> createState() => _CatSpriteState();
}

class _CatSpriteState extends State<CatSprite> {
  Timer? _timer;
  int _frameIndex = 0;

  @override
  void initState() {
    super.initState();
    _syncWalkAnim();
  }

  @override
  void didUpdateWidget(covariant CatSprite oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) {
      _frameIndex = 0;
      _syncWalkAnim();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _syncWalkAnim() {
    _timer?.cancel();
    _timer = null;
    if (widget.state != CatState.norm || !CatSprite.walkAnimationEnabled) {
      return;
    }
    _timer = Timer.periodic(CatSprite.walkFrameInterval, (_) {
      if (!mounted) return;
      setState(() {
        _frameIndex = (_frameIndex + 1) % CatSprite.walkFrameCount;
      });
    });
  }

  String get _fileName {
    switch (widget.state) {
      case CatState.norm:
        return 'fuff_walk_${_frameIndex.toString().padLeft(3, '0')}.png';
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
      '${widget.skinFolder}/$_fileName',
      width: widget.size,
      height: widget.size,
      // Yuruyus kareleri henuz eklenmemisse (veya bu skin'de yoksa) statik
      // "norm" gorseline, o da yoksa yer tutucuya geri duser.
      errorBuilder: (context, error, stackTrace) {
        if (widget.state == CatState.norm) {
          return Image.asset(
            '${widget.skinFolder}/fuff_norm.png',
            width: widget.size,
            height: widget.size,
            errorBuilder: (context, error, stackTrace) => _placeholder(),
          );
        }
        return _placeholder();
      },
    );
  }

  Widget _placeholder() {
    return Container(
      width: widget.size,
      height: widget.size,
      decoration: const BoxDecoration(
        color: Color(0xFF5AAAFF),
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Text(
        widget.state.name,
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
