import 'package:intl/intl.dart';

final _num = NumberFormat.decimalPattern('en_IN');
final _num1 = NumberFormat('#,##0.#', 'en_IN');
final _money = NumberFormat.currency(locale: 'en_IN', symbol: '₹', decimalDigits: 0);

String fmtInt(num? v) => v == null ? '—' : _num.format(v.round());
String fmtNum(num? v) => v == null ? '—' : _num1.format(v);
String fmtKg(num? v) => v == null ? '—' : '${_num1.format(v)} kg';
String fmtMoney(num? v) => v == null ? '—' : _money.format(v);
String fmtPct(num? v) => v == null ? '—' : '${_num1.format(v)}%';

String fmtDate(DateTime? d) => d == null ? '—' : DateFormat('d MMM y').format(d);
String fmtDateShort(DateTime? d) => d == null ? '—' : DateFormat('d MMM').format(d);
String fmtTime(DateTime? d) => d == null ? '—' : DateFormat('h:mm a').format(d);
String fmtDateTime(DateTime? d) => d == null ? '—' : DateFormat('d MMM, h:mm a').format(d);
String fmtRange(DateTime? a, DateTime? b) {
  if (a == null) return '—';
  final same = b != null && a.year == b.year && a.month == b.month && a.day == b.day;
  return same ? '${fmtDateTime(a)} – ${fmtTime(b)}' : '${fmtDateTime(a)} – ${fmtDateTime(b)}';
}

String isoDate(DateTime d) => DateFormat('yyyy-MM-dd').format(d);

String timeAgo(DateTime? d) {
  if (d == null) return '';
  final diff = DateTime.now().difference(d);
  if (diff.inMinutes < 1) return 'just now';
  if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
  if (diff.inHours < 24) return '${diff.inHours}h ago';
  if (diff.inDays < 7) return '${diff.inDays}d ago';
  return fmtDate(d);
}

String expiryLabel(int days) {
  if (days < 0) return 'Expired ${-days}d ago';
  if (days == 0) return 'Expires today';
  if (days == 1) return 'Expires tomorrow';
  return 'Expires in ${days}d';
}

String titleCase(String s) => s
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
    .split(' ')
    .where((w) => w.isNotEmpty)
    .map((w) => w[0].toUpperCase() + w.substring(1))
    .join(' ');
