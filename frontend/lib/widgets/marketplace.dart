import 'package:flutter/material.dart';

import '../theme.dart';
import '../utils/format.dart';
import '../utils/json.dart';
import 'common.dart';

const dietaryTags = {
  'veg': 'Vegetarian',
  'non_veg': 'Non-veg',
  'vegan': 'Vegan',
  'jain': 'Jain',
  'halal': 'Halal',
  'contains_nuts': 'Contains nuts',
  'contains_dairy': 'Contains dairy',
  'gluten_free': 'Gluten free',
};

class TimeWindow {
  DateTime start;
  DateTime end;
  TimeWindow(this.start, this.end);
  Json toJson() => {'start': start.toUtc().toIso8601String(), 'end': end.toUtc().toIso8601String()};
}

Future<DateTime?> pickDateTime(BuildContext context, DateTime initial) async {
  final d = await showDatePicker(
    context: context,
    initialDate: initial,
    firstDate: DateTime.now().subtract(const Duration(days: 1)),
    lastDate: DateTime.now().add(const Duration(days: 60)),
  );
  if (d == null || !context.mounted) return null;
  final t = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(initial));
  if (t == null) return null;
  return DateTime(d.year, d.month, d.day, t.hour, t.minute);
}

/// Editable list of pickup availability windows.
class WindowEditor extends StatefulWidget {
  final List<TimeWindow> windows;
  final bool single;
  const WindowEditor({super.key, required this.windows, this.single = false});
  @override
  State<WindowEditor> createState() => _WindowEditorState();
}

class _WindowEditorState extends State<WindowEditor> {
  @override
  Widget build(BuildContext context) {
    final w = widget.windows;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      for (var i = 0; i < w.length; i++)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(children: [
            const Icon(Icons.schedule_rounded, color: FB.leaf, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Wrap(spacing: 8, runSpacing: 6, children: [
                OutlinedButton(
                  onPressed: () async {
                    final d = await pickDateTime(context, w[i].start);
                    if (d != null) {
                      setState(() {
                        final len = w[i].end.difference(w[i].start);
                        w[i].start = d;
                        if (!w[i].end.isAfter(d)) w[i].end = d.add(len.inMinutes > 0 ? len : const Duration(hours: 2));
                      });
                    }
                  },
                  child: Text('From ${fmtDateTime(w[i].start)}'),
                ),
                OutlinedButton(
                  onPressed: () async {
                    final d = await pickDateTime(context, w[i].end);
                    if (d != null && d.isAfter(w[i].start)) setState(() => w[i].end = d);
                  },
                  child: Text('To ${fmtDateTime(w[i].end)}'),
                ),
              ]),
            ),
            if (!widget.single)
              IconButton(
              tooltip: 'Remove',
              onPressed: w.length == 1 ? null : () => setState(() => w.removeAt(i)),
              icon: const Icon(Icons.delete_outline_rounded),
            ),
          ]),
        ),
      if (!widget.single)
        Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          onPressed: () => setState(() {
            final base = w.isEmpty ? _nextHour() : w.last.end.add(const Duration(hours: 1));
            w.add(TimeWindow(base, base.add(const Duration(hours: 3))));
          }),
          icon: const Icon(Icons.add_rounded),
          label: const Text('Add availability window'),
        ),
      ),
    ]);
  }
}

DateTime _nextHour() {
  final n = DateTime.now();
  return DateTime(n.year, n.month, n.day, n.hour + 1);
}

List<TimeWindow> defaultWindows() {
  final s = _nextHour();
  return [TimeWindow(s, s.add(const Duration(hours: 4)))];
}

/// Explains an AI match score: weighted signals + human-readable reasons.
class MatchBreakdown extends StatelessWidget {
  final Json breakdown;
  final List reasons;
  const MatchBreakdown({super.key, required this.breakdown, required this.reasons});

  static const labels = {
    'category': 'Food type fit',
    'proximity': 'Proximity',
    'quantity': 'Quantity fit',
    'semantic': 'Needs text match',
    'history': 'Past pickups',
    'reliability': 'Reliability',
    'timing': 'Pickup timing',
  };

  @override
  Widget build(BuildContext context) {
    final w = toJ(breakdown['_weights']);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (reasons.isNotEmpty)
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: reasons.map((r) => Pill(r.toString(), color: FB.leaf, icon: Icons.check_rounded)).toList(),
        ),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 0, children: [
        for (final e in labels.entries)
          if (breakdown.containsKey(e.key))
            SizedBox(
              width: 150,
              child: MeterBar(
                label: '${e.value}${w[e.key] != null ? ' ·${(toD(w[e.key]) * 100).round()}%' : ''}',
                value: toD(breakdown[e.key]),
                color: FB.leaf,
                trailing: '${(toD(breakdown[e.key]) * 100).round()}',
              ),
            ),
      ]),
    ]);
  }
}

class ScoreRing extends StatelessWidget {
  final double score;
  final double size;
  const ScoreRing(this.score, {super.key, this.size = 48});
  @override
  Widget build(BuildContext context) {
    final c = score >= 70 ? FB.leaf : score >= 45 ? FB.amber : FB.muted;
    return SizedBox(
      width: size,
      height: size,
      child: Stack(alignment: Alignment.center, children: [
        SizedBox(
          width: size,
          height: size,
          child: CircularProgressIndicator(
            value: (score / 100).clamp(0, 1).toDouble(),
            strokeWidth: 4,
            color: c,
            backgroundColor: c.withOpacity(.15),
          ),
        ),
        Text(score.toStringAsFixed(0), style: TextStyle(fontWeight: FontWeight.w800, color: c, fontSize: size * .3)),
      ]),
    );
  }
}

/// Claim (NGO) or offer (donor) form: quantity + window or custom slot + driver details.
class PickupRequestDialog extends StatefulWidget {
  final Json listing;
  final String title;
  final String submitLabel;
  final Future<void> Function(Json payload) onSubmit;
  const PickupRequestDialog({
    super.key,
    required this.listing,
    required this.title,
    required this.submitLabel,
    required this.onSubmit,
  });
  @override
  State<PickupRequestDialog> createState() => _PickupRequestDialogState();
}

class _PickupRequestDialogState extends State<PickupRequestDialog> {
  late final _qty = TextEditingController(text: fmtNum(toD(widget.listing['remaining_kg'], toD(widget.listing['quantity_kg']))).replaceAll(',', ''));
  final _driver = TextEditingController();
  final _phone = TextEditingController();
  final _vehicle = TextEditingController();
  final _notes = TextEditingController();
  int? _window;
  bool _custom = false;
  late TimeWindow _slot = defaultWindows().first;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final ws = toL(widget.listing['windows']);
    final upcoming = ws.where((w) => (toDate(w['end']) ?? DateTime.now()).isAfter(DateTime.now())).toList();
    if (upcoming.isNotEmpty) {
      _window = toI(upcoming.first['id']);
    } else {
      _custom = true;
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = widget.listing;
    final ws = toL(l['windows']).where((w) => (toDate(w['end']) ?? DateTime.now()).isAfter(DateTime.now())).toList();
    return FormDialog(
      title: widget.title,
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: _busy
              ? null
              : () async {
                  final q = double.tryParse(_qty.text);
                  if (q == null || q <= 0) return toast(context, 'Enter a quantity in kg', error: true);
                  setState(() => _busy = true);
                  try {
                    await widget.onSubmit({
                      'quantity_kg': q,
                      if (!_custom && _window != null) 'window': _window,
                      if (_custom) 'scheduled_start': _slot.start.toUtc().toIso8601String(),
                      if (_custom) 'scheduled_end': _slot.end.toUtc().toIso8601String(),
                      'driver_name': _driver.text,
                      'driver_phone': _phone.text,
                      'vehicle': _vehicle.text,
                      'notes': _notes.text,
                    });
                  } finally {
                    if (mounted) setState(() => _busy = false);
                  }
                },
          child: Text(_busy ? 'Sending…' : widget.submitLabel),
        ),
      ],
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(toS(l['title']), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        Text('${fmtKg(toD(l['remaining_kg'], toD(l['quantity_kg'])))} available · ${expiryLabel(toI(l['days_to_expiry']))}',
            style: const TextStyle(color: FB.muted)),
        const SizedBox(height: 14),
        TextField(
          controller: _qty,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Quantity (kg)'),
        ),
        const SizedBox(height: 14),
        const Text('Pickup slot', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        ...ws.map((w) => RadioListTile<int>(
              dense: true,
              contentPadding: EdgeInsets.zero,
              value: toI(w['id']),
              groupValue: _custom ? null : _window,
              onChanged: (v) => setState(() {
                _window = v;
                _custom = false;
              }),
              title: Text(fmtRange(toDate(w['start']), toDate(w['end']))),
            )),
        RadioListTile<int>(
          dense: true,
          contentPadding: EdgeInsets.zero,
          value: -1,
          groupValue: _custom ? -1 : null,
          onChanged: (_) => setState(() => _custom = true),
          title: const Text('Propose another time'),
        ),
        if (_custom) WindowEditor(windows: [_slot], single: true),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: TextField(controller: _driver, decoration: const InputDecoration(labelText: 'Driver / volunteer'))),
          const SizedBox(width: 10),
          Expanded(child: TextField(controller: _phone, decoration: const InputDecoration(labelText: 'Phone'))),
        ]),
        const SizedBox(height: 10),
        TextField(controller: _vehicle, decoration: const InputDecoration(labelText: 'Vehicle (optional)')),
        const SizedBox(height: 10),
        TextField(controller: _notes, maxLines: 2, decoration: const InputDecoration(labelText: 'Notes (optional)')),
      ]),
    );
  }
}
