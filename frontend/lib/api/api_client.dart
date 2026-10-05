import 'package:flutter/foundation.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config.dart';

class ApiException implements Exception {
  final int status;
  final String message;
  final dynamic body;
  ApiException(this.status, this.message, [this.body]);
  @override
  String toString() => message;
}

/// REST client for the Django API with JWT auth and transparent token refresh.
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  final String base = AppConfig.apiBaseUrl.replaceAll(RegExp(r'/$'), '');
  final http.Client _http = http.Client();
  String? _access;
  String? _refresh;
  Future<bool>? _refreshing;

  /// false while the API is unreachable - the shell shows an offline banner.
  final ValueNotifier<bool> online = ValueNotifier(true);

  /// Called when the session can no longer be refreshed.
  void Function()? onUnauthorized;

  bool get hasSession => _access != null;

  Future<void> restore() async {
    final p = await SharedPreferences.getInstance();
    _access = p.getString('fb_access');
    _refresh = p.getString('fb_refresh');
  }

  Future<void> setTokens(String access, String refresh) async {
    _access = access;
    _refresh = refresh;
    final p = await SharedPreferences.getInstance();
    await p.setString('fb_access', access);
    await p.setString('fb_refresh', refresh);
  }

  Future<void> clear() async {
    _access = null;
    _refresh = null;
    final p = await SharedPreferences.getInstance();
    await p.remove('fb_access');
    await p.remove('fb_refresh');
  }

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    final p = path.startsWith('/') ? path : '/$path';
    final q = <String, String>{};
    query?.forEach((k, v) {
      if (v != null && v.toString().isNotEmpty) q[k] = v.toString();
    });
    return Uri.parse('$base$p').replace(queryParameters: q.isEmpty ? null : q);
  }

  Map<String, String> _headers({bool json = true}) => {
        if (json) 'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (_access != null) 'Authorization': 'Bearer $_access',
      };

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _send(() => _http.get(_uri(path, query), headers: _headers()));

  Future<dynamic> post(String path, [Object? body]) => _send(() =>
      _http.post(_uri(path), headers: _headers(), body: jsonEncode(body ?? <String, dynamic>{})));

  Future<dynamic> patch(String path, Object body) =>
      _send(() => _http.patch(_uri(path), headers: _headers(), body: jsonEncode(body)));

  Future<dynamic> put(String path, Object body) =>
      _send(() => _http.put(_uri(path), headers: _headers(), body: jsonEncode(body)));

  Future<dynamic> delete(String path) => _send(() => _http.delete(_uri(path), headers: _headers()));

  Future<dynamic> upload(String path, Uint8List bytes, String filename,
      {Map<String, String> fields = const {}}) {
    return _send(() async {
      final req = http.MultipartRequest('POST', _uri(path))
        ..headers.addAll(_headers(json: false))
        ..fields.addAll(fields)
        ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));
      return http.Response.fromStream(await _http.send(req));
    });
  }

  /// Raw text GET (CSV templates etc.).
  Future<String> getText(String path, {Map<String, dynamic>? query}) async {
    final r = await _http.get(_uri(path, query), headers: _headers());
    if (r.statusCode >= 400) throw ApiException(r.statusCode, 'Request failed (${r.statusCode})');
    return utf8.decode(r.bodyBytes);
  }

  Future<dynamic> _send(Future<http.Response> Function() call, {bool retried = false}) async {
    http.Response r;
    try {
      r = await call().timeout(const Duration(seconds: 45));
    } on TimeoutException {
      online.value = false;
      throw ApiException(0, 'The server took too long to respond.');
    } catch (e) {
      online.value = false;
      throw ApiException(0, 'Cannot reach the server. Check your connection - we will retry automatically.');
    }
    online.value = true;
    if (r.statusCode == 429) {
      throw ApiException(429, 'Too many requests - please wait a few seconds and try again.');
    }
    if (r.statusCode == 401 && !retried && _refresh != null) {
      if (await _tryRefresh()) return _send(call, retried: true);
      await clear();
      onUnauthorized?.call();
    }
    final text = utf8.decode(r.bodyBytes);
    dynamic body;
    if (text.isNotEmpty) {
      try {
        body = jsonDecode(text);
      } catch (_) {
        body = text;
      }
    }
    if (r.statusCode >= 400) throw ApiException(r.statusCode, _message(body, r.statusCode), body);
    return body;
  }

  Future<bool> _tryRefresh() {
    return _refreshing ??= () async {
      try {
        final r = await _http.post(_uri('/auth/refresh/'),
            headers: {'Content-Type': 'application/json'}, body: jsonEncode({'refresh': _refresh}));
        if (r.statusCode != 200) return false;
        final j = jsonDecode(r.body) as Map<String, dynamic>;
        await setTokens(j['access'] as String, (j['refresh'] as String?) ?? _refresh!);
        return true;
      } catch (_) {
        return false;
      } finally {
        _refreshing = null;
      }
    }();
  }

  static String _message(dynamic body, int status) {
    if (body is Map) {
      if (body['detail'] != null) return body['detail'].toString();
      final parts = <String>[];
      body.forEach((k, v) {
        final msg = v is List ? v.map((e) => e is Map ? e.values.join(' ') : e.toString()).join(' ') : v.toString();
        parts.add(k == 'non_field_errors' ? msg : '${k.toString().replaceAll('_', ' ')}: $msg');
      });
      if (parts.isNotEmpty) return parts.join('\n');
    }
    if (body is List && body.isNotEmpty) return body.join('\n');
    if (status == 403) return 'You do not have permission to do this.';
    if (status == 404) return 'Not found.';
    return 'Something went wrong ($status).';
  }
}

final api = ApiClient.instance;
