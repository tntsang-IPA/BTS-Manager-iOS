import 'dart:convert';
import 'dart:math' as math;
import 'package:supabase_flutter/supabase_flutter.dart';
import 'offline_store.dart';
import 'network_status.dart';

class CloudService {
  // Prevent concurrent callers (startup, network reconnect, Home, Operations,
  // Notifications) from processing the same offline queue simultaneously.
  Future<SyncReport>? _syncInFlight;

  Future<SyncReport> syncPending() {
    final running = _syncInFlight;
    if (running != null) return running;
    final future = _syncPendingInternal();
    _syncInFlight = future;
    future.then((_) {
      if (identical(_syncInFlight, future)) _syncInFlight = null;
    }, onError: (Object _, StackTrace __) {
      if (identical(_syncInFlight, future)) _syncInFlight = null;
    });
    return future;
  }

  Future<T> _retryCloud<T>(Future<T> Function() action) async {
    Object? last;
    for (var attempt = 0; attempt < 3; attempt++) {
      try {
        return await action();
      } catch (e) {
        last = e;
        if (attempt < 2) {
          await Future<void>.delayed(Duration(milliseconds: 500 * (attempt + 1)));
        }
      }
    }
    throw last ?? Exception('Cloud sync failed');
  }

  double _toDouble(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse((value ?? '').toString().replaceAll(',', '.')) ?? 0.0;
  }

  final SupabaseClient client = Supabase.instance.client;
  final OfflineStore local = OfflineStore.instance;
  final NetworkStatus network = NetworkStatus.instance;
  User? get user => client.auth.currentUser;

  /// Refresh the Supabase access token before dashboard reads when the session
  /// is close to expiry. This is intentionally lightweight and does not force
  /// a refresh on every request.
  Future<void> ensureFreshSession({Duration threshold = const Duration(minutes: 1)}) async {
    final session = client.auth.currentSession;
    if (session == null) return;
    final expiresAt = session.expiresAt;
    if (expiresAt == null) return;
    final expiry = DateTime.fromMillisecondsSinceEpoch(expiresAt * 1000, isUtc: true);
    final now = DateTime.now().toUtc();
    if (expiry.isBefore(now.add(threshold))) {
      await client.auth.refreshSession();
    }
  }

  bool _isJwtExpired(Object error) {
    if (error is PostgrestException && error.code == 'PGRST303') return true;
    final text = error.toString().toLowerCase();
    return text.contains('pgrst303') || text.contains('jwt expired') || text.contains('token has expired');
  }

  /// Execute one authenticated read, refreshing the Supabase session once
  /// when PostgREST reports an expired JWT. A second failure is propagated so
  /// callers can use their normal offline/cache handling.
  Future<T> _withAuthRetry<T>(Future<T> Function() action) async {
    try {
      await ensureFreshSession();
      return await action();
    } catch (e) {
      if (!_isJwtExpired(e)) rethrow;
      await client.auth.refreshSession();
      return await action();
    }
  }

  Future<void> signIn(String email, String password) async =>
      client.auth.signInWithPassword(email: email, password: password);
  Future<void> signOut() => client.auth.signOut();
  Future<void> changePassword(String password) async =>
      client.auth.updateUser(UserAttributes(password: password));

  bool can(String permission) {
    final meta = user?.appMetadata ?? const <String, dynamic>{};
    final permissions = (meta['permissions'] as List?)?.map((e) => e.toString()).toSet() ?? <String>{};
    if ((user?.email ?? '').trim().toLowerCase() == 'tntsang@gmail.com') return true;
    return permissions.contains('*') || permissions.contains(permission);
  }


  static const Map<String, String> sheetToTable = {
    'TRẠM BTS': 'stations',
    'HỢP ĐỒNG': 'contracts',
    'THIẾT BỊ': 'equipment',
    'TRUYỀN DẪN': 'transmission',
    'NGUỒN': 'power',
    'PIN - BATTERY': 'batteries',
    'THIẾT BỊ PHỤ TRỢ': 'auxiliary',
    'BTBD': 'maintenance',
    'MLL': 'mll_events',
  };

  static const Map<String, String> tablePrimaryKey = {
    'stations': 'id',
    'contracts': 'contract_id',
    'equipment': 'equipment_id',
    'transmission': 'transmission_id',
    'power': 'power_id',
    'batteries': 'battery_id',
    'auxiliary': 'aux_id',
    'maintenance': 'work_id',
    'mll_events': 'id',
  };

  static const List<String> editableSheets = [
    'TRẠM BTS', 'HỢP ĐỒNG', 'THIẾT BỊ', 'TRUYỀN DẪN', 'NGUỒN',
    'PIN - BATTERY', 'THIẾT BỊ PHỤ TRỢ', 'BTBD', 'MLL',
  ];

  Future<List<String>> stationCodes() async {
    try {
      final rows = await client.from('stations').select('code').order('code').limit(10000);
      final codes = List<Map<String, dynamic>>.from(rows)
          .map((r) => (r['code'] ?? '').toString().trim())
          .where((v) => v.isNotEmpty).toList();
      await local.cacheItem('station_codes', codes);
      return codes;
    } catch (_) {
      final cached = await local.readItem('station_codes');
      if (cached is List) return cached.map((e) => e.toString()).where((e) => e.isNotEmpty).toList();
      return (await local.allStations()).map((r) => (r['code'] ?? '').toString()).where((e) => e.isNotEmpty).toList()..sort();
    }
  }

  Future<List<Map<String, dynamic>>> findSheetRows(String sheet, String stationCode) async {
    final table = sheetToTable[sheet];
    if (table == null) throw Exception('Sheet không được hỗ trợ: $sheet');
    try {
      final rows = List<Map<String, dynamic>>.from(
        await client.from(table).select().eq(table == 'stations' ? 'code' : 'station_code', stationCode).order('updated_at', ascending: false).limit(200),
      );
      await local.cacheItem('sheet:$sheet:$stationCode', rows);
      return rows;
    } catch (_) {
      final cached = await local.readItem('sheet:$sheet:$stationCode');
      if (cached is List) return List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
      if (table == 'stations') {
        final row = await local.station(stationCode);
        return row == null ? [] : [row];
      }
      return [];
    }
  }

  Future<void> updateSheetRow(String sheet, String stationCode, Map<String, dynamic> row) async {
    final table = sheetToTable[sheet];
    final pk = table == null ? null : tablePrimaryKey[table];
    if (table == null || pk == null) throw Exception('Không xác định được bảng dữ liệu cho $sheet');
    final permissionOk = can('stations.write') || can('station.update') || can('$table.write') || can('data.write');
    if (!permissionOk) throw Exception('Tài khoản không có quyền cập nhật dữ liệu $sheet.');
    final key = row[pk];
    if (key == null) throw Exception('Không xác định được khóa dữ liệu của dòng $sheet.');
    final editable = Map<String, dynamic>.from(row)..remove('created_at')..remove('updated_at');
    editable.remove(pk);
    editable['updated_at'] = DateTime.now().toUtc().toIso8601String();
    final baseUpdatedAt = row['updated_at']?.toString();
    try {
      // RLS/PostgREST can return an empty representation when an UPDATE
      // matched no row. Treat that as a failed cloud write so the change is
      // queued instead of falsely reporting success.
      final returned = await _withAuthRetry(() async =>
          await client.from(table).update(editable).eq(pk, key).select(pk));
      if (returned.isEmpty) {
        throw Exception('Cloud không cập nhật được $sheet (0 dòng). Kiểm tra quyền/RLS hoặc mã dữ liệu.');
      }
      final rows = await findSheetRows(sheet, stationCode);
      for (final r in rows) { if (r[pk].toString() == key.toString()) r.addAll(editable); }
      await local.cacheItem('sheet:$sheet:$stationCode', rows);
      if (table == 'stations') await local.updateCachedStation(stationCode, editable);
    } catch (_) {
      await local.enqueue(table: table, operation: 'update', key: key.toString(), payload: editable, baseUpdatedAt: baseUpdatedAt);
      final cached = await local.readItem('sheet:$sheet:$stationCode');
      if (cached is List) {
        final rows = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
        for (final r in rows) { if (r[pk].toString() == key.toString()) r.addAll(editable); }
        await local.cacheItem('sheet:$sheet:$stationCode', rows);
      }
      if (table == 'stations') await local.updateCachedStation(stationCode, editable);
    }
  }

  /// Returns the same operational distribution cards used by the PC dashboard.
  Future<Map<String, List<Map<String, dynamic>>>> overviewStats() async {
    const fields = ['type', 'upe', 'pole_type', 'csht_type', 'technician'];
    final result = <String, List<Map<String, dynamic>>>{};
    try {
      final rows = List<Map<String, dynamic>>.from(
        await client.from('stations').select('type,upe,pole_type,csht_type,technician').limit(10000),
      );
      for (final field in fields) {
        final counts = <String, int>{};
        for (final row in rows) {
          final label = (row[field] ?? '').toString().trim();
          final key = label.isEmpty ? 'Chưa cập nhật' : label;
          counts[key] = (counts[key] ?? 0) + 1;
        }
        final items = counts.entries
            .map((e) => <String, dynamic>{'label': e.key, 'count': e.value})
            .toList()
          ..sort((a, b) => (b['count'] as int).compareTo(a['count'] as int));
        result[field] = items;
        await local.cacheItem('overview:$field', items);
      }
      return result;
    } catch (_) {
      for (final field in fields) {
        final cached = await local.readItem('overview:$field');
        result[field] = cached is List
            ? List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)))
            : <Map<String, dynamic>>[];
      }
      return result;
    }
  }

  Future<int> stationCount() async {
    try {
      final count = (await client.from('stations').select('id').count(CountOption.exact)).count;
      return count;
    } catch (_) {
      return (await local.allStations()).length;
    }
  }

  Future<List<Map<String, dynamic>>> kpis() async {
    try {
      final data = await _withAuthRetry<List<Map<String, dynamic>>>(() async {
        try {
          // Newer KPI imports may carry an explicit reporting month.
          final rows = List<Map<String, dynamic>>.from(
            await client.from('kpi_targets')
                .select('content,target,actual,month,updated_at')
                .order('updated_at', ascending: false),
          );
          return rows;
        } catch (e) {
          // Backward-compatible schema: older databases do not have month.
          if (_isJwtExpired(e)) rethrow;
          return List<Map<String, dynamic>>.from(
            await client.from('kpi_targets')
                .select('content,target,actual,updated_at')
                .order('updated_at', ascending: false),
          );
        }
      });
      // The PC dashboard uses the latest imported KPI row for each content.
      data.sort((a, b) => _dateScore(b['updated_at']).compareTo(_dateScore(a['updated_at'])));
      await local.cacheItem('kpis', data);
      return data;
    } catch (_) {
      final cached = await local.readItem('kpis');
      if (cached is List) {
        final data = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
        data.sort((a, b) => _dateScore(b['updated_at']).compareTo(_dateScore(a['updated_at'])));
        return data;
      }
      return <Map<String, dynamic>>[];
    }
  }

  int _dateScore(dynamic value) => DateTime.tryParse(value?.toString() ?? '')?.millisecondsSinceEpoch ?? 0;

  /// Parse KPI numeric values consistently with the PC import format.
  /// Handles numeric JSON values plus comma/dot decimal separators.
  double? _numberValue(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    final text = value.toString().trim();
    if (text.isEmpty) return null;
    // KPI imports are normally numeric, but some Cloud/Excel versions may
    // preserve the display unit (e.g. "0.48 phút"). Extract the first
    // numeric token so the Mobile KPI reader behaves like the PC reader.
    final compact = text.replaceAll(RegExp(r'\s+'), '');
    final direct = _parseFlexibleNumber(compact);
    if (direct != null) return direct;
    final match = RegExp(r'-?\d+(?:[.,]\d+)?').firstMatch(text);
    return match == null ? null : _parseFlexibleNumber(match.group(0)!);
  }

  double? _parseFlexibleNumber(String value) {
    var normalized = value.trim();
    if (normalized.isEmpty) return null;
    if (normalized.contains(',') && normalized.contains('.')) {
      final lastComma = normalized.lastIndexOf(',');
      final lastDot = normalized.lastIndexOf('.');
      if (lastComma > lastDot) {
        normalized = normalized.replaceAll('.', '').replaceAll(',', '.');
      } else {
        normalized = normalized.replaceAll(',', '');
      }
    } else if (normalized.contains(',')) {
      normalized = normalized.replaceAll(',', '.');
    }
    return double.tryParse(normalized);
  }

  String _normLabel(String value) {
    var s = value.toLowerCase().trim();
    // Normalize Vietnamese labels so imported KPI content such as
    // 'Bảo trì bảo dưỡng ngoài trời', 'BTBD ngoài trời', 'BTBD Outdoor'
    // and punctuation/underscore variants are treated as the same KPI.
    const from = 'àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ';
    const to   = 'aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd';
    final chars = s.split('');
    final b = StringBuffer();
    for (final c in chars) {
      final i = from.indexOf(c);
      b.write(i >= 0 ? to[i] : c);
    }
    return b.toString().replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
  }

  Future<Map<String, dynamic>> dashboardMetrics() async {
    final result = <String, dynamic>{};
    final kpiRows = await kpis();

    num? number(dynamic v) {
      if (v == null) return null;
      final text = v.toString().trim();
      if (text.isEmpty) return null;
      if (text.contains(',')) {
        return num.tryParse(text.replaceAll('.', '').replaceAll(',', '.'));
      }
      return num.tryParse(text);
    }

    Map<String, dynamic>? findKpi(List<String> aliases) {
      final wanted = aliases.map(_normLabel).where((e) => e.isNotEmpty).toSet();
      Map<String, dynamic>? best;
      var bestScore = 0;
      for (final row in kpiRows) {
        final label = _normLabel(row['content']?.toString() ?? '');
        if (label.isEmpty) continue;
        var score = 0;
        for (final alias in wanted) {
          if (label == alias) score = math.max(score, 100);
          else if (label.contains(alias) || alias.contains(label)) score = math.max(score, 80);
        }
        // PC labels can be imported as short labels or full Vietnamese text.
        // Match by semantic KPI family as well as exact aliases.
        if (wanted.contains(_normLabel('XL PAKH')) &&
            (label.contains('xu ly pakh') || label.contains('xl pakh') || label.contains('pakh'))) {
          score = math.max(score, 95);
        }
        final isBtbd = label.contains('btbd') ||
            label.contains('bao tri bao duong') ||
            label.contains('bao tri bao duong');
        final isOutdoor = label.contains('outdoor') || label.contains('ngoai troi');
        final isIndoor = label.contains('indoor') || label.contains('trong nha');
        if (wanted.contains(_normLabel('BTBD Outdoor')) && isBtbd && isOutdoor) {
          score = math.max(score, 98);
        }
        if (wanted.contains(_normLabel('BTBD Indoor')) && isBtbd && isIndoor) {
          score = math.max(score, 98);
        }
        // MLL labels vary between PC imports: 'Mất LL', 'Mất liên lạc',
        // 'Thời gian mất liên lạc (TB BSC)', etc. Match the semantic family
        // explicitly so a valid PC KPI such as 0.48/0.50 is never missed.
        final isMllFamily = label.contains('mll') ||
            label.contains('mat ll') ||
            label.contains('mat lien lac');
        final asksMll = wanted.any((a) => a.contains('mll') ||
            a.contains('mat ll') || a.contains('mat lien lac'));
        if (asksMll && isMllFamily) {
          var mllScore = 92;
          if (label.contains('tb bsc')) mllScore += 5;
          if (label.contains('mat lien lac')) mllScore += 2;
          score = math.max(score, mllScore);
        }
        if (score > bestScore) { bestScore = score; best = row; }
      }
      return best;
    }

    Map<String, dynamic>? findKpiByFamily({required bool outdoor}) {
      Map<String, dynamic>? best;
      var bestScore = 0;
      for (final row in kpiRows) {
        final label = _normLabel(row['content']?.toString() ?? '');
        if (label.isEmpty) continue;
        final isBtbd = label.contains('btbd') || label.contains('bao tri bao duong');
        final isTargetFamily = outdoor
            ? (label.contains('outdoor') || label.contains('ngoai troi'))
            : (label.contains('indoor') || label.contains('trong nha'));
        if (isBtbd && isTargetFamily) {
          // kpiRows is newest-first, so only replace on a strictly stronger
          // semantic score; equal matches retain the newest row.
          final score = (label.contains('btbd') ? 100 : 95) + (isTargetFamily ? 10 : 0);
          if (score > bestScore) { bestScore = score; best = row; }
        }
      }
      return best;
    }

    // PC dashboard contract: BTBD cards are driven by the KPI import table.
    // Do NOT recalculate these from maintenance rows: the PC app displays the
    // imported "Đã thực hiện / Chỉ tiêu" values (e.g. 158/180, 96/120).
    final indoorKpi = findKpi(['BTBD Indoor', 'BTBD INDOOR', 'BTBD trong nhà']) ?? findKpiByFamily(outdoor: false);
    final outdoorKpi = findKpi(['BTBD Outdoor', 'BTBD OUTDOOR', 'BTBD ngoài trời']) ?? findKpiByFamily(outdoor: true);
    final pakhKpi = findKpi(['XL PAKH', 'Xử lý PAKH', 'Xu ly PAKH']);
    final developmentKpi = findKpi(['Trạm phát triển mới', 'Phát triển mới']);
    result['indoor'] = <String, dynamic>{
      'content': 'BTBD Indoor',
      'actual': number(indoorKpi?['actual']),
      'target': number(indoorKpi?['target']),
    };
    result['outdoor'] = <String, dynamic>{
      'content': 'BTBD Outdoor',
      'actual': number(outdoorKpi?['actual']),
      'target': number(outdoorKpi?['target']),
    };
    result['pakh'] = <String, dynamic>{
      'content': 'XL PAKH',
      'actual': number(pakhKpi?['actual']),
      'target': number(pakhKpi?['target']),
    };
    result['development'] = <String, dynamic>{
      'content': 'Trạm phát triển mới',
      'actual': number(developmentKpi?['actual']),
      'target': number(developmentKpi?['target']),
    };

    // NEW MLL CARD CONTRACT (V85.26): do NOT use TB BSC/avg_6m/event data
    // for the Dashboard card. The card is now named 'Chỉ tiêu MLL' and must
    // display exactly KPI!B6 from the PC KPI workbook. In the normalized
    // cloud table this is the row whose Nội dung/`content` is 'MLL' and whose
    // Chỉ tiêu/`target` is the value from column B.
    final mllTarget = await _readPcMllTargetFromKpi();
    result['mll'] = mllTarget;
    result['mllActual'] = null;
    result['mllTarget'] = mllTarget;
    return result;
  }

  /// Reads the exact six-month TB BSC result produced by the PC app.
  /// There is deliberately NO fallback to mll_events here.
  Future<double?> mllPcSixMonthAverage() async {
    try {
      // The PC dashboard card uses the explicit TB 6 tháng value from
      // BSC TỔNG (stored as month_no=0 / avg_6m). Never average the six
      // monthly rows again here; that can produce a different result from PC.
      final rows = List<Map<String, dynamic>>.from(
        await client.from('mll_bsc_summary').select('dept,month_no,value,avg_6m').order('dept').order('month_no'),
      );
      if (rows.isNotEmpty) {
        await local.cacheItem('mll_bsc_summary', rows);
      }
      final avgs = rows
          .where((r) => (int.tryParse((r['month_no'] ?? '').toString()) ?? -1) == 0)
          .map((r) => _numberValue(r['avg_6m']))
          .whereType<double>()
          .where((v) => v.isFinite)
          .toList();
      if (avgs.isNotEmpty) return avgs.reduce((a, b) => a + b) / avgs.length;

      // Compatibility with a cloud table that stores avg_6m without the
      // month_no=0 marker. Still prefer avg_6m over monthly value rows.
      final anyAvgs = rows
          .map((r) => _numberValue(r['avg_6m']))
          .whereType<double>()
          .where((v) => v.isFinite)
          .toList();
      if (anyAvgs.isNotEmpty) return anyAvgs.reduce((a, b) => a + b) / anyAvgs.length;
    } catch (_) {
      // Older cloud projects may not yet have mll_bsc_summary. Continue with
      // the cached PC-authoritative summary before using the compatibility path.
    }

    try {
      final cached = await local.readItem('mll_bsc_summary');
      if (cached is List) {
        final rows = List<Map<String, dynamic>>.from(
          cached.map((e) => Map<String, dynamic>.from(e)),
        );
        final avgs = rows
            .where((r) => (int.tryParse((r['month_no'] ?? '').toString()) ?? -1) == 0)
            .map((r) => _numberValue(r['avg_6m']))
            .whereType<double>()
            .where((v) => v.isFinite)
            .toList();
        if (avgs.isNotEmpty) return avgs.reduce((a, b) => a + b) / avgs.length;
        final anyAvgs = rows
            .map((r) => _numberValue(r['avg_6m']))
            .whereType<double>()
            .where((v) => v.isFinite)
            .toList();
        if (anyAvgs.isNotEmpty) return anyAvgs.reduce((a, b) => a + b) / anyAvgs.length;
      }
    } catch (_) {}

    // Older Cloud projects may not yet have mll_bsc_summary. Fall through to
    // the authoritative PC analysis result instead of recalculating from raw
    // MLL events.
    // Compatibility path: the PC also publishes its exact BSC average inside
    // mll_analysis_summary. This remains PC-authoritative and is NOT derived
    // by Android.
    try {
      final rows = List<Map<String, dynamic>>.from(
        await client
            .from('mll_analysis_summary')
            .select('bsc_avg,updated_at')
            .eq('range_key', '1-6')
            .limit(1),
      );
      if (rows.isNotEmpty) {
        final value = _numberValue(rows.first['bsc_avg']);
        if (value != null && value.isFinite) return value;
      }
    } catch (_) {}
    return null;
  }

  // Explicit scoring prevents a generic "Mất LL" total from beating the
  // specific "Mất LL (TB BSC)" measured KPI.
  bool _isValidTbBscValue(double? value) {
    // TB BSC is a minutes KPI with a 0.50-minute target in the PC contract.
    // Values such as 54.10/73.80 are aggregate event minutes and must never
    // be promoted to the TB BSC KPI. Keep a generous 5-minute ceiling so the
    // guard is about data type safety, not normal KPI performance.
    return value != null && value.isFinite && value >= 0 && value <= 5.0;
  }

  /// Exact PC KPI source for the Dashboard 'Chỉ tiêu MLL' card.
  /// Excel source: sheet KPI, cell B6 = row 'MLL' / column 'Chỉ tiêu'.
  /// Cloud mapping: kpi_targets.content == 'MLL', kpi_targets.target == B6.
  /// No TB BSC, avg_6m, actual, or mll_events value is used for this card.
  Future<double?> _readPcMllTargetFromKpi() async {
    try {
      final direct = await _withAuthRetry<List<Map<String, dynamic>>>(() async {
        final r = await client.from('kpi_targets')
            .select('content,target,updated_at')
            .eq('content', 'MLL')
            .limit(1);
        return List<Map<String, dynamic>>.from(r);
      });
      if (direct.isNotEmpty) {
        return _numberValue(direct.first['target']);
      }
    } catch (_) {}

    // Use the already loaded KPI cache as a compatibility path. The semantic
    // match is still exact: content == 'MLL'; value comes only from target.
    try {
      final rows = await kpis();
      for (final row in rows) {
        if (_normLabel(row['content']?.toString() ?? '') == _normLabel('MLL')) {
          return _numberValue(row['target']);
        }
      }
    } catch (_) {}
    return null;
  }

  Future<Map<String, dynamic>?> _readPcMllKpi(List<Map<String, dynamic>> rows) async {
    // 1) Exact PC labels. kpi_targets.content is the PC primary key.
    const exact = [
      'Mất LL (TB BSC)',
      'Mất LL TB BSC',
      'Mất liên lạc (TB BSC)',
      'Mất liên lạc TB BSC',
      'Thời gian mất liên lạc (TB BSC)',
      'Thời gian mất liên lạc TB BSC',
      'MLL (TB BSC)',
      'MLL TB BSC',
    ];
    try {
      final direct = <Map<String, dynamic>>[];
      for (final name in exact) {
        final row = await _withAuthRetry<List<Map<String, dynamic>>>(() async {
          final r = await client.from('kpi_targets')
              .select('content,target,actual,updated_at')
              .eq('content', name)
              .limit(1);
          return List<Map<String, dynamic>>.from(r);
        });
        if (row.isNotEmpty) direct.add(row.first);
      }
      final found = _findMllKpi(direct);
      if (found != null) return found;
    } catch (_) {
      // Continue with the already loaded KPI rows/cache below.
    }

    // 2) Robust in-memory match from the normal KPI load.
    final found = _findMllKpi(rows);
    if (found != null) return found;

    // 3) Compatibility for a PC/Cloud schema where the KPI row is present
    // under an extended label. Still use only PC-authoritative KPI/summary
    // data; never derive the card from raw mll_events.
    try {
      final candidates = await _withAuthRetry<List<Map<String, dynamic>>>(() async {
        final r = await client.from('kpi_targets')
            .select('content,target,actual,updated_at')
            .or('content.ilike.%Mất LL%,content.ilike.%Mất liên lạc%,content.ilike.%MLL%,content.ilike.%TB BSC%')
            .limit(100);
        return List<Map<String, dynamic>>.from(r);
      });
      final extended = _findMllKpi(candidates);
      if (extended != null) return extended;
    } catch (_) {}

    return null;
  }

  Map<String, dynamic>? _findMllKpi(List<Map<String, dynamic>> rows) {
    Map<String, dynamic>? best;
    var bestScore = 0;
    for (final r in rows) {
      final label = _normLabel(r['content']?.toString() ?? '');
      if (label.isEmpty) continue;
      final actual = _numberValue(r['actual']);
      if (!_isValidTbBscValue(actual)) continue;

      var score = 0;
      if (label == _normLabel('Mất LL (TB BSC)')) score = 140;
      else if (label == _normLabel('Mất LL TB BSC')) score = 135;
      else if (label == _normLabel('Mất liên lạc (TB BSC)')) score = 130;
      else if (label == _normLabel('Mất liên lạc TB BSC')) score = 125;
      else if (label == _normLabel('Thời gian mất liên lạc (TB BSC)')) score = 130;
      else if (label == _normLabel('Thời gian mất liên lạc TB BSC')) score = 125;
      else if (label == _normLabel('MLL (TB BSC)')) score = 120;
      else if (label == _normLabel('MLL TB BSC')) score = 115;
      else if (label == _normLabel('TB BSC')) score = 110;
      else if (label == _normLabel('Mất LL')) score = 60;
      else if (label == _normLabel('MLL')) score = 55;
      else if (label.contains('tb bsc')) score = 100;
      // Some PC KPI templates append units or extra wording. Treat any
      // explicit MLL/TB-BSC family label as a valid candidate, while the
      // numeric guard above prevents aggregate values such as 54.10/73.80
      // from being mistaken for the 0.50-minute KPI.
      else if ((label.contains('mat ll') || label.contains('mat lien lac') || label.contains('mll')) &&
               label.contains('tb bsc')) score = 105;

      if (score > bestScore) {
        bestScore = score;
        best = r;
      } else if (score == bestScore && score > 0) {
        final current = _dateScore(r['updated_at']);
        final previous = _dateScore(best?['updated_at']);
        if (current > previous) best = r;
      }
    }
    return best;
  }

  /// Reads the monthly TB BSC values already calculated by the PC app.
  /// Android does not calculate TB BSC from raw MLL event durations.
  /// Reads the exact MLL analysis result last calculated by the PC app for
  /// the selected month-number range. Android does not recompute the PC
  /// dashboard metrics; it only renders this authoritative result.
  /// Compatibility fallback for older mll_analysis_summary rows that were
  /// created before top_station_json/longest_json were published. The primary
  /// path remains the PC-authoritative JSON fields; this only reconstructs the
  /// two table rows from the same raw MLL columns used by the PC dashboard when
  /// those fields are absent/empty.
  Future<Map<String, List<Map<String, dynamic>>>> mllTableFallback(int fromMonth, int toMonth) async {
    try {
      final rows = List<Map<String, dynamic>>.from(
        await client.from('mll_events').select('month,station_code,downtime_min,error_content,resolution,g5,g3,g4').limit(20000),
      );
      final selected = rows.where((r) {
        final raw = (r['month'] ?? '').toString();
        final m = RegExp(r'(\d+)').firstMatch(raw);
        final n = int.tryParse(m?.group(1) ?? '0') ?? 0;
        return n >= fromMonth && n <= toMonth;
      }).toList();

      final station = <String, Map<String, dynamic>>{};
      for (final r in selected) {
        final code = (r['station_code'] ?? '').toString().trim();
        final key = code.isEmpty ? 'Không rõ' : code;
        final item = station.putIfAbsent(key, () => {'cases': 0, 'minutes': 0.0});
        item['cases'] = (item['cases'] as int) + 1;
        item['minutes'] = (item['minutes'] as double) + _toDouble(r['downtime_min']);
      }
      final top = station.entries.toList()
        ..sort((a,b) => (b.value['minutes'] as double).compareTo(a.value['minutes'] as double));
      final topRows = top.take(8).map((e) => {
        'station': e.key, 'cases': e.value['cases'], 'minutes': e.value['minutes']
      }).toList();

      final longRows = [...selected];
      longRows.sort((a,b) => _toDouble(b['downtime_min']).compareTo(_toDouble(a['downtime_min'])));
      final longest = longRows.take(5).map((r) {
        final raw = (r['month'] ?? '').toString();
        final m = RegExp(r'(\d+)').firstMatch(raw);
        final mn = int.tryParse(m?.group(1) ?? '0') ?? 0;
        return {
          'station': (r['station_code'] ?? '').toString(),
          'month': 'Tháng $mn',
          'reason': _mllReasonGroup((r['error_content'] ?? '').toString().trim().isNotEmpty
              ? r['error_content']
              : r['resolution']),
          'minutes': _toDouble(r['downtime_min']),
        };
      }).toList();
      return {'top': topRows, 'longest': longest};
    } catch (_) {
      return {'top': const [], 'longest': const []};
    }
  }

  String _mllReasonGroup(dynamic text) {
    final s = (text ?? '').toString().toLowerCase();
    if (s.contains('br') || s.contains('switch') || s.contains('router')) return 'Lỗi BR / SW';
    if (s.contains('quang') || s.contains('cáp') || s.contains('cap ')) return 'Đứt cáp / FO';
    if (s.contains('điện') || s.contains('nguồn') || s.contains('ac')) return 'Nguồn điện';
    if (s.contains('duw') || s.contains('rru') || s.contains('bbu') || s.contains('thiết bị')) return 'Lỗi thiết bị';
    if (s.contains('truyền dẫn')) return 'Truyền dẫn';
    return 'Khác';
  }

  Future<Map<String, dynamic>?> mllAnalysisSummary(int fromMonth, int toMonth) async {
    final key = '${fromMonth}-${toMonth}';
    try {
      final rows = List<Map<String, dynamic>>.from(
        await client.from('mll_analysis_summary').select('*').eq('range_key', key).limit(1),
      );
      if (rows.isNotEmpty) {
        final row = rows.first;
        await local.cacheItem('mll_analysis:$key', row);
        return row;
      }
    } catch (_) {
      // The summary table is intentionally authoritative. Do not calculate a
      // replacement from raw mll_events here.
    }
    final cached = await local.readItem('mll_analysis:$key');
    if (cached is Map) return Map<String, dynamic>.from(cached);
    return null;
  }

  Future<List<Map<String, dynamic>>> mllMonthlyBsc(DateTime from, DateTime to) async {
    final targetRow = _findMllKpi(await kpis());
    final target = targetRow == null ? null : _numberValue(targetRow['target']);
    final wantedMonths = <DateTime>[];
    var cursor = DateTime(from.year, from.month);
    final end = DateTime(to.year, to.month);
    while (!cursor.isAfter(end)) {
      wantedMonths.add(cursor);
      cursor = DateTime(cursor.year, cursor.month + 1);
    }

    // The PC summary currently stores month_no (1..12) and the exact value
    // calculated from BSC TỔNG. Use only that result; never derive TB BSC from
    // mll_events.bsc_min/downtime_min.
    List<Map<String, dynamic>> summary = [];
    try {
      summary = List<Map<String, dynamic>>.from(
        await client.from('mll_bsc_summary').select('dept,month_no,value,avg_6m').order('month_no'),
      );
      await local.cacheItem('mll_bsc_summary', summary);
    } catch (_) {
      final cached = await local.readItem('mll_bsc_summary');
      if (cached is List) summary = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
    }

    // Compatibility for older cloud schema: use the exact PC-published
    // monthly_json for the full 1-12 range. Android still does not calculate
    // any BSC value from raw events.
    if (summary.isEmpty) {
      try {
        final rows = List<Map<String, dynamic>>.from(
          await client
              .from('mll_analysis_summary')
              .select('monthly_json')
              .eq('range_key', '1-12')
              .limit(1),
        );
        if (rows.isNotEmpty) {
          final raw = rows.first['monthly_json'];
          if (raw is String && raw.isNotEmpty) {
            final decoded = jsonDecode(raw);
            if (decoded is List) {
              summary = decoded
                  .whereType<Map>()
                  .map((e) {
                    final m = Map<String, dynamic>.from(e);
                    final label = m['month']?.toString() ?? '';
                    final monthNo = int.tryParse(label.replaceAll(RegExp(r'[^0-9]'), ''));
                    return <String, dynamic>{
                      'dept': 'PC',
                      'month_no': monthNo,
                      'value': m['bsc'],
                      'avg_6m': null,
                    };
                  })
                  .where((e) => e['month_no'] != null)
                  .toList();
            }
          }
        }
      } catch (_) {}
    }

    // Count events only for the PC's "Tổng vụ MLL" card; the TB BSC value is
    // always taken from PC-authoritative summary data.
    List<Map<String, dynamic>> events = [];
    try {
      events = List<Map<String, dynamic>>.from(await client.from('mll_events').select('month').limit(20000));
    } catch (_) {
      events = [];
    }
    int countFor(DateTime month) {
      var count = 0;
      for (final e in events) {
        // PC imports store the month as 'Tháng 1', 'Tháng 2', ... in
        // mll_events. Use the selected report year for this month-only
        // representation; do not recalculate any MLL metric.
        final parsed = _parseMllMonth(e['month']?.toString(), null, defaultYear: month.year);
        if (parsed != null && parsed.year == month.year && parsed.month == month.month) count++;
      }
      return count;
    }

    final result = <Map<String, dynamic>>[];
    for (final month in wantedMonths) {
      final matching = summary.where((r) {
        final n = int.tryParse((r['month_no'] ?? '').toString());
        return n == month.month;
      }).toList();
      double? value;
      if (matching.isNotEmpty) {
        final values = matching.map((r) => _numberValue(r['value'])).whereType<double>().where((v) => v.isFinite).toList();
        if (values.isNotEmpty) value = values.reduce((a, b) => a + b) / values.length;
        if (value == null) {
          final avgs = matching.map((r) => _numberValue(r['avg_6m'])).whereType<double>().where((v) => v.isFinite).toList();
          if (avgs.isNotEmpty) value = avgs.reduce((a, b) => a + b) / avgs.length;
        }
      }
      result.add({
        'year': month.year,
        'month': month.month,
        'count': countFor(month),
        'bsc_avg': value,
        'bsc_sum': value ?? 0,
        'bsc_count': value == null ? 0 : 1,
        'bsc_target': target,
      });
    }
    return result;
  }

  DateTime? _parseMllMonth(String? raw, String? fallback, {int? defaultYear}) {
    final s = (raw ?? '').trim();
    if (s.isNotEmpty) {
      final monthWord = RegExp(r'^(?:tháng|thang)\s*(\d{1,2})$', caseSensitive: false).firstMatch(s);
      if (monthWord != null) {
        final m = int.tryParse(monthWord.group(1)!);
        final y = defaultYear ?? DateTime.now().year;
        if (m != null && m >= 1 && m <= 12) return DateTime(y, m);
      }
      final iso = DateTime.tryParse(s);
      if (iso != null) return DateTime(iso.year, iso.month);
      // Some imports store the month as a numeric 1..12 value. In that case
      // take the year from updated_at when available.
      final numericMonth = int.tryParse(s);
      if (numericMonth != null && numericMonth >= 1 && numericMonth <= 12) {
        final fb = DateTime.tryParse(fallback ?? '');
        if (fb != null) return DateTime(fb.year, numericMonth);
      }
      final patterns = [
        RegExp(r'^(\d{1,2})[\/-](\d{4})'),
        RegExp(r'^(\d{4})[\/-](\d{1,2})'),
        RegExp(r'^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})'),
      ];
      for (final p in patterns) {
        final m = p.firstMatch(s);
        if (m != null) {
          int? year;
          int? month;
          if (m.groupCount == 2) {
            final a = int.tryParse(m.group(1)!);
            final b = int.tryParse(m.group(2)!);
            if (a != null && b != null) {
              year = a > 12 ? a : b;
              month = a > 12 ? b : a;
            }
          } else {
            year = int.tryParse(m.group(3)!);
            month = int.tryParse(m.group(2)!);
          }
          if (year != null && month != null && month >= 1 && month <= 12 && year >= 2000) return DateTime(year, month);
        }
      }
    }
    final fb = DateTime.tryParse(fallback ?? '');
    if (fb != null) return DateTime(fb.year, fb.month);
    return null;
  }

  Future<List<Map<String, dynamic>>> searchStations(String q) async {
    final s = q.trim().toLowerCase();
    if (s.isEmpty) return [];
    try {
      final pattern = '%${s.replaceAll('%', '\\%').replaceAll('_', '\\_')}%';
      final data = await client.from('stations').select('id,code,name,address,upe,meter_code,technician,type,pole_type,csht_type,status,latitude,longitude,email,updated_at')
        .or('code.ilike.$pattern,name.ilike.$pattern,address.ilike.$pattern,upe.ilike.$pattern,meter_code.ilike.$pattern,technician.ilike.$pattern')
        .order('code').limit(50);
      final contractRows = await client.from('contracts').select('station_code,contract_no').ilike('contract_no', pattern).limit(50);
      final contractCodes = <String>{...List<Map<String, dynamic>>.from(contractRows).map((r) => (r['station_code'] ?? '').toString()).where((v) => v.isNotEmpty)};
      final merged = <String, Map<String, dynamic>>{for (final row in List<Map<String, dynamic>>.from(data)) (row['code'] ?? '').toString(): Map<String, dynamic>.from(row)};
      final missingCodes = contractCodes.where((code) => !merged.containsKey(code)).toList();
      if (missingCodes.isNotEmpty) {
        final extra = await client.from('stations').select('id,code,name,address,upe,meter_code,technician,type,pole_type,csht_type,status,latitude,longitude,email,updated_at').inFilter('code', missingCodes);
        for (final row in List<Map<String, dynamic>>.from(extra)) merged[(row['code'] ?? '').toString()] = Map<String, dynamic>.from(row);
      }
      final result = merged.values.toList()..sort((a, b) => (a['code'] ?? '').toString().compareTo((b['code'] ?? '').toString()));
      await local.cacheStations(result);
      return result.take(50).toList();
    } catch (_) {
      final rows = await local.allStations();
      return rows.where((r) => r.values.any((v) => v != null && v.toString().toLowerCase().contains(s))).take(50).toList();
    }
  }

  Future<Map<String, dynamic>> station(String code) async {
    try {
      final rows = await client.from('stations').select().eq('code', code).limit(1);
      if (rows.isEmpty) throw Exception('Không tìm thấy mã trạm $code');
      final station = Map<String, dynamic>.from(rows.first);
      final related = <String, List<Map<String, dynamic>>>{};
      const tables = ['contracts','equipment','transmission','power','batteries','auxiliary','maintenance','mll_events'];
      for (final table in tables) {
        final data = await client.from(table).select().eq('station_code', code).order('updated_at', ascending: false).limit(100);
        related[table] = List<Map<String, dynamic>>.from(data);
      }
      station['_related'] = related;
      await local.cacheStations([station]);
      await local.cacheItem('station:$code:related', related);
      return station;
    } catch (_) {
      final cached = await local.station(code);
      if (cached == null) throw Exception('Không có dữ liệu offline cho mã trạm $code');
      final related = await local.readItem('station:$code:related');
      if (related is Map) cached['_related'] = Map<String, dynamic>.from(related.map((k, v) => MapEntry(k.toString(), List<Map<String, dynamic>>.from((v as List).map((e) => Map<String, dynamic>.from(e))))));
      return cached;
    }
  }

  Future<void> updateStation(String code, Map<String, dynamic> values) async {
    if (!can('stations.write') && !can('station.update')) throw Exception('Tài khoản không có quyền cập nhật thông tin trạm.');
    final cached = await local.station(code);
    final baseUpdatedAt = cached?['updated_at']?.toString();
    final payload = {...values, 'updated_at': DateTime.now().toUtc().toIso8601String()};
    try {
      // Require a returned row. Without this check an RLS-filtered UPDATE can
      // look successful while nothing is actually written to Supabase.
      final returned = await _withAuthRetry(() async =>
          await client.from('stations').update(payload).eq('code', code).select('code'));
      if (returned.isEmpty) {
        throw Exception('Cloud không cập nhật được trạm $code (0 dòng). Kiểm tra quyền/RLS.');
      }
      await local.updateCachedStation(code, payload);
    } catch (_) {
      await local.updateCachedStation(code, payload);
      await local.enqueue(table: 'stations', operation: 'update', key: code, payload: payload, baseUpdatedAt: baseUpdatedAt);
    }
  }



  Future<List<Map<String, dynamic>>> nearestStations(double latitude, double longitude, {int limit = 4}) async {
    List<Map<String, dynamic>> rows;
    try {
      rows = List<Map<String, dynamic>>.from(await client.from('stations').select('code,name,address,latitude,longitude,status').not('latitude', 'is', null).not('longitude', 'is', null).limit(5000));
      await local.cacheStations(rows);
    } catch (_) {
      rows = await local.allStations();
    }
    const earthRadiusKm = 6371.0088;
    double distanceKm(double lat1, double lon1, double lat2, double lon2) {
      final dLat = (lat2 - lat1) * math.pi / 180.0;
      final dLon = (lon2 - lon1) * math.pi / 180.0;
      final a = math.sin(dLat / 2) * math.sin(dLat / 2) + math.cos(lat1 * math.pi / 180.0) * math.cos(lat2 * math.pi / 180.0) * math.sin(dLon / 2) * math.sin(dLon / 2);
      final c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));
      return earthRadiusKm * c;
    }
    final result = <Map<String, dynamic>>[];
    for (final raw in rows) {
      final lat = double.tryParse((raw['latitude'] ?? '').toString().trim());
      final lon = double.tryParse((raw['longitude'] ?? '').toString().trim());
      if (lat == null || lon == null || lat.abs() > 90 || lon.abs() > 180) continue;
      final item = Map<String, dynamic>.from(raw);
      item['_distance_km'] = distanceKm(latitude, longitude, lat, lon);
      result.add(item);
    }
    result.sort((a, b) => (a['_distance_km'] as double).compareTo(b['_distance_km'] as double));
    return result.take(limit).toList();
  }

  String get currentEmail => (user?.email ?? '').trim().toLowerCase();

  bool get isAdminUser => currentEmail == 'tntsang@gmail.com';

  bool canCreateOwnNotification() => user != null;

  // Notification cache is isolated per authenticated email. This prevents a
  // second user on the same phone from ever inheriting the previous user's
  // locally cached notification list. Cloud/RLS remains the authoritative
  // security boundary; this is an additional local isolation layer.
  String get _notificationCacheKey =>
      'notifications:${currentEmail.isEmpty ? 'anonymous' : currentEmail}';

  bool notificationVisibleToCurrentUser(Map<String, dynamic> row) {
    if (isAdminUser) return true;
    final target = (row['target_email'] ?? '').toString().trim().toLowerCase();
    final creator = (row['created_by_email'] ?? '').toString().trim().toLowerCase();
    // Manual notifications use target_email/created_by_email. Automatic alerts
    // are additionally checked against the current station Email assignment.
    if (target.isNotEmpty) return target == currentEmail;
    // Backward compatibility: a legacy Mobile/PC manual notification may only
    // have created_by_email. It remains private to its creator.
    if (creator.isNotEmpty) return creator == currentEmail;
    return false;
  }

  Future<Set<String>> _currentManagedStationCodes() async {
    if (isAdminUser) return <String>{};
    final codes = <String>{};
    try {
      final rows = await _withAuthRetry(() async =>
          await client.from('stations').select('code').ilike('email', currentEmail).limit(10000));
      for (final row in rows) {
        final code = (row['code'] ?? '').toString().trim().toUpperCase();
        if (code.isNotEmpty) codes.add(code);
      }
    } catch (_) {
      final localRows = await local.allStations();
      for (final row in localRows) {
        final email = (row['email'] ?? '').toString().trim().toLowerCase();
        final code = (row['code'] ?? '').toString().trim().toUpperCase();
        if (email == currentEmail && code.isNotEmpty) codes.add(code);
      }
    }
    return codes;
  }

  bool _notificationVisible(Map<String, dynamic> row, Set<String> managedStationCodes) {
    if (isAdminUser) return true;
    final target = (row['target_email'] ?? '').toString().trim().toLowerCase();
    final creator = (row['created_by_email'] ?? '').toString().trim().toLowerCase();
    final autoKey = (row['auto_alert_key'] ?? '').toString().trim();
    final station = (row['station_code'] ?? '').toString().trim().toUpperCase();
    if (autoKey.isNotEmpty && station.isNotEmpty && managedStationCodes.contains(station)) return true;
    if (target.isNotEmpty) return target == currentEmail;
    return creator.isNotEmpty && creator == currentEmail;
  }

  Future<List<Map<String, dynamic>>> notifications({bool pendingOnly = false, int limit = 100}) async {
    Object? remoteError;
    final managedStationCodes = await _currentManagedStationCodes();
    try {
      // Notifications must be readable even when an older Supabase schema is
      // still installed.  Do not request optional columns explicitly: select(*)
      // lets the Mobile app display existing PC notifications first.
      dynamic raw;
      try {
        raw = await _withAuthRetry(() async {
          var q = client.from('notifications').select('*');
          if (pendingOnly) q = q.eq('done', false);
          return await q.order('notify_date', ascending: false).order('notify_time', ascending: false).limit(limit);
        });
      } catch (e) {
        // Older Cloud schemas may not yet contain newer notification columns.
        // Fall back to the original/basic columns so PC notifications still render.
        if (_isJwtExpired(e)) rethrow;
        raw = await _withAuthRetry(() async {
          var q = client.from('notifications').select('id,title,notify_date,notify_time,content,sound,popup,done,auto_alert_key,station_code,created_at,updated_at');
          if (pendingOnly) q = q.eq('done', false);
          return await q.order('notify_date', ascending: false).order('notify_time', ascending: false).limit(limit);
        });
      }
      var data = List<Map<String, dynamic>>.from(raw).where((r) => r['deleted_at'] == null || r['deleted_at'].toString().isEmpty).where((r) => _notificationVisible(r, managedStationCodes)).toList();
      // Defensive Mobile-side reconciliation: a legacy Cloud can temporarily
      // contain exact logical duplicates with different/empty sync_key values.
      // Collapse those before caching/displaying so the UI cannot amplify the
      // apparent notification count. Keep a row that already has a sync_key.
      final seenLogical = <String, Map<String, dynamic>>{};
      for (final r in data) {
        final auto = (r['auto_alert_key'] ?? '').toString().trim();
        final logical = auto.isNotEmpty
            ? 'AUTO|$auto'
            : 'MANUAL|${(r['notify_date'] ?? '').toString().trim()}|${(r['notify_time'] ?? '').toString().trim()}|${(r['title'] ?? '').toString().trim()}|${(r['content'] ?? '').toString().trim()}|${(r['station_code'] ?? '').toString().trim()}';
        final current = seenLogical[logical];
        if (current == null || ((current['sync_key'] ?? '').toString().trim().isEmpty && (r['sync_key'] ?? '').toString().trim().isNotEmpty)) {
          seenLogical[logical] = r;
        }
      }
      data = seenLogical.values.toList();
      // Keep queued Mobile-originated notifications visible until their write
      // is actually accepted by Cloud. Merge by sync_key; Cloud remains the
      // source of truth for rows already present remotely.
      final cached = await local.readItem(_notificationCacheKey);
      if (cached is List) {
        final cloudKeys = data.map((r) => r['sync_key']?.toString()).whereType<String>().toSet();
        final queued = <Map<String, dynamic>>[];
        for (final rawLocal in cached) {
          final r = Map<String, dynamic>.from(rawLocal);
          // Never re-introduce an unauthorized cached notification after the
          // Cloud/RLS query has already filtered it out. This was the last
          // visibility leak seen by non-admin users in V85.60.9.
          if (!_notificationVisible(r, managedStationCodes)) continue;
          final k = r['sync_key']?.toString();
          if (k != null && k.isNotEmpty && !cloudKeys.contains(k)) queued.add(r);
        }
        data.addAll(queued);
      }
      // Normalize fields expected by the UI without inventing notification rows.
      for (final row in data) {
        row['done'] = row['done'] == true || row['done'] == 1 || row['done'] == '1';
      }
      data.sort((a, b) {
        final ad = '${a['notify_date'] ?? ''} ${a['notify_time'] ?? ''}';
        final bd = '${b['notify_date'] ?? ''} ${b['notify_time'] ?? ''}';
        return bd.compareTo(ad);
      });
      await local.cacheItem(_notificationCacheKey, data);
      return data.take(limit).toList();
    } catch (e) {
      remoteError = e;
      final cached = await local.readItem(_notificationCacheKey);
      final rows = cached is List
          ? List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e))).where((r) => _notificationVisible(r, managedStationCodes)).toList()
          : <Map<String, dynamic>>[];
      if (rows.isNotEmpty) {
        final filtered = pendingOnly ? rows.where((r) => r['done'] != true && r['done'] != 1 && r['done'] != '1').toList() : rows;
        return filtered.take(limit).toList();
      }
      // Propagate the real Cloud/RLS/schema error when there is no offline data.
      throw Exception('Không đọc được Thông báo từ Supabase: $remoteError');
    }
  }

  /// V85.57: Resolve notification identity explicitly instead of relying on
  /// ON CONFLICT(sync_key). The shared schema may use a partial unique index,
  /// which PostgreSQL cannot infer for that conflict target.
  Future<Map<String, dynamic>> _upsertNotificationBySyncKey(Map<String, dynamic> payload) async {
    final key = (payload['sync_key'] ?? '').toString().trim();
    if (key.isEmpty) throw Exception('Notification thiếu sync_key.');
    final existing = await _withAuthRetry(() async =>
        await client.from('notifications').select('*').eq('sync_key', key).limit(1));
    if (existing.isNotEmpty) {
      final result = await _withAuthRetry(() async =>
          await client.from('notifications').update(payload).eq('sync_key', key).select().single());
      return Map<String, dynamic>.from(result);
    }
    try {
      final result = await _withAuthRetry(() async =>
          await client.from('notifications').insert(payload).select().single());
      return Map<String, dynamic>.from(result);
    } catch (e) {
      final again = await _withAuthRetry(() async =>
          await client.from('notifications').select('*').eq('sync_key', key).limit(1));
      if (again.isNotEmpty) {
        final result = await _withAuthRetry(() async =>
            await client.from('notifications').update(payload).eq('sync_key', key).select().single());
        return Map<String, dynamic>.from(result);
      }
      rethrow;
    }
  }

  Future<Map<String, dynamic>> _insertNotificationWithOptionalId(Map<String, dynamic> payload) async {
    final result = await _withAuthRetry(() async =>
        await client.from('notifications').insert(payload).select().single());
    return Map<String, dynamic>.from(result);
  }

  Future<void> addNotification({required DateTime when, required String title, required String content, bool sound = true, bool popup = true, String? stationCode}) async {
    if (!canCreateOwnNotification()) throw Exception('Tài khoản không có quyền tạo thông báo cá nhân.');

    // sync_key is the only cross-device identity for notifications.  Do not
    // depend on the numeric id generated by either PC or Mobile.
    final syncKey = 'MOBILE|${DateTime.now().microsecondsSinceEpoch}';
    final now = DateTime.now().toUtc().toIso8601String();
    final payload = <String, dynamic>{
      'title': title.trim(),
      'notify_date': '${when.year.toString().padLeft(4,'0')}-${when.month.toString().padLeft(2,'0')}-${when.day.toString().padLeft(2,'0')}',
      'notify_time': '${when.hour.toString().padLeft(2,'0')}:${when.minute.toString().padLeft(2,'0')}',
      'content': content.trim(),
      'sound': sound,
      'popup': popup,
      'done': false,
      'station_code': stationCode,
      'target_email': currentEmail,
      'created_by_email': currentEmail,
      'sync_key': syncKey,
      'created_by': client.auth.currentUser?.id,
      'created_at': now,
      'updated_at': now,
    };

    try {
      // Request the representation back.  The previous implementation used
      // upsert() without select(), so a successful INSERT was not cached
      // locally and a later PC sync could not be verified from Mobile.
      Map<String, dynamic> saved;
      try {
        saved = await _upsertNotificationBySyncKey(payload);
      } catch (e) {
        // Self-heal legacy notifications.id identity-sequence collisions.
        final msg = e.toString().toLowerCase();
        if (!(msg.contains('notifications.id') || msg.contains('notifications_pkey'))) rethrow;
        final latest = await _withAuthRetry(() async =>
          await client.from('notifications').select('id').order('id', ascending: false).limit(1));
        final maxId = latest.isNotEmpty ? int.tryParse((latest.first['id'] ?? '0').toString()) ?? 0 : 0;
        saved = await _insertNotificationWithOptionalId({...payload, 'id': maxId + 1});
      }

      // Always cache the exact Cloud representation. This makes the newly
      // created row appear immediately in Mobile and preserves its Cloud id
      // for diagnostics, while sync_key remains the cross-device key.
      final cached = await local.readItem(_notificationCacheKey);
      final rows = cached is List
          ? List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)))
          : <Map<String, dynamic>>[];
      rows.removeWhere((r) => r['sync_key']?.toString() == syncKey);
      rows.insert(0, saved);
      await local.cacheItem(_notificationCacheKey, rows);
    } catch (e) {
      // Offline/RLS/network failures are queued with the REAL sync_key, not a
      // temporary local id. syncPending() can therefore upsert this exact row
      // later and PC can discover it by sync_key.
      final tempId = -DateTime.now().millisecondsSinceEpoch;
      final cached = await local.readItem(_notificationCacheKey);
      final rows = cached is List ? List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e))) : <Map<String, dynamic>>[];
      rows.removeWhere((r) => r['sync_key']?.toString() == syncKey);
      rows.insert(0, {'id': tempId, ...payload});
      await local.cacheItem(_notificationCacheKey, rows);
      await local.enqueue(table: 'notifications', operation: 'insert', key: syncKey, payload: payload);
    }
  }

  Future<void> updateNotification(Map<String, dynamic> row, {required DateTime when, required String title, required String content}) async {
    if (!can('notifications.write') && !can('notification.write')) throw Exception('Tài khoản không có quyền sửa thông báo.');
    final syncKey = row['sync_key']?.toString();
    if (syncKey == null || syncKey.trim().isEmpty) {
      throw Exception('Thông báo thiếu sync_key; cần đồng bộ lại dữ liệu Cloud.');
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final payload = {
      'notify_date': '${when.year.toString().padLeft(4,'0')}-${when.month.toString().padLeft(2,'0')}-${when.day.toString().padLeft(2,'0')}',
      'notify_time': '${when.hour.toString().padLeft(2,'0')}:${when.minute.toString().padLeft(2,'0')}',
      'title': title.trim(), 'content': content.trim(), 'updated_at': now,
    };
    try {
      await _withAuthRetry(() async {
        final result = await client.from('notifications').update(payload).eq('sync_key', syncKey).select('sync_key');
        if (result.isEmpty) throw Exception('Không tìm thấy thông báo trên Cloud với sync_key=$syncKey');
      });
      final cached = await local.readItem(_notificationCacheKey);
      if (cached is List) {
        final rows = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
        for (final r in rows) { if (r['sync_key']?.toString() == syncKey) r.addAll(payload); }
        await local.cacheItem(_notificationCacheKey, rows);
      }
    } catch (_) {
      final cached = await local.readItem(_notificationCacheKey);
      if (cached is List) {
        final rows = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
        for (final r in rows) { if (r['sync_key']?.toString() == syncKey) r.addAll(payload); }
        await local.cacheItem(_notificationCacheKey, rows);
      }
      await local.enqueue(table: 'notifications', operation: 'update', key: syncKey, payload: payload);
    }
  }

  Future<void> completeNotification(Map<String, dynamic> row, bool done) async {
    final syncKey = row['sync_key']?.toString();
    if (syncKey == null || syncKey.trim().isEmpty) {
      throw Exception('Thông báo thiếu sync_key; cần đồng bộ lại dữ liệu Cloud.');
    }
    final payload = {'done': done, 'updated_at': DateTime.now().toUtc().toIso8601String()};
    try {
      await _withAuthRetry(() async {
        final result = await client.from('notifications').update(payload).eq('sync_key', syncKey).select('sync_key');
        if (result.isEmpty) throw Exception('Không tìm thấy thông báo trên Cloud với sync_key=$syncKey');
      });
      final cached = await local.readItem(_notificationCacheKey);
      if (cached is List) {
        final rows = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
        for (final r in rows) { if (r['sync_key']?.toString() == syncKey) r.addAll(payload); }
        await local.cacheItem(_notificationCacheKey, rows);
      }
    } catch (_) {
      final cached = await local.readItem(_notificationCacheKey);
      if (cached is List) {
        final rows = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
        for (final r in rows) { if (r['sync_key']?.toString() == syncKey) r.addAll(payload); }
        await local.cacheItem(_notificationCacheKey, rows);
      }
      await local.enqueue(table: 'notifications', operation: 'update', key: syncKey, payload: payload);
    }
  }

  Future<void> deleteNotification(Map<String, dynamic> row) async {
    if (!can('notifications.write') && !can('notification.write')) throw Exception('Tài khoản không có quyền xóa thông báo.');
    final syncKey = row['sync_key']?.toString();
    if (syncKey == null || syncKey.trim().isEmpty) {
      throw Exception('Thông báo thiếu sync_key; cần đồng bộ lại dữ liệu Cloud.');
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final payload = {'done': true, 'deleted_at': now, 'updated_at': now};
    try {
      await _withAuthRetry(() async {
        final result = await client.from('notifications').update(payload).eq('sync_key', syncKey).select('sync_key');
        if (result.isEmpty) throw Exception('Không tìm thấy thông báo trên Cloud với sync_key=$syncKey');
      });
      final cached = await local.readItem(_notificationCacheKey);
      if (cached is List) {
        final rows = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
        rows.removeWhere((r) => r['sync_key']?.toString() == syncKey);
        await local.cacheItem(_notificationCacheKey, rows);
      }
    } catch (_) {
      final cached = await local.readItem(_notificationCacheKey);
      if (cached is List) {
        final rows = List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)));
        rows.removeWhere((r) => r['sync_key']?.toString() == syncKey);
        await local.cacheItem(_notificationCacheKey, rows);
      }
      await local.enqueue(table: 'notifications', operation: 'delete', key: syncKey, payload: payload);
    }
  }

  Future<SyncReport> _syncPendingInternal() async {
    if (!network.online) return SyncReport(online: false);
    int synced = 0, conflicts = 0, failed = 0;
    for (final item in await local.queue()) {
      final id = item['id'] as int;
      final table = item['table_name'].toString();
      final op = item['operation'].toString();
      final key = item['row_key'].toString();
      final payload = Map<String, dynamic>.from(jsonDecode(item['payload'] as String));
      try {
        if (table == 'stations' && op == 'update') {
          final rows = await client.from('stations').select().eq('code', key).limit(1);
          final remote = rows.isEmpty ? <String, dynamic>{} : Map<String, dynamic>.from(rows.first);
          final base = item['base_updated_at']?.toString();
          final remoteUpdated = remote['updated_at']?.toString();
          if (base != null && remoteUpdated != null && base != remoteUpdated) {
            await local.addConflict(table: table, key: key, localPayload: payload, remotePayload: remote);
            await local.removeQueue(id);
            conflicts++;
            continue;
          }
          final returned = await _retryCloud(() async =>
              await client.from('stations').update(payload).eq('code', key).select('code'));
          if (returned.isEmpty) throw Exception('Cloud không cập nhật được trạm $key (0 dòng).');
          await local.removeQueue(id);
          synced++;
        } else if (table == 'notifications' && op == 'insert') {
          Map<String, dynamic> saved;
          try {
            saved = await _upsertNotificationBySyncKey(payload);
          } catch (e) {
            // Recover the legacy PostgreSQL identity-sequence collision in the
            // queued/offline path too. Never use the local negative id.
            final msg = e.toString().toLowerCase();
            if (!(msg.contains('notifications.id') || msg.contains('notifications_pkey'))) rethrow;
            final latest = await _withAuthRetry(() async =>
                await client.from('notifications').select('id').order('id', ascending: false).limit(1));
            final maxId = latest.isNotEmpty ? int.tryParse((latest.first['id'] ?? '0').toString()) ?? 0 : 0;
            saved = await _insertNotificationWithOptionalId({...payload, 'id': maxId + 1});
          }
          final cached = await local.readItem(_notificationCacheKey);
          final rows = cached is List
              ? List<Map<String, dynamic>>.from(cached.map((e) => Map<String, dynamic>.from(e)))
              : <Map<String, dynamic>>[];
          rows.removeWhere((r) => r['sync_key']?.toString() == key);
          rows.insert(0, Map<String, dynamic>.from(saved));
          await local.cacheItem(_notificationCacheKey, rows);
          await local.removeQueue(id);
          synced++;
        } else if (table == 'notifications' && op == 'update') {
          await _withAuthRetry(() async {
            final result = await client.from('notifications').update(payload).eq('sync_key', key).select('sync_key');
            if (result.isEmpty) throw Exception('Không tìm thấy thông báo trên Cloud với sync_key=$key');
          });
          await local.removeQueue(id);
          synced++;
        } else if (table == 'notifications' && op == 'delete') {
          await _withAuthRetry(() async {
            final result = await client.from('notifications').update(payload).eq('sync_key', key).select('sync_key');
            if (result.isEmpty) throw Exception('Không tìm thấy thông báo trên Cloud với sync_key=$key');
          });
          await local.removeQueue(id);
          synced++;
        } else if (op == 'update' && tablePrimaryKey.containsKey(table)) {
          // Generic table update; primary key name is resolved from table.
          final pk = tablePrimaryKey[table];
          if (pk == null) throw Exception('Unknown sync table: $table');
          final rows = await client.from(table).select().eq(pk, key).limit(1);
          final remote = rows.isEmpty ? <String, dynamic>{} : Map<String, dynamic>.from(rows.first);
          final base = item['base_updated_at']?.toString();
          final remoteUpdated = remote['updated_at']?.toString();
          if (base != null && remoteUpdated != null && base != remoteUpdated) {
            await local.addConflict(table: table, key: key, localPayload: payload, remotePayload: remote);
            await local.removeQueue(id); conflicts++; continue;
          }
          final returned = await _retryCloud(() async =>
              await client.from(table).update(payload).eq(pk, key).select(pk));
          if (returned.isEmpty) throw Exception('Cloud không cập nhật được $table/$key (0 dòng).');
          await local.removeQueue(id); synced++;
        } else {
          await local.removeQueue(id);
        }
      } catch (_) {
        failed++;
      }
    }
    await local.cacheItem('last_sync_report', {
      'at': DateTime.now().toUtc().toIso8601String(),
      'synced': synced, 'conflicts': conflicts, 'failed': failed,
      'pending_after': await local.pendingCount(),
    });
    return SyncReport(online: true, synced: synced, conflicts: conflicts, failed: failed);
  }

  Future<int> pendingSyncCount() => local.pendingCount();
  Future<int> conflictCount() => local.conflictCount();
}

class SyncReport {
  final bool online;
  final int synced;
  final int conflicts;
  final int failed;
  const SyncReport({required this.online, this.synced = 0, this.conflicts = 0, this.failed = 0});
}
