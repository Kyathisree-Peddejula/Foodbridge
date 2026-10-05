import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'nav.dart';
import 'screens/admin/admin_dashboard_screen.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/register_screen.dart';
import 'screens/business/alerts_screen.dart';
import 'screens/business/dashboard_screen.dart';
import 'screens/business/inventory_screen.dart';
import 'screens/business/listings_screen.dart';
import 'screens/business/predictions_screen.dart';
import 'screens/business/scan_screen.dart';
import 'screens/ngo/feed_screen.dart';
import 'screens/ngo/ngo_dashboard_screen.dart';
import 'screens/ngo/requirements_screen.dart';
import 'screens/shared/impact_screen.dart';
import 'screens/shared/ngo_network_screen.dart';
import 'screens/shared/notifications_screen.dart';
import 'screens/shared/pickups_screen.dart';
import 'screens/shared/settings_screen.dart';
import 'state/auth_state.dart';
import 'widgets/app_shell.dart';

GoRouter buildRouter(AuthState auth) {
  int idOf(GoRouterState s) => int.tryParse(s.pathParameters['id'] ?? '') ?? 0;

  return GoRouter(
    initialLocation: '/',
    refreshListenable: auth,
    redirect: (context, state) {
      final loc = state.uri.path;
      final public = loc == '/login' || loc == '/register';
      if (!auth.ready) return null;
      if (!auth.loggedIn) return public ? null : '/login';
      if (public) return auth.home;
      if (!routeAllowed(auth.role, loc)) return auth.home;
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/register', builder: (_, __) => const RegisterScreen()),
      ShellRoute(
        builder: (context, state, child) => AppShell(location: state.uri.path, child: child),
        routes: [
          // business
          GoRoute(path: '/', builder: (_, __) => const BusinessDashboardScreen()),
          GoRoute(path: '/inventory', builder: (_, __) => const InventoryScreen()),
          GoRoute(path: '/scan', builder: (_, __) => const ScanScreen()),
          GoRoute(path: '/alerts', builder: (_, __) => const AlertsScreen()),
          GoRoute(path: '/predictions', builder: (_, __) => const PredictionsScreen()),
          GoRoute(path: '/predictions/forecast/:id', builder: (_, s) => ForecastScreen(productId: idOf(s))),
          GoRoute(path: '/listings', builder: (_, __) => const ListingsScreen()),
          GoRoute(
              path: '/listings/new',
              builder: (_, s) => NewListingScreen(batchId: int.tryParse(s.uri.queryParameters['batch'] ?? ''))),
          GoRoute(path: '/listings/:id', builder: (_, s) => ListingDetailScreen(listingId: idOf(s))),
          // ngo
          GoRoute(path: '/ngo', builder: (_, __) => const NgoDashboardScreen()),
          GoRoute(path: '/feed', builder: (_, __) => const FeedScreen()),
          GoRoute(path: '/requirements', builder: (_, __) => const RequirementsScreen()),
          // admin
          GoRoute(path: '/admin', builder: (_, __) => const AdminDashboardScreen()),
          // shared
          GoRoute(path: '/pickups', builder: (_, __) => const PickupsScreen()),
          GoRoute(path: '/pickups/:id', builder: (_, s) => PickupDetailScreen(pickupId: idOf(s))),
          GoRoute(path: '/ngos', builder: (_, __) => const NgoNetworkScreen()),
          GoRoute(path: '/impact', builder: (_, __) => const ImpactScreen()),
          GoRoute(path: '/notifications', builder: (_, __) => const NotificationsScreen()),
          GoRoute(path: '/settings', builder: (_, __) => const SettingsScreen()),
        ],
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Text('Page not found'),
          TextButton(onPressed: () => context.go(auth.home), child: const Text('Go home')),
        ]),
      ),
    ),
  );
}
