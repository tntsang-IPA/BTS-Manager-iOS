import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';

class NetworkStatus {
  NetworkStatus._();
  static final NetworkStatus instance = NetworkStatus._();
  final Connectivity _connectivity = Connectivity();
  final StreamController<bool> _controller = StreamController<bool>.broadcast();
  StreamSubscription? _sub;
  bool online = true;

  Stream<bool> get stream => _controller.stream;

  Future<void> init() async {
    final current = await _connectivity.checkConnectivity();
    online = _isOnline(current);
    _sub ??= _connectivity.onConnectivityChanged.listen((result) {
      online = _isOnline(result);
      _controller.add(online);
    });
  }

  bool _isOnline(dynamic result) {
    if (result is List<ConnectivityResult>) {
      return result.any((r) => r != ConnectivityResult.none);
    }
    return result != ConnectivityResult.none;
  }
}
