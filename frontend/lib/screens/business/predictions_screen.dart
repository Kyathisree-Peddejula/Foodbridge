import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/charts.dart';
import '../../widgets/common.dart';

class PredictionsScreen extends StatefulWidget {
  const PredictionsScreen({super.key});
  @override
  State<PredictionsScreen> createState() => _PredictionsScreenState();
}

class _PredictionsScreenState extends State<PredictionsScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 3, vsync: this);

  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: EdgeInsets.fromLTRB(pad, pad, pad, 0),
        child: const PageHeader(
          title: 'Waste predictions',
          help: 'Prophet and LSTM models forecast daily demand from your sales history. The risk score compares that demand with stock and days to expiry.',
          subtitle: 'Prophet + LSTM demand forecasts → waste risk scores → smart reorder quantities',
        ),
      ),
      Padding(
        padding: EdgeInsets.symmetric(horizontal: pad),
        child: TabBar(
          controller: _tabs,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          labelColor: FB.forest,
          unselectedLabelColor: FB.muted,
          indicatorColor: FB.leaf,
          labelStyle: const TextStyle(fontWeight: FontWeight.w700),
          tabs: const [Tab(text: 'Waste risk'), Tab(text: 'Smart reorder'), Tab(text: 'Model performance')],
        ),
      ),
      const Divider(),
      Expanded(
        child: TabBarView(controller: _tabs, children: const [_RiskTab(), _ReorderTab(), _ModelTab()]),
      ),
    ]);
  }
}

// ------------------------------------------------------------------ risk
class _RiskTab extends StatefulWidget {
  const _RiskTab();
  @override
  State<_RiskTab> createState() => _RiskTabState();
}

class _RiskTabState extends State<_RiskTab> {
  int _v = 0;
  bool _busy = false;

  Future<void> _refresh() async {
    setState(() => _busy = true);
    try {
      final r = toJ(await api.post('/predictions/risk/refresh/', {}));
      toast(context,
          'Scored ${toI(r['items_scored'])} batches with ${toS(r['engine'])} · ${toI(r['high_risk_items'])} high risk');
      setState(() => _v++);
    } on ApiException catch (e) {
      toast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    return RemoteView<Json>(
      key: ValueKey(_v),
      load: () async => toJ(await api.get('/predictions/risk/summary/')),
      builder: (context, d, reload) {
        final dist = toJ(d['distribution']);
        final last = toJ(d['last_run']);
        final top = toL(d['top_risky']);
        return ListView(padding: EdgeInsets.all(pad), children: [
          Wrap(spacing: 10, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: [
            FilledButton.icon(
              onPressed: _busy ? null : _refresh,
              icon: _busy
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.bolt_rounded),
              label: const Text('Score now (real-time)'),
            ),
            if (last.isNotEmpty)
              Text(
                'Last run ${timeAgo(toDate(last['finished_at'] ?? last['started_at']))} · ${toS(last['source']).replaceAll('_', '-')} · '
                'engine ${toS(last['engine'])} · ${toI(last['items_scored'])} scored',
                style: const TextStyle(color: FB.muted, fontSize: 13),
              ),
            const HelpTip('Risk = 45% expected unsold share + 25% expiry urgency + 15% stock cover + 15% waste probability. '
                'Scores are refreshed automatically every 6 hours by the ML batch job.'),
          ]),
          const SizedBox(height: 14),
          ResponsiveGrid(minTileWidth: 180, children: [
            for (final l in ['critical', 'high', 'medium', 'low'])
              KpiCard(label: '${titleCase(l)} risk', value: '${toI(dist[l])}', caption: 'batches', color: FB.risk(l)),
          ]),
          const SizedBox(height: 14),
          SectionCard(
            title: 'Expected waste by category',
            help: 'Units predicted to remain unsold at expiry, per category.',
            child: CategoryBarChart(
              data: toL(d['by_category'])
                  .asMap()
                  .entries
                  .map((e) => ChartDatum(toS(e.value['category']).split(' ').first, toD(e.value['expected_waste']),
                      FB.chart[e.key % FB.chart.length]))
                  .toList(),
            ),
          ),
          const SizedBox(height: 14),
          SectionCard(
            title: 'Highest-risk batches',
            child: top.isEmpty
                ? const EmptyState(icon: Icons.verified_rounded, title: 'No scored batches yet')
                : Column(children: top.map((b) => _RiskRow(b: b)).toList()),
          ),
        ]);
      },
    );
  }
}

class _RiskRow extends StatelessWidget {
  final Json b;
  const _RiskRow({required this.b});
  @override
  Widget build(BuildContext context) {
    final f = toJ(b['risk_factors']);
    Widget factor(String label, dynamic v, Color c) => SizedBox(
          width: 130,
          child: MeterBar(label: label, value: toD(v), color: c, trailing: '${(toD(v) * 100).round()}%'),
        );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(toS(b['product_name']), style: const TextStyle(fontWeight: FontWeight.w700)),
              Text(
                '${fmtNum(toD(b['quantity']))} ${toS(b['product_unit'])} · ${expiryLabel(toI(b['days_to_expiry']))} · '
                'forecast demand ${fmtNum(toD(b['predicted_demand']))} · model ${toS(b['risk_model'])}',
                style: const TextStyle(color: FB.muted, fontSize: 12.5),
              ),
            ]),
          ),
          RiskBadge(score: toDn(b['risk_score']), level: toS(b['risk_level'])),
          IconButton(
            tooltip: 'Forecast',
            onPressed: () => context.go('/predictions/forecast/${toI(b['product'])}'),
            icon: const Icon(Icons.show_chart_rounded, color: FB.leaf),
          ),
        ]),
        if (f['expired'] != true)
          Wrap(spacing: 14, children: [
            factor('Unsold share', f['surplus_ratio'], FB.tomato),
            factor('Expiry urgency', f['expiry_urgency'], FB.amber),
            factor('Waste prob.', f['waste_probability'], FB.violet),
          ]),
        Row(children: [
          const Icon(Icons.auto_awesome, size: 14, color: FB.amber),
          const SizedBox(width: 6),
          Expanded(child: Text(toS(b['recommended_action']), style: const TextStyle(fontSize: 13))),
          if (toS(b['risk_level']) == 'high' || toS(b['risk_level']) == 'critical')
            TextButton(
              onPressed: () => context.go('/listings/new?batch=${toI(b['id'])}'),
              child: const Text('List surplus'),
            ),
        ]),
        const Divider(),
      ]),
    );
  }
}

// ------------------------------------------------------------------ reorder
class _ReorderTab extends StatefulWidget {
  const _ReorderTab();
  @override
  State<_ReorderTab> createState() => _ReorderTabState();
}

class _ReorderTabState extends State<_ReorderTab> {
  int _v = 0;
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    return RemoteView<List<Json>>(
      key: ValueKey(_v),
      load: () async => toL(await api.get('/predictions/reorder/')),
      builder: (context, rows, reload) {
        final avoided = rows.fold<double>(0, (a, r) => a + toD(r['expected_waste_avoided']));
        final urgent = rows.where((r) => toS(r['urgency']) == 'urgent').length;
        return ListView(padding: EdgeInsets.all(pad), children: [
          Wrap(spacing: 10, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: [
            FilledButton.icon(
              onPressed: _busy
                  ? null
                  : () async {
                      setState(() => _busy = true);
                      final ok = await runAction(context, () => api.post('/predictions/reorder/', {}),
                          success: 'Reorder plan generated');
                      if (mounted) setState(() => _busy = false);
                      if (ok) setState(() => _v++);
                    },
              icon: const Icon(Icons.shopping_cart_checkout_rounded),
              label: Text(_busy ? 'Generating…' : 'Generate reorder plan'),
            ),
            const HelpTip('Order-up-to policy: forecast over lead time + review period plus safety stock, capped by what '
                'can sell within shelf life and scaled to your free storage capacity.'),
          ]),
          const SizedBox(height: 14),
          if (rows.isNotEmpty)
            ResponsiveGrid(minTileWidth: 200, children: [
              KpiCard(label: 'Products planned', value: '${rows.length}', color: FB.forest, icon: Icons.list_alt_rounded),
              KpiCard(label: 'Urgent reorders', value: '$urgent', color: FB.tomato, icon: Icons.priority_high_rounded),
              KpiCard(
                  label: 'Waste avoided vs naive',
                  value: fmtNum(avoided),
                  caption: 'units not over-ordered',
                  color: FB.leaf,
                  icon: Icons.eco_rounded),
            ]),
          const SizedBox(height: 14),
          SectionCard(
            padding: const EdgeInsets.all(8),
            child: rows.isEmpty
                ? const EmptyState(
                    icon: Icons.shopping_cart_outlined,
                    title: 'No reorder plan yet',
                    message: 'Generate one from the latest demand forecast.')
                : DataTableCard(
                    columns: const ['Product', 'Urgency', 'On hand', 'Forecast', 'Safety', 'Order', 'Naive order', 'Why'],
                    rows: rows
                        .map((r) => <Widget>[
                              Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(toS(r['product_name']), style: const TextStyle(fontWeight: FontWeight.w600)),
                                    Text(toS(r['category']), style: const TextStyle(fontSize: 11, color: FB.muted)),
                                  ]),
                              StatusChip(
                                  {'urgent': 'cancelled', 'high': 'in_transit', 'normal': 'available'}[toS(r['urgency'])] ??
                                      'none',
                                  label: titleCase(toS(r['urgency']))),
                              Text(fmtNum(toD(r['current_stock']))),
                              Text(fmtNum(toD(r['forecast_demand']))),
                              Text(fmtNum(toD(r['safety_stock']))),
                              Text('${fmtNum(toD(r['recommended_qty']))} ${toS(r['unit'])}',
                                  style: const TextStyle(fontWeight: FontWeight.w800, color: FB.forest)),
                              Text(fmtNum(toD(r['naive_order_qty'])), style: const TextStyle(color: FB.muted)),
                              Tooltip(
                                message: toS(r['rationale']),
                                child: const Icon(Icons.info_outline_rounded, size: 18, color: FB.muted),
                              ),
                            ])
                        .toList(),
                  ),
          ),
        ]);
      },
    );
  }
}

// ------------------------------------------------------------------ model
class _ModelTab extends StatelessWidget {
  const _ModelTab();
  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    return RemoteView<Json>(
      load: () async => toJ(await api.get('/predictions/model-status/')),
      builder: (context, d, reload) {
        if (d['online'] != true) {
          return ListView(padding: EdgeInsets.all(pad), children: [
            SectionCard(
              child: EmptyState(
                icon: Icons.cloud_off_rounded,
                title: 'ML service offline',
                message: 'Risk scores fall back to a moving-average heuristic until the FastAPI service is reachable.\n'
                    '${toS(d['error'])}',
                action: OutlinedButton(onPressed: reload, child: const Text('Retry')),
              ),
            ),
          ]);
        }
        final metrics = toJ(d['metrics']);
        final weights = toJ(d['ensemble_weights']);
        final curve = toL(d['lstm_training_curve']);
        final perCat = toL(d['per_category_wape']);
        final sched = toJ(d['batch_scheduler']);
        return ListView(padding: EdgeInsets.all(pad), children: [
          ResponsiveGrid(minTileWidth: 200, children: [
            KpiCard(
                label: 'Best model (WAPE)',
                value: titleCase(toS(d['best_model'], '—')),
                caption: toS(d['evaluation_mode']),
                color: FB.leaf,
                icon: Icons.emoji_events_rounded),
            KpiCard(
                label: 'Series evaluated',
                value: fmtInt(toI(d['series_evaluated'])),
                caption: '${toI(d['horizon_days'])}-day horizon',
                color: FB.forest,
                icon: Icons.stacked_line_chart_rounded),
            KpiCard(
                label: 'Ensemble weights',
                value: weights.entries.map((e) => '${titleCase(e.key)} ${(toD(e.value) * 100).round()}%').join(' · '),
                caption: 'inverse-WAPE weighting',
                color: FB.amber,
                icon: Icons.balance_rounded),
            KpiCard(
                label: 'Batch scoring',
                value: 'every ${fmtNum(toD(sched['every_hours']))} h',
                caption: sched['next_run'] == null ? 'scheduler idle' : 'next ${fmtDateTime(toDate(sched['next_run']))}',
                color: FB.sky,
                icon: Icons.schedule_rounded),
          ]),
          const SizedBox(height: 14),
          SectionCard(
            title: 'Hold-out accuracy on FreshRetailNet-50K',
            help: 'WAPE = sum|error| / sum(actual). Demand targets are stock-out corrected.',
            padding: const EdgeInsets.all(8),
            child: DataTableCard(
              columns: const ['Model', 'WAPE', 'MAE', 'RMSE', 'sMAPE', 'Bias'],
              rows: metrics.entries.map((e) {
                final m = toJ(e.value);
                final best = e.key == toS(d['best_model']);
                return <Widget>[
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    Text(titleCase(e.key), style: TextStyle(fontWeight: best ? FontWeight.w800 : FontWeight.w500)),
                    if (best) ...[const SizedBox(width: 6), const Icon(Icons.star_rounded, size: 16, color: FB.amber)],
                  ]),
                  Text(fmtPct(toD(m['wape']) * 100)),
                  Text(toD(m['mae']).toStringAsFixed(3)),
                  Text(toD(m['rmse']).toStringAsFixed(3)),
                  Text(fmtPct(toD(m['smape']) * 100)),
                  Text(fmtPct(toD(m['bias']) * 100)),
                ];
              }).toList(),
            ),
          ),
          const SizedBox(height: 14),
          SplitRow(
            leftFlex: 1,
            left: SectionCard(
              title: 'WAPE by category (lower is better)',
              child: perCat.isEmpty
                  ? const Text('—')
                  : GroupedBarChart(
                      labels: perCat.map((c) => titleCase(toS(c['taxonomy'])).split(' ').first).toList(),
                      series: [
                        SeriesSpec('Prophet', FB.forest, perCat.map((c) => toD(c['prophet']) * 100).toList()),
                        SeriesSpec('LSTM', FB.amber, perCat.map((c) => toD(c['lstm']) * 100).toList()),
                        SeriesSpec('Naive', FB.muted, perCat.map((c) => toD(c['seasonal_naive']) * 100).toList()),
                      ],
                    ),
            ),
            right: SectionCard(
              title: 'LSTM training curve (Huber loss)',
              child: curve.isEmpty
                  ? const Text('—')
                  : TrendLineChart(
                      labels: curve.map((c) => 'Epoch ${toI(c['epoch'])}').toList(),
                      values: curve.map((c) => toD(c['val_loss'] ?? c['val'])).toList(),
                      color: FB.violet,
                    ),
            ),
          ),
        ]);
      },
    );
  }
}

// ------------------------------------------------------------------ forecast detail
class ForecastScreen extends StatefulWidget {
  final int productId;
  const ForecastScreen({super.key, required this.productId});
  @override
  State<ForecastScreen> createState() => _ForecastScreenState();
}

class _ForecastScreenState extends State<ForecastScreen> {
  int _horizon = 14;

  @override
  Widget build(BuildContext context) {
    return RemoteView<Json>(
      key: ValueKey(_horizon),
      load: () async => toJ(await api.get('/predictions/forecast/${widget.productId}/', query: {'horizon': _horizon})),
      builder: (context, d, reload) {
        final p = toJ(d['product']);
        final daily = toDL(d['daily']);
        final weekly = toDL(d['weekly']);
        final history = toDL(d['history']);
        final unit = toS(p['unit']);
        final start = toDate(d['start_date']) ?? DateTime.now();
        final avgHist = history.isEmpty ? 0.0 : history.reduce((a, b) => a + b) / history.length;
        final avgFc = daily.isEmpty ? 0.0 : daily.reduce((a, b) => a + b) / daily.length;
        final change = avgHist == 0 ? null : (avgFc - avgHist) / avgHist * 100;
        return PageScaffold(
          title: 'Demand forecast · ${toS(p['name'])}',
          subtitle: 'Model: ${toS(d['model'])}'
              '${d['expected_error_wape'] != null ? ' · expected error ±${(toD(d['expected_error_wape']) * 100).round()}% (WAPE)' : ''}',
          onRefresh: reload,
          actions: [
            OutlinedButton.icon(
                onPressed: () => context.go('/predictions'),
                icon: const Icon(Icons.arrow_back_rounded),
                label: const Text('Predictions')),
            SegmentedButton<int>(
              segments: const [
                ButtonSegment(value: 7, label: Text('7 d')),
                ButtonSegment(value: 14, label: Text('14 d')),
                ButtonSegment(value: 28, label: Text('28 d')),
              ],
              selected: {_horizon},
              onSelectionChanged: (s) => setState(() => _horizon = s.first),
            ),
          ],
          children: [
            ResponsiveGrid(minTileWidth: 200, children: [
              KpiCard(label: 'Next 7 days', value: '${fmtNum(weekly.isEmpty ? 0 : weekly.first)} $unit', color: FB.amber, icon: Icons.date_range_rounded),
              KpiCard(label: 'Avg daily forecast', value: '${fmtNum(avgFc)} $unit', color: FB.forest, icon: Icons.today_rounded),
              KpiCard(
                label: 'vs last 28 days',
                value: change == null ? '—' : '${change >= 0 ? '+' : ''}${change.toStringAsFixed(0)}%',
                caption: 'avg ${fmtNum(avgHist)} $unit/day before',
                color: (change ?? 0) >= 0 ? FB.leaf : FB.tomato,
                icon: Icons.trending_up_rounded,
              ),
            ]),
            const SizedBox(height: 14),
            SectionCard(
              title: 'Daily demand ($unit)',
              child: ForecastChart(
                history: history,
                forecast: daily,
                lower: toDL(d['lower']),
                upper: toDL(d['upper']),
                start: start,
              ),
            ),
            const SizedBox(height: 14),
            SectionCard(
              title: 'Weekly totals',
              child: CategoryBarChart(
                height: 200,
                data: [
                  for (var i = 0; i < weekly.length; i++)
                    ChartDatum('Week ${i + 1}', weekly[i], i.isEven ? FB.leaf : FB.forest),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}
