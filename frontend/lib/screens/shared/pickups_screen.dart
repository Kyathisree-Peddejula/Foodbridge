import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:table_calendar/table_calendar.dart';

import '../../api/api_client.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';
import '../../widgets/marketplace.dart';

/// Pickup scheduling: calendar of pickups + items needing my confirmation.
class PickupsScreen extends StatefulWidget {
  const PickupsScreen({super.key});
  @override
  State<PickupsScreen> createState() => _PickupsScreenState();
}

class _PickupsScreenState extends State<PickupsScreen> {
  DateTime _focused = DateTime.now();
  DateTime _selected = DateTime.now();
  CalendarFormat _format = CalendarFormat.month;
  Map<DateTime, List<Json>> _events = {};
  List<Json> _pending = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  DateTime _day(DateTime d) => DateTime.utc(d.year, d.month, d.day);

  Future<void> _load() async {
    final first = DateTime(_focused.year, _focused.month, 1).subtract(const Duration(days: 7));
    final last = DateTime(_focused.year, _focused.month + 1, 0).add(const Duration(days: 7));
    try {
      final r = await Future.wait([
        api.get('/pickups/calendar/', query: {'start': isoDate(first), 'end': isoDate(last)}),
        api.get('/pickups/', query: {'status': 'requested', 'page_size': 50}),
      ]);
      final ev = <DateTime, List<Json>>{};
      for (final e in toL(toJ(r[0])['events'])) {
        final s = toDate(e['start']);
        if (s == null) continue;
        ev.putIfAbsent(_day(s), () => []).add(e);
      }
      setState(() {
        _events = ev;
        _pending = toL(r[1]).where((p) => p['awaiting'] != null && p['awaiting'] == p['my_side']).toList();
        _loading = false;
        _error = null;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  List<Json> _for(DateTime d) => _events[_day(d)] ?? const [];

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator(color: FB.leaf));
    if (_error != null && _events.isEmpty) return ErrorView(error: _error!, onRetry: _load);
    final today = _for(_selected);
    final calendar = SectionCard(
      padding: const EdgeInsets.fromLTRB(8, 12, 8, 8),
      child: TableCalendar<Json>(
        firstDay: DateTime.utc(2024, 1, 1),
        lastDay: DateTime.utc(2030, 12, 31),
        focusedDay: _focused,
        calendarFormat: _format,
        startingDayOfWeek: StartingDayOfWeek.monday,
        availableCalendarFormats: const {CalendarFormat.month: 'Month', CalendarFormat.twoWeeks: '2 weeks', CalendarFormat.week: 'Week'},
        selectedDayPredicate: (d) => isSameDay(d, _selected),
        eventLoader: _for,
        onDaySelected: (sel, foc) => setState(() {
          _selected = sel;
          _focused = foc;
        }),
        onFormatChanged: (f) => setState(() => _format = f),
        onPageChanged: (foc) {
          _focused = foc;
          _load();
        },
        headerStyle: HeaderStyle(
          titleTextStyle: FB.display(18),
          formatButtonDecoration: BoxDecoration(border: Border.all(color: FB.line), borderRadius: BorderRadius.circular(8)),
          formatButtonTextStyle: const TextStyle(fontSize: 12),
        ),
        calendarStyle: CalendarStyle(
          todayDecoration: BoxDecoration(color: FB.leaf.withOpacity(.25), shape: BoxShape.circle),
          todayTextStyle: const TextStyle(color: FB.forest, fontWeight: FontWeight.w700),
          selectedDecoration: const BoxDecoration(color: FB.forest, shape: BoxShape.circle),
          markersMaxCount: 4,
          outsideDaysVisible: false,
        ),
        calendarBuilders: CalendarBuilders<Json>(
          markerBuilder: (context, day, events) {
            if (events.isEmpty) return null;
            return Positioned(
              bottom: 4,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: events
                    .take(4)
                    .map((e) => Container(
                          width: 6,
                          height: 6,
                          margin: const EdgeInsets.symmetric(horizontal: 1),
                          decoration: BoxDecoration(color: FB.statusColor(toS(e['status'])), shape: BoxShape.circle),
                        ))
                    .toList(),
              ),
            );
          },
        ),
      ),
    );
    final dayList = SectionCard(
      title: fmtDate(_selected),
      trailing: Text('${today.length} pickup${today.length == 1 ? '' : 's'}', style: const TextStyle(color: FB.muted)),
      child: today.isEmpty
          ? const Padding(
              padding: EdgeInsets.all(16),
              child: Text('No pickups on this day.', style: TextStyle(color: FB.muted)),
            )
          : Column(
              children: today
                  .map((e) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        onTap: () => context.go('/pickups/${toI(e['id'])}'),
                        leading: Container(
                          width: 4,
                          height: 40,
                          decoration: BoxDecoration(
                              color: FB.statusColor(toS(e['status'])), borderRadius: BorderRadius.circular(2)),
                        ),
                        title: Text(toS(e['title']), style: const TextStyle(fontWeight: FontWeight.w600)),
                        subtitle: Text(
                            '${fmtTime(toDate(e['start']))}–${fmtTime(toDate(e['end']))} · ${fmtKg(toD(e['quantity_kg']))}\n'
                            '${toS(e['donor'])} → ${toS(e['ngo'])}'),
                        isThreeLine: true,
                        trailing: StatusChip(toS(e['status'])),
                      ))
                  .toList(),
            ),
    );
    return PageScaffold(
      title: 'Pickup schedule',
          help: 'A pickup is confirmed once both the donor and the NGO accept the slot. Reminders are sent 2 hours before.',
      subtitle: 'Calendar of donation pickups · both donor and NGO confirm every slot',
      onRefresh: _load,
      children: [
        if (_pending.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: FB.skySoft,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: FB.sky.withOpacity(.35)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Row(children: [
                const Icon(Icons.pending_actions_rounded, color: FB.sky),
                const SizedBox(width: 8),
                Text('${_pending.length} pickup${_pending.length == 1 ? '' : 's'} waiting for your confirmation',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ]),
              const SizedBox(height: 8),
              ..._pending.map((p) {
                final l = toJ(p['listing']);
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(children: [
                    Expanded(
                      child: Text(
                        '${toS(l['title'])} · ${fmtKg(toD(p['quantity_kg']))} · ${fmtRange(toDate(p['scheduled_start']), toDate(p['scheduled_end']))}'
                        ' · ${p['my_side'] == 'donor' ? toS(toJ(p['ngo'])['name']) : toS(toJ(l['donor'])['name'])}',
                      ),
                    ),
                    TextButton(onPressed: () => context.go('/pickups/${toI(p['id'])}'), child: const Text('Review')),
                    FilledButton(
                      style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10)),
                      onPressed: () async {
                        final ok = await runAction(context, () => api.post('/pickups/${toI(p['id'])}/confirm/'),
                            success: 'Pickup confirmed');
                        if (ok) _load();
                      },
                      child: const Text('Confirm'),
                    ),
                  ]),
                );
              }),
            ]),
          ),
          const SizedBox(height: 14),
        ],
        SplitRow(leftFlex: 3, rightFlex: 2, left: calendar, right: dayList),
        const SizedBox(height: 10),
        const Wrap(spacing: 14, runSpacing: 6, children: [
          _LegendDot('Awaiting', 'requested'),
          _LegendDot('Scheduled', 'confirmed'),
          _LegendDot('In transit', 'in_transit'),
          _LegendDot('Delivered', 'completed'),
          _LegendDot('Cancelled', 'cancelled'),
        ]),
      ],
    );
  }
}

class _LegendDot extends StatelessWidget {
  final String label;
  final String status;
  const _LegendDot(this.label, this.status);
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Dot(FB.statusColor(status)),
        const SizedBox(width: 6),
        Text(label, style: const TextStyle(fontSize: 12, color: FB.muted)),
      ]);
}

// ------------------------------------------------------------------ detail
class PickupDetailScreen extends StatefulWidget {
  final int pickupId;
  const PickupDetailScreen({super.key, required this.pickupId});
  @override
  State<PickupDetailScreen> createState() => _PickupDetailScreenState();
}

class _PickupDetailScreenState extends State<PickupDetailScreen> {
  int _v = 0;

  String get _base => '/pickups/${widget.pickupId}';

  Future<void> _act(String path, [Json? body, String? ok]) async {
    final done = await runAction(context, () => api.post('$_base/$path/', body ?? {}), success: ok);
    if (done) setState(() => _v++);
  }

  Future<void> _reschedule(Json p) async {
    final slot = TimeWindow(toDate(p['scheduled_start']) ?? DateTime.now(), toDate(p['scheduled_end']) ?? DateTime.now());
    final go = await showDialog<bool>(
      context: context,
      builder: (c) => FormDialog(
        title: 'Propose a new time',
        width: 460,
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Send')),
        ],
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('The other side will be asked to confirm the new slot.', style: TextStyle(color: FB.muted)),
          const SizedBox(height: 12),
          WindowEditor(windows: [slot], single: true),
        ]),
      ),
    );
    if (go == true) {
      await _act('reschedule', {
        'scheduled_start': slot.start.toUtc().toIso8601String(),
        'scheduled_end': slot.end.toUtc().toIso8601String(),
      }, 'New time proposed');
    }
  }

  Future<void> _collect() async {
    final driver = TextEditingController();
    final phone = TextEditingController();
    final vehicle = TextEditingController();
    final go = await showDialog<bool>(
      context: context,
      builder: (c) => FormDialog(
        title: 'Mark as collected',
        width: 460,
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Collected')),
        ],
        child: Column(children: [
          const Text('Stock is deducted from the donor inventory as a donation.', style: TextStyle(color: FB.muted)),
          const SizedBox(height: 12),
          TextField(controller: driver, decoration: const InputDecoration(labelText: 'Driver / volunteer')),
          const SizedBox(height: 10),
          TextField(controller: phone, decoration: const InputDecoration(labelText: 'Phone')),
          const SizedBox(height: 10),
          TextField(controller: vehicle, decoration: const InputDecoration(labelText: 'Vehicle')),
        ]),
      ),
    );
    if (go == true) {
      await _act('collect', {'driver_name': driver.text, 'driver_phone': phone.text, 'vehicle': vehicle.text},
          'Marked in transit');
    }
  }

  Future<void> _complete(Json p) async {
    final kg = TextEditingController(text: fmtNum(toD(p['quantity_kg'])).replaceAll(',', ''));
    final meals = TextEditingController();
    final people = TextEditingController();
    final notes = TextEditingController();
    final go = await showDialog<bool>(
      context: context,
      builder: (c) => FormDialog(
        title: 'Confirm delivery',
        width: 460,
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Complete')),
        ],
        child: Column(children: [
          const Text('Record what arrived and who it fed — this powers the impact dashboards.',
              style: TextStyle(color: FB.muted)),
          const SizedBox(height: 12),
          TextField(controller: kg, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Quantity received (kg)')),
          const SizedBox(height: 10),
          TextField(
              controller: meals,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Meals served', hintText: 'Leave blank to estimate (0.42 kg/meal)')),
          const SizedBox(height: 10),
          TextField(controller: people, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Beneficiaries served')),
          const SizedBox(height: 10),
          TextField(controller: notes, decoration: const InputDecoration(labelText: 'Notes')),
        ]),
      ),
    );
    if (go == true) {
      await _act('complete', {
        if (double.tryParse(kg.text) != null) 'quantity_received_kg': double.parse(kg.text),
        if (int.tryParse(meals.text) != null) 'meals_served': int.parse(meals.text),
        if (int.tryParse(people.text) != null) 'beneficiaries_served': int.parse(people.text),
        'notes': notes.text,
      }, 'Delivery recorded — thank you!');
    }
  }

  Future<void> _cancel({bool noShow = false}) async {
    final reason = TextEditingController();
    final go = await showDialog<bool>(
      context: context,
      builder: (c) => FormDialog(
        title: noShow ? 'Report no-show' : 'Cancel pickup',
        width: 440,
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Back')),
          FilledButton(
              style: FilledButton.styleFrom(backgroundColor: FB.tomato),
              onPressed: () => Navigator.pop(c, true),
              child: Text(noShow ? 'Report' : 'Cancel pickup')),
        ],
        child: TextField(controller: reason, decoration: const InputDecoration(labelText: 'Reason')),
      ),
    );
    if (go == true) await _act('cancel', {'reason': reason.text, 'no_show': noShow}, noShow ? 'No-show reported' : 'Pickup cancelled');
  }

  @override
  Widget build(BuildContext context) {
    final isAdmin = context.watch<AuthState>().role == Role.admin;
    return RemoteView<Json>(
      key: ValueKey(_v),
      load: () async => toJ(await api.get('$_base/')),
      builder: (context, p, reload) {
        final l = toJ(p['listing']);
        final ngo = toJ(p['ngo']);
        final donor = toJ(l['donor']);
        final status = toS(p['status']);
        final side = toS(p['my_side']);
        final awaiting = p['awaiting'];
        final start = toDate(p['scheduled_start']);
        final actions = <Widget>[
          OutlinedButton.icon(
              onPressed: () => context.go('/pickups'), icon: const Icon(Icons.calendar_month_rounded), label: const Text('Calendar')),
          if (!isAdmin && status == 'requested' && awaiting == side)
            FilledButton.icon(
                onPressed: () => _act('confirm', null, 'Confirmed'),
                icon: const Icon(Icons.check_rounded),
                label: const Text('Confirm')),
          if (!isAdmin && (status == 'requested' || status == 'confirmed'))
            OutlinedButton.icon(
                onPressed: () => _reschedule(p), icon: const Icon(Icons.update_rounded), label: const Text('Reschedule')),
          if (!isAdmin && status == 'confirmed')
            FilledButton.icon(
                onPressed: _collect, icon: const Icon(Icons.local_shipping_rounded), label: const Text('Mark collected')),
          if ((side == 'ngo' || isAdmin) && status == 'in_transit')
            FilledButton.icon(
                onPressed: () => _complete(p), icon: const Icon(Icons.task_alt_rounded), label: const Text('Confirm delivery')),
          if (!isAdmin && side == 'donor' && status == 'confirmed' && start != null && start.isBefore(DateTime.now()))
            OutlinedButton(onPressed: () => _cancel(noShow: true), child: const Text('Report no-show')),
          if (!isAdmin && (status == 'requested' || status == 'confirmed'))
            TextButton(
                style: TextButton.styleFrom(foregroundColor: FB.tomato), onPressed: _cancel, child: const Text('Cancel')),
        ];
        return PageScaffold(
          title: toS(l['title'], 'Pickup'),
          subtitle: 'Pickup #${toI(p['id'])} · ${fmtRange(start, toDate(p['scheduled_end']))}',
          onRefresh: reload,
          actions: actions,
          children: [
            SectionCard(child: _Timeline(p: p)),
            const SizedBox(height: 14),
            SplitRow(
              leftFlex: 1,
              left: SectionCard(
                title: 'Donation',
                trailing: StatusChip(status),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  InfoRow('Food', '${toS(l['title'])} (${toS(toJ(l['category_detail'])['name'], '—')})'),
                  InfoRow('Quantity', fmtKg(toD(p['quantity_kg']))),
                  if (p['quantity_received_kg'] != null) InfoRow('Received', fmtKg(toD(p['quantity_received_kg']))),
                  if (p['meals_served'] != null) InfoRow('Meals served', fmtInt(toI(p['meals_served']))),
                  if (p['beneficiaries_served'] != null) InfoRow('Beneficiaries', fmtInt(toI(p['beneficiaries_served']))),
                  InfoRow('Best before', fmtDate(toDate(l['expiry_date']))),
                  InfoRow('Storage', l['requires_refrigeration'] == true ? 'Keep refrigerated' : 'Ambient / hot-hold'),
                  InfoRow('Initiated by', p['initiated_by'] == 'donor' ? 'Donor offer' : 'NGO claim'),
                  if (toS(p['notes']).isNotEmpty) InfoRow('Notes', toS(p['notes'])),
                  if (toS(p['cancel_reason']).isNotEmpty) InfoRow('Cancel reason', toS(p['cancel_reason'])),
                ]),
              ),
              right: SectionCard(
                title: 'People & place',
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  InfoRow('Donor', toS(donor['name']), icon: Icons.storefront_rounded),
                  InfoRow('Donor phone', toS(donor['phone'], '—'), icon: Icons.phone_rounded),
                  InfoRow('Pickup address', toS(l['pickup_address'], '—'), icon: Icons.place_rounded),
                  InfoRow('NGO', toS(ngo['name']), icon: Icons.volunteer_activism_rounded),
                  InfoRow('NGO phone', toS(ngo['phone'], '—'), icon: Icons.phone_rounded),
                  InfoRow('Driver', [toS(p['driver_name']), toS(p['driver_phone']), toS(p['vehicle'])].where((s) => s.isNotEmpty).join(' · ').isEmpty
                      ? '—'
                      : [toS(p['driver_name']), toS(p['driver_phone']), toS(p['vehicle'])].where((s) => s.isNotEmpty).join(' · '),
                      icon: Icons.person_pin_circle_rounded),
                ]),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _Timeline extends StatelessWidget {
  final Json p;
  const _Timeline({required this.p});

  @override
  Widget build(BuildContext context) {
    final status = toS(p['status']);
    final cancelled = status == 'cancelled' || status == 'no_show';
    final steps = [
      ('Requested', toDate(p['created_at']), true),
      ('Donor confirmed', toDate(p['donor_confirmed_at']), p['donor_confirmed_at'] != null),
      ('NGO confirmed', toDate(p['ngo_confirmed_at']), p['ngo_confirmed_at'] != null),
      ('Collected', toDate(p['picked_up_at']), p['picked_up_at'] != null),
      ('Delivered', toDate(p['delivered_at']), p['delivered_at'] != null),
    ];
    return LayoutBuilder(builder: (context, c) {
      final vertical = c.maxWidth < 620;
      final items = <Widget>[];
      for (var i = 0; i < steps.length; i++) {
        final s = steps[i];
        final done = s.$3;
        final color = cancelled && !done ? FB.tomato.withOpacity(.4) : done ? FB.leaf : FB.line;
        final node = Column(mainAxisSize: MainAxisSize.min, children: [
          CircleAvatar(
            radius: 14,
            backgroundColor: color,
            child: Icon(done ? Icons.check_rounded : Icons.circle_outlined, size: 16, color: Colors.white),
          ),
          const SizedBox(height: 6),
          Text(s.$1, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12.5, color: done ? FB.ink : FB.muted)),
          Text(done ? fmtDateTime(s.$2) : '—', style: const TextStyle(fontSize: 11, color: FB.muted)),
        ]);
        items.add(vertical ? Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Row(children: [node])) : Expanded(child: node));
        if (!vertical && i < steps.length - 1) {
          items.add(Container(width: 20, height: 2, margin: const EdgeInsets.only(bottom: 40), color: steps[i + 1].$3 ? FB.leaf : FB.line));
        }
      }
      final body = vertical ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: items) : Row(children: items);
      if (!cancelled) return body;
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        body,
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: FB.tomatoSoft, borderRadius: BorderRadius.circular(8)),
          child: Text(status == 'no_show' ? 'The NGO did not show up for this pickup.' : 'This pickup was cancelled.',
              style: const TextStyle(color: FB.tomato, fontWeight: FontWeight.w600)),
        ),
      ]);
    });
  }
}
