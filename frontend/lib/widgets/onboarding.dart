import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../state/auth_state.dart';
import '../theme.dart';

class _Step {
  final IconData icon;
  final String title;
  final String text;
  final String route;
  const _Step(this.icon, this.title, this.text, this.route);
}

const _steps = {
  Role.business: [
    _Step(Icons.inventory_2_rounded, 'Add your stock', 'Enter batches by hand, upload a CSV, scan barcodes or connect your POS.',
        '/inventory'),
    _Step(Icons.insights_rounded, 'Check waste risk', 'The AI forecasts demand and flags batches likely to go unsold.',
        '/predictions'),
    _Step(Icons.volunteer_activism_rounded, 'List surplus', 'Turn a risky batch into a donation - nearby NGOs are matched instantly.',
        '/listings'),
    _Step(Icons.local_shipping_rounded, 'Confirm pickups', 'Accept the slot the NGO requests; both sides get reminders.', '/pickups'),
  ],
  Role.ngo: [
    _Step(Icons.tune_rounded, 'Tell us your needs', 'Food types, quantities, distance and cold storage drive the matching.',
        '/requirements'),
    _Step(Icons.bolt_rounded, 'Claim donations', 'The live feed ranks surplus by how well it fits you.', '/feed'),
    _Step(Icons.local_shipping_rounded, 'Collect & confirm', 'Mark pickups collected and record who you fed.', '/pickups'),
    _Step(Icons.eco_rounded, 'See your impact', 'Meals served, food rescued and CO₂ avoided.', '/impact'),
  ],
  Role.admin: [
    _Step(Icons.dashboard_rounded, 'Platform overview', 'Listings, rescued food and CO₂ across all partners.', '/admin'),
    _Step(Icons.local_shipping_rounded, 'Rescue operations', 'Every pickup on one calendar.', '/pickups'),
    _Step(Icons.groups_rounded, 'NGO network', 'Capacity and reach of every receiving partner.', '/ngos'),
  ],
};

/// Dismissible "how FoodBridge works" panel shown on each role's dashboard until closed.
class GettingStartedCard extends StatefulWidget {
  final Role role;
  const GettingStartedCard({super.key, required this.role});
  @override
  State<GettingStartedCard> createState() => _GettingStartedCardState();
}

class _GettingStartedCardState extends State<GettingStartedCard> {
  bool? _visible;
  String get _key => 'onboarding_dismissed_${widget.role.name}';

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) {
      if (mounted) setState(() => _visible = !(p.getBool(_key) ?? false));
    });
  }

  Future<void> _dismiss() async {
    setState(() => _visible = false);
    (await SharedPreferences.getInstance()).setBool(_key, true);
  }

  @override
  Widget build(BuildContext context) {
    if (_visible != true) return const SizedBox.shrink();
    final steps = _steps[widget.role] ?? const <_Step>[];
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: FB.leafSoft.withOpacity(.55),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: FB.leaf.withOpacity(.35)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            const Icon(Icons.tips_and_updates_rounded, color: FB.forest),
            const SizedBox(width: 8),
            const Expanded(
                child: Text('Getting started with FoodBridge', style: TextStyle(fontWeight: FontWeight.w800))),
            TextButton(onPressed: _dismiss, child: const Text('Got it, hide')),
          ]),
          const SizedBox(height: 8),
          LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth > 900 ? steps.length : c.maxWidth > 560 ? 2 : 1;
            final w = (c.maxWidth - 10 * (cols - 1)) / cols;
            return Wrap(spacing: 10, runSpacing: 10, children: [
              for (var i = 0; i < steps.length; i++)
                SizedBox(
                  width: w,
                  child: Material(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(10),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(10),
                      onTap: () => context.go(steps[i].route),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          CircleAvatar(
                            radius: 15,
                            backgroundColor: FB.leafSoft,
                            child: Icon(steps[i].icon, size: 16, color: FB.forest),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text('${i + 1}. ${steps[i].title}', style: const TextStyle(fontWeight: FontWeight.w700)),
                              const SizedBox(height: 2),
                              Text(steps[i].text, style: const TextStyle(fontSize: 12.5, color: FB.muted, height: 1.35)),
                            ]),
                          ),
                        ]),
                      ),
                    ),
                  ),
                ),
            ]);
          }),
        ]),
      ),
    );
  }
}
