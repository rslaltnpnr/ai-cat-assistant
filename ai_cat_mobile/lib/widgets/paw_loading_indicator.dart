import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Kedi "dusunurken" gosterilen, art arda parlayan pati izlerinden olusan
/// hafif bir loading animasyonu. Masaustu uygulamasindaki
/// `PawLoadingIndicator` (main.py) ile ayni gorsel dili paylasir - disaridan
/// gorsel dosyasi gerektirmez, tamami CustomPainter ile cizilir.
class PawLoadingIndicator extends StatefulWidget {
  final Color color;
  final double size;
  final int pawCount;

  const PawLoadingIndicator({
    super.key,
    this.color = const Color(0xFF5AAAFF),
    this.size = 28,
    this.pawCount = 4,
  });

  @override
  State<PawLoadingIndicator> createState() => _PawLoadingIndicatorState();
}

class _PawLoadingIndicatorState extends State<PawLoadingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size * (widget.pawCount + 1) * 0.55,
      height: widget.size,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) => CustomPaint(
          painter: _PawPainter(
            phase: _controller.value * 2 * math.pi,
            color: widget.color,
            pawCount: widget.pawCount,
          ),
        ),
      ),
    );
  }
}

class _PawPainter extends CustomPainter {
  final double phase;
  final Color color;
  final int pawCount;

  _PawPainter({
    required this.phase,
    required this.color,
    required this.pawCount,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final spacing = size.width / (pawCount + 1);
    final cy = size.height / 2;
    for (var i = 0; i < pawCount; i++) {
      final wave = (math.sin(phase - i * 0.9) + 1) / 2;
      final scale = 0.65 + 0.35 * wave;
      final opacity = 0.25 + 0.75 * wave;
      _drawPaw(canvas, Offset(spacing * (i + 1), cy), scale, opacity);
    }
  }

  void _drawPaw(Canvas canvas, Offset center, double scale, double opacity) {
    final paint = Paint()
      ..color = color.withValues(alpha: opacity.clamp(0.0, 1.0));
    canvas.drawOval(
      Rect.fromCenter(
        center: center + Offset(0, 5 * scale),
        width: 18 * scale,
        height: 14 * scale,
      ),
      paint,
    );
    const toeOffsets = [
      Offset(-8, -6),
      Offset(-3, -10),
      Offset(3, -10),
      Offset(8, -6),
    ];
    for (final off in toeOffsets) {
      canvas.drawOval(
        Rect.fromCenter(
          center: center + Offset(off.dx * scale, off.dy * scale),
          width: 8 * scale,
          height: 11 * scale,
        ),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _PawPainter oldDelegate) =>
      oldDelegate.phase != phase || oldDelegate.color != color;
}
