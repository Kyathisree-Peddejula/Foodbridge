import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../api/api_client.dart';
import '../../state/auth_state.dart';
import '../../theme.dart';
import 'auth_layout.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  static const demos = [
    ('Hotel (business)', 'hotel@foodbridge.dev', 'Demo@12345'),
    ('Supermarket', 'store4@foodbridge.dev', 'Demo@12345'),
    ('NGO', 'hope@foodbridge.dev', 'Demo@12345'),
    ('Admin', 'admin@foodbridge.dev', 'Admin@12345'),
  ];

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.read<AuthState>().login(_email.text, _password.text);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthLayout(
      child: Form(
        key: _form,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Welcome back', style: FB.display(32)),
          const SizedBox(height: 6),
          const Text('Sign in to your business or NGO workspace.', style: TextStyle(color: FB.muted)),
          const SizedBox(height: 28),
          TextFormField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            decoration: const InputDecoration(labelText: 'Email', prefixIcon: Icon(Icons.mail_outline)),
            validator: (v) => (v == null || !v.contains('@')) ? 'Enter a valid email' : null,
          ),
          const SizedBox(height: 14),
          TextFormField(
            controller: _password,
            obscureText: _obscure,
            autofillHints: const [AutofillHints.password],
            onFieldSubmitted: (_) => _submit(),
            decoration: InputDecoration(
              labelText: 'Password',
              prefixIcon: const Icon(Icons.lock_outline),
              suffixIcon: IconButton(tooltip: 'Show or hide password', 
                icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                onPressed: () => setState(() => _obscure = !_obscure),
              ),
            ),
            validator: (v) => (v == null || v.isEmpty) ? 'Enter your password' : null,
          ),
          if (_error != null) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(color: FB.tomatoSoft, borderRadius: BorderRadius.circular(8)),
              child: Text(_error!, style: const TextStyle(color: FB.tomato)),
            ),
          ],
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: _busy
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Text('Sign in'),
          ),
          const SizedBox(height: 12),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Text('New to FoodBridge?', style: TextStyle(color: FB.muted)),
            TextButton(onPressed: () => context.go('/register'), child: const Text('Create an account')),
          ]),
          const SizedBox(height: 18),
          const Row(children: [
            Expanded(child: Divider()),
            Padding(
              padding: EdgeInsets.symmetric(horizontal: 10),
              child: Text('Demo accounts', style: TextStyle(color: FB.muted, fontSize: 12)),
            ),
            Expanded(child: Divider()),
          ]),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: demos
                .map((d) => ActionChip(
                      avatar: const Icon(Icons.person_outline, size: 16, color: FB.forest),
                      label: Text(d.$1),
                      backgroundColor: FB.leafSoft,
                      side: BorderSide.none,
                      onPressed: () => setState(() {
                        _email.text = d.$2;
                        _password.text = d.$3;
                      }),
                    ))
                .toList(),
          ),
        ]),
      ),
    );
  }
}
