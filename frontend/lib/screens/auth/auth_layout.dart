import 'package:flutter/material.dart';

import '../../theme.dart';

/// Split layout: brand panel (wide screens) + form card.
class AuthLayout extends StatelessWidget {
  final Widget child;
  const AuthLayout({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    final form = Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 440), child: child),
      ),
    );
    if (!wide) {
      return Scaffold(
        backgroundColor: FB.surface,
        body: SafeArea(
          child: Column(children: [
            Container(
              width: double.infinity,
              color: FB.forest,
              padding: const EdgeInsets.fromLTRB(24, 22, 24, 22),
              child: const _Brand(compact: true),
            ),
            Expanded(child: form),
          ]),
        ),
      );
    }
    return Scaffold(
      backgroundColor: FB.surface,
      body: Row(children: [
        Expanded(
          flex: 5,
          child: Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [FB.forest, FB.forestDeep],
              ),
            ),
            padding: const EdgeInsets.all(56),
            child: const _Brand(),
          ),
        ),
        Expanded(flex: 4, child: form),
      ]),
    );
  }
}

class _Brand extends StatelessWidget {
  final bool compact;
  const _Brand({this.compact = false});

  @override
  Widget build(BuildContext context) {
    final logo = Row(children: [
      Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(color: FB.leaf, borderRadius: BorderRadius.circular(11)),
        child: const Icon(Icons.eco_rounded, color: Colors.white),
      ),
      const SizedBox(width: 12),
      Text('FoodBridge', style: FB.display(26, color: Colors.white)),
    ]);
    if (compact) return logo;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      logo,
      const Spacer(),
      Text('Surplus food,\nrescued before\nit becomes waste.', style: FB.display(46, color: Colors.white)),
      const SizedBox(height: 20),
      const Text(
        'Forecast demand, catch expiring stock early, and match every surplus kilogram '
        'to the nearest NGO that can use it.',
        style: TextStyle(color: Color(0xCCFFFFFF), fontSize: 16, height: 1.5),
      ),
      const SizedBox(height: 36),
      const Wrap(spacing: 28, runSpacing: 16, children: [
        _Stat('Prophet + LSTM', 'demand forecasting'),
        _Stat('AI matching', 'type · quantity · distance'),
        _Stat('CO₂e tracked', 'for every pickup'),
      ]),
      const Spacer(),
    ]);
  }
}

class _Stat extends StatelessWidget {
  final String a;
  final String b;
  const _Stat(this.a, this.b);
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(a, style: const TextStyle(color: FB.amber, fontWeight: FontWeight.w800, fontSize: 15)),
        const SizedBox(height: 2),
        Text(b, style: const TextStyle(color: Color(0xB3FFFFFF), fontSize: 13)),
      ]);
}
