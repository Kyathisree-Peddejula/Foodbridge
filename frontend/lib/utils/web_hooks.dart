/// Browser-only hooks (no-ops on Android / iOS).
export 'web_hooks_stub.dart' if (dart.library.js_interop) 'web_hooks_web.dart';
