/// Small, forgiving JSON helpers (the API returns decimals as strings for coordinates).
typedef Json = Map<String, dynamic>;

double toD(dynamic v, [double fallback = 0]) {
  if (v == null) return fallback;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? fallback;
}

double? toDn(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString());
}

int toI(dynamic v, [int fallback = 0]) {
  if (v == null) return fallback;
  if (v is int) return v;
  if (v is num) return v.round();
  return int.tryParse(v.toString()) ?? fallback;
}

String toS(dynamic v, [String fallback = '']) => v == null ? fallback : v.toString();

Json toJ(dynamic v) => v is Map ? Map<String, dynamic>.from(v) : <String, dynamic>{};

/// Accepts a plain list or a DRF paginated response ({count, results}).
List<Json> toL(dynamic v) {
  if (v is Map && v['results'] is List) v = v['results'];
  if (v is! List) return <Json>[];
  return v.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
}

List<double> toDL(dynamic v) => v is List ? v.map((e) => toD(e)).toList() : <double>[];

DateTime? toDate(dynamic v) {
  if (v == null) return null;
  return DateTime.tryParse(v.toString())?.toLocal();
}
