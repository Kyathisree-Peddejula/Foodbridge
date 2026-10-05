import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/charts.dart';
import '../../widgets/common.dart';

/// Sustainability impact: food diverted, CO2e avoided, meals provided.
class ImpactScreen extends StatefulWidget {
  const ImpactScreen({super.key});
  @override
  State<ImpactScreen> createState() => _ImpactScreenState();
}

class _ImpactScreenState extends State<ImpactScreen> {
  String? _scope;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final scope = _scope ?? (auth.role == Role.admin ? 'platform' : 'mine');
    return RemoteView<Json>(
      key: ValueKey(scope),
      load: () async => toJ(await api.get('/analytics/impact/', query: {'scope': scope})),
      builder: (context, d, reload) {
        final eq = toJ(d['equivalents']);
        final monthly = toL(d['monthly']);
        final cats = toL(d['by_category']);
        final m = toJ(d['methodology']);
        return PageScaffold(
          title: 'Sustainability impact',
          help: 'Counts only delivered pickups. Meals = kg ÷ 0.42; CO₂e uses a per-category emission factor from the food taxonomy.',
          subtitle: scope == 'platform' ? 'All FoodBridge donors and NGOs' : 'Impact of ${auth.orgName}',
          onRefresh: reload,
          actions: [
            if (auth.role != Role.admin)
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'mine', label: Text('Us')),
                  ButtonSegment(value: 'platform', label: Text('Whole platform')),
                ],
                selected: {scope},
                onSelectionChanged: (s) => setState(() => _scope = s.first),
              ),
          ],
          children: [
            _Hero(d: d, eq: eq),
            const SizedBox(height: 14),
            ResponsiveGrid(children: [
              KpiCard(
                  label: 'Food diverted from waste',
                  value: fmtKg(toD(d['food_diverted_kg'])),
                  caption: '${fmtInt(toI(d['pickups_completed']))} completed pickups',
                  color: FB.leaf,
                  icon: Icons.recycling_rounded),
              KpiCard(
                  label: 'CO₂e emissions avoided',
                  value: fmtKg(toD(d['co2e_avoided_kg'])),
                  caption: '≈ ${fmtInt(toD(eq['car_km_avoided']))} car-km',
                  color: FB.sky,
                  icon: Icons.cloud_done_rounded),
              KpiCard(
                  label: 'Meals provided',
                  value: fmtInt(toI(d['meals'])),
                  caption: '${fmtInt(toI(d['beneficiaries']))} beneficiaries reached',
                  color: FB.amber,
                  icon: Icons.restaurant_rounded),
              if (d['diversion_rate'] != null)
                KpiCard(
                    label: 'Diversion rate',
                    value: fmtPct(toD(d['diversion_rate'])),
                    caption: '${fmtKg(toD(d['wasted_kg']))} still wasted',
                    color: FB.forest,
                    icon: Icons.pie_chart_rounded),
            ]),
            const SizedBox(height: 14),
            SplitRow(
              leftFlex: 1,
              left: SectionCard(
                title: 'Food diverted by month (kg)',
                child: TrendLineChart(
                  labels: monthly.map((e) => toS(e['month'])).toList(),
                  values: monthly.map((e) => toD(e['kg'])).toList(),
                ),
              ),
              right: SectionCard(
                title: 'CO₂e avoided by month (kg)',
                child: TrendLineChart(
                  labels: monthly.map((e) => toS(e['month'])).toList(),
                  values: monthly.map((e) => toD(e['co2e_kg'])).toList(),
                  color: FB.sky,
                ),
              ),
            ),
            const SizedBox(height: 14),
            SplitRow(
              left: SectionCard(
                title: 'Food diverted by category (kg)',
                child: CategoryBarChart(
                  data: cats.map((c) => ChartDatum(toS(c['category']).split(' ').first, toD(c['kg']), hexColor(toS(c['color'])))).toList(),
                ),
              ),
              right: SectionCard(
                title: 'CO₂e share by category',
                child: Center(
                  child: DonutChart(
                    data: cats
                        .map((c) => ChartDatum(toS(c['category']), toD(c['co2e_kg']), hexColor(toS(c['color']))))
                        .toList(),
                    centerValue: '${(toD(d['co2e_avoided_kg']) / 1000).toStringAsFixed(1)} t',
                    centerLabel: 'CO₂e',
                  ),
                ),
              ),
            ),
            const SizedBox(height: 14),
            SectionCard(
              title: 'Methodology',
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                InfoRow('Meals', '1 meal = ${toS(m['kg_per_meal'], '0.42')} kg of food (WRAP / FAO convention)'),
                InfoRow('CO₂e', toS(m['co2e'], 'Category emission factor per kg food')),
                InfoRow('Car-km', toS(m['car_km'], '0.17 kg CO₂e per km')),
                InfoRow('Trees', toS(m['tree'], '21 kg CO₂ absorbed per tree per year')),
              ]),
            ),
          ],
        );
      },
    );
  }
}

class _Hero extends StatelessWidget {
  final Json d;
  final Json eq;
  const _Hero({required this.d, required this.eq});
  @override
  Widget build(BuildContext context) {
    Widget item(IconData i, String v, String l) => Padding(
          padding: const EdgeInsets.only(right: 32, bottom: 8),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(i, color: FB.amber, size: 28),
            const SizedBox(width: 10),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(v, style: FB.display(24, color: Colors.white)),
              Text(l, style: const TextStyle(color: Color(0xB3FFFFFF), fontSize: 12.5)),
            ]),
          ]),
        );
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [FB.forest, Color(0xFF1C6B45)]),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Every kilogram rescued is food on a plate and emissions kept out of the air.',
            style: FB.display(isPhone(context) ? 18 : 22, color: Colors.white)),
        const SizedBox(height: 16),
        Wrap(children: [
          item(Icons.restaurant_rounded, fmtInt(toI(d['meals'])), 'meals provided'),
          item(Icons.directions_car_filled_rounded, '${fmtInt(toD(eq['car_km_avoided']))} km', 'of driving avoided'),
          item(Icons.park_rounded, fmtNum(toD(eq['trees_year'])), 'trees growing for a year'),
        ]),
      ]),
    );
  }
}
