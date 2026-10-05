{{flutter_js}}
{{flutter_build_config}}

// Custom bootstrap: Flutter's own service worker is not registered - FoodBridge ships sw.js (see index.html).
_flutter.loader.load({
  onEntrypointLoaded: async function (engineInitializer) {
    const appRunner = await engineInitializer.initializeEngine();
    await appRunner.runApp();
  },
});
