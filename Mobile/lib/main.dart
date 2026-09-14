import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'services/offline_store.dart';
import 'services/network_status.dart';
import 'services/cloud_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  const url = String.fromEnvironment('SUPABASE_URL');
  const key = String.fromEnvironment('SUPABASE_PUBLISHABLE_KEY');
  if (url.isEmpty || key.isEmpty) {
    runApp(const ConfigErrorApp());
    return;
  }
  await OfflineStore.instance.init();
  await NetworkStatus.instance.init();
  await Supabase.initialize(url: url, anonKey: key);

  // V85.52 TEST: clear only Mobile-local notifications once, then bootstrap
  // from PC/Cloud. Never delete or modify Cloud/Supabase notifications here.
  const resetKey = 'notification_reset_v85_52_done';
  final resetDone = await OfflineStore.instance.readItem(resetKey);
  if (resetDone != true) {
    await OfflineStore.instance.resetLocalNotificationsForBootstrap();
    await OfflineStore.instance.cacheItem(resetKey, true);
  }

  await CloudService().syncPending();
  NetworkStatus.instance.stream.where((online) => online).listen((_) { CloudService().syncPending(); });
  runApp(const BTSManagerMobileApp());
}

class BTSManagerMobileApp extends StatelessWidget {
  const BTSManagerMobileApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'BTS Manager Mobile',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: const Color(0xff1565c0), scaffoldBackgroundColor: const Color(0xfff4f7fb), cardTheme: const CardThemeData(margin: EdgeInsets.zero, elevation: 1, surfaceTintColor: Colors.white)),
      home: Supabase.instance.client.auth.currentSession == null
          ? const LoginScreen()
          : const HomeScreen(),
    );
  }
}

class ConfigErrorApp extends StatelessWidget {
  const ConfigErrorApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    home: Scaffold(
      appBar: AppBar(title: const Text('BTS Manager Mobile')),
      body: const Padding(
        padding: EdgeInsets.all(24),
        child: Text('Thiếu SUPABASE_URL hoặc SUPABASE_PUBLISHABLE_KEY. Hãy chạy app bằng --dart-define.'),
      ),
    ),
  );
}
