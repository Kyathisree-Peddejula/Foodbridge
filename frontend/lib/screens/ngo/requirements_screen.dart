import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';
import '../../widgets/marketplace.dart';
import '../business/stock_dialogs.dart';

const _days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/// NGO needs profile — drives the AI matching engine (hard constraints + preferences).
class RequirementsScreen extends StatefulWidget {
  const RequirementsScreen({super.key});
  @override
  State<RequirementsScreen> createState() => _RequirementsScreenState();
}

class _RequirementsScreenState extends State<RequirementsScreen> {
  int _v = 0;

  Future<void> _edit([Json? r]) async {
    final ok = await showDialog<bool>(context: context, builder: (_) => _RequirementDialog(existing: r));
    if (ok == true) setState(() => _v++);
  }

  @override
  Widget build(BuildContext context) {
    return RemoteView<List<Json>>(
      key: ValueKey(_v),
      load: () async => toL(await api.get('/marketplace/requirements/')),
      builder: (context, rows, reload) => PageScaffold(
        title: 'Our food needs',
        subtitle: 'Tell the matching engine what you can accept — food types, quantities, distance, storage and times',
        onRefresh: reload,
        actions: [
          FilledButton.icon(onPressed: () => _edit(), icon: const Icon(Icons.add_rounded), label: const Text('Add need')),
        ],
        children: [
          if (rows.isEmpty)
            SectionCard(
              child: EmptyState(
                icon: Icons.tune_rounded,
                title: 'No needs defined',
                message: 'Without a needs profile you are matched on distance and capacity only.',
                action: FilledButton(onPressed: () => _edit(), child: const Text('Define your needs')),
              ),
            ),
          ResponsiveGrid(
            minTileWidth: 340,
            children: rows.map((r) {
              final days = (r['pickup_days'] is List ? r['pickup_days'] as List : const []).map((d) => _days[toI(d) % 7]);
              return SectionCard(
                title: toS(r['title']),
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  StatusChip(r['is_active'] == true ? 'active' : 'cancelled', label: r['is_active'] == true ? 'Active' : 'Paused'),
                  IconButton(tooltip: 'Edit', onPressed: () => _edit(r), icon: const Icon(Icons.edit_outlined, size: 20)),
                  IconButton(tooltip: 'Delete', 
                    onPressed: () async {
                      if (!await confirmDialog(context, 'Delete need?', 'This removes it from matching.',
                          confirm: 'Delete', danger: true)) {
                        return;
                      }
                      final ok = await runAction(context, () => api.delete('/marketplace/requirements/${toI(r['id'])}/'));
                      if (ok) setState(() => _v++);
                    },
                    icon: const Icon(Icons.delete_outline_rounded, size: 20),
                  ),
                ]),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      ...(r['category_names'] is List ? r['category_names'] as List : const [])
                          .map((c) => Pill(c.toString(), color: FB.leaf)),
                      if ((r['category_names'] as List?)?.isEmpty ?? true) const Pill('Any food type', color: FB.muted),
                    ],
                  ),
                  const SizedBox(height: 10),
                  InfoRow('Quantity', '${fmtKg(toD(r['min_quantity_kg']))} – ${fmtKg(toD(r['max_quantity_kg']))}',
                      icon: Icons.scale_rounded),
                  InfoRow('Max distance', '${fmtNum(toD(r['max_distance_km']))} km', icon: Icons.near_me_rounded),
                  InfoRow('Cold storage', r['has_refrigeration'] == true ? 'Yes' : 'No', icon: Icons.ac_unit_rounded),
                  InfoRow('Pickup hours', '${toI(r['pickup_from_hour'])}:00 – ${toI(r['pickup_to_hour'])}:00 · '
                      '${days.isEmpty ? 'any day' : days.join(', ')}', icon: Icons.schedule_rounded),
                  InfoRow(
                      'Dietary',
                      (r['dietary_restrictions'] as List?)?.isNotEmpty == true
                          ? (r['dietary_restrictions'] as List).map((t) => dietaryTags[t] ?? t).join(', ')
                          : 'No restriction',
                      icon: Icons.eco_outlined),
                  if (toS(r['notes']).isNotEmpty) InfoRow('Notes', toS(r['notes']), icon: Icons.notes_rounded),
                ]),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _RequirementDialog extends StatefulWidget {
  final Json? existing;
  const _RequirementDialog({this.existing});
  @override
  State<_RequirementDialog> createState() => _RequirementDialogState();
}

class _RequirementDialogState extends State<_RequirementDialog> {
  late final Json e = widget.existing ?? {};
  late final _title = TextEditingController(text: toS(e['title']));
  late final _min = TextEditingController(text: e.isEmpty ? '0' : fmtNum(toD(e['min_quantity_kg'])).replaceAll(',', ''));
  late final _max = TextEditingController(text: e.isEmpty ? '200' : fmtNum(toD(e['max_quantity_kg'])).replaceAll(',', ''));
  late final _notes = TextEditingController(text: toS(e['notes']));
  late double _dist = toD(e['max_distance_km'], 15).clamp(1, 50).toDouble();
  late bool _fridge = e['has_refrigeration'] == true;
  late bool _active = e.isEmpty || e['is_active'] == true;
  late RangeValues _hours = RangeValues(toD(e['pickup_from_hour'], 8), toD(e['pickup_to_hour'], 21));
  late final Set<int> _cats = {...(e['categories'] is List ? (e['categories'] as List).map((c) => toI(c)) : <int>[])};
  late final Set<String> _diet = {...(e['dietary_restrictions'] is List ? (e['dietary_restrictions'] as List).map((c) => c.toString()) : <String>[])};
  late final Set<int> _dayset = {...(e['pickup_days'] is List ? (e['pickup_days'] as List).map((c) => toI(c)) : <int>[])};
  List<Json> _all = [];
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    Taxonomy.load().then((c) {
      if (mounted) setState(() => _all = c);
    });
  }

  Future<void> _save() async {
    if (_title.text.trim().isEmpty) return toast(context, 'Give this need a title', error: true);
    setState(() => _busy = true);
    final body = {
      'title': _title.text.trim(),
      'categories': _cats.toList(),
      'min_quantity_kg': double.tryParse(_min.text) ?? 0,
      'max_quantity_kg': double.tryParse(_max.text) ?? 500,
      'max_distance_km': _dist.roundToDouble(),
      'dietary_restrictions': _diet.toList(),
      'has_refrigeration': _fridge,
      'pickup_days': (_dayset.toList()..sort()),
      'pickup_from_hour': _hours.start.round(),
      'pickup_to_hour': _hours.end.round(),
      'notes': _notes.text.trim(),
      'is_active': _active,
    };
    final ok = await runAction(
      context,
      () => e.isEmpty
          ? api.post('/marketplace/requirements/', body)
          : api.put('/marketplace/requirements/${toI(e['id'])}/', body),
      success: 'Needs saved — future listings will be matched against them',
    );
    if (mounted) setState(() => _busy = false);
    if (ok && mounted) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    return FormDialog(
      title: e.isEmpty ? 'Add a food need' : 'Edit need',
      width: 620,
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Saving…' : 'Save')),
      ],
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        TextField(controller: _title, decoration: const InputDecoration(labelText: 'Title', hintText: 'e.g. Hot meals for night shelter')),
        const SizedBox(height: 14),
        const Text('Food types we accept (none = any)', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: _all
              .map((c) => FilterChip(
                    label: Text(toS(c['name'])),
                    selected: _cats.contains(toI(c['id'])),
                    selectedColor: hexColor(toS(c['color'])).withOpacity(.2),
                    onSelected: (v) => setState(() => v ? _cats.add(toI(c['id'])) : _cats.remove(toI(c['id']))),
                  ))
              .toList(),
        ),
        const SizedBox(height: 14),
        Row(children: [
          Expanded(child: TextField(controller: _min, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Min kg per pickup'))),
          const SizedBox(width: 10),
          Expanded(child: TextField(controller: _max, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Max kg per pickup'))),
        ]),
        const SizedBox(height: 14),
        Text('Max distance: ${_dist.round()} km', style: const TextStyle(fontWeight: FontWeight.w700)),
        Slider(value: _dist, min: 1, max: 50, divisions: 49, activeColor: FB.leaf, onChanged: (v) => setState(() => _dist = v)),
        Text('Pickup hours: ${_hours.start.round()}:00 – ${_hours.end.round()}:00', style: const TextStyle(fontWeight: FontWeight.w700)),
        RangeSlider(
          values: _hours,
          min: 0,
          max: 24,
          divisions: 24,
          activeColor: FB.leaf,
          onChanged: (v) => setState(() => _hours = v),
        ),
        const Text('Pickup days (none = any day)', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        Wrap(
          spacing: 6,
          children: [
            for (var i = 0; i < 7; i++)
              FilterChip(
                label: Text(_days[i]),
                selected: _dayset.contains(i),
                onSelected: (v) => setState(() => v ? _dayset.add(i) : _dayset.remove(i)),
              ),
          ],
        ),
        const SizedBox(height: 14),
        const Text('Dietary: accept only these tags (none = no restriction)', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: dietaryTags.entries
              .map((d) => FilterChip(
                    label: Text(d.value),
                    selected: _diet.contains(d.key),
                    onSelected: (v) => setState(() => v ? _diet.add(d.key) : _diet.remove(d.key)),
                  ))
              .toList(),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: _fridge,
          onChanged: (v) => setState(() => _fridge = v),
          title: const Text('We have refrigeration'),
          subtitle: const Text('Required to be matched with chilled food'),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: _active,
          onChanged: (v) => setState(() => _active = v),
          title: const Text('Active'),
        ),
        TextField(controller: _notes, maxLines: 2, decoration: const InputDecoration(labelText: 'Notes (used for text matching)')),
      ]),
    );
  }
}
