import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../utils/format.dart';

// ---------------------------------------------------------------- layout helpers
bool isWide(BuildContext c) => MediaQuery.sizeOf(c).width >= 1000;
bool isPhone(BuildContext c) => MediaQuery.sizeOf(c).width < 640;

/// Standard scrollable page with a header.
class PageScaffold extends StatelessWidget {
  final String title;
  final String? subtitle;
  final List<Widget> actions;
  final List<Widget> children;
  final Future<void> Function()? onRefresh;
  final String? help;

  const PageScaffold({
    super.key,
    required this.title,
    this.subtitle,
    this.actions = const [],
    required this.children,
    this.onRefresh,
    this.help,
  });

  @override
  Widget build(BuildContext context) {
    final pad = isPhone(context) ? 14.0 : 24.0;
    final list = ListView(
      padding: EdgeInsets.fromLTRB(pad, pad, pad, pad + 24),
      children: [
        PageHeader(title: title, subtitle: subtitle, actions: actions, help: help),
        const SizedBox(height: 18),
        ...children,
      ],
    );
    return onRefresh == null ? list : RefreshIndicator(onRefresh: onRefresh!, color: FB.leaf, child: list);
  }
}

class PageHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  final List<Widget> actions;
  final String? help;
  const PageHeader({super.key, required this.title, this.subtitle, this.actions = const [], this.help});

  @override
  Widget build(BuildContext context) {
    final head = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          Flexible(child: Text(title, style: FB.display(isPhone(context) ? 24 : 28))),
          if (help != null) ...[const SizedBox(width: 8), HelpTip(help!)],
        ]),
        if (subtitle != null) ...[
          const SizedBox(height: 4),
          Text(subtitle!, style: const TextStyle(color: FB.muted, fontSize: 14)),
        ],
      ],
    );
    if (actions.isEmpty) return head;
    return Wrap(
      alignment: WrapAlignment.spaceBetween,
      crossAxisAlignment: WrapCrossAlignment.center,
      runSpacing: 12,
      spacing: 12,
      children: [head, Wrap(spacing: 8, runSpacing: 8, children: actions)],
    );
  }
}

class HelpTip extends StatelessWidget {
  final String text;
  const HelpTip(this.text, {super.key});
  @override
  Widget build(BuildContext context) => Semantics(
        label: 'Help: $text',
        button: true,
        child: Tooltip(
          message: text,
          triggerMode: TooltipTriggerMode.tap,
          showDuration: const Duration(seconds: 8),
          padding: const EdgeInsets.all(10),
          textStyle: const TextStyle(color: Colors.white, fontSize: 12.5, height: 1.4),
          child: const Padding(
            padding: EdgeInsets.all(4), // larger tap target on touch screens
            child: Icon(Icons.help_outline_rounded, size: 18, color: FB.muted),
          ),
        ),
      );
}

/// White rounded card with optional title row.
class SectionCard extends StatelessWidget {
  final String? title;
  final Widget? trailing;
  final Widget child;
  final EdgeInsetsGeometry padding;
  final String? help;
  const SectionCard({
    super.key,
    this.title,
    this.trailing,
    required this.child,
    this.padding = const EdgeInsets.all(18),
    this.help,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: FB.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: FB.line),
        boxShadow: const [BoxShadow(color: Color(0x0A14452F), blurRadius: 12, offset: Offset(0, 4))],
      ),
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (title != null) ...[
            Row(children: [
              Flexible(
                child: Text(title!, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ),
              if (help != null) ...[const SizedBox(width: 6), HelpTip(help!)],
              const Spacer(),
              if (trailing != null) trailing!,
            ]),
            const SizedBox(height: 14),
          ],
          child,
        ],
      ),
    );
  }
}

/// KPI card with a coloured top rule, like the sample dashboard.
class KpiCard extends StatelessWidget {
  final String label;
  final String value;
  final String? caption;
  final Color color;
  final IconData? icon;
  final String? help;
  const KpiCard(
      {super.key, required this.label, required this.value, this.caption, required this.color, this.icon, this.help});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      label: '$label: $value${caption != null ? ', $caption' : ''}',
      child: ExcludeSemantics(child: _card()),
    );
  }

  Widget _card() {
    return Container(
      decoration: BoxDecoration(
        color: FB.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: FB.line),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Container(height: 4, color: color),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(
                child: Text(label,
                    style: const TextStyle(color: FB.muted, fontSize: 13, fontWeight: FontWeight.w500),
                    overflow: TextOverflow.ellipsis),
              ),
              if (help != null) ...[HelpTip(help!), const SizedBox(width: 6)],
              if (icon != null)
                Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(color: color.withOpacity(.12), borderRadius: BorderRadius.circular(8)),
                  child: Icon(icon, size: 16, color: color),
                ),
            ]),
            const SizedBox(height: 8),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(value, style: FB.display(26)),
            ),
            if (caption != null) ...[
              const SizedBox(height: 4),
              Text(caption!,
                  style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600),
                  overflow: TextOverflow.ellipsis),
            ],
          ]),
        ),
      ]),
    );
  }
}

/// Lays out children in a responsive grid (1–4 columns).
class ResponsiveGrid extends StatelessWidget {
  final List<Widget> children;
  final double minTileWidth;
  final double spacing;
  const ResponsiveGrid({super.key, required this.children, this.minTileWidth = 230, this.spacing = 14});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      final cols = (c.maxWidth / minTileWidth).floor().clamp(1, 4);
      final w = (c.maxWidth - spacing * (cols - 1)) / cols;
      return Wrap(
        spacing: spacing,
        runSpacing: spacing,
        children: children.map((e) => SizedBox(width: w, child: e)).toList(),
      );
    });
  }
}

/// Two panes side-by-side on wide screens, stacked on narrow ones.
class SplitRow extends StatelessWidget {
  final Widget left;
  final Widget right;
  final int leftFlex;
  final int rightFlex;
  final double breakpoint;
  const SplitRow({
    super.key,
    required this.left,
    required this.right,
    this.leftFlex = 2,
    this.rightFlex = 1,
    this.breakpoint = 900,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      if (c.maxWidth < breakpoint) {
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [left, const SizedBox(height: 14), right]);
      }
      return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(flex: leftFlex, child: left),
        const SizedBox(width: 14),
        Expanded(flex: rightFlex, child: right),
      ]);
    });
  }
}

// ---------------------------------------------------------------- chips & badges
class StatusChip extends StatelessWidget {
  final String status;
  final String? label;
  const StatusChip(this.status, {super.key, this.label});

  static String labelFor(String s) => switch (s) {
        'completed' => 'Picked Up',
        'in_transit' => 'In Transit',
        'confirmed' => 'Scheduled',
        'requested' => 'Awaiting',
        'no_show' => 'No-show',
        _ => titleCase(s),
      };

  @override
  Widget build(BuildContext context) {
    final c = FB.statusColor(status);
    final solid = status == 'completed';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: solid ? c : c.withOpacity(.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label ?? labelFor(status),
          style: TextStyle(color: solid ? Colors.white : c, fontSize: 12, fontWeight: FontWeight.w700)),
    );
  }
}

class RiskBadge extends StatelessWidget {
  final double? score;
  final String level;
  final bool compact;
  const RiskBadge({super.key, required this.score, required this.level, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final c = FB.risk(level);
    return Tooltip(
      message: score == null ? 'Not scored yet' : 'Waste risk ${score!.toStringAsFixed(0)}/100 · ${titleCase(level)}',
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: compact ? 8 : 10, vertical: 4),
        decoration: BoxDecoration(color: c.withOpacity(.12), borderRadius: BorderRadius.circular(20)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Container(width: 7, height: 7, decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
          const SizedBox(width: 6),
          Text(
            score == null ? '—' : (compact ? score!.toStringAsFixed(0) : '${score!.toStringAsFixed(0)} · ${titleCase(level)}'),
            style: TextStyle(color: c, fontSize: 12, fontWeight: FontWeight.w700),
          ),
        ]),
      ),
    );
  }
}

class Pill extends StatelessWidget {
  final String text;
  final Color color;
  final IconData? icon;
  const Pill(this.text, {super.key, this.color = FB.forest, this.icon});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
        decoration: BoxDecoration(color: color.withOpacity(.1), borderRadius: BorderRadius.circular(6)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icon != null) ...[Icon(icon, size: 13, color: color), const SizedBox(width: 4)],
          Text(text, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
        ]),
      );
}

class Dot extends StatelessWidget {
  final Color color;
  final double size;
  const Dot(this.color, {super.key, this.size = 9});
  @override
  Widget build(BuildContext context) =>
      Container(width: size, height: size, decoration: BoxDecoration(color: color, shape: BoxShape.circle));
}

Color hexColor(String? hex, [Color fallback = FB.leaf]) {
  if (hex == null || hex.length < 7) return fallback;
  final v = int.tryParse(hex.replaceFirst('#', ''), radix: 16);
  return v == null ? fallback : Color(0xFF000000 | v);
}

// ---------------------------------------------------------------- states
class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? message;
  final Widget? action;
  const EmptyState({super.key, required this.icon, required this.title, this.message, this.action});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 16),
        child: Column(children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: const BoxDecoration(color: FB.leafSoft, shape: BoxShape.circle),
            child: Icon(icon, color: FB.leaf, size: 30),
          ),
          const SizedBox(height: 12),
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16), textAlign: TextAlign.center),
          if (message != null) ...[
            const SizedBox(height: 6),
            Text(message!, style: const TextStyle(color: FB.muted), textAlign: TextAlign.center),
          ],
          if (action != null) ...[const SizedBox(height: 14), action!],
        ]),
      );
}

class ErrorView extends StatelessWidget {
  final Object error;
  final VoidCallback onRetry;
  const ErrorView({super.key, required this.error, required this.onRetry});
  @override
  Widget build(BuildContext context) => Center(
        child: EmptyState(
          icon: Icons.cloud_off_rounded,
          title: 'Could not load this page',
          message: error.toString(),
          action: OutlinedButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Try again')),
        ),
      );
}

/// Loads data once (and on demand) and rebuilds with it.
class RemoteView<T> extends StatefulWidget {
  final Future<T> Function() load;
  final Widget Function(BuildContext context, T data, Future<void> Function() reload) builder;
  final Duration? poll;
  const RemoteView({super.key, required this.load, required this.builder, this.poll});

  @override
  State<RemoteView<T>> createState() => _RemoteViewState<T>();
}

class _RemoteViewState<T> extends State<RemoteView<T>> {
  T? _data;
  Object? _error;
  bool _loading = true;
  bool _disposed = false;

  @override
  void initState() {
    super.initState();
    _reload();
    if (widget.poll != null) _schedule();
  }

  void _schedule() {
    Future.delayed(widget.poll!, () async {
      if (_disposed) return;
      await _reload(silent: true);
      _schedule();
    });
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  Future<void> _reload({bool silent = false}) async {
    if (!silent && mounted) setState(() => _loading = _data == null);
    try {
      final d = await widget.load();
      if (!mounted) return;
      setState(() {
        _data = d;
        _error = null;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        if (!silent || _data == null) _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _data == null) {
      return const Center(child: Padding(padding: EdgeInsets.all(40), child: CircularProgressIndicator(color: FB.leaf)));
    }
    if (_error != null && _data == null) return ErrorView(error: _error!, onRetry: _reload);
    return widget.builder(context, _data as T, _reload);
  }
}

// ---------------------------------------------------------------- feedback
void toast(BuildContext context, String msg, {bool error = false}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: error ? FB.tomato : FB.forestDeep,
      duration: Duration(seconds: error ? 5 : 3),
    ));
}

/// Runs an API action with a toast on success/failure. Returns true on success.
Future<bool> runAction(BuildContext context, Future<dynamic> Function() fn, {String? success}) async {
  try {
    await fn();
    if (success != null && context.mounted) toast(context, success);
    return true;
  } on ApiException catch (e) {
    if (context.mounted) toast(context, e.message, error: true);
  } catch (e) {
    if (context.mounted) toast(context, e.toString(), error: true);
  }
  return false;
}

Future<bool> confirmDialog(BuildContext context, String title, String message,
    {String confirm = 'Confirm', bool danger = false}) async {
  final r = await showDialog<bool>(
    context: context,
    builder: (c) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
        FilledButton(
          style: danger ? FilledButton.styleFrom(backgroundColor: FB.tomato) : null,
          onPressed: () => Navigator.pop(c, true),
          child: Text(confirm),
        ),
      ],
    ),
  );
  return r ?? false;
}

/// Consistent dialog shell used for forms.
class FormDialog extends StatelessWidget {
  final String title;
  final Widget child;
  final List<Widget> actions;
  final double width;
  const FormDialog({super.key, required this.title, required this.child, required this.actions, this.width = 520});

  @override
  Widget build(BuildContext context) {
    if (isPhone(context)) {
      // phones: full-screen form with the actions pinned above the keyboard
      return Dialog.fullscreen(
        child: Scaffold(
          appBar: AppBar(
            title: Text(title),
            leading: IconButton(
                tooltip: 'Close', onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
          ),
          body: SafeArea(
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Expanded(child: SingleChildScrollView(padding: const EdgeInsets.fromLTRB(18, 16, 18, 16), child: child)),
              const Divider(height: 1),
              Padding(
                padding: const EdgeInsets.all(12),
                child: Wrap(alignment: WrapAlignment.end, spacing: 8, runSpacing: 8, children: actions),
              ),
            ]),
          ),
        ),
      );
    }
    return Dialog(
      insetPadding: const EdgeInsets.all(16),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: width, maxHeight: MediaQuery.sizeOf(context).height * .9),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(22, 20, 12, 8),
            child: Row(children: [
              Expanded(child: Text(title, style: FB.display(20))),
              IconButton(
                  tooltip: 'Close', onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
            ]),
          ),
          Flexible(
            child: SingleChildScrollView(padding: const EdgeInsets.fromLTRB(22, 4, 22, 12), child: child),
          ),
          const Divider(),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Wrap(alignment: WrapAlignment.end, spacing: 8, runSpacing: 8, children: actions),
          ),
        ]),
      ),
    );
  }
}

/// Simple label/value row.
class InfoRow extends StatelessWidget {
  final String label;
  final String value;
  final IconData? icon;
  const InfoRow(this.label, this.value, {super.key, this.icon});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (icon != null) ...[Icon(icon, size: 16, color: FB.muted), const SizedBox(width: 8)],
          SizedBox(width: 130, child: Text(label, style: const TextStyle(color: FB.muted, fontSize: 13))),
          Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13))),
        ]),
      );
}

/// Horizontal progress bar with label.
class MeterBar extends StatelessWidget {
  final String label;
  final double value; // 0..1
  final Color color;
  final String? trailing;
  const MeterBar({super.key, required this.label, required this.value, required this.color, this.trailing});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(label, style: const TextStyle(fontSize: 13))),
            if (trailing != null) Text(trailing!, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
          ]),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: value.clamp(0, 1).toDouble(),
              minHeight: 8,
              color: color,
              backgroundColor: color.withOpacity(.12),
            ),
          ),
        ]),
      );
}

/// Scrollable data table styled like the sample "Recent Rescue Operations".
class DataTableCard extends StatelessWidget {
  final List<String> columns;
  final List<List<Widget>> rows;
  final List<VoidCallback?>? onTap;
  const DataTableCard({super.key, required this.columns, required this.rows, this.onTap});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, c) {
      if (c.maxWidth < 560) return _stacked();
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: ConstrainedBox(
          constraints: BoxConstraints(minWidth: c.maxWidth),
          child: DataTable(
            headingRowHeight: 40,
            dataRowMinHeight: 46,
            dataRowMaxHeight: 58,
            horizontalMargin: 12,
            columnSpacing: 22,
            showCheckboxColumn: false,
            headingRowColor: WidgetStateProperty.all(const Color(0xFFF1F4F1)),
            headingTextStyle: const TextStyle(fontWeight: FontWeight.w700, color: FB.muted, fontSize: 12.5),
            dataTextStyle: const TextStyle(fontSize: 13, color: FB.ink),
            columns: columns.map((e) => DataColumn(label: Text(e))).toList(),
            rows: [
              for (var i = 0; i < rows.length; i++)
                DataRow(
                  color: WidgetStateProperty.all(i.isOdd ? const Color(0xFFF8FBF8) : Colors.white),
                  onSelectChanged: onTap != null && onTap![i] != null ? (_) => onTap![i]!() : null,
                  cells: rows[i].map((w) => DataCell(w)).toList(),
                ),
            ],
          ),
        ),
      );
    });
  }

  /// Phone layout: each row becomes a card of label/value pairs (no sideways scrolling).
  Widget _stacked() {
    return Column(children: [
      for (var i = 0; i < rows.length; i++)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Material(
            color: i.isOdd ? const Color(0xFFF8FBF8) : Colors.white,
            borderRadius: BorderRadius.circular(10),
            child: InkWell(
              borderRadius: BorderRadius.circular(10),
              onTap: onTap != null && onTap![i] != null ? onTap![i] : null,
              child: Container(
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                decoration:
                    BoxDecoration(border: Border.all(color: FB.line), borderRadius: BorderRadius.circular(10)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  for (var j = 0; j < rows[i].length && j < columns.length; j++)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
                        if (columns[j].isNotEmpty)
                          SizedBox(
                            width: 110,
                            child: Text(columns[j],
                                style: const TextStyle(color: FB.muted, fontSize: 12, fontWeight: FontWeight.w600)),
                          ),
                        Expanded(
                          child: Align(
                            alignment: Alignment.centerLeft,
                            child: DefaultTextStyle.merge(style: const TextStyle(fontSize: 13), child: rows[i][j]),
                          ),
                        ),
                      ]),
                    ),
                ]),
              ),
            ),
          ),
        ),
    ]);
  }
}
