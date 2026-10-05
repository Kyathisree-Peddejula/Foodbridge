import 'package:flutter/material.dart';

import 'state/auth_state.dart';

class NavItem {
  final String label;
  final IconData icon;
  final String path;
  final bool primary; // shown in the phone bottom bar
  const NavItem(this.label, this.icon, this.path, {this.primary = false});
}

List<NavItem> navFor(Role role) => switch (role) {
      Role.business => const [
          NavItem('Dashboard', Icons.dashboard_rounded, '/', primary: true),
          NavItem('Inventory', Icons.inventory_2_rounded, '/inventory', primary: true),
          NavItem('Scan', Icons.qr_code_scanner_rounded, '/scan', primary: true),
          NavItem('Expiry Alerts', Icons.notification_important_rounded, '/alerts'),
          NavItem('Waste Predictions', Icons.insights_rounded, '/predictions'),
          NavItem('Surplus Listings', Icons.volunteer_activism_rounded, '/listings', primary: true),
          NavItem('Pickup Schedule', Icons.local_shipping_rounded, '/pickups'),
          NavItem('NGO Network', Icons.groups_rounded, '/ngos'),
          NavItem('Impact Tracker', Icons.eco_rounded, '/impact'),
          NavItem('Settings', Icons.settings_rounded, '/settings'),
        ],
      Role.ngo => const [
          NavItem('Dashboard', Icons.dashboard_rounded, '/ngo', primary: true),
          NavItem('Live Donations', Icons.bolt_rounded, '/feed', primary: true),
          NavItem('Pickup Schedule', Icons.local_shipping_rounded, '/pickups', primary: true),
          NavItem('Our Needs', Icons.tune_rounded, '/requirements'),
          NavItem('Impact Tracker', Icons.eco_rounded, '/impact', primary: true),
          NavItem('Settings', Icons.settings_rounded, '/settings'),
        ],
      Role.admin => const [
          NavItem('Dashboard', Icons.dashboard_rounded, '/admin', primary: true),
          NavItem('Pickup Routes', Icons.local_shipping_rounded, '/pickups', primary: true),
          NavItem('NGO Network', Icons.groups_rounded, '/ngos', primary: true),
          NavItem('Impact Tracker', Icons.eco_rounded, '/impact', primary: true),
        ],
    };

/// Routes each role may open (prefix match). Shared routes are included for everyone.
bool routeAllowed(Role role, String path) {
  const shared = ['/notifications', '/pickups', '/impact'];
  if (shared.any((p) => path == p || path.startsWith('$p/'))) return true;
  final own = switch (role) {
    Role.business => ['/', '/inventory', '/scan', '/alerts', '/predictions', '/listings', '/ngos', '/settings'],
    Role.ngo => ['/ngo', '/feed', '/requirements', '/settings'],
    Role.admin => ['/admin', '/ngos'],
  };
  return own.any((p) => p == '/' ? path == '/' : (path == p || path.startsWith('$p/')));
}
