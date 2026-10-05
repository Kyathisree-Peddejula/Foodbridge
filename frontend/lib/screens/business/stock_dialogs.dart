import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';

/// Cached food taxonomy.
class Taxonomy {
  static List<Json>? _cache;
  static Future<List<Json>> load() async => _cache ??= toL(await api.get('/taxonomy/categories/'));
}

const units = ['kg', 'g', 'l', 'ml', 'pcs', 'portion', 'pack', 'box', 'loaf', 'dozen', 'tray', 'bottle'];

Future<DateTime?> pickDate(BuildContext context, DateTime? initial) => showDatePicker(
      context: context,
      initialDate: initial ?? DateTime.now().add(const Duration(days: 3)),
      firstDate: DateTime.now().subtract(const Duration(days: 30)),
      lastDate: DateTime.now().add(const Duration(days: 730)),
    );

/// Receive stock: pick an existing product or create one (auto-categorised), then quantity + expiry.
class AddStockDialog extends StatefulWidget {
  final String? barcode;
  const AddStockDialog({super.key, this.barcode});
  @override
  State<AddStockDialog> createState() => _AddStockDialogState();
}

class _AddStockDialogState extends State<AddStockDialog> {
  List<Json> _products = [];
  List<Json> _cats = [];
  int? _productId;
  bool _newProduct = false;
  bool _busy = false;
  final _name = TextEditingController();
  final _barcode = TextEditingController();
  final _qty = TextEditingController();
  final _cost = TextEditingController();
  final _shelf = TextEditingController();
  final _weight = TextEditingController();
  final _location = TextEditingController();
  String _unit = 'kg';
  int? _catId;
  DateTime? _expiry;
  String? _classified;

  @override
  void initState() {
    super.initState();
    _barcode.text = widget.barcode ?? '';
    _newProduct = widget.barcode != null;
    Future.wait([api.get('/inventory/products/', query: {'page_size': 500}), Taxonomy.load()]).then((r) {
      if (!mounted) return;
      setState(() {
        _products = toL(r[0]);
        _cats = r[1] as List<Json>;
        if (_products.isEmpty) _newProduct = true;
      });
    });
  }

  Future<void> _classify() async {
    if (_name.text.trim().length < 3) return;
    try {
      final r = toJ(await api.post('/taxonomy/categories/classify/', {'text': _name.text}));
      final c = toJ(r['category']);
      if (c.isNotEmpty && mounted) {
        setState(() {
          _catId ??= toI(c['id']);
          _classified = '${toS(c['name'])} · ${toS(c['perishability'])} perishability · ${toS(c['storage'])}';
          if (_shelf.text.isEmpty) _shelf.text = toS(c['default_shelf_life_days']);
        });
      }
    } catch (_) {}
  }

  Future<void> _save() async {
    final qty = double.tryParse(_qty.text);
    if (qty == null || qty <= 0) return toast(context, 'Enter a quantity', error: true);
    setState(() => _busy = true);
    try {
      var pid = _productId;
      if (_newProduct) {
        if (_name.text.trim().isEmpty) {
          setState(() => _busy = false);
          return toast(context, 'Enter a product name', error: true);
        }
        final p = toJ(await api.post('/inventory/products/', {
          'name': _name.text.trim(),
          'unit': _unit,
          if (_catId != null) 'category': _catId,
          if (_barcode.text.trim().isNotEmpty) 'barcode': _barcode.text.trim(),
          if (double.tryParse(_cost.text) != null) 'unit_cost': _cost.text,
          if (int.tryParse(_shelf.text) != null) 'shelf_life_days': int.parse(_shelf.text),
          if (double.tryParse(_weight.text) != null) 'unit_weight_kg': double.parse(_weight.text),
        }));
        pid = toI(p['id']);
      }
      if (pid == null) {
        setState(() => _busy = false);
        return toast(context, 'Choose a product', error: true);
      }
      await api.post('/inventory/batches/', {
        'product': pid,
        'quantity': qty,
        if (_expiry != null) 'expiry_date': isoDate(_expiry!),
        'storage_location': _location.text.trim(),
      });
      if (mounted) {
        Navigator.pop(context, true);
        toast(context, 'Stock received${_expiry == null ? ' (expiry set from category shelf life)' : ''}');
      }
    } on ApiException catch (e) {
      toast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FormDialog(
      title: 'Receive stock',
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _busy ? null : _save, child: Text(_busy ? 'Saving…' : 'Add to inventory')),
      ],
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SegmentedButton<bool>(
          segments: const [
            ButtonSegment(value: false, label: Text('Existing product')),
            ButtonSegment(value: true, label: Text('New product')),
          ],
          selected: {_newProduct},
          onSelectionChanged: (s) => setState(() => _newProduct = s.first),
        ),
        const SizedBox(height: 14),
        if (!_newProduct)
          DropdownButtonFormField<int>(
            value: _productId,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Product'),
            items: _products
                .map((p) => DropdownMenuItem(
                    value: toI(p['id']),
                    child: Text('${toS(p['name'])} (${toS(p['unit'])})', overflow: TextOverflow.ellipsis)))
                .toList(),
            onChanged: (v) => setState(() => _productId = v),
          )
        else ...[
          Focus(
            onFocusChange: (f) {
              if (!f) _classify();
            },
            child: TextField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Product name', hintText: 'e.g. Paneer butter masala'),
              onSubmitted: (_) => _classify(),
            ),
          ),
          if (_classified != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Row(children: [
                const Icon(Icons.auto_awesome, size: 14, color: FB.leaf),
                const SizedBox(width: 6),
                Expanded(
                    child: Text('Auto-classified: $_classified', style: const TextStyle(fontSize: 12, color: FB.leaf))),
              ]),
            ),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: DropdownButtonFormField<int?>(
                value: _catId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Category'),
                items: [
                  const DropdownMenuItem<int?>(value: null, child: Text('Auto-detect')),
                  ..._cats.map((c) => DropdownMenuItem<int?>(value: toI(c['id']), child: Text(toS(c['name'])))),
                ],
                onChanged: (v) => setState(() => _catId = v),
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              width: 120,
              child: DropdownButtonFormField<String>(
                value: _unit,
                decoration: const InputDecoration(labelText: 'Unit'),
                items: units.map((u) => DropdownMenuItem(value: u, child: Text(u))).toList(),
                onChanged: (v) => setState(() => _unit = v ?? 'kg'),
              ),
            ),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: TextField(controller: _barcode, decoration: const InputDecoration(labelText: 'Barcode / QR'))),
            const SizedBox(width: 10),
            Expanded(
              child: TextField(
                controller: _shelf,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Shelf life (days)'),
              ),
            ),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _cost,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Unit cost (₹)'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: TextField(
                controller: _weight,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(labelText: 'kg per unit', hintText: _unit == 'kg' ? '1' : 'e.g. 0.3'),
              ),
            ),
          ]),
        ],
        const SizedBox(height: 16),
        const Text('Batch', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _qty,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Quantity'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: OutlinedButton.icon(
              icon: const Icon(Icons.event_rounded, size: 18),
              label: Text(_expiry == null ? 'Expiry date' : fmtDate(_expiry)),
              onPressed: () async {
                final d = await pickDate(context, _expiry);
                if (d != null) setState(() => _expiry = d);
              },
            ),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _location,
          decoration: const InputDecoration(labelText: 'Storage location (optional)', hintText: 'e.g. Walk-in chiller 2'),
        ),
      ]),
    );
  }
}

/// Remove stock from a batch as sold / wasted / donated / corrected.
class AdjustDialog extends StatefulWidget {
  final Json batch;
  const AdjustDialog({super.key, required this.batch});
  @override
  State<AdjustDialog> createState() => _AdjustDialogState();
}

class _AdjustDialogState extends State<AdjustDialog> {
  String _reason = 'sale';
  final _qty = TextEditingController();
  final _note = TextEditingController();

  @override
  Widget build(BuildContext context) {
    final b = widget.batch;
    return FormDialog(
      title: 'Update ${toS(b['product_name'])}',
      width: 440,
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () async {
            final q = double.tryParse(_qty.text);
            if (q == null || q <= 0) return toast(context, 'Enter a quantity', error: true);
            final ok = await runAction(
                context,
                () => api.post('/inventory/batches/${toI(b['id'])}/adjust/',
                    {'quantity': q, 'reason': _reason, 'note': _note.text}),
                success: 'Batch updated');
            if (ok && context.mounted) Navigator.pop(context, true);
          },
          child: const Text('Save'),
        ),
      ],
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('On hand: ${fmtNum(toD(b['quantity']))} ${toS(b['product_unit'])} · ${expiryLabel(toI(b['days_to_expiry']))}',
            style: const TextStyle(color: FB.muted)),
        const SizedBox(height: 14),
        Wrap(
          spacing: 8,
          children: const [('sale', 'Sold'), ('waste', 'Wasted'), ('donation', 'Donated'), ('adjustment', 'Correction')]
              .map((r) => ChoiceChip(
                    label: Text(r.$2),
                    selected: _reason == r.$1,
                    onSelected: (_) => setState(() => _reason = r.$1),
                  ))
              .toList(),
        ),
        const SizedBox(height: 14),
        TextField(
          controller: _qty,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: 'Quantity (${toS(b['product_unit'])})'),
        ),
        const SizedBox(height: 12),
        TextField(controller: _note, decoration: const InputDecoration(labelText: 'Note (optional)')),
      ]),
    );
  }
}

/// Bulk CSV upload with template preview and per-row error report.
class CsvUploadDialog extends StatefulWidget {
  const CsvUploadDialog({super.key});
  @override
  State<CsvUploadDialog> createState() => _CsvUploadDialogState();
}

class _CsvUploadDialogState extends State<CsvUploadDialog> {
  String _mode = 'inventory';
  PlatformFile? _file;
  bool _busy = false;
  Json? _result;
  String? _template;

  Future<void> _loadTemplate() async {
    try {
      final t = await api.getText('/inventory/csv-template/', query: {'mode': _mode});
      setState(() => _template = t);
    } catch (e) {
      toast(context, e.toString(), error: true);
    }
  }

  Future<void> _pick() async {
    final r = await FilePicker.platform.pickFiles(type: FileType.custom, allowedExtensions: ['csv'], withData: true);
    if (r != null && r.files.isNotEmpty) setState(() => _file = r.files.single);
  }

  Future<void> _upload() async {
    final bytes = _file?.bytes;
    if (bytes == null) return toast(context, 'Choose a CSV file first', error: true);
    setState(() => _busy = true);
    try {
      final r = toJ(await api.upload('/inventory/upload-csv/', bytes, _file!.name, fields: {'mode': _mode}));
      setState(() => _result = r);
    } on ApiException catch (e) {
      toast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = _result;
    return FormDialog(
      title: 'Bulk upload (CSV)',
      width: 600,
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, r != null), child: Text(r == null ? 'Cancel' : 'Done')),
        if (r == null)
          FilledButton.icon(
            onPressed: _busy ? null : _upload,
            icon: const Icon(Icons.cloud_upload_rounded),
            label: Text(_busy ? 'Uploading…' : 'Upload'),
          ),
      ],
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'inventory', icon: Icon(Icons.inventory_2_outlined), label: Text('Stock on hand')),
            ButtonSegment(value: 'transactions', icon: Icon(Icons.receipt_long_outlined), label: Text('Sales / purchase history')),
          ],
          selected: {_mode},
          onSelectionChanged: (s) => setState(() {
            _mode = s.first;
            _template = null;
            _result = null;
          }),
        ),
        const SizedBox(height: 10),
        Text(
          _mode == 'inventory'
              ? 'Each row creates a batch. Unknown products are created and auto-categorised.'
              : 'Historic sales, purchases and waste feed the demand forecasting models.',
          style: const TextStyle(color: FB.muted, fontSize: 13),
        ),
        const SizedBox(height: 14),
        InkWell(
          onTap: _pick,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: FB.leafSoft.withOpacity(.5),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: FB.leaf.withOpacity(.4)),
            ),
            child: Column(children: [
              const Icon(Icons.upload_file_rounded, color: FB.leaf, size: 34),
              const SizedBox(height: 8),
              Text(_file == null ? 'Choose a .csv file' : '${_file!.name} · ${(_file!.size / 1024).toStringAsFixed(1)} KB',
                  style: const TextStyle(fontWeight: FontWeight.w700)),
            ]),
          ),
        ),
        const SizedBox(height: 10),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: _loadTemplate,
            icon: const Icon(Icons.description_outlined, size: 18),
            label: const Text('Show CSV template'),
          ),
        ),
        if (_template != null)
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: const Color(0xFF10261B), borderRadius: BorderRadius.circular(8)),
            child: SelectableText(_template!,
                style: const TextStyle(fontFamily: 'monospace', color: Color(0xFFBFE8CF), fontSize: 12)),
          ),
        if (r != null) ...[
          const SizedBox(height: 14),
          Row(children: [
            Pill('${toI(r['rows_created'])} created', color: FB.leaf, icon: Icons.check_circle),
            const SizedBox(width: 8),
            Pill('${toI(r['rows_failed'])} failed', color: toI(r['rows_failed']) > 0 ? FB.tomato : FB.muted),
            const SizedBox(width: 8),
            Pill('${toI(r['rows_total'])} rows', color: FB.muted),
          ]),
          if (r['errors'] is List && (r['errors'] as List).isNotEmpty) ...[
            const SizedBox(height: 10),
            ...(r['errors'] as List).take(20).map((e) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text('• ${e is Map ? 'Row ${e['row']}: ${e['error'] ?? e['message'] ?? e}' : e}',
                      style: const TextStyle(color: FB.tomato, fontSize: 12.5)),
                )),
          ],
        ],
      ]),
    );
  }
}
