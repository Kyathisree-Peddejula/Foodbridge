import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';
import 'stock_dialogs.dart';

class InventoryScreen extends StatefulWidget {
  const InventoryScreen({super.key});
  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 4, vsync: this);
  int _version = 0;

  void _bump() => setState(() => _version++);

  Future<void> _add() async {
    final ok = await showDialog<bool>(context: context, builder: (_) => const AddStockDialog());
    if (ok == true) _bump();
  }

  Future<void> _csv() async {
    final ok = await showDialog<bool>(context: context, builder: (_) => const CsvUploadDialog());
    if (ok == true) _bump();
  }

  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: EdgeInsets.fromLTRB(pad, pad, pad, 0),
        child: PageHeader(
          title: 'Inventory',
          help: 'Each delivery is a batch with its own expiry date. Stock is used first-expired-first-out. Colours on the left edge show the AI waste risk.',
          subtitle: 'Batches with expiry tracking and AI waste risk · manual, CSV, scan or POS input',
          actions: [
            OutlinedButton.icon(
                onPressed: () => context.go('/scan'),
                icon: const Icon(Icons.qr_code_scanner_rounded),
                label: const Text('Scan')),
            OutlinedButton.icon(onPressed: _csv, icon: const Icon(Icons.upload_file_rounded), label: const Text('CSV upload')),
            FilledButton.icon(onPressed: _add, icon: const Icon(Icons.add_rounded), label: const Text('Receive stock')),
          ],
        ),
      ),
      const SizedBox(height: 8),
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
          tabs: const [Tab(text: 'Batches'), Tab(text: 'Products'), Tab(text: 'Transactions'), Tab(text: 'Upload history')],
        ),
      ),
      const Divider(),
      Expanded(
        child: TabBarView(controller: _tabs, children: [
          _BatchesTab(key: ValueKey('b$_version'), onChanged: _bump),
          _ProductsTab(key: ValueKey('p$_version')),
          _TransactionsTab(key: ValueKey('t$_version')),
          _UploadsTab(key: ValueKey('u$_version')),
        ]),
      ),
    ]);
  }
}

// ------------------------------------------------------------------ batches
class _BatchesTab extends StatefulWidget {
  final VoidCallback onChanged;
  const _BatchesTab({super.key, required this.onChanged});
  @override
  State<_BatchesTab> createState() => _BatchesTabState();
}

class _BatchesTabState extends State<_BatchesTab> {
  String _search = '';
  String? _category;
  int? _within;
  String _ordering = 'expiry_date';
  List<Json> _cats = [];
  int _v = 0;

  @override
  void initState() {
    super.initState();
    Taxonomy.load().then((c) {
      if (mounted) setState(() => _cats = c);
    });
  }

  Future<List<Json>> _load() async => toL(await api.get('/inventory/batches/', query: {
        'page_size': 200,
        'in_stock': 'true',
        'search': _search,
        'category': _category,
        'expiring_within': _within,
        'ordering': _ordering,
      }));

  Future<void> _adjust(Json b) async {
    final ok = await showDialog<bool>(context: context, builder: (_) => AdjustDialog(batch: b));
    if (ok == true) setState(() => _v++);
  }

  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: EdgeInsets.fromLTRB(pad, 14, pad, 8),
        child: Wrap(spacing: 10, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: [
          SizedBox(
            width: 260,
            child: TextField(
              decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Search product, SKU, batch'),
              onSubmitted: (v) => setState(() => _search = v),
            ),
          ),
          SizedBox(
            width: 200,
            child: DropdownButtonFormField<String?>(
              value: _category,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Category'),
              items: [
                const DropdownMenuItem<String?>(value: null, child: Text('All categories')),
                ..._cats.map((c) => DropdownMenuItem<String?>(value: toS(c['slug']), child: Text(toS(c['name'])))),
              ],
              onChanged: (v) => setState(() => _category = v),
            ),
          ),
          ...[null, 1, 3, 7].map((d) => ChoiceChip(
                label: Text(d == null ? 'Any expiry' : '≤ $d day${d == 1 ? '' : 's'}'),
                selected: _within == d,
                selectedColor: FB.amberSoft,
                onSelected: (_) => setState(() => _within = d),
              )),
          DropdownButton<String>(
            value: _ordering,
            underline: const SizedBox.shrink(),
            items: const [
              DropdownMenuItem(value: 'expiry_date', child: Text('Sort: soonest expiry')),
              DropdownMenuItem(value: '-risk_score', child: Text('Sort: highest risk')),
              DropdownMenuItem(value: '-quantity', child: Text('Sort: largest quantity')),
              DropdownMenuItem(value: '-received_date', child: Text('Sort: newest')),
            ],
            onChanged: (v) => setState(() => _ordering = v ?? _ordering),
          ),
        ]),
      ),
      Expanded(
        child: RemoteView<List<Json>>(
          key: ValueKey('$_search|$_category|$_within|$_ordering|$_v'),
          load: _load,
          builder: (context, rows, reload) {
            if (rows.isEmpty) {
              return const EmptyState(
                  icon: Icons.inventory_2_outlined,
                  title: 'No batches match',
                  message: 'Receive stock, upload a CSV or scan a barcode to get started.');
            }
            return RefreshIndicator(
              onRefresh: reload,
              child: ListView.separated(
                padding: EdgeInsets.fromLTRB(pad, 4, pad, 30),
                itemCount: rows.length,
                separatorBuilder: (_, __) => const SizedBox(height: 8),
                itemBuilder: (context, i) => _BatchTile(
                  b: rows[i],
                  onAdjust: () => _adjust(rows[i]),
                ),
              ),
            );
          },
        ),
      ),
    ]);
  }
}

class _BatchTile extends StatelessWidget {
  final Json b;
  final VoidCallback onAdjust;
  const _BatchTile({required this.b, required this.onAdjust});

  @override
  Widget build(BuildContext context) {
    final cat = toJ(b['category']);
    final days = toI(b['days_to_expiry']);
    final expColor = days < 0 ? FB.tomato : days <= 1 ? const Color(0xFFEF7D3C) : days <= 3 ? FB.amber : FB.muted;
    final phone = isPhone(context);
    final info = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(toS(b['product_name']), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
      const SizedBox(height: 4),
      Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
        if (cat.isNotEmpty) Pill(toS(cat['name']), color: hexColor(toS(cat['color']))),
        Text('Batch ${toS(b['batch_code'])}', style: const TextStyle(fontSize: 12, color: FB.muted)),
        if (toS(b['storage_location']).isNotEmpty)
          Text('· ${toS(b['storage_location'])}', style: const TextStyle(fontSize: 12, color: FB.muted)),
      ]),
      if (toS(b['recommended_action']).isNotEmpty && toS(b['risk_level']) != 'low') ...[
        const SizedBox(height: 6),
        Row(children: [
          const Icon(Icons.auto_awesome, size: 14, color: FB.amber),
          const SizedBox(width: 4),
          Expanded(
            child: Text(toS(b['recommended_action']),
                style: const TextStyle(fontSize: 12.5), maxLines: 2, overflow: TextOverflow.ellipsis),
          ),
        ]),
      ],
    ]);
    final stats = Wrap(spacing: 16, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${fmtNum(toD(b['quantity']))} ${toS(b['product_unit'])}', style: FB.display(18)),
        Text('of ${fmtNum(toD(b['initial_quantity']))} received', style: const TextStyle(fontSize: 11, color: FB.muted)),
      ]),
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(expiryLabel(days), style: TextStyle(color: expColor, fontWeight: FontWeight.w700, fontSize: 13)),
        Text(fmtDate(toDate(b['expiry_date'])), style: const TextStyle(fontSize: 11, color: FB.muted)),
      ]),
      StatusChip(toS(b['status'])),
      RiskBadge(score: toDn(b['risk_score']), level: toS(b['risk_level'], 'unknown')),
    ]);
    final menu = PopupMenuButton<String>(
      tooltip: 'Actions',
      onSelected: (v) {
        if (v == 'adjust') onAdjust();
        if (v == 'list') context.go('/listings/new?batch=${toI(b['id'])}');
        if (v == 'forecast') context.go('/predictions/forecast/${toI(b['product'])}');
      },
      itemBuilder: (_) => const [
        PopupMenuItem(value: 'adjust', child: Text('Record sale / waste / donation')),
        PopupMenuItem(value: 'list', child: Text('List surplus for donation')),
        PopupMenuItem(value: 'forecast', child: Text('View demand forecast')),
      ],
    );
    final body = phone
        ? Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [Expanded(child: info), menu]),
            const SizedBox(height: 10),
            stats,
          ])
        : Row(children: [
            Expanded(flex: 3, child: info),
            const SizedBox(width: 12),
            Expanded(flex: 4, child: stats),
            menu,
          ]);
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: FB.line),
      ),
      child: Stack(children: [
        Padding(padding: const EdgeInsets.fromLTRB(18, 12, 4, 12), child: body),
        Positioned(left: 0, top: 0, bottom: 0, child: Container(width: 4, color: FB.risk(toS(b['risk_level'])))),
      ]),
    );
  }
}

// ------------------------------------------------------------------ products
class _ProductsTab extends StatelessWidget {
  const _ProductsTab({super.key});
  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    return RemoteView<List<Json>>(
      load: () async => toL(await api.get('/inventory/products/', query: {'page_size': 500, 'ordering': 'name'})),
      builder: (context, rows, reload) {
        if (rows.isEmpty) {
          return const EmptyState(icon: Icons.category_outlined, title: 'No products yet');
        }
        return ListView(padding: EdgeInsets.all(pad), children: [
          SectionCard(
            padding: const EdgeInsets.all(8),
            child: DataTableCard(
              columns: const ['Product', 'SKU', 'Barcode', 'Category', 'Unit', 'On hand', 'Shelf life', ''],
              rows: rows.map((p) {
                final c = toJ(p['category_detail']);
                return <Widget>[
                  Text(toS(p['name']), style: const TextStyle(fontWeight: FontWeight.w600)),
                  Text(toS(p['sku'])),
                  Text(toS(p['barcode'], '—')),
                  c.isEmpty ? const Text('—') : Pill(toS(c['name']), color: hexColor(toS(c['color']))),
                  Text(toS(p['unit'])),
                  Text(fmtNum(toD(p['on_hand']))),
                  Text(p['shelf_life_days'] == null ? 'default' : '${toI(p['shelf_life_days'])} d'),
                  IconButton(
                    tooltip: 'Demand forecast',
                    icon: const Icon(Icons.show_chart_rounded, color: FB.leaf),
                    onPressed: () => context.go('/predictions/forecast/${toI(p['id'])}'),
                  ),
                ];
              }).toList(),
            ),
          ),
        ]);
      },
    );
  }
}

// ------------------------------------------------------------------ transactions
class _TransactionsTab extends StatefulWidget {
  const _TransactionsTab({super.key});
  @override
  State<_TransactionsTab> createState() => _TransactionsTabState();
}

class _TransactionsTabState extends State<_TransactionsTab> {
  String? _type;

  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    final colors = {
      'purchase': FB.forest,
      'sale': FB.leaf,
      'waste': FB.tomato,
      'donation': FB.violet,
      'adjustment': FB.muted,
      'return': FB.sky,
    };
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: EdgeInsets.fromLTRB(pad, 14, pad, 6),
        child: Wrap(spacing: 8, runSpacing: 8, children: [
          ChoiceChip(label: const Text('All'), selected: _type == null, onSelected: (_) => setState(() => _type = null)),
          ...colors.keys.map((t) => ChoiceChip(
                label: Text(titleCase(t)),
                selected: _type == t,
                onSelected: (_) => setState(() => _type = t),
              )),
        ]),
      ),
      Expanded(
        child: RemoteView<List<Json>>(
          key: ValueKey(_type),
          load: () async => toL(await api.get('/inventory/transactions/', query: {'page_size': 100, 'txn_type': _type})),
          builder: (context, rows, reload) => ListView(padding: EdgeInsets.fromLTRB(pad, 6, pad, 24), children: [
            SectionCard(
              padding: const EdgeInsets.all(8),
              child: rows.isEmpty
                  ? const EmptyState(icon: Icons.receipt_long_outlined, title: 'No transactions')
                  : DataTableCard(
                      columns: const ['When', 'Product', 'Type', 'Qty', 'Source', 'Reference'],
                      rows: rows
                          .map((t) => <Widget>[
                                Text(fmtDateTime(toDate(t['occurred_at']))),
                                Text(toS(t['product_name'])),
                                Pill(titleCase(toS(t['txn_type'])), color: colors[toS(t['txn_type'])] ?? FB.muted),
                                Text(fmtNum(toD(t['quantity']))),
                                Text(toS(t['source']).toUpperCase(), style: const TextStyle(fontSize: 12, color: FB.muted)),
                                Text(toS(t['reference'], '—')),
                              ])
                          .toList(),
                    ),
            ),
          ]),
        ),
      ),
    ]);
  }
}

// ------------------------------------------------------------------ upload history
class _UploadsTab extends StatelessWidget {
  const _UploadsTab({super.key});
  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    return RemoteView<List<Json>>(
      load: () async => toL(await api.get('/inventory/uploads/')),
      builder: (context, rows, reload) => ListView(padding: EdgeInsets.all(pad), children: [
        if (rows.isEmpty)
          const EmptyState(icon: Icons.upload_file_outlined, title: 'No CSV uploads yet')
        else
          SectionCard(
            padding: const EdgeInsets.all(8),
            child: DataTableCard(
              columns: const ['Uploaded', 'File', 'Mode', 'Rows', 'Created', 'Failed'],
              rows: rows
                  .map((u) => <Widget>[
                        Text(fmtDateTime(toDate(u['created_at']))),
                        Text(toS(u['file_name'])),
                        Text(titleCase(toS(u['mode']))),
                        Text('${toI(u['rows_total'])}'),
                        Text('${toI(u['rows_created'])}', style: const TextStyle(color: FB.leaf, fontWeight: FontWeight.w700)),
                        Text('${toI(u['rows_failed'])}',
                            style: TextStyle(color: toI(u['rows_failed']) > 0 ? FB.tomato : FB.muted)),
                      ])
                  .toList(),
            ),
          ),
      ]),
    );
  }
}
