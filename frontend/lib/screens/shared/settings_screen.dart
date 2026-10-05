import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../config.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';
import '../business/stock_dialogs.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final business = auth.role == Role.business;
    return PageScaffold(
      title: 'Settings',
      subtitle: 'Organization profile${business ? ', expiry thresholds and POS integrations' : ''}',
      children: [
        const _ProfileCard(),
        if (business) ...[
          const SizedBox(height: 14),
          const _ThresholdsCard(),
          const SizedBox(height: 14),
          const _PosCard(),
        ],
      ],
    );
  }
}

// ------------------------------------------------------------------ profile
class _ProfileCard extends StatefulWidget {
  const _ProfileCard();
  @override
  State<_ProfileCard> createState() => _ProfileCardState();
}

class _ProfileCardState extends State<_ProfileCard> {
  final _c = <String, TextEditingController>{};
  bool _canPickup = true;
  bool _loaded = false;
  bool _busy = false;

  static const common = [
    ('name', 'Organization name'),
    ('contact_email', 'Contact email'),
    ('phone', 'Phone'),
    ('city', 'City'),
    ('address', 'Address'),
    ('latitude', 'Latitude'),
    ('longitude', 'Longitude'),
  ];
  static const businessFields = [
    ('storage_capacity_kg', 'Storage capacity (kg)'),
    ('reorder_lead_time_days', 'Supplier lead time (days)'),
  ];
  static const ngoFields = [
    ('daily_capacity_kg', 'Daily capacity (kg)'),
    ('beneficiaries', 'People served'),
  ];

  @override
  void initState() {
    super.initState();
    api.get('/organizations/mine/').then((o) {
      final j = toJ(o);
      if (!mounted) return;
      setState(() {
        for (final f in [...common, ...businessFields, ...ngoFields]) {
          _c[f.$1] = TextEditingController(text: toS(j[f.$1]));
        }
        _canPickup = j['can_pickup'] != false;
        _loaded = true;
      });
    }).catchError((e) {
      if (mounted) toast(context, e.toString(), error: true);
    });
  }

  Future<void> _save(bool business) async {
    setState(() => _busy = true);
    final body = <String, dynamic>{
      for (final f in common)
        if (f.$1 == 'latitude' || f.$1 == 'longitude')
          f.$1: double.tryParse(_c[f.$1]!.text)?.toStringAsFixed(6)
        else
          f.$1: _c[f.$1]!.text.trim(),
      'can_pickup': _canPickup,
    };
    for (final f in business ? businessFields : ngoFields) {
      final v = _c[f.$1]!.text.trim();
      if (v.isEmpty) continue;
      body[f.$1] = (f.$1 == 'reorder_lead_time_days' || f.$1 == 'beneficiaries') ? int.tryParse(v) : double.tryParse(v);
    }
    final ok = await runAction(context, () => api.patch('/organizations/mine/', body), success: 'Profile saved');
    if (ok && mounted) await context.read<AuthState>().reloadMe();
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final business = context.watch<AuthState>().role == Role.business;
    if (!_loaded) return const SectionCard(child: Center(child: CircularProgressIndicator()));
    final fields = [...common, ...(business ? businessFields : ngoFields)];
    return SectionCard(
      title: 'Organization profile',
      help: 'Coordinates are used for distance-based matching; storage capacity caps reorder recommendations.',
      trailing: FilledButton(onPressed: _busy ? null : () => _save(business), child: Text(_busy ? 'Saving…' : 'Save')),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        ResponsiveGrid(
          minTileWidth: 260,
          spacing: 12,
          children: fields
              .map((f) => TextField(
                    controller: _c[f.$1],
                    keyboardType: const {'latitude', 'longitude', 'storage_capacity_kg', 'reorder_lead_time_days', 'daily_capacity_kg', 'beneficiaries'}
                            .contains(f.$1)
                        ? const TextInputType.numberWithOptions(decimal: true, signed: true)
                        : TextInputType.text,
                    decoration: InputDecoration(labelText: f.$2),
                  ))
              .toList(),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: _canPickup,
          onChanged: (v) => setState(() => _canPickup = v),
          title: Text(business ? 'Pickups allowed at our address' : 'We can collect donations ourselves'),
        ),
      ]),
    );
  }
}

// ------------------------------------------------------------------ thresholds
class _ThresholdsCard extends StatefulWidget {
  const _ThresholdsCard();
  @override
  State<_ThresholdsCard> createState() => _ThresholdsCardState();
}

class _ThresholdsCardState extends State<_ThresholdsCard> {
  int _v = 0;

  Future<void> _edit(List<Json> cats, [Json? t]) async {
    int? cat = t == null ? null : (t['category'] == null ? null : toI(t['category']));
    final warn = TextEditingController(text: t == null ? '3' : '${toI(t['warning_days'])}');
    final crit = TextEditingController(text: t == null ? '1' : '${toI(t['critical_days'])}');
    final go = await showDialog<bool>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, set) => FormDialog(
          title: t == null ? 'Add alert threshold' : 'Edit threshold',
          width: 440,
          actions: [
            TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Save')),
          ],
          child: Column(children: [
            DropdownButtonFormField<int?>(
              value: cat,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Applies to'),
              items: [
                const DropdownMenuItem<int?>(value: null, child: Text('All categories (default)')),
                ...cats.map((x) => DropdownMenuItem<int?>(value: toI(x['id']), child: Text(toS(x['name'])))),
              ],
              onChanged: (v) => set(() => cat = v),
            ),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                  child: TextField(
                      controller: warn, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Warning at ≤ days'))),
              const SizedBox(width: 10),
              Expanded(
                  child: TextField(
                      controller: crit, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Critical at ≤ days'))),
            ]),
          ]),
        ),
      ),
    );
    if (go != true || !mounted) return;
    final body = {'category': cat, 'warning_days': int.tryParse(warn.text) ?? 3, 'critical_days': int.tryParse(crit.text) ?? 1};
    final ok = await runAction(
        context,
        () => t == null ? api.post('/expiry/thresholds/', body) : api.put('/expiry/thresholds/${toI(t['id'])}/', body),
        success: 'Threshold saved');
    if (ok) setState(() => _v++);
  }

  @override
  Widget build(BuildContext context) {
    return RemoteView<(List<Json>, List<Json>)>(
      key: ValueKey(_v),
      load: () async => (toL(await api.get('/expiry/thresholds/')), await Taxonomy.load()),
      builder: (context, data, reload) {
        final (rows, cats) = data;
        return SectionCard(
          title: 'Expiry alert thresholds',
          help: 'Alerts fire when days-to-expiry reach these values. Without an override, each category uses its taxonomy '
              'defaults (e.g. cooked meals 1/0 days, dairy 3/1, grains 30/10).',
          trailing: OutlinedButton.icon(
              onPressed: () => _edit(cats), icon: const Icon(Icons.add_rounded, size: 18), label: const Text('Add')),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            if (rows.isEmpty)
              const Text('Using category defaults:', style: TextStyle(color: FB.muted)),
            ...rows.map((t) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.tune_rounded, color: FB.leaf),
                  title: Text(toS(t['category_name'], 'All categories')),
                  subtitle: Text('Warning ≤ ${toI(t['warning_days'])} d · critical ≤ ${toI(t['critical_days'])} d'),
                  trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                    IconButton(tooltip: 'Edit', onPressed: () => _edit(cats, t), icon: const Icon(Icons.edit_outlined)),
                    IconButton(tooltip: 'Delete', 
                      onPressed: () async {
                        final ok = await runAction(context, () => api.delete('/expiry/thresholds/${toI(t['id'])}/'));
                        if (ok) setState(() => _v++);
                      },
                      icon: const Icon(Icons.delete_outline_rounded),
                    ),
                  ]),
                )),
            if (rows.isEmpty)
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: cats
                    .map((c) => Pill('${toS(c['name'])}: ${toI(c['warning_days'])}/${toI(c['critical_days'])} d',
                        color: hexColor(toS(c['color']))))
                    .toList(),
              ),
          ]),
        );
      },
    );
  }
}

// ------------------------------------------------------------------ POS
class _PosCard extends StatefulWidget {
  const _PosCard();
  @override
  State<_PosCard> createState() => _PosCardState();
}

class _PosCardState extends State<_PosCard> {
  int _v = 0;
  final Set<int> _revealed = {};

  Future<void> _create() async {
    final name = TextEditingController(text: 'Counter POS');
    final provider = TextEditingController(text: 'generic');
    final go = await showDialog<bool>(
      context: context,
      builder: (c) => FormDialog(
        title: 'Connect a POS system',
        width: 440,
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Create key')),
        ],
        child: Column(children: [
          TextField(controller: name, decoration: const InputDecoration(labelText: 'Name')),
          const SizedBox(height: 10),
          TextField(controller: provider, decoration: const InputDecoration(labelText: 'Provider (e.g. Petpooja, Square)')),
        ]),
      ),
    );
    if (go != true || !mounted) return;
    final ok = await runAction(context, () => api.post('/pos/integrations/', {'name': name.text, 'provider': provider.text}),
        success: 'POS key created');
    if (ok) setState(() => _v++);
  }

  @override
  Widget build(BuildContext context) {
    final base = AppConfig.apiBaseUrl;
    return RemoteView<List<Json>>(
      key: ValueKey(_v),
      load: () async => toL(await api.get('/pos/integrations/')),
      builder: (context, rows, reload) => SectionCard(
        title: 'POS integrations',
        help: 'Your POS pushes sales and deliveries to FoodBridge over REST using the X-POS-Key header.',
        trailing: OutlinedButton.icon(onPressed: _create, icon: const Icon(Icons.add_link_rounded, size: 18), label: const Text('Connect')),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (rows.isEmpty) const Text('No POS connected yet.', style: TextStyle(color: FB.muted)),
          ...rows.map((p) {
            final id = toI(p['id']);
            final key = toS(p['api_key']);
            final shown = _revealed.contains(id);
            return Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(border: Border.all(color: FB.line), borderRadius: BorderRadius.circular(10)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  const Icon(Icons.point_of_sale_rounded, color: FB.forest),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text('${toS(p['name'])} · ${toS(p['provider'])}', style: const TextStyle(fontWeight: FontWeight.w700)),
                  ),
                  Switch(
                    value: p['is_active'] == true,
                    activeColor: FB.leaf,
                    onChanged: (v) async {
                      final ok = await runAction(context, () => api.patch('/pos/integrations/$id/', {'is_active': v}));
                      if (ok) setState(() => _v++);
                    },
                  ),
                ]),
                const SizedBox(height: 6),
                Row(children: [
                  Expanded(
                    child: SelectableText(shown ? key : '${key.substring(0, key.length.clamp(0, 8))}••••••••••••',
                        style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
                  ),
                  IconButton(
                    tooltip: shown ? 'Hide' : 'Reveal',
                    onPressed: () => setState(() => shown ? _revealed.remove(id) : _revealed.add(id)),
                    icon: Icon(shown ? Icons.visibility_off_outlined : Icons.visibility_outlined, size: 20),
                  ),
                  IconButton(
                    tooltip: 'Copy',
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: key));
                      toast(context, 'Key copied');
                    },
                    icon: const Icon(Icons.copy_rounded, size: 20),
                  ),
                  IconButton(
                    tooltip: 'Rotate key',
                    onPressed: () async {
                      if (!await confirmDialog(context, 'Rotate key?', 'The old key stops working immediately.', confirm: 'Rotate')) {
                        return;
                      }
                      final ok = await runAction(context, () => api.post('/pos/integrations/$id/rotate-key/'), success: 'Key rotated');
                      if (ok) setState(() => _v++);
                    },
                    icon: const Icon(Icons.autorenew_rounded, size: 20),
                  ),
                  IconButton(
                    tooltip: 'Delete',
                    onPressed: () async {
                      if (!await confirmDialog(context, 'Disconnect POS?', 'This deletes the key.', confirm: 'Delete', danger: true)) {
                        return;
                      }
                      final ok = await runAction(context, () => api.delete('/pos/integrations/$id/'));
                      if (ok) setState(() => _v++);
                    },
                    icon: const Icon(Icons.delete_outline_rounded, size: 20),
                  ),
                ]),
                Text(
                  '${toI(p['events_received'])} events · last sync ${p['last_sync_at'] == null ? 'never' : timeAgo(toDate(p['last_sync_at']))}',
                  style: const TextStyle(color: FB.muted, fontSize: 12),
                ),
              ]),
            );
          }),
          const SizedBox(height: 6),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: const Color(0xFF10261B), borderRadius: BorderRadius.circular(8)),
            child: SelectableText(
              'curl -X POST $base/pos/v1/sales/ \\\n'
              '  -H "X-POS-Key: <key>" -H "Content-Type: application/json" \\\n'
              '  -d \'{"transactions":[{"sku":"MILK-0001","quantity":2,"unit_price":"56","reference":"BILL-1042"}]}\'\n\n'
              '# deliveries: POST $base/pos/v1/receipts/   catalogue: GET $base/pos/v1/products/',
              style: const TextStyle(fontFamily: 'monospace', color: Color(0xFFBFE8CF), fontSize: 12),
            ),
          ),
        ]),
      ),
    );
  }
}
