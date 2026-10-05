import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../utils/json.dart';
import '../utils/web_hooks.dart';

enum Role { business, ngo, admin }

class AuthState extends ChangeNotifier {
  Json? user;
  bool ready = false;
  int unread = 0;

  AuthState() {
    api.onUnauthorized = () {
      user = null;
      notifyListeners();
    };
  }

  bool get loggedIn => user != null;
  Json get org => toJ(user?['organization']);
  String get orgName => toS(org['name'], 'FoodBridge');
  String get displayName {
    final n = '${toS(user?['first_name'])} ${toS(user?['last_name'])}'.trim();
    return n.isEmpty ? toS(user?['email']) : n;
  }

  String get initials {
    final src = orgName.isNotEmpty ? orgName : displayName;
    final parts = src.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return 'FB';
    return (parts.first[0] + (parts.length > 1 ? parts[1][0] : '')).toUpperCase();
  }

  Role get role {
    final r = toS(user?['role']);
    if (r == 'admin') return Role.admin;
    if (r == 'ngo') return Role.ngo;
    return Role.business;
  }

  String get home => switch (role) { Role.admin => '/admin', Role.ngo => '/ngo', Role.business => '/' };

  Future<void> bootstrap() async {
    await api.restore();
    if (api.hasSession) {
      try {
        user = toJ(await api.get('/auth/me/'));
        await refreshUnread();
      } catch (_) {
        await api.clear();
        user = null;
      }
    }
    ready = true;
    notifyListeners();
  }

  Future<void> login(String email, String password) async {
    final r = toJ(await api.post('/auth/login/', {'email': email.trim(), 'password': password}));
    await api.setTokens(toS(r['access']), toS(r['refresh']));
    user = toJ(r['user']);
    await refreshUnread();
    notifyListeners();
  }

  Future<void> register(Json payload) async {
    final r = toJ(await api.post('/auth/register/', payload));
    await api.setTokens(toS(r['access']), toS(r['refresh']));
    user = toJ(r['user']);
    notifyListeners();
  }

  Future<void> reloadMe() async {
    user = toJ(await api.get('/auth/me/'));
    notifyListeners();
  }

  Future<void> refreshUnread() async {
    try {
      unread = toI(toJ(await api.get('/notifications/unread-count/'))['unread']);
      notifyListeners();
    } catch (_) {}
  }

  Future<void> logout() async {
    await api.clear();
    clearOfflineApiCache();
    user = null;
    unread = 0;
    notifyListeners();
  }
}
