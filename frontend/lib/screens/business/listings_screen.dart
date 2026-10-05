import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';
import '../../widgets/marketplace.dart';
import 'stock_dialogs.dart';

// ------------------------------------------------------------------ list
class ListingsScreen extends StatefulWidget {
  const ListingsScreen({super.key});
  @override
  State<ListingsScreen> createState() => _ListingsScreenState();
}

class _ListingsScreenState extends State<ListingsScreen> {
  String? _status = 'available';

  @override
  Widget build(BuildContext context) {
    return RemoteView<(List<Json>, List<Json>)>(
      key: ValueKey(_status),
      load: () async {
        final r = await Future.wait([
          api.get('/marketplace/listings/', query: {'page_size': 100, 'status': _status, 'ordering': '-created_at'}),
          api.get('/marketplace/listings/suggestions/'),
        ]);
        return (toL(r[0]), toL(r[1]));
      },
      builder: (context, data, reload) {
        final (rows, suggestions) = data;
        return PageScaffold(
          title: 'Surplus listings',
          help: 'A listing tells nearby NGOs what food is available, how much, until when and when it can be collected.',
          subtitle: 'Share surplus with nearby NGOs — the AI engine ranks the best recipients for every listing',
          onRefresh: reload,
          actions: [
            FilledButton.icon(
              onPressed: () => context.go('/listings/new'),
              icon: const Icon(Icons.add_rounded),
              label: const Text('New listing'),
            ),
          ],
          children: [
            if (suggestions.isNotEmpty) ...[
              SectionCard(
                title: 'Suggested from waste predictions',
                help: 'High and critical risk batches that are not yet listed.',
                child: Column(
                  children: suggestions.take(5).map((b) {
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: RiskBadge(score: toDn(b['risk_score']), level: toS(b['risk_level']), compact: true),
                      title: Text(toS(b['product_name'])),
                      subtitle: Text(
                          '~${fmtNum(toD(b['expected_waste_qty']))} ${toS(b['product_unit'])} likely unsold · ${expiryLabel(toI(b['days_to_expiry']))}'),
                      trailing: FilledButton.tonal(
                        onPressed: () => context.go('/listings/new?batch=${toI(b['id'])}'),
                        child: const Text('List'),
                      ),
                    );
                  }).toList(),
                ),
              ),
              const SizedBox(height: 14),
            ],
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final s in [null, 'available', 'reserved', 'completed', 'expired', 'cancelled'])
                ChoiceChip(
                  label: Text(s == null ? 'All' : titleCase(s)),
                  selected: _status == s,
                  onSelected: (_) => setState(() => _status = s),
                ),
            ]),
            const SizedBox(height: 14),
            if (rows.isEmpty)
              SectionCard(
                child: EmptyState(
                  icon: Icons.volunteer_activism_outlined,
                  title: 'No listings here',
                  message: 'Create a listing to reach NGOs near you.',
                  action: FilledButton(onPressed: () => context.go('/listings/new'), child: const Text('New listing')),
                ),
              ),
            ResponsiveGrid(
              minTileWidth: 320,
              children: rows.map((l) => ListingCard(l: l, onTap: () => context.go('/listings/${toI(l['id'])}'))).toList(),
            ),
          ],
        );
      },
    );
  }
}

class ListingCard extends StatelessWidget {
  final Json l;
  final VoidCallback onTap;
  final Widget? footer;
  final bool showDonor;
  const ListingCard({super.key, required this.l, required this.onTap, this.footer, this.showDonor = false});

  @override
  Widget build(BuildContext context) {
    final cat = toJ(l['category_detail']);
    final color = hexColor(toS(cat['color']));
    final days = toI(l['days_to_expiry']);
    final windows = toL(l['windows']);
    final next = windows.isEmpty ? null : windows.first;
    final score = toDn(l['match_score']);
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(12),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(border: Border.all(color: FB.line), borderRadius: BorderRadius.circular(12)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Container(
              height: 6,
              color: color,
            ),
            Padding(
              padding: const EdgeInsets.all(14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(toS(l['title']),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5)),
                      const SizedBox(height: 3),
                      Text(
                        showDonor
                            ? '${toS(toJ(l['donor'])['name'])}${l['distance_km'] != null ? ' · ${fmtNum(toD(l['distance_km']))} km away' : ''}'
                            : 'LST-${toI(l['id']).toString().padLeft(4, '0')} · ${timeAgo(toDate(l['created_at']))}',
                        style: const TextStyle(color: FB.muted, fontSize: 12.5),
                      ),
                    ]),
                  ),
                  if (score != null) ScoreRing(score, size: 44) else StatusChip(toS(l['status'])),
                ]),
                const SizedBox(height: 10),
                Wrap(spacing: 6, runSpacing: 6, children: [
                  if (cat.isNotEmpty) Pill(toS(cat['name']), color: color),
                  Pill(days < 0 ? 'Expired' : expiryLabel(days),
                      color: days <= 0 ? FB.tomato : days <= 1 ? FB.amber : FB.muted, icon: Icons.schedule_rounded),
                  if (l['requires_refrigeration'] == true) const Pill('Chilled', color: FB.sky, icon: Icons.ac_unit_rounded),
                  ...(l['dietary_tags'] is List ? l['dietary_tags'] as List : const [])
                      .map((t) => Pill(dietaryTags[t] ?? t.toString(), color: FB.violet)),
                ]),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(fmtKg(toD(l['remaining_kg'])), style: FB.display(20)),
                      Text('of ${fmtKg(toD(l['quantity_kg']))} · ~${fmtInt(toI(l['estimated_meals']))} meals',
                          style: const TextStyle(fontSize: 12, color: FB.muted)),
                    ]),
                  ),
                  if (next != null)
                    Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                      const Text('Next window', style: TextStyle(fontSize: 11, color: FB.muted)),
                      Text(fmtRange(toDate(next['start']), toDate(next['end'])),
                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                    ]),
                ]),
                if (footer != null) ...[const SizedBox(height: 12), footer!],
              ]),
            ),
          ]),
        ),
      ),
    );
  }
}

// ------------------------------------------------------------------ create
class NewListingScreen extends StatefulWidget {
  final int? batchId;
  const NewListingScreen({super.key, this.batchId});
  @override
  State<NewListingScreen> createState() => _NewListingScreenState();
}

class _NewListingScreenState extends State<NewListingScreen> {
  final _title = TextEditingController();
  final _desc = TextEditingController();
  final _qty = TextEditingController();
  final _address = TextEditingController();
  final _notes = TextEditingController();
  DateTime _expiry = DateTime.now();
  int? _cat;
  bool _fridge = false;
  final Set<String> _tags = {};
  final List<TimeWindow> _windows = defaultWindows();
  List<Json> _cats = [];
  Json? _batch;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    Taxonomy.load().then((c) {
      if (mounted) setState(() => _cats = c);
    });
    if (widget.batchId != null) {
      api.get('/inventory/batches/${widget.batchId}/').then((b) {
        if (!mounted) return;
        final j = toJ(b);
        setState(() {
          _batch = j;
          _title.text = toS(j['product_name']);
          final q = toD(j['expected_waste_qty']) > 0 ? toD(j['expected_waste_qty']) : toD(j['quantity']);
          _qty.text = q.toStringAsFixed(q % 1 == 0 ? 0 : 1);
          _expiry = toDate(j['expiry_date']) ?? DateTime.now();
        });
      }).catchError((_) {});
    }
  }

  Future<void> _submit() async {
    final q = double.tryParse(_qty.text);
    if (_title.text.trim().isEmpty || q == null || q <= 0) {
      return toast(context, 'Title and a positive quantity are required', error: true);
    }
    setState(() => _busy = true);
    try {
      Json created;
      if (_batch != null) {
        created = toJ(await api.post('/marketplace/listings/from-batch/', {
          'batch': toI(_batch!['id']),
          'quantity': q,
          'title': _title.text.trim(),
          'description': _desc.text.trim(),
          'dietary_tags': _tags.toList(),
          'windows': _windows.map((w) => w.toJson()).toList(),
        }));
      } else {
        created = toJ(await api.post('/marketplace/listings/', {
          'title': _title.text.trim(),
          'description': _desc.text.trim(),
          if (_cat != null) 'category': _cat,
          'quantity_kg': q,
          'expiry_date': isoDate(_expiry),
          if (_address.text.trim().isNotEmpty) 'pickup_address': _address.text.trim(),
          'dietary_tags': _tags.toList(),
          'requires_refrigeration': _fridge,
          'handling_notes': _notes.text.trim(),
          'windows': _windows.map((w) => w.toJson()).toList(),
        }));
      }
      if (!mounted) return;
      toast(context, 'Listing published — matched NGOs have been notified');
      context.go('/listings/${toI(created['id'])}');
    } on ApiException catch (e) {
      toast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final fromBatch = _batch != null;
    final unit = fromBatch ? toS(_batch!['product_unit']) : 'kg';
    return PageScaffold(
      title: 'New surplus listing',
      subtitle: fromBatch
          ? 'Listing from batch ${toS(_batch!['batch_code'])} · quantity defaults to the AI-predicted unsold amount'
          : 'Describe the food, when it can be collected and any dietary details',
      actions: [
        OutlinedButton(onPressed: () => context.go('/listings'), child: const Text('Cancel')),
        FilledButton.icon(
          onPressed: _busy ? null : _submit,
          icon: const Icon(Icons.send_rounded),
          label: Text(_busy ? 'Publishing…' : 'Publish & match'),
        ),
      ],
      children: [
        SplitRow(
          left: SectionCard(
            title: 'Food details',
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              TextField(controller: _title, decoration: const InputDecoration(labelText: 'Title', hintText: 'e.g. Veg biryani – 40 portions')),
              const SizedBox(height: 12),
              TextField(
                controller: _desc,
                maxLines: 3,
                decoration: const InputDecoration(
                    labelText: 'Description', hintText: 'What is it, how was it stored, packaging…'),
              ),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: _qty,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    decoration: InputDecoration(labelText: 'Quantity ($unit)'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: fromBatch
                      ? InputDecorator(
                          decoration: const InputDecoration(labelText: 'Expiry'),
                          child: Text(fmtDate(_expiry)),
                        )
                      : OutlinedButton.icon(
                          onPressed: () async {
                            final d = await pickDate(context, _expiry);
                            if (d != null) setState(() => _expiry = d);
                          },
                          icon: const Icon(Icons.event_rounded, size: 18),
                          label: Text('Best before ${fmtDate(_expiry)}'),
                        ),
                ),
              ]),
              if (!fromBatch) ...[
                const SizedBox(height: 12),
                DropdownButtonFormField<int?>(
                  value: _cat,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Food category'),
                  items: [
                    const DropdownMenuItem<int?>(value: null, child: Text('Auto-detect from title')),
                    ..._cats.map((c) => DropdownMenuItem<int?>(value: toI(c['id']), child: Text(toS(c['name'])))),
                  ],
                  onChanged: (v) => setState(() => _cat = v),
                ),
                const SizedBox(height: 4),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _fridge,
                  onChanged: (v) => setState(() => _fridge = v),
                  title: const Text('Needs refrigeration'),
                  subtitle: const Text('Only NGOs with cold storage will be matched'),
                ),
                TextField(
                  controller: _address,
                  decoration: const InputDecoration(labelText: 'Pickup address', hintText: 'Defaults to your organization address'),
                ),
                const SizedBox(height: 12),
                TextField(controller: _notes, decoration: const InputDecoration(labelText: 'Handling notes')),
              ],
              const SizedBox(height: 14),
              const Text('Dietary information', style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: dietaryTags.entries
                    .map((e) => FilterChip(
                          label: Text(e.value),
                          selected: _tags.contains(e.key),
                          selectedColor: FB.leafSoft,
                          onSelected: (v) => setState(() => v ? _tags.add(e.key) : _tags.remove(e.key)),
                        ))
                    .toList(),
              ),
            ]),
          ),
          right: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            SectionCard(
              title: 'Pickup availability',
              help: 'NGOs claim one of these windows; you can also accept a proposed time.',
              child: WindowEditor(windows: _windows),
            ),
            const SizedBox(height: 14),
            SectionCard(
              title: 'What happens next',
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: const [
                _Step(1, 'AI matching ranks NGOs by food type, quantity, distance, timing and reliability.'),
                _Step(2, 'The top matches are notified and see it in their live feed.'),
                _Step(3, 'An NGO claims a slot — or you offer it directly to a match.'),
                _Step(4, 'Both sides confirm; reminders go out before pickup.'),
              ]),
            ),
          ]),
        ),
      ],
    );
  }
}

class _Step extends StatelessWidget {
  final int n;
  final String text;
  const _Step(this.n, this.text);
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          CircleAvatar(
              radius: 11,
              backgroundColor: FB.leafSoft,
              child: Text('$n', style: const TextStyle(fontSize: 11, color: FB.forest, fontWeight: FontWeight.w800))),
          const SizedBox(width: 10),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
        ]),
      );
}

// ------------------------------------------------------------------ detail
class ListingDetailScreen extends StatefulWidget {
  final int listingId;
  const ListingDetailScreen({super.key, required this.listingId});
  @override
  State<ListingDetailScreen> createState() => _ListingDetailScreenState();
}

class _ListingDetailScreenState extends State<ListingDetailScreen> {
  int _v = 0;
  bool _refreshMatches = false;

  Future<(Json, List<Json>, List<Json>)> _load() async {
    final id = widget.listingId;
    final r = await Future.wait([
      api.get('/marketplace/listings/$id/'),
      api.get('/marketplace/listings/$id/matches/', query: {'refresh': _refreshMatches ? '1' : null}),
      api.get('/pickups/', query: {'listing': id, 'page_size': 50}),
    ]);
    _refreshMatches = false;
    return (toJ(r[0]), toL(r[1]), toL(r[2]));
  }

  Future<void> _offer(Json listing, Json match) async {
    final ngo = toJ(match['ngo']);
    await showDialog(
      context: context,
      builder: (dc) => PickupRequestDialog(
        listing: listing,
        title: 'Offer to ${toS(ngo['name'])}',
        submitLabel: 'Send offer',
        onSubmit: (payload) async {
          final ok = await runAction(
              dc, () => api.post('/marketplace/listings/${widget.listingId}/offer/', {...payload, 'ngo': toI(ngo['id'])}),
              success: 'Offer sent — ${toS(ngo['name'])} has been notified');
          if (ok && dc.mounted) {
            Navigator.pop(dc);
            setState(() => _v++);
          }
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RemoteView<(Json, List<Json>, List<Json>)>(
      key: ValueKey(_v),
      load: _load,
      builder: (context, data, reload) {
        final (l, matches, pickups) = data;
        final open = toS(l['status']) == 'available' || toS(l['status']) == 'reserved';
        return PageScaffold(
          title: toS(l['title']),
          subtitle: 'LST-${toI(l['id']).toString().padLeft(4, '0')} · ${fmtKg(toD(l['remaining_kg']))} of '
              '${fmtKg(toD(l['quantity_kg']))} remaining · ${expiryLabel(toI(l['days_to_expiry']))}',
          onRefresh: reload,
          actions: [
            OutlinedButton.icon(
                onPressed: () => context.go('/listings'),
                icon: const Icon(Icons.arrow_back_rounded),
                label: const Text('Listings')),
            if (open)
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(foregroundColor: FB.tomato),
                onPressed: () async {
                  if (!await confirmDialog(context, 'Withdraw listing?',
                      'Pending and scheduled pickups will be cancelled and NGOs notified.',
                      confirm: 'Withdraw', danger: true)) {
                    return;
                  }
                  final ok = await runAction(context, () => api.post('/marketplace/listings/${toI(l['id'])}/cancel/'),
                      success: 'Listing withdrawn');
                  if (ok) setState(() => _v++);
                },
                icon: const Icon(Icons.block_rounded),
                label: const Text('Withdraw'),
              ),
          ],
          children: [
            SplitRow(
              leftFlex: 3,
              rightFlex: 2,
              left: SectionCard(
                title: 'AI-ranked NGO matches',
                help: 'Scores combine food-type fit, proximity, quantity fit, needs text similarity, pickup history, '
                    'reliability and timing. Weights adapt to urgency — closer NGOs matter more as expiry nears.',
                trailing: TextButton.icon(
                  onPressed: () => setState(() {
                    _refreshMatches = true;
                    _v++;
                  }),
                  icon: const Icon(Icons.refresh_rounded, size: 18),
                  label: const Text('Re-run'),
                ),
                child: matches.isEmpty
                    ? const EmptyState(
                        icon: Icons.search_off_rounded,
                        title: 'No eligible NGOs yet',
                        message: 'No NGO passes the hard constraints (category, distance, cold storage, capacity).')
                    : Column(
                        children: matches.asMap().entries.map((e) {
                          final m = e.value;
                          final ngo = toJ(m['ngo']);
                          return Container(
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: e.key == 0 ? FB.leafSoft.withOpacity(.5) : Colors.white,
                              border: Border.all(color: e.key == 0 ? FB.leaf.withOpacity(.4) : FB.line),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                              Row(children: [
                                ScoreRing(toD(m['score'])),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                    Row(children: [
                                      Flexible(
                                        child: Text(toS(ngo['name']),
                                            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                                      ),
                                      if (e.key == 0) ...[const SizedBox(width: 8), const Pill('Best match', color: FB.leaf)],
                                    ]),
                                    Text(
                                      '${titleCase(toS(ngo['kind']))} · ${fmtNum(toD(m['distance_km']))} km · '
                                      'serves ${fmtInt(toI(ngo['beneficiaries']))} people · ${titleCase(toS(m['status']))}',
                                      style: const TextStyle(color: FB.muted, fontSize: 12.5),
                                    ),
                                  ]),
                                ),
                                if (open)
                                  FilledButton(
                                    style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12)),
                                    onPressed: () => _offer(l, m),
                                    child: const Text('Offer'),
                                  ),
                              ]),
                              const SizedBox(height: 10),
                              MatchBreakdown(breakdown: toJ(m['breakdown']), reasons: m['reasons'] is List ? m['reasons'] as List : const []),
                            ]),
                          );
                        }).toList(),
                      ),
              ),
              right: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                SectionCard(
                  title: 'Details',
                  trailing: StatusChip(toS(l['status'])),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    InfoRow('Category', toS(toJ(l['category_detail'])['name'], '—')),
                    InfoRow('Quantity', '${fmtKg(toD(l['quantity_kg']))}'
                        '${l['quantity_units'] != null ? ' (${fmtNum(toD(l['quantity_units']))} ${toS(l['unit'])})' : ''}'),
                    InfoRow('Est. meals', fmtInt(toI(l['estimated_meals']))),
                    InfoRow('Best before', fmtDate(toDate(l['expiry_date']))),
                    InfoRow('Pickup at', toS(l['pickup_address'], '—')),
                    InfoRow('Storage', l['requires_refrigeration'] == true ? 'Refrigerated' : 'Ambient / hot-hold'),
                    if (toS(l['description']).isNotEmpty) InfoRow('Description', toS(l['description'])),
                    if (toS(l['handling_notes']).isNotEmpty) InfoRow('Handling', toS(l['handling_notes'])),
                    const SizedBox(height: 8),
                    const Text('Availability windows', style: TextStyle(fontWeight: FontWeight.w700)),
                    ...toL(l['windows']).map((w) => Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Row(children: [
                            const Icon(Icons.schedule_rounded, size: 16, color: FB.leaf),
                            const SizedBox(width: 6),
                            Text(fmtRange(toDate(w['start']), toDate(w['end']))),
                          ]),
                        )),
                  ]),
                ),
                const SizedBox(height: 14),
                SectionCard(
                  title: 'Pickups',
                  child: pickups.isEmpty
                      ? const Text('No pickups yet.', style: TextStyle(color: FB.muted))
                      : Column(
                          children: pickups
                              .map((p) => ListTile(
                                    contentPadding: EdgeInsets.zero,
                                    onTap: () => context.go('/pickups/${toI(p['id'])}'),
                                    title: Text(toS(toJ(p['ngo'])['name'])),
                                    subtitle: Text(
                                        '${fmtKg(toD(p['quantity_kg']))} · ${fmtRange(toDate(p['scheduled_start']), toDate(p['scheduled_end']))}'),
                                    trailing: StatusChip(toS(p['status'])),
                                  ))
                              .toList(),
                        ),
                ),
              ]),
            ),
          ],
        );
      },
    );
  }
}
