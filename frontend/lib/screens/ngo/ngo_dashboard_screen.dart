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

class NgoDashboardScreen extends StatelessWidget {
  const NgoDashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return RemoteView<Json>(
      load: () async => toJ(await api.get('/analytics/ngo/')),
      builder: (context, d, reload) {
        final k = toJ(d['kpis']);
        final incoming = toL(d['incoming']);
        final history = toL(d['history']);
        final monthly = toL(d['monthly']);
        return PageScaffold(
          title: auth.orgName,
          subtitle: 'Incoming donations, pickup history and the people you reach',
          onRefresh: reload,
          actions: [
            FilledButton.icon(
              onPressed: () => context.go('/feed'),
              icon: const Icon(Icons.bolt_rounded),
              label: Text('Live donations (${toI(k['matched_donations'])})'),
            ),
          ],
          children: [
            GettingStartedCard(role: auth.role),
            ResponsiveGrid(children: [
              KpiCard(
                  label: 'Matched donations',
                  help: 'Available listings that pass your needs profile (food type, distance, cold storage, quantity).',
                  value: fmtInt(toI(k['matched_donations'])),
                  caption: '${toI(k['high_match_donations'])} strong matches (≥70)',
                  color: FB.amber,
                  icon: Icons.bolt_rounded),
              KpiCard(
                  label: 'Upcoming pickups',
                  value: fmtInt(toI(k['upcoming_pickups'])),
                  caption: 'scheduled or awaiting',
                  color: FB.violet,
                  icon: Icons.local_shipping_rounded),
              KpiCard(
                  label: 'Food received',
                  value: fmtKg(toD(k['food_received_kg'])),
                  caption: '${fmtInt(toI(k['meals_served']))} meals served',
                  color: FB.leaf,
                  icon: Icons.restaurant_rounded),
              KpiCard(
                  label: 'Beneficiaries reached',
                  help: 'Sum of people served that you recorded when confirming deliveries.',
                  value: fmtInt(toI(k['beneficiaries_reached'])),
                  caption: '${fmtKg(toD(k['co2e_avoided_kg']))} CO₂e avoided',
                  color: FB.sky,
                  icon: Icons.diversity_3_rounded),
            ]),
            const SizedBox(height: 14),
            SplitRow(
              left: SectionCard(
                title: 'Incoming donations',
                trailing: TextButton(onPressed: () => context.go('/pickups'), child: const Text('Calendar')),
                child: incoming.isEmpty
                    ? EmptyState(
                        icon: Icons.inbox_rounded,
                        title: 'No pickups scheduled',
                        message: 'Claim a donation from the live feed.',
                        action: OutlinedButton(onPressed: () => context.go('/feed'), child: const Text('Open live feed')),
                      )
                    : Column(
                        children: incoming
                            .map((p) => _IncomingTile(p: p, onTap: () => context.go('/pickups/${toI(p['id'])}')))
                            .toList()),
              ),
              right: SectionCard(
                title: 'Your reliability',
                help: 'Share of confirmed pickups you completed. Higher reliability ranks you higher in matching.',
                child: Column(children: [
                  const SizedBox(height: 8),
                  SizedBox(
                    width: 130,
                    height: 130,
                    child: Stack(alignment: Alignment.center, children: [
                      SizedBox(
                        width: 130,
                        height: 130,
                        child: CircularProgressIndicator(
                          value: toD(k['reliability']).clamp(0, 1).toDouble(),
                          strokeWidth: 10,
                          color: FB.leaf,
                          backgroundColor: FB.leafSoft,
                        ),
                      ),
                      Text('${(toD(k['reliability']) * 100).round()}%', style: FB.display(30)),
                    ]),
                  ),
                  const SizedBox(height: 16),
                  const Text('Top donors', style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 6),
                  ...toL(d['top_donors']).map((t) => ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.storefront_rounded, color: FB.leaf),
                        title: Text(toS(t['donor'])),
                        trailing: Text('${fmtKg(toD(t['kg']))} · ${toI(t['pickups'])}×',
                            style: const TextStyle(fontWeight: FontWeight.w700)),
                      )),
                ]),
              ),
            ),
            const SizedBox(height: 14),
            SplitRow(
              leftFlex: 1,
              left: SectionCard(
                title: 'Food received by category (kg)',
                child: CategoryBarChart(
                  data: toL(d['by_category'])
                      .map((c) => ChartDatum(toS(c['category']).split(' ').first, toD(c['kg']), hexColor(toS(c['color']))))
                      .toList(),
                ),
              ),
              right: SectionCard(
                title: 'Monthly food received (kg)',
                child: TrendLineChart(
                  labels: monthly.map((m) => toS(m['month'])).toList(),
                  values: monthly.map((m) => toD(m['kg'])).toList(),
                ),
              ),
            ),
            const SizedBox(height: 14),
            SectionCard(
              title: 'Pickup history & beneficiary impact',
              padding: const EdgeInsets.all(8),
              child: history.isEmpty
                  ? const EmptyState(icon: Icons.history_rounded, title: 'No completed pickups yet')
                  : DataTableCard(
                      columns: const ['Date', 'Donation', 'Donor', 'Category', 'Received', 'Meals', 'Status'],
                      onTap: history.map<VoidCallback?>((h) => () => context.go('/pickups/${toI(h['id'])}')).toList(),
                      rows: history
                          .map((h) => <Widget>[
                                Text(fmtDate(toDate(h['start']))),
                                Text(toS(h['title'])),
                                Text(toS(h['donor'])),
                                Text(toS(h['category'])),
                                Text(fmtKg(toDn(h['received_kg']) ?? toD(h['kg']))),
                                Text(h['meals'] == null ? '—' : fmtInt(toI(h['meals']))),
                                StatusChip(toS(h['status'])),
                              ])
                          .toList(),
                    ),
            ),
          ],
        );
      },
    );
  }
}

class _IncomingTile extends StatelessWidget {
  final Json p;
  final VoidCallback onTap;
  const _IncomingTile({required this.p, required this.onTap});
  @override
  Widget build(BuildContext context) {
    final start = toDate(p['start']);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(children: [
          Container(
            width: 54,
            padding: const EdgeInsets.symmetric(vertical: 8),
            decoration: BoxDecoration(color: FB.violetSoft, borderRadius: BorderRadius.circular(10)),
            child: Column(children: [
              Text(start == null ? '' : '${start.day}', style: FB.display(20, color: FB.violet)),
              Text(start == null ? '' : fmtDateShort(start).split(' ').last,
                  style: const TextStyle(fontSize: 11, color: FB.violet, fontWeight: FontWeight.w700)),
            ]),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(toS(p['title']), style: const TextStyle(fontWeight: FontWeight.w700)),
              Text('${toS(p['donor'])} · ${fmtKg(toD(p['kg']))} · ${fmtTime(start)}–${fmtTime(toDate(p['end']))}',
                  style: const TextStyle(color: FB.muted, fontSize: 12.5)),
              Text(toS(p['address']), style: const TextStyle(color: FB.muted, fontSize: 12)),
            ]),
          ),
          StatusChip(toS(p['status'])),
        ]),
      ),
    );
  }
}
