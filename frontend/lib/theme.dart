import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// FoodBridge palette — forest canopy greens with harvest amber accents.
class FB {
  static const forest = Color(0xFF14452F); // top bar, primary ink-green
  static const forestDeep = Color(0xFF0E3322);
  static const leaf = Color(0xFF1FA463); // active, success
  static const leafSoft = Color(0xFFE3F4EA);
  static const mint = Color(0xFFF0F7F1); // sidebar
  static const amber = Color(0xFFE8A33D); // highlights, "in transit"
  static const amberSoft = Color(0xFFFFF4E0);
  static const tomato = Color(0xFFD9534F); // risk
  static const tomatoSoft = Color(0xFFFCE9E8);
  static const sky = Color(0xFF3AAFD9);
  static const skySoft = Color(0xFFE5F4FA);
  static const violet = Color(0xFF6C63FF);
  static const violetSoft = Color(0xFFEEEDFF);
  static const surface = Color(0xFFF6F8F5);
  static const card = Colors.white;
  static const ink = Color(0xFF1C2B22);
  static const muted = Color(0xFF66756B);
  static const line = Color(0xFFE2E8E3);

  static const chart = [
    Color(0xFFF07B22), Color(0xFFE5B21E), leaf, sky, Color(0xFFA0522D), violet,
    Color(0xFFE05297), Color(0xFF2E9C9C), Color(0xFF8A9A2B), Color(0xFF5B7BD5),
  ];

  static TextStyle display(double size, {Color color = ink, FontWeight weight = FontWeight.w600}) =>
      GoogleFonts.getFont('Fraunces', fontSize: size, color: color, fontWeight: weight, height: 1.1);

  static Color risk(String level) => switch (level) {
        'critical' => tomato,
        'high' => const Color(0xFFEF7D3C),
        'medium' => amber,
        'low' => leaf,
        _ => muted,
      };

  static Color statusColor(String s) => switch (s) {
        'completed' || 'picked_up' || 'available' || 'active' || 'done' => leaf,
        'in_transit' || 'reserved' || 'expiring' || 'listed' => amber,
        'confirmed' || 'scheduled' => violet,
        'requested' => sky,
        'cancelled' || 'no_show' || 'expired' || 'failed' || 'critical' => tomato,
        _ => muted,
      };
}

ThemeData buildTheme() {
  final base = ThemeData(useMaterial3: true, brightness: Brightness.light);
  final text = GoogleFonts.getTextTheme('DM Sans', base.textTheme).apply(bodyColor: FB.ink, displayColor: FB.ink);
  final scheme = ColorScheme.fromSeed(
    seedColor: FB.forest,
    primary: FB.forest,
    secondary: FB.leaf,
    tertiary: FB.amber,
    error: FB.tomato,
    surface: FB.card,
  );
  final radius = BorderRadius.circular(10);
  return base.copyWith(
    colorScheme: scheme,
    scaffoldBackgroundColor: FB.surface,
    textTheme: text,
    dividerTheme: const DividerThemeData(color: FB.line, thickness: 1, space: 1),
    appBarTheme: AppBarTheme(
      backgroundColor: FB.forest,
      foregroundColor: Colors.white,
      elevation: 0,
      titleTextStyle: text.titleMedium?.copyWith(color: Colors.white, fontWeight: FontWeight.w700),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(borderRadius: radius, borderSide: const BorderSide(color: FB.line)),
      enabledBorder: OutlineInputBorder(borderRadius: radius, borderSide: const BorderSide(color: FB.line)),
      focusedBorder: OutlineInputBorder(borderRadius: radius, borderSide: const BorderSide(color: FB.leaf, width: 1.6)),
      labelStyle: const TextStyle(color: FB.muted),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: FB.forest,
        foregroundColor: Colors.white,
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: radius),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: FB.forest,
        side: const BorderSide(color: FB.line),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: radius),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: FB.forest, textStyle: const TextStyle(fontWeight: FontWeight.w600)),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating, backgroundColor: FB.forestDeep),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: FB.forestDeep, borderRadius: BorderRadius.circular(6)),
      textStyle: const TextStyle(color: Colors.white, fontSize: 12),
      waitDuration: const Duration(milliseconds: 400),
    ),
  );
}
