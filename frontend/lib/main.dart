import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import 'router.dart';
import 'state/auth_state.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final auth = AuthState()..bootstrap();
  runApp(ChangeNotifierProvider.value(value: auth, child: FoodBridgeApp(auth: auth)));
}

class FoodBridgeApp extends StatefulWidget {
  final AuthState auth;
  const FoodBridgeApp({super.key, required this.auth});
  @override
  State<FoodBridgeApp> createState() => _FoodBridgeAppState();
}

class _FoodBridgeAppState extends State<FoodBridgeApp> {
  late final GoRouter _router = buildRouter(widget.auth);

  @override
  Widget build(BuildContext context) {
    final ready = context.watch<AuthState>().ready;
    if (!ready) {
      return MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        home: const Scaffold(
          backgroundColor: FB.forest,
          body: Center(child: CircularProgressIndicator(color: Colors.white)),
        ),
      );
    }
    return MaterialApp.router(
      title: 'FoodBridge',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      routerConfig: _router,
      // keep layouts intact for users with very large system fonts, while still honouring their setting
      builder: (context, child) => MediaQuery.withClampedTextScaling(maxScaleFactor: 1.35, child: child!),
    );
  }
}
