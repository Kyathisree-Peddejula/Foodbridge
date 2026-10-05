import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../config.dart';
import '../nav.dart';
import '../state/auth_state.dart';
import '../api/api_client.dart';
import '../theme.dart';

/// Responsive shell: green top bar + mint sidebar on wide screens (like the sample dashboard),
/// app bar + drawer + bottom navigation on phones.
class AppShell extends StatelessWidget {
  final Widget child;
  final String location;
  const AppShell({super.key, required this.child, required this.location});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final items = navFor(auth.role);
    final width = MediaQuery.sizeOf(context).width;
    final active = _activeIndex(items, location);

    final body = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const _OfflineBanner(),
      Expanded(child: child),
    ]);

    if (width >= 1000) {
      return Scaffold(
        body: Column(children: [
          _TopBar(auth: auth),
          Expanded(
            child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              _Sidebar(items: items, active: active),
              Expanded(child: body),
            ]),
          ),
        ]),
      );
    }

    // tablets (640-999 px): compact top bar + navigation rail with every destination
    if (width >= 640) {
      return Scaffold(
        body: Column(children: [
          _TopBar(auth: auth, compact: true),
          Expanded(
            child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              SingleChildScrollView(
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: MediaQuery.sizeOf(context).height - 60),
                  child: IntrinsicHeight(
                    child: NavigationRail(
                      backgroundColor: FB.mint,
                      selectedIndex: active < 0 ? null : active,
                      labelType: NavigationRailLabelType.all,
                      minWidth: 76,
                      indicatorColor: FB.leaf.withOpacity(.18),
                      selectedIconTheme: const IconThemeData(color: FB.forest),
                      unselectedIconTheme: const IconThemeData(color: FB.muted),
                      selectedLabelTextStyle:
                          const TextStyle(color: FB.forest, fontWeight: FontWeight.w700, fontSize: 11.5),
                      unselectedLabelTextStyle: const TextStyle(color: FB.muted, fontSize: 11.5),
                      onDestinationSelected: (i) => context.go(items[i].path),
                      destinations: items
                          .map((e) => NavigationRailDestination(
                                icon: Tooltip(message: e.label, child: Icon(e.icon)),
                                label: Text(e.label.split(' ').first),
                              ))
                          .toList(),
                    ),
                  ),
                ),
              ),
              const VerticalDivider(width: 1),
              Expanded(child: body),
            ]),
          ),
        ]),
      );
    }

    final primary = items.where((i) => i.primary).toList();
    final pIndex = active >= 0 ? primary.indexOf(items[active]) : -1;
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Row(children: [
          const _Logo(size: 26),
          const SizedBox(width: 10),
          Text('FoodBridge', style: FB.display(19, color: Colors.white)),
        ]),
        actions: [_Bell(auth: auth), _AccountMenu(auth: auth), const SizedBox(width: 6)],
      ),
      drawer: Drawer(
        backgroundColor: FB.mint,
        child: SafeArea(
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 6),
              child: Text(auth.orgName, style: FB.display(18), maxLines: 2, overflow: TextOverflow.ellipsis),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
              child: Text(auth.displayName, style: const TextStyle(color: FB.muted, fontSize: 13)),
            ),
            const Divider(),
            Expanded(
              child: _NavList(items: items, active: active, onTap: (_) => Navigator.of(context).maybePop()),
            ),
          ]),
        ),
      ),
      body: body,
      bottomNavigationBar: primary.length >= 2
          ? NavigationBar(
              height: 64,
              backgroundColor: Colors.white,
              indicatorColor: FB.leafSoft,
              selectedIndex: pIndex < 0 ? 0 : pIndex,
              labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
              onDestinationSelected: (i) => context.go(primary[i].path),
              destinations: primary
                  .map((e) => NavigationDestination(
                        icon: Icon(e.icon, color: pIndex < 0 ? FB.muted : null),
                        selectedIcon: Icon(e.icon, color: pIndex < 0 ? FB.muted : FB.forest),
                        label: e.label.split(' ').first,
                      ))
                  .toList(),
            )
          : null,
    );
  }

  static int _activeIndex(List<NavItem> items, String loc) {
    var best = -1;
    var bestLen = -1;
    for (var i = 0; i < items.length; i++) {
      final p = items[i].path;
      final hit = p == '/' ? loc == '/' : (loc == p || loc.startsWith('$p/'));
      if (hit && p.length > bestLen) {
        best = i;
        bestLen = p.length;
      }
    }
    return best;
  }
}

class _Logo extends StatelessWidget {
  final double size;
  const _Logo({this.size = 30});
  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(color: FB.leaf, borderRadius: BorderRadius.circular(size * .28)),
        child: Icon(Icons.eco_rounded, color: Colors.white, size: size * .62),
      );
}

class _TopBar extends StatelessWidget {
  final AuthState auth;
  final bool compact;
  const _TopBar({required this.auth, this.compact = false});
  @override
  Widget build(BuildContext context) {
    return Container(
      height: 60,
      color: FB.forest,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Row(children: [
        const _Logo(),
        const SizedBox(width: 12),
        Text('FoodBridge', style: FB.display(21, color: Colors.white)),
        if (!compact) ...[
          const SizedBox(width: 10),
          const Flexible(
            child: Text('–  AI Food Waste Reduction Platform',
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: Color(0xCCFFFFFF), fontSize: 14, fontWeight: FontWeight.w500)),
          ),
        ],
        const Spacer(),
        _Bell(auth: auth),
        const SizedBox(width: 6),
        _AccountMenu(auth: auth, showName: !compact),
      ]),
    );
  }
}

class _Bell extends StatelessWidget {
  final AuthState auth;
  const _Bell({required this.auth});
  @override
  Widget build(BuildContext context) => IconButton(
        tooltip: 'Notifications',
        onPressed: () => context.go('/notifications'),
        icon: Badge(
          isLabelVisible: auth.unread > 0,
          label: Text(auth.unread > 99 ? '99+' : '${auth.unread}'),
          backgroundColor: FB.amber,
          textColor: FB.forestDeep,
          child: const Icon(Icons.notifications_rounded, color: Colors.white),
        ),
      );
}

class _AccountMenu extends StatelessWidget {
  final AuthState auth;
  final bool showName;
  const _AccountMenu({required this.auth, this.showName = false});

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      tooltip: 'Account',
      offset: const Offset(0, 48),
      onSelected: (v) async {
        switch (v) {
          case 'settings':
            context.go('/settings');
          case 'docs':
            await launchUrl(Uri.parse(AppConfig.apiDocsUrl));
          case 'mldocs':
            await launchUrl(Uri.parse(AppConfig.mlDocsUrl));
          case 'logout':
            await auth.logout();
        }
      },
      itemBuilder: (_) => [
        PopupMenuItem(
          enabled: false,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(auth.orgName, style: const TextStyle(fontWeight: FontWeight.w700, color: FB.ink)),
            Text(toTitle(auth.role.name), style: const TextStyle(fontSize: 12, color: FB.muted)),
          ]),
        ),
        const PopupMenuDivider(),
        if (auth.role != Role.admin)
          const PopupMenuItem(value: 'settings', child: ListTile(leading: Icon(Icons.settings), title: Text('Settings'))),
        const PopupMenuItem(value: 'docs', child: ListTile(leading: Icon(Icons.api_rounded), title: Text('API docs (Swagger)'))),
        const PopupMenuItem(value: 'mldocs', child: ListTile(leading: Icon(Icons.psychology_rounded), title: Text('ML service docs'))),
        const PopupMenuItem(value: 'logout', child: ListTile(leading: Icon(Icons.logout), title: Text('Log out'))),
      ],
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        CircleAvatar(
          radius: 16,
          backgroundColor: FB.amber,
          child: Text(auth.initials,
              style: const TextStyle(color: FB.forestDeep, fontSize: 12, fontWeight: FontWeight.w800)),
        ),
        if (showName) ...[
          const SizedBox(width: 8),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 180),
            child: Text(auth.orgName,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
          ),
          const Icon(Icons.expand_more, color: Colors.white),
        ],
      ]),
    );
  }

  static String toTitle(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}

class _Sidebar extends StatelessWidget {
  final List<NavItem> items;
  final int active;
  const _Sidebar({required this.items, required this.active});
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 236,
      decoration: const BoxDecoration(color: FB.mint, border: Border(right: BorderSide(color: FB.line))),
      child: Column(children: [
        const SizedBox(height: 14),
        Expanded(child: _NavList(items: items, active: active)),
        const Padding(
          padding: EdgeInsets.all(16),
          child: Text('Rescue surplus. Feed people.\nCut CO₂.',
              style: TextStyle(color: FB.muted, fontSize: 12, height: 1.4)),
        ),
      ]),
    );
  }
}

class _NavList extends StatelessWidget {
  final List<NavItem> items;
  final int active;
  final void Function(NavItem)? onTap;
  const _NavList({required this.items, required this.active, this.onTap});

  @override
  Widget build(BuildContext context) {
    return ListView(padding: const EdgeInsets.symmetric(horizontal: 10), children: [
      for (var i = 0; i < items.length; i++)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Material(
            color: i == active ? FB.leaf.withOpacity(.14) : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () {
                onTap?.call(items[i]);
                context.go(items[i].path);
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
                decoration: BoxDecoration(
                  border: Border(left: BorderSide(color: i == active ? FB.leaf : Colors.transparent, width: 3)),
                ),
                child: Row(children: [
                  Icon(items[i].icon, size: 20, color: i == active ? FB.forest : FB.muted),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(items[i].label,
                        style: TextStyle(
                          color: i == active ? FB.forest : FB.ink,
                          fontWeight: i == active ? FontWeight.w700 : FontWeight.w500,
                          fontSize: 14,
                        )),
                  ),
                ]),
              ),
            ),
          ),
        ),
    ]);
  }
}

/// Shown while the API cannot be reached; hides itself as soon as a request succeeds again.
class _OfflineBanner extends StatelessWidget {
  const _OfflineBanner();
  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: api.online,
      builder: (context, online, _) => AnimatedSize(
        duration: const Duration(milliseconds: 200),
        child: online
            ? const SizedBox(width: double.infinity)
            : Semantics(
                liveRegion: true,
                child: Container(
                  width: double.infinity,
                  color: FB.amberSoft,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: const Row(children: [
                    Icon(Icons.cloud_off_rounded, size: 18, color: FB.forestDeep),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text('You are offline or the server is unreachable. Showing the last loaded data.',
                          style: TextStyle(fontSize: 13, color: FB.forestDeep)),
                    ),
                  ]),
                ),
              ),
      ),
    );
  }
}
