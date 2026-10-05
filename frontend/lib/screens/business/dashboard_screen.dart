import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/charts.dart';
import '../../widgets/onboarding.dart';
import '../../widgets/common.dart';

class BusinessDashboardScreen extends StatelessWidget {
  const BusinessDashboardScreen({super.key});

  Future<(Json, List<Json>)> _load() async {
    final r = await Future.wait([api.get('/analytics/business/'), api.get('/marketplace/listings/suggestions/')]);
    return (toJ(r[0]), toL(r[1]));
  }

  String _greeting() {
    final h = DateTime.now().hour;
    return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return RemoteView<(Json, List<Json>)>(
      load: _load,
      builder: (context, data, reload) {
        final (d, suggestions) = data;
        final k = toJ(d['kpis']);
        final impact = toJ(d['impact']);
        return PageScaffold(
          title: '${_greeting()}, ${auth.orgName}',
          subtitle: 'Inventory health, waste risk and donations at a glance · ${fmtDate(DateTime.now())}',
          onRefresh: reload,
          actions: [
            OutlinedButton.icon(
              icon: const Icon(Icons.auto_graph_rounded),
              label: const Text('Re-score waste risk'),
              onPressed: () async {
                final ok = await runAction(context, () => api.post('/predictions/risk/refresh/', {}),
                    success: 'Waste risk updated with the latest forecasts');
                if (ok) await reload();
              },
            ),
            FilledButton.icon(
              icon: const Icon(Icons.add_rounded),
              label: const Text('New listing'),
              onPressed: () => context.go('/listings/new'),
            ),
          ],
          children: [
            GettingStartedCard(role: auth.role),
            ResponsiveGrid(children: [
              KpiCard(
                  label: 'Stock value',
                  help: 'Cost value of all stock on hand (quantity × unit cost).',
                  value: fmtMoney(toD(k['stock_value'])),
                  caption: '${toI(k['active_batches'])} active batches · ${toI(k['products'])} products',
                  color: FB.forest,
                  icon: Icons.inventory_2_rounded),
              KpiCard(
                  label: 'Value at risk',
                  help: 'Cost of the stock the AI expects to remain unsold at expiry, based on the demand forecast.',
                  value: fmtMoney(toD(k['value_at_risk'])),
                  caption: '${fmtKg(toD(k['kg_at_risk']))} likely unsold',
                  color: FB.tomato,
                  icon: Icons.warning_amber_rounded),
              KpiCard(
                  label: 'Expiring in 3 days',
                  value: fmtInt(toI(k['expiring_3_days'])),
                  caption: '${toI(k['open_alerts'])} open expiry alerts',
                  color: FB.amber,
                  icon: Icons.schedule_rounded),
              KpiCard(
                  label: 'High-risk batches',
                  help: 'Batches with a waste-risk score of 60 or more. Discount or donate them first.',
                  value: fmtInt(toI(k['high_risk'])),
                  caption: 'Risk score ≥ 60',
                  color: const Color(0xFFEF7D3C),
                  icon: Icons.local_fire_department_rounded),
              KpiCard(
                  label: 'Donated this month',
                  value: fmtKg(toD(k['donated_this_month_kg'])),
                  caption: '${fmtInt(toI(impact['pickups_completed']))} pickups completed',
                  color: FB.leaf,
                  icon: Icons.volunteer_activism_rounded),
              KpiCard(
                  label: 'CO₂e prevented',
                  help: 'Greenhouse gas avoided by donating instead of wasting (category-specific kg CO₂e per kg of food).',
                  value: fmtKg(toD(k['co2e_avoided_kg'])),
                  caption: '${fmtInt(toI(k['meals_donated']))} meals donated',
                  color: FB.sky,
                  icon: Icons.eco_rounded),
            ]),
            const SizedBox(height: 14),
            if (suggestions.isNotEmpty) ...[
              _SuggestionsCard(items: suggestions),
              const SizedBox(height: 14),
            ],
            SplitRow(
              left: SectionCard(
                title: 'Waste risk by category',
                help: 'Average AI waste-risk score of active batches per food category (0–100).',
                child: CategoryBarChart(
                  data: toL(d['risk_by_category'])
                      .map((c) => ChartDatum(toS(c['category']).split(' ').first, toD(c['avg_risk']), hexColor(toS(c['color']))))
                      .toList(),
                ),
              ),
              right: SectionCard(
                title: 'Risk distribution',
                child: Center(child: _RiskDonut(dist: toJ(d['risk_distribution']))),
              ),
            ),
            const SizedBox(height: 14),
            SectionCard(
              title: 'Weekly stock flow (kg)',
              help: 'What happened to your stock each week: sold, wasted or donated.',
              trailing: _wasteRateTrend(toL(d['weekly_flow'])),
              child: () {
                final w = toL(d['weekly_flow']);
                return GroupedBarChart(labels: w.map((e) => toS(e['week'])).toList(), series: [
                  SeriesSpec('Sold', FB.forest, w.map((e) => toD(e['sold_kg'])).toList()),
                  SeriesSpec('Donated', FB.leaf, w.map((e) => toD(e['donated_kg'])).toList()),
                  SeriesSpec('Wasted', FB.tomato, w.map((e) => toD(e['wasted_kg'])).toList()),
                ]);
              }(),
            ),
            const SizedBox(height: 14),
            SplitRow(
              leftFlex: 1,
              left: SectionCard(title: 'Inventory health', child: _Health(h: toJ(d['inventory_health']))),
              right: SectionCard(
                title: 'Donation tracker',
                trailing: TextButton(onPressed: () => context.go('/listings'), child: const Text('All listings')),
                child: _DonationTracker(t: toJ(d['donation_tracker'])),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _wasteRateTrend(List<Json> w) {
    if (w.isEmpty) return const SizedBox.shrink();
    final last = toD(w.last['waste_rate']);
    return Pill('Waste rate ${fmtPct(last)} last week', color: last > 10 ? FB.tomato : FB.leaf);
  }
}

class _RiskDonut extends StatelessWidget {
  final Json dist;
  const _RiskDonut({required this.dist});
  @override
  Widget build(BuildContext context) {
    final items = ['critical', 'high', 'medium', 'low']
        .map((k) => ChartDatum(titleCase(k), toD(dist[k]), FB.risk(k)))
        .toList();
    final total = items.fold<double>(0, (a, b) => a + b.value);
    return DonutChart(data: items, centerValue: fmtInt(total), centerLabel: 'batches scored');
  }
}

class _Health extends StatelessWidget {
  final Json h;
  const _Health({required this.h});
  @override
  Widget build(BuildContext context) {
    final entries = [
      ('Healthy stock', toD(h['active']), FB.leaf),
      ('Expiring soon', toD(h['expiring']), FB.amber),
      ('Listed for donation', toD(h['listed']), FB.violet),
      ('Expired', toD(h['expired']), FB.tomato),
    ];
    final total = entries.fold<double>(0, (a, b) => a + b.$2);
    return Column(
      children: entries
          .map((e) => MeterBar(
              label: e.$1, value: total == 0 ? 0 : e.$2 / total, color: e.$3, trailing: '${e.$2.toInt()} batches'))
          .toList(),
    );
  }
}

class _DonationTracker extends StatelessWidget {
  final Json t;
  const _DonationTracker({required this.t});
  @override
  Widget build(BuildContext context) {
    final l = toJ(t['listings']);
    final p = toJ(t['pickups']);
    final recent = toL(t['recent']);
    Widget stat(String label, dynamic v, Color c) => Expanded(
          child: Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: c.withOpacity(.08), borderRadius: BorderRadius.circular(8)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(fmtInt(toI(v)), style: FB.display(20, color: c)),
              Text(label, style: const TextStyle(fontSize: 11.5, color: FB.muted)),
            ]),
          ),
        );
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(children: [
        stat('Available', l['available'], FB.leaf),
        const SizedBox(width: 8),
        stat('Awaiting', p['requested'], FB.sky),
        const SizedBox(width: 8),
        stat('Scheduled', p['confirmed'], FB.violet),
        const SizedBox(width: 8),
        stat('Delivered', p['completed'], FB.forest),
      ]),
      const SizedBox(height: 10),
      if (recent.isEmpty)
        const Padding(
          padding: EdgeInsets.all(12),
          child: Text('No donations yet — list your first surplus.', style: TextStyle(color: FB.muted)),
        ),
      ...recent.take(5).map((r) => ListTile(
            dense: true,
            contentPadding: EdgeInsets.zero,
            onTap: () => context.go('/pickups/${toI(r['id'])}'),
            leading: const CircleAvatar(
                radius: 16, backgroundColor: FB.leafSoft, child: Icon(Icons.local_shipping_rounded, size: 16, color: FB.leaf)),
            title: Text(toS(r['title']), maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text('${toS(r['ngo'])} · ${fmtKg(toD(r['kg']))} · ${timeAgo(toDate(r['when']))}'),
            trailing: StatusChip(toS(r['status'])),
          )),
    ]);
  }
}

class _SuggestionsCard extends StatelessWidget {
  final List<Json> items;
  const _SuggestionsCard({required this.items});
  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [Color(0xFFFFF8EA), Color(0xFFFDF1E9)]),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFF3DDB5)),
      ),
      padding: const EdgeInsets.all(18),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          const Icon(Icons.auto_awesome_rounded, color: FB.amber),
          const SizedBox(width: 8),
          Expanded(
            child: Text('AI donation suggestions · ${items.length} batch${items.length == 1 ? '' : 'es'} likely to go unsold',
                style: const TextStyle(fontWeight: FontWeight.w700)),
          ),
          TextButton(onPressed: () => context.go('/predictions'), child: const Text('See predictions')),
        ]),
        const SizedBox(height: 10),
        SizedBox(
          height: 150,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (context, i) {
              final b = items[i];
              return Container(
                width: 260,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(10)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(
                      child: Text(toS(b['product_name']),
                          maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700)),
                    ),
                    RiskBadge(score: toDn(b['risk_score']), level: toS(b['risk_level']), compact: true),
                  ]),
                  const SizedBox(height: 4),
                  Text(
                    '~${fmtNum(toD(b['expected_waste_qty']))} ${toS(b['product_unit'])} unsold · ${expiryLabel(toI(b['days_to_expiry']))}',
                    style: const TextStyle(fontSize: 12, color: FB.muted),
                  ),
                  const SizedBox(height: 4),
                  Expanded(
                    child: Text(toS(b['recommended_action']),
                        maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12)),
                  ),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 10)),
                      onPressed: () => context.go('/listings/new?batch=${toI(b['id'])}'),
                      child: const Text('List for donation'),
                    ),
                  ),
                ]),
              );
            },
          ),
        ),
      ]),
    );
  }
}
