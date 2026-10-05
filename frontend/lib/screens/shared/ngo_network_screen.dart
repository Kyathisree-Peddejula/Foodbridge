import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';

double? _haversine(double? lat1, double? lng1, double? lat2, double? lng2) {
  if (lat1 == null || lng1 == null || lat2 == null || lng2 == null) return null;
  const r = 6371.0;
  final dLat = (lat2 - lat1) * math.pi / 180;
  final dLng = (lng2 - lng1) * math.pi / 180;
  final a = math.pow(math.sin(dLat / 2), 2) +
      math.cos(lat1 * math.pi / 180) * math.cos(lat2 * math.pi / 180) * math.pow(math.sin(dLng / 2), 2);
  return 2 * r * math.asin(math.sqrt(a.toDouble()));
}

class NgoNetworkScreen extends StatefulWidget {
  const NgoNetworkScreen({super.key});
  @override
  State<NgoNetworkScreen> createState() => _NgoNetworkScreenState();
}

class _NgoNetworkScreenState extends State<NgoNetworkScreen> {
  String _q = '';

  @override
  Widget build(BuildContext context) {
    final org = context.watch<AuthState>().org;
    final myLat = toDn(org['latitude']);
    final myLng = toDn(org['longitude']);
    return RemoteView<List<Json>>(
      load: () async => toL(await api.get('/organizations/ngo-network/')),
      builder: (context, rows, reload) {
        final list = rows
            .where((n) => _q.isEmpty || '${n['name']} ${n['city']} ${n['kind']}'.toLowerCase().contains(_q.toLowerCase()))
            .map((n) => <String, dynamic>{...n, '_km': _haversine(myLat, myLng, toDn(n['latitude']), toDn(n['longitude']))})
            .toList()
          ..sort((a, b) => (toDn(a['_km']) ?? 1e9).compareTo(toDn(b['_km']) ?? 1e9));
        final people = rows.fold<int>(0, (a, n) => a + toI(n['beneficiaries']));
        final cap = rows.fold<double>(0, (a, n) => a + toD(n['daily_capacity_kg']));
        return PageScaffold(
          title: 'NGO network',
          subtitle: 'Food banks, shelters and community kitchens receiving surplus on FoodBridge',
          onRefresh: reload,
          children: [
            ResponsiveGrid(minTileWidth: 200, children: [
              KpiCard(label: 'Partner NGOs', value: fmtInt(rows.length), color: FB.forest, icon: Icons.groups_rounded),
              KpiCard(label: 'People served', value: fmtInt(people), color: FB.amber, icon: Icons.diversity_3_rounded),
              KpiCard(label: 'Daily intake capacity', value: fmtKg(cap), color: FB.leaf, icon: Icons.scale_rounded),
            ]),
            const SizedBox(height: 14),
            SizedBox(
              width: 340,
              child: TextField(
                decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Search by name, city or type'),
                onChanged: (v) => setState(() => _q = v),
              ),
            ),
            const SizedBox(height: 14),
            ResponsiveGrid(
              minTileWidth: 300,
              children: list.map((n) {
                final km = toDn(n['_km']);
                return SectionCard(
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    CircleAvatar(
                      radius: 22,
                      backgroundColor: FB.leafSoft,
                      child: Text(toS(n['name']).isEmpty ? '?' : toS(n['name'])[0],
                          style: FB.display(18, color: FB.forest)),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(toS(n['name']), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                        Text('${titleCase(toS(n['kind']))} · ${toS(n['city'])}', style: const TextStyle(color: FB.muted, fontSize: 12.5)),
                        const SizedBox(height: 8),
                        Wrap(spacing: 6, runSpacing: 6, children: [
                          Pill('${fmtInt(toI(n['beneficiaries']))} people', color: FB.amber, icon: Icons.people_alt_rounded),
                          Pill('${fmtKg(toD(n['daily_capacity_kg']))}/day', color: FB.leaf, icon: Icons.scale_rounded),
                          if (km != null) Pill('${km.toStringAsFixed(1)} km', color: FB.sky, icon: Icons.near_me_rounded),
                        ]),
                        const SizedBox(height: 6),
                        Text(toS(n['address']), style: const TextStyle(fontSize: 12, color: FB.muted)),
                        if (toS(n['phone']).isNotEmpty) Text(toS(n['phone']), style: const TextStyle(fontSize: 12, color: FB.muted)),
                      ]),
                    ),
                  ]),
                );
              }).toList(),
            ),
          ],
        );
      },
    );
  }
}
