import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../api/api_client.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';
import 'stock_dialogs.dart';

/// Barcode / QR scanning (camera on Android, iOS and browsers; manual entry everywhere).
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});
  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  MobileScannerController? _cam;
  bool _cameraOn = false;
  String? _code;
  Json? _product;
  bool _notFound = false;
  bool _busy = false;
  String _action = 'receive';
  final _manual = TextEditingController();
  final _qty = TextEditingController(text: '1');
  final _name = TextEditingController();
  DateTime? _expiry;
  final List<String> _log = [];
  DateTime _lastHit = DateTime.fromMillisecondsSinceEpoch(0);

  @override
  void dispose() {
    _cam?.dispose();
    super.dispose();
  }

  void _toggleCamera() {
    setState(() {
      if (_cameraOn) {
        _cam?.dispose();
        _cam = null;
        _cameraOn = false;
      } else {
        _cam = MobileScannerController(detectionSpeed: DetectionSpeed.noDuplicates, facing: CameraFacing.back);
        _cameraOn = true;
      }
    });
  }

  void _onDetect(BarcodeCapture capture) {
    if (capture.barcodes.isEmpty) return;
    final raw = capture.barcodes.first.rawValue;
    if (raw == null || raw.isEmpty) return;
    final now = DateTime.now();
    if (raw == _code && now.difference(_lastHit).inSeconds < 3) return;
    _lastHit = now;
    _lookup(raw);
  }

  /// QR payloads may be JSON-ish or URLs; take the last path segment / "code=" value when present.
  String _normalise(String raw) {
    final t = raw.trim();
    final uri = Uri.tryParse(t);
    if (uri != null && uri.hasScheme) {
      return uri.queryParameters['code'] ?? uri.queryParameters['barcode'] ??
          (uri.pathSegments.isNotEmpty ? uri.pathSegments.last : t);
    }
    return t;
  }

  Future<void> _lookup(String raw) async {
    final code = _normalise(raw);
    setState(() {
      _code = code;
      _busy = true;
      _product = null;
      _notFound = false;
    });
    try {
      final p = toJ(await api.get('/inventory/products/by-barcode/${Uri.encodeComponent(code)}/'));
      setState(() {
        _product = p;
        _action = 'sell';
      });
    } on ApiException catch (e) {
      if (e.status == 404) {
        setState(() {
          _notFound = true;
          _action = 'receive';
        });
      } else {
        toast(context, e.message, error: true);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _apply() async {
    final q = double.tryParse(_qty.text);
    if (_code == null || q == null || q <= 0) return toast(context, 'Enter a quantity', error: true);
    if (_notFound && _name.text.trim().isEmpty) return toast(context, 'Name the new product', error: true);
    setState(() => _busy = true);
    try {
      final r = toJ(await api.post('/inventory/scan/', {
        'barcode': _code,
        'action': _action,
        'quantity': q,
        if (_action == 'receive' && _expiry != null) 'expiry_date': isoDate(_expiry!),
        if (_notFound) 'name': _name.text.trim(),
      }));
      final msg = toS(r['message'], 'Done');
      setState(() {
        _product = toJ(r['product']);
        _notFound = false;
        _log.insert(0, '${fmtTime(DateTime.now())} · $msg');
        _name.clear();
      });
      toast(context, msg);
    } on ApiException catch (e) {
      toast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final camera = SectionCard(
      title: 'Camera scanner',
      trailing: FilledButton.icon(
        style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10)),
        onPressed: _toggleCamera,
        icon: Icon(_cameraOn ? Icons.videocam_off_rounded : Icons.videocam_rounded, size: 18),
        label: Text(_cameraOn ? 'Stop' : 'Start camera'),
      ),
      child: AspectRatio(
        aspectRatio: 4 / 3,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: Container(
            color: const Color(0xFF0B1F15),
            child: _cameraOn && _cam != null
                ? Stack(fit: StackFit.expand, children: [
                    MobileScanner(
                      controller: _cam!,
                      onDetect: _onDetect,
                      errorBuilder: (context, error, child) => Center(
                        child: Padding(
                          padding: const EdgeInsets.all(20),
                          child: Text(
                            'Camera unavailable (${error.errorCode.name}). '
                            '${kIsWeb ? 'Allow camera access in the browser (HTTPS or localhost required). ' : ''}'
                            'You can type the code below instead.',
                            textAlign: TextAlign.center,
                            style: const TextStyle(color: Colors.white70),
                          ),
                        ),
                      ),
                    ),
                    IgnorePointer(
                      child: Center(
                        child: Container(
                          width: 240,
                          height: 150,
                          decoration: BoxDecoration(
                            border: Border.all(color: FB.amber, width: 3),
                            borderRadius: BorderRadius.circular(14),
                          ),
                        ),
                      ),
                    ),
                  ])
                : const Center(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      Icon(Icons.qr_code_scanner_rounded, size: 56, color: Colors.white38),
                      SizedBox(height: 10),
                      Text('Point the camera at a barcode or QR code',
                          style: TextStyle(color: Colors.white60), textAlign: TextAlign.center),
                    ]),
                  ),
          ),
        ),
      ),
    );

    final manual = SectionCard(
      title: 'Or enter a code',
      child: Row(children: [
        Expanded(
          child: TextField(
            controller: _manual,
            decoration: const InputDecoration(hintText: 'e.g. 8901234567890', prefixIcon: Icon(Icons.keyboard_rounded)),
            onSubmitted: (v) => v.trim().isEmpty ? null : _lookup(v),
          ),
        ),
        const SizedBox(width: 10),
        FilledButton(
          onPressed: () => _manual.text.trim().isEmpty ? null : _lookup(_manual.text),
          child: const Text('Look up'),
        ),
      ]),
    );

    return PageScaffold(
      title: 'Scan stock',
          help: 'Works with EAN/UPC barcodes and QR codes. On the web the camera needs HTTPS or localhost; you can always type the code.',
      subtitle: 'Receive deliveries, record sales or log waste with a barcode / QR scan',
      children: [
        SplitRow(
          leftFlex: 1,
          left: Column(children: [camera, const SizedBox(height: 14), manual]),
          right: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            _resultCard(),
            const SizedBox(height: 14),
            SectionCard(
              title: 'This session',
              child: _log.isEmpty
                  ? const Text('Scans you apply will appear here.', style: TextStyle(color: FB.muted))
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: _log
                          .take(12)
                          .map((l) => Padding(
                                padding: const EdgeInsets.symmetric(vertical: 4),
                                child: Row(children: [
                                  const Icon(Icons.check_circle, size: 16, color: FB.leaf),
                                  const SizedBox(width: 8),
                                  Expanded(child: Text(l, style: const TextStyle(fontSize: 13))),
                                ]),
                              ))
                          .toList(),
                    ),
            ),
          ]),
        ),
      ],
    );
  }

  Widget _resultCard() {
    if (_code == null) {
      return const SectionCard(
        child: EmptyState(
            icon: Icons.qr_code_2_rounded, title: 'Nothing scanned yet', message: 'Scan or type a code to begin.'),
      );
    }
    if (_busy && _product == null && !_notFound) {
      return const SectionCard(child: Center(child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())));
    }
    final p = _product;
    final cat = toJ(p?['category_detail']);
    return SectionCard(
      title: _notFound ? 'New barcode' : 'Product found',
      trailing: Pill(_code!, color: FB.muted, icon: Icons.qr_code_rounded),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (p != null && p.isNotEmpty) ...[
          Text(toS(p['name']), style: FB.display(22)),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 6, children: [
            if (cat.isNotEmpty) Pill(toS(cat['name']), color: hexColor(toS(cat['color']))),
            Pill('On hand ${fmtNum(toD(p['on_hand']))} ${toS(p['unit'])}', color: FB.forest),
            Pill('SKU ${toS(p['sku'])}', color: FB.muted),
          ]),
        ] else ...[
          const Text('This code is not in your catalogue yet. Name it to create the product and receive stock — '
              'the category is detected automatically.'),
          const SizedBox(height: 12),
          TextField(controller: _name, decoration: const InputDecoration(labelText: 'Product name')),
        ],
        const SizedBox(height: 16),
        SegmentedButton<String>(
          segments: [
            const ButtonSegment(value: 'receive', icon: Icon(Icons.move_to_inbox_rounded), label: Text('Receive')),
            ButtonSegment(value: 'sell', enabled: !_notFound, icon: const Icon(Icons.point_of_sale_rounded), label: const Text('Sell')),
            ButtonSegment(value: 'waste', enabled: !_notFound, icon: const Icon(Icons.delete_outline_rounded), label: const Text('Waste')),
          ],
          selected: {_action},
          onSelectionChanged: (s) => setState(() => _action = s.first),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _qty,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(labelText: 'Quantity${p != null && p.isNotEmpty ? ' (${toS(p['unit'])})' : ''}'),
            ),
          ),
          if (_action == 'receive') ...[
            const SizedBox(width: 10),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () async {
                  final d = await pickDate(context, _expiry);
                  if (d != null) setState(() => _expiry = d);
                },
                icon: const Icon(Icons.event_rounded, size: 18),
                label: Text(_expiry == null ? 'Expiry (auto)' : fmtDate(_expiry)),
              ),
            ),
          ],
        ]),
        const SizedBox(height: 14),
        FilledButton(
          onPressed: _busy ? null : _apply,
          child: Text(_busy ? 'Applying…' : 'Apply ${_action == 'receive' ? 'receipt' : _action == 'sell' ? 'sale' : 'waste'}'),
        ),
      ]),
    );
  }
}
