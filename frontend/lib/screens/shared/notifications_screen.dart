import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../nav.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import '../../utils/format.dart';
import '../../utils/json.dart';
import '../../widgets/common.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});
  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  int _v = 0;
  bool _unreadOnly = false;

  static const icons = {
    'expiry': (Icons.hourglass_bottom_rounded, FB.amber),
    'risk': (Icons.local_fire_department_rounded, FB.tomato),
    'match': (Icons.bolt_rounded, FB.leaf),
    'pickup': (Icons.local_shipping_rounded, FB.violet),
    'listing': (Icons.volunteer_activism_rounded, FB.sky),
    'system': (Icons.info_rounded, FB.muted),
  };

  Future<void> _open(Json n) async {
    final auth = context.read<AuthState>();
    if (n['is_read'] != true) {
      try {
        await api.patch('/notifications/${toI(n['id'])}/', {'is_read': true});
        auth.refreshUnread();
      } catch (_) {}
    }
    final link = toS(n['link']);
    if (!mounted) return;
    if (link.startsWith('/') && routeAllowed(auth.role, link.split('?').first)) {
      context.go(link);
    } else {
      setState(() => _v++);
    }
  }

  @override
  Widget build(BuildContext context) {
    return RemoteView<List<Json>>(
      key: ValueKey('$_v|$_unreadOnly'),
      load: () async => toL(await api.get('/notifications/', query: {'page_size': 100, 'is_read': _unreadOnly ? 'false' : null})),
      builder: (context, rows, reload) => PageScaffold(
        title: 'Notifications',
        subtitle: 'Expiry alerts, waste-risk escalations, new matches and pickup confirmations (also sent by email)',
        onRefresh: reload,
        actions: [
          FilterChip(label: const Text('Unread only'), selected: _unreadOnly, onSelected: (v) => setState(() => _unreadOnly = v)),
          OutlinedButton.icon(
            onPressed: () async {
              final ok = await runAction(context, () => api.post('/notifications/mark-all-read/'), success: 'All caught up');
              if (ok && context.mounted) {
                context.read<AuthState>().refreshUnread();
                setState(() => _v++);
              }
            },
            icon: const Icon(Icons.done_all_rounded),
            label: const Text('Mark all read'),
          ),
        ],
        children: [
          if (rows.isEmpty)
            const SectionCard(child: EmptyState(icon: Icons.notifications_none_rounded, title: 'No notifications')),
          if (rows.isNotEmpty)
            SectionCard(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Column(
                children: rows.map((n) {
                  final (icon, color) = icons[toS(n['kind'])] ?? (Icons.notifications_rounded, FB.muted);
                  final unread = n['is_read'] != true;
                  return Material(
                    color: unread ? FB.leafSoft.withOpacity(.35) : Colors.transparent,
                    child: ListTile(
                      onTap: () => _open(n),
                      leading: CircleAvatar(backgroundColor: color.withOpacity(.14), child: Icon(icon, color: color, size: 20)),
                      title: Text(toS(n['title']), style: TextStyle(fontWeight: unread ? FontWeight.w700 : FontWeight.w500)),
                      subtitle: Text(toS(n['body']), maxLines: 3, overflow: TextOverflow.ellipsis),
                      trailing: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
                        Text(timeAgo(toDate(n['created_at'])), style: const TextStyle(fontSize: 11.5, color: FB.muted)),
                        if (unread) ...[const SizedBox(height: 6), const Dot(FB.leaf, size: 8)],
                      ]),
                    ),
                  );
                }).toList(),
              ),
            ),
        ],
      ),
    );
  }
}
