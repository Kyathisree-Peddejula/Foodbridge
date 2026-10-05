import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';

class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key});
  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> {
  bool _open = true;
  String? _level;
  int _v = 0;

  static const levels = {'expired': FB.tomato, 'critical': Color(0xFFEF7D3C), 'warning': FB.amber};

  @override
  Widget build(BuildContext context) {
    return RemoteView<List<Json>>(
      key: ValueKey('$_open|$_level|$_v'),
      load: () async => toL(await api.get('/expiry/alerts/', query: {
        'page_size': 200,
        'is_acknowledged': _open ? 'false' : 'true',
        'level': _level,
      })),
      builder: (context, rows, reload) {
        final counts = <String, int>{};
        for (final r in rows) {
          counts[toS(r['level'])] = (counts[toS(r['level'])] ?? 0) + 1;
        }
        return PageScaffold(
          title: 'Expiry alerts',
          help: 'Warning and critical alerts fire when days-to-expiry reach your thresholds. The expiry scan also runs automatically every hour.',
          subtitle: 'Automated alerts at your days-to-expiry thresholds (configure them in Settings)',
          onRefresh: reload,
          actions: [
            OutlinedButton.icon(
              onPressed: () => context.go('/settings'),
              icon: const Icon(Icons.tune_rounded),
              label: const Text('Thresholds'),
            ),
            FilledButton.icon(
              icon: const Icon(Icons.radar_rounded),
              label: const Text('Run expiry scan'),
              onPressed: () async {
                final ok = await runAction(context, () => api.post('/expiry/alerts/scan/'),
                    success: 'Expiry scan complete');
                if (ok) setState(() => _v++);
              },
            ),
          ],
          children: [
            ResponsiveGrid(minTileWidth: 200, children: [
              for (final e in levels.entries)
                KpiCard(
                  label: '${titleCase(e.key)} ${_open ? '(open)' : ''}',
                  value: '${counts[e.key] ?? 0}',
                  color: e.value,
                  icon: e.key == 'expired' ? Icons.block_rounded : Icons.schedule_rounded,
                ),
            ]),
            const SizedBox(height: 14),
            Wrap(spacing: 8, runSpacing: 8, children: [
              ChoiceChip(label: const Text('Open'), selected: _open, onSelected: (_) => setState(() => _open = true)),
              ChoiceChip(
                  label: const Text('Acknowledged'), selected: !_open, onSelected: (_) => setState(() => _open = false)),
              const SizedBox(width: 12),
              ChoiceChip(label: const Text('All levels'), selected: _level == null, onSelected: (_) => setState(() => _level = null)),
              for (final l in levels.keys)
                ChoiceChip(label: Text(titleCase(l)), selected: _level == l, onSelected: (_) => setState(() => _level = l)),
            ]),
            const SizedBox(height: 14),
            if (rows.isEmpty)
              const SectionCard(
                child: EmptyState(
                    icon: Icons.task_alt_rounded, title: 'All clear', message: 'No alerts match these filters.'),
              ),
            ...rows.map((a) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _AlertTile(a: a, onChanged: () => setState(() => _v++)),
                )),
          ],
        );
      },
    );
  }
}

class _AlertTile extends StatelessWidget {
  final Json a;
  final VoidCallback onChanged;
  const _AlertTile({required this.a, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final b = toJ(a['batch']);
    final level = toS(a['level']);
    final c = _AlertsScreenState.levels[level] ?? FB.amber;
    return SectionCard(
      padding: const EdgeInsets.all(14),
      child: Wrap(
        spacing: 14,
        runSpacing: 10,
        crossAxisAlignment: WrapCrossAlignment.center,
        alignment: WrapAlignment.spaceBetween,
        children: [
          Row(mainAxisSize: MainAxisSize.min, children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: c.withOpacity(.12), borderRadius: BorderRadius.circular(10)),
              child: Icon(level == 'expired' ? Icons.block_rounded : Icons.hourglass_bottom_rounded, color: c),
            ),
            const SizedBox(width: 12),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(toS(a['message']), style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 3),
                Text(
                  '${titleCase(level)} · raised ${timeAgo(toDate(a['created_at']))}'
                  '${b['risk_score'] != null ? ' · waste risk ${toD(b['risk_score']).toStringAsFixed(0)}' : ''}',
                  style: const TextStyle(color: FB.muted, fontSize: 12.5),
                ),
                if (toS(b['recommended_action']).isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text('Suggested: ${toS(b['recommended_action'])}', style: const TextStyle(fontSize: 12.5)),
                  ),
              ]),
            ),
          ]),
          Wrap(spacing: 8, children: [
            if (level != 'expired' && toD(b['quantity']) > 0)
              FilledButton.tonalIcon(
                onPressed: () => context.go('/listings/new?batch=${toI(b['id'])}'),
                icon: const Icon(Icons.volunteer_activism_rounded, size: 18),
                label: const Text('Donate'),
              ),
            if (a['is_acknowledged'] != true)
              OutlinedButton(
                onPressed: () async {
                  final ok = await runAction(context, () => api.post('/expiry/alerts/${toI(a['id'])}/acknowledge/'));
                  if (ok) onChanged();
                },
                child: const Text('Acknowledge'),
              ),
          ]),
        ],
      ),
    );
  }
}
