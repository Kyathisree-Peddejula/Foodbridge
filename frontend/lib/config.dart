/// Build-time configuration.
///   flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000/api
///   Android emulator: --dart-define=API_BASE_URL=http://10.0.2.2:8000/api
class AppConfig {
  static const apiBaseUrl =
      String.fromEnvironment('API_BASE_URL', defaultValue: 'http://localhost:8000/api');
  static const mlDocsUrl =
      String.fromEnvironment('ML_DOCS_URL', defaultValue: 'http://localhost:8001/docs');
  static String get apiDocsUrl => apiBaseUrl.replaceFirst(RegExp(r'/api/?$'), '/api/docs/');
  static const feedPollSeconds = 30;
}
