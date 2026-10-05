import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../api/api_client.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/charts.dart';
import '../../widgets/onboarding.dart';
import '../../widgets/common.dart';

/// Platform overview — mirrors the sample "FoodBridge – AI Food Waste Reduction Platform" dashboard.
class AdminDashboardScreen extends StatelessWidget {
  const AdminDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return RemoteView<Json>(
      load: () async => toJ(await api.get('/analytics/admin/', query: {'days': 30})),
      builder: (context, d, reload) {
        final k = toJ(d['kpis']);
        final cats = toL(d['rescued_by_category']);
        final donors = toL(d['top_donors']);
        final ops = toL(d['recent_operations']);
        final maxDonor = donors.isEmpty ? 1.0 : donors.map((e) => toD(e['kg'])).reduce((a, b) => a > b ? a : b);
        return PageScaffold(
          title: 'Dashboard',
          subtitle: 'Platform-wide surplus redistribution · last 30 days',
          onRefresh: reload,
          children: [
            const GettingStartedCard(role: Role.admin),
            ResponsiveGrid(children: [
              KpiCard(
                  label: 'Listings Active',
                  value: fmtInt(toI(k['listings_active'])),
                  caption: '${fmtInt(toI(k['donors']))} donor businesses',
                  color: FB.leaf),
              KpiCard(
                  label: 'Food Rescued',
                  value: fmtKg(toD(k['food_rescued_kg'])),
                  caption: '${fmtKg(toD(k['food_rescued_period_kg']))} in the last 30 days',
                  color: FB.amber),
              KpiCard(
                  label: 'CO₂ Prevented',
                  value: fmtKg(toD(k['co2e_avoided_kg'])),
                  caption: '${fmtInt(toI(k['meals']))} meals provided',
                  color: FB.sky),
              KpiCard(
                  label: 'NGOs Active',
                  value: fmtInt(toI(k['ngos_active'])),
                  caption: 'receiving partners',
                  color: FB.violet),
            ]),
            const SizedBox(height: 14),
            SplitRow(
              left: SectionCard(
                title: 'Food Rescued by Category (kg — Last 30 Days)',
                child: CategoryBarChart(
                  height: 260,
                  data: cats
                      .map((c) => ChartDatum(toS(c['category']).split(' ').first, toD(c['kg']), hexColor(toS(c['color']))))
                      .toList(),
                ),
              ),
              right: SectionCard(
                title: 'Top Donor Partners',
                child: donors.isEmpty
                    ? const Text('No deliveries in this period.', style: TextStyle(color: FB.muted))
                    : Column(
                        children: donors.asMap().entries.map((e) {
                          final kg = toD(e.value['kg']);
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 7),
                            child: Row(children: [
                              CircleAvatar(
                                radius: 14,
                                backgroundColor: FB.chart[e.key % FB.chart.length].withOpacity(.15),
                                child: Text('${e.key + 1}',
                                    style: TextStyle(
                                        fontSize: 12, fontWeight: FontWeight.w800, color: FB.chart[e.key % FB.chart.length])),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: MeterBar(
                                  label: toS(e.value['donor']),
                                  value: maxDonor == 0 ? 0 : kg / maxDonor,
                                  color: FB.chart[e.key % FB.chart.length],
                                  trailing: fmtKg(kg),
                                ),
                              ),
                            ]),
                          );
                        }).toList(),
                      ),
              ),
            ),
            const SizedBox(height: 14),
            SectionCard(
              title: 'Recent Rescue Operations',
              padding: const EdgeInsets.fromLTRB(8, 18, 8, 8),
              child: ops.isEmpty
                  ? const EmptyState(icon: Icons.local_shipping_outlined, title: 'No operations yet')
                  : DataTableCard(
                      columns: const ['Listing ID', 'Donor', 'Food Type', 'Qty (kg)', 'NGO Assigned', 'Status'],
                      onTap: ops
                          .map<VoidCallback?>((o) => o['pickup_id'] == null ? null : () => context.go('/pickups/${toI(o['pickup_id'])}'))
                          .toList(),
                      rows: ops
                          .map((o) => <Widget>[
                                Text(toS(o['listing_id']), style: const TextStyle(fontWeight: FontWeight.w700, color: FB.forest)),
                                Text(toS(o['donor'])),
                                Text(toS(o['food_type'])),
                                Text(fmtNum(toD(o['kg']))),
                                Text(toS(o['ngo'])),
                                StatusChip(toS(o['status'])),
                              ])
                          .toList(),
                    ),
            ),
            const SizedBox(height: 14),
            SectionCard(
              title: 'Monthly food rescued (kg)',
              child: TrendLineChart(
                labels: toL(d['monthly']).map((m) => toS(m['month'])).toList(),
                values: toL(d['monthly']).map((m) => toD(m['kg'])).toList(),
                color: FB.amber,
              ),
            ),
          ],
        );
      },
    );
  }
}
