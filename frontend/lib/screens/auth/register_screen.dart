import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import 'auth_layout.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});
  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _form = GlobalKey<FormState>();
  String _type = 'business';
  String _kind = 'restaurant';
  final _c = {
    for (final k in ['org', 'first', 'email', 'password', 'city', 'address', 'phone', 'lat', 'lng', 'benef', 'cap'])
      k: TextEditingController(),
  };
  bool _busy = false;
  String? _error;

  static const businessKinds = {
    'restaurant': 'Restaurant',
    'supermarket': 'Supermarket',
    'bakery': 'Bakery',
    'canteen': 'Canteen / cafeteria',
    'hotel': 'Hotel / caterer',
    'household': 'Household',
  };
  static const ngoKinds = {
    'ngo': 'NGO',
    'community_kitchen': 'Community kitchen',
    'food_bank': 'Food bank',
    'shelter': 'Shelter',
  };

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final lat = double.tryParse(_c['lat']!.text.trim());
    final lng = double.tryParse(_c['lng']!.text.trim());
    try {
      await context.read<AuthState>().register({
        'org_type': _type,
        'kind': _kind,
        'organization_name': _c['org']!.text.trim(),
        'first_name': _c['first']!.text.trim(),
        'email': _c['email']!.text.trim(),
        'password': _c['password']!.text,
        'city': _c['city']!.text.trim(),
        'address': _c['address']!.text.trim(),
        'phone': _c['phone']!.text.trim(),
        if (lat != null) 'latitude': lat.toStringAsFixed(6),
        if (lng != null) 'longitude': lng.toStringAsFixed(6),
        if (_type == 'ngo' && int.tryParse(_c['benef']!.text) != null) 'beneficiaries': int.parse(_c['benef']!.text),
        if (_type == 'ngo' && double.tryParse(_c['cap']!.text) != null)
          'daily_capacity_kg': double.parse(_c['cap']!.text),
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Widget _field(String key, String label,
      {bool required = false, bool obscure = false, TextInputType? type, IconData? icon, String? hint}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        controller: _c[key],
        obscureText: obscure,
        keyboardType: type,
        decoration: InputDecoration(labelText: label, hintText: hint, prefixIcon: icon == null ? null : Icon(icon)),
        validator: (v) {
          if (required && (v == null || v.trim().isEmpty)) return 'Required';
          if (key == 'email' && v != null && !v.contains('@')) return 'Enter a valid email';
          if (key == 'password' && v != null && v.length < 8) return 'At least 8 characters';
          return null;
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final kinds = _type == 'business' ? businessKinds : ngoKinds;
    return AuthLayout(
      child: Form(
        key: _form,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Create your workspace', style: FB.display(30)),
          const SizedBox(height: 6),
          const Text('Donors list surplus; NGOs receive matched donations.', style: TextStyle(color: FB.muted)),
          const SizedBox(height: 22),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'business', icon: Icon(Icons.storefront_rounded), label: Text('Food business')),
              ButtonSegment(value: 'ngo', icon: Icon(Icons.volunteer_activism_rounded), label: Text('NGO')),
            ],
            selected: {_type},
            onSelectionChanged: (s) => setState(() {
              _type = s.first;
              _kind = _type == 'business' ? 'restaurant' : 'ngo';
            }),
          ),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            value: _kind,
            decoration: const InputDecoration(labelText: 'Type'),
            items: kinds.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value))).toList(),
            onChanged: (v) => setState(() => _kind = v ?? _kind),
          ),
          const SizedBox(height: 12),
          _field('org', 'Organization name', required: true, icon: Icons.business_rounded),
          _field('first', 'Your name', icon: Icons.person_outline),
          _field('email', 'Work email', required: true, type: TextInputType.emailAddress, icon: Icons.mail_outline),
          _field('password', 'Password', required: true, obscure: true, icon: Icons.lock_outline),
          _field('phone', 'Phone', type: TextInputType.phone, icon: Icons.phone_outlined),
          _field('city', 'City', icon: Icons.location_city_rounded),
          _field('address', 'Pickup / delivery address', icon: Icons.place_outlined),
          Row(children: [
            Expanded(child: _field('lat', 'Latitude', type: TextInputType.number, hint: '12.9716')),
            const SizedBox(width: 10),
            Expanded(child: _field('lng', 'Longitude', type: TextInputType.number, hint: '77.5946')),
          ]),
          if (_type == 'ngo')
            Row(children: [
              Expanded(child: _field('benef', 'People served', type: TextInputType.number)),
              const SizedBox(width: 10),
              Expanded(child: _field('cap', 'Daily capacity (kg)', type: TextInputType.number)),
            ]),
          const Text('Coordinates power distance-based matching. You can edit them later in Settings.',
              style: TextStyle(color: FB.muted, fontSize: 12)),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: FB.tomatoSoft, borderRadius: BorderRadius.circular(8)),
              child: Text(_error!, style: const TextStyle(color: FB.tomato)),
            ),
          ],
          const SizedBox(height: 18),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: _busy
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Text('Create account'),
          ),
          const SizedBox(height: 8),
          TextButton(onPressed: () => context.go('/login'), child: const Text('I already have an account')),
        ]),
      ),
    );
  }
}
