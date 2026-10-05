import 'dart:js_interop';

@JS('fbClearApiCache')
external JSFunction? get _clearFn;

/// Drops API responses cached by the PWA service worker (called on logout so the next
/// person using this device never sees the previous user's data offline).
void clearOfflineApiCache() {
  try {
    _clearFn?.callAsFunction();
  } catch (_) {}
}
