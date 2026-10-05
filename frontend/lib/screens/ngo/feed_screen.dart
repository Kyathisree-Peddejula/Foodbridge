import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../config.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';
import '../../widgets/marketplace.dart';
import '../business/listings_screen.dart';
import '../business/stock_dialogs.dart';

/// Live donation feed: available listings ranked by this NGO's AI match score (auto-refreshes).
class FeedScreen extends StatefulWidget {
  const FeedScreen({super.key});
  @override
  State<FeedScreen> createState() => _FeedScreenState();
}

class _FeedScreenState extends State<FeedScreen> {
  String? _category;
  double _maxKm = 0; // 0 = any
  double _minScore = 0;
  List<Json> _cats = [];
  int _v = 0;
  DateTime _updated = DateTime.now();

  @override
  void initState() {
    super.initState();
    Taxonomy.load().then((c) {
      if (mounted) setState(() => _cats = c);
    });
  }

  Future<List<Json>> _load() async {
    final r = toL(await api.get('/marketplace/listings/feed/', query: {
      'category': _category,
      'max_distance_km': _maxKm > 0 ? _maxKm.round() : null,
      'min_score': _minScore > 0 ? _minScore.round() : null,
    }));
    _updated = DateTime.now();
    return r;
  }

  Future<void> _claim(Json l) async {
    await showDialog(
      context: context,
      builder: (dc) => PickupRequestDialog(
        listing: l,
        title: 'Claim donation',
        submitLabel: 'Request pickup',
        onSubmit: (payload) async {
          final ok = await runAction(dc, () => api.post('/marketplace/listings/${toI(l['id'])}/claim/', payload),
              success: 'Pickup requested — the donor has been notified to confirm');
          if (ok && dc.mounted) {
            Navigator.pop(dc);
            setState(() => _v++);
          }
        },
      ),
    );
  }

  Future<void> _decline(Json l) async {
    final ok = await runAction(context, () => api.post('/marketplace/listings/${toI(l['id'])}/decline/'),
        success: 'Hidden from your feed');
    if (ok) setState(() => _v++);
  }

  void _details(Json l) {
    final donor = toJ(l['donor']);
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Colors.white,
      builder: (c) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .6,
        maxChildSize: .92,
        builder: (c, scroll) => ListView(controller: scroll, padding: const EdgeInsets.fromLTRB(22, 0, 22, 24), children: [
          Text(toS(l['title']), style: FB.display(22)),
          const SizedBox(height: 4),
          Text('${toS(donor['name'])} · ${toS(donor['city'])}', style: const TextStyle(color: FB.muted)),
          const SizedBox(height: 14),
          if (l['match_score'] != null)
            Row(children: [
              ScoreRing(toD(l['match_score']), size: 54),
              const SizedBox(width: 12),
              Expanded(
                child: Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: (l['match_reasons'] is List ? l['match_reasons'] as List : const [])
                      .map((r) => Pill(r.toString(), color: FB.leaf, icon: Icons.check_rounded))
                      .toList(),
                ),
              ),
            ]),
          const SizedBox(height: 14),
          InfoRow('Available', '${fmtKg(toD(l['remaining_kg']))} (~${fmtInt(toI(l['estimated_meals']))} meals)'),
          InfoRow('Best before', fmtDate(toDate(l['expiry_date']))),
          InfoRow('Distance', l['distance_km'] == null ? '—' : '${fmtNum(toD(l['distance_km']))} km'),
          InfoRow('Pickup at', toS(l['pickup_address'], '—')),
          InfoRow('Donor phone', toS(donor['phone'], '—')),
          InfoRow('Storage', l['requires_refrigeration'] == true ? 'Keep refrigerated' : 'Ambient / hot-hold'),
          if (toS(l['description']).isNotEmpty) InfoRow('Description', toS(l['description'])),
          if (toS(l['handling_notes']).isNotEmpty) InfoRow('Handling', toS(l['handling_notes'])),
          const SizedBox(height: 10),
          const Text('Pickup windows', style: TextStyle(fontWeight: FontWeight.w700)),
          ...toL(l['windows']).map((w) => Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text('• ${fmtRange(toDate(w['start']), toDate(w['end']))}'),
              )),
          const SizedBox(height: 18),
          FilledButton.icon(
            onPressed: () {
              Navigator.pop(c);
              _claim(l);
            },
            icon: const Icon(Icons.volunteer_activism_rounded),
            label: const Text('Claim this donation'),
          ),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RemoteView<List<Json>>(
      key: ValueKey('$_category|$_maxKm|$_minScore|$_v'),
      load: _load,
      poll: const Duration(seconds: AppConfig.feedPollSeconds),
      builder: (context, rows, reload) {
        return PageScaffold(
          title: 'Live donations',
          help: 'Only listings that fit your needs profile appear here. The score (0-100) combines food type, distance, quantity, timing and your pickup history.',
          subtitle: 'Ranked by AI match score for your needs · refreshes every ${AppConfig.feedPollSeconds}s · '
              'updated ${fmtTime(_updated)}',
          onRefresh: reload,
          actions: [OutlinedButton.icon(onPressed: reload, icon: const Icon(Icons.refresh_rounded), label: const Text('Refresh'))],
          children: [
            SectionCard(
              child: Wrap(spacing: 18, runSpacing: 12, crossAxisAlignment: WrapCrossAlignment.center, children: [
                SizedBox(
                  width: 220,
                  child: DropdownButtonFormField<String?>(
                    value: _category,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Food type'),
                    items: [
                      const DropdownMenuItem<String?>(value: null, child: Text('All food types')),
                      ..._cats.map((c) => DropdownMenuItem<String?>(value: toS(c['slug']), child: Text(toS(c['name'])))),
                    ],
                    onChanged: (v) => setState(() => _category = v),
                  ),
                ),
                SizedBox(
                  width: 260,
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(_maxKm == 0 ? 'Any distance' : 'Within ${_maxKm.round()} km',
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                    Slider(
                      value: _maxKm,
                      min: 0,
                      max: 30,
                      divisions: 6,
                      activeColor: FB.leaf,
                      onChanged: (v) => setState(() => _maxKm = v),
                    ),
                  ]),
                ),
                SizedBox(
                  width: 260,
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('Match score ≥ ${_minScore.round()}', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                    Slider(
                      value: _minScore,
                      min: 0,
                      max: 90,
                      divisions: 9,
                      activeColor: FB.amber,
                      onChanged: (v) => setState(() => _minScore = v),
                    ),
                  ]),
                ),
              ]),
            ),
            const SizedBox(height: 14),
            if (rows.isEmpty)
              const SectionCard(
                child: EmptyState(
                  icon: Icons.hourglass_empty_rounded,
                  title: 'No matching donations right now',
                  message: 'New surplus appears here automatically. Broaden your needs to see more.',
                ),
              ),
            ResponsiveGrid(
              minTileWidth: 320,
              children: rows
                  .map((l) => ListingCard(
                        l: l,
                        showDonor: true,
                        onTap: () => _details(l),
                        footer: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                          if (l['match_reasons'] is List && (l['match_reasons'] as List).isNotEmpty)
                            Text((l['match_reasons'] as List).take(3).join(' · '),
                                style: const TextStyle(fontSize: 12, color: FB.leaf, fontWeight: FontWeight.w600)),
                          const SizedBox(height: 10),
                          Row(children: [
                            Expanded(
                              child: FilledButton(onPressed: () => _claim(l), child: const Text('Claim')),
                            ),
                            const SizedBox(width: 8),
                            OutlinedButton(onPressed: () => _decline(l), child: const Text('Not for us')),
                          ]),
                        ]),
                      ))
                  .toList(),
            ),
          ],
        );
      },
    );
  }
}
