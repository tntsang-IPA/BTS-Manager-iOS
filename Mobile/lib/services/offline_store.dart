import 'dart:convert';
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

class OfflineStore {
  OfflineStore._();
  static final OfflineStore instance = OfflineStore._();
  Database? _db;

  Future<void> init() async {
    if (_db != null) return;
    final dbPath = p.join(await getDatabasesPath(), 'bts_manager_mobile_v83.db');
    _db = await openDatabase(dbPath, version: 1, onCreate: (db, version) async {
      await db.execute('''CREATE TABLE stations (
        code TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT
      )''');
      await db.execute('''CREATE TABLE cache_items (
        name TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT
      )''');
      await db.execute('''CREATE TABLE sync_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT NOT NULL, operation TEXT NOT NULL, row_key TEXT NOT NULL,
        payload TEXT NOT NULL, base_updated_at TEXT, created_at TEXT NOT NULL
      )''');
      await db.execute('''CREATE TABLE conflicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_name TEXT NOT NULL, row_key TEXT NOT NULL,
        local_payload TEXT NOT NULL, remote_payload TEXT NOT NULL,
        created_at TEXT NOT NULL, resolved INTEGER NOT NULL DEFAULT 0
      )''');
    });
  }

  Database get db => _db!;

  Future<void> cacheStations(List<Map<String, dynamic>> rows) async {
    if (rows.isEmpty) return;
    final batch = db.batch();
    for (final row in rows) {
      final code = (row['code'] ?? '').toString().trim();
      if (code.isEmpty) continue;
      batch.insert('stations', {
        'code': code,
        'data': jsonEncode(row),
        'updated_at': row['updated_at']?.toString(),
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await batch.commit(noResult: true);
  }

  Future<List<Map<String, dynamic>>> allStations() async {
    final rows = await db.query('stations');
    return rows.map((r) => Map<String, dynamic>.from(jsonDecode(r['data'] as String))).toList();
  }

  Future<Map<String, dynamic>?> station(String code) async {
    final rows = await db.query('stations', where: 'code = ?', whereArgs: [code], limit: 1);
    if (rows.isEmpty) return null;
    return Map<String, dynamic>.from(jsonDecode(rows.first['data'] as String));
  }

  Future<void> cacheItem(String name, dynamic data, {String? updatedAt}) async {
    await db.insert('cache_items', {
      'name': name,
      'data': jsonEncode(data),
      'updated_at': updatedAt,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<dynamic> readItem(String name) async {
    final rows = await db.query('cache_items', where: 'name = ?', whereArgs: [name], limit: 1);
    if (rows.isEmpty) return null;
    return jsonDecode(rows.first['data'] as String);
  }

  Future<void> updateCachedStation(String code, Map<String, dynamic> values) async {
    final current = await station(code) ?? {'code': code};
    current.addAll(values);
    current['code'] = code;
    current['updated_at'] = DateTime.now().toUtc().toIso8601String();
    await cacheStations([current]);
  }

  Future<int> enqueue({required String table, required String operation, required String key, required Map<String, dynamic> payload, String? baseUpdatedAt}) async {
    return db.insert('sync_queue', {
      'table_name': table,
      'operation': operation,
      'row_key': key,
      'payload': jsonEncode(payload),
      'base_updated_at': baseUpdatedAt,
      'created_at': DateTime.now().toUtc().toIso8601String(),
    });
  }

  Future<List<Map<String, dynamic>>> queue() => db.query('sync_queue', orderBy: 'id ASC');

  Future<void> removeQueue(int id) async => db.delete('sync_queue', where: 'id = ?', whereArgs: [id]);

  /// Test-only reset for V85.52: remove Mobile-local notification cache and
  /// any queued notification writes, without touching Cloud/Supabase.
  Future<void> resetLocalNotificationsForBootstrap() async {
    await db.delete('cache_items', where: 'name = ?', whereArgs: ['notifications']);
    await db.delete('sync_queue', where: 'table_name = ?', whereArgs: ['notifications']);
  }

  Future<int> pendingCount() async {
    final result = await db.rawQuery('SELECT COUNT(*) AS c FROM sync_queue');
    return Sqflite.firstIntValue(result) ?? 0;
  }

  Future<void> addConflict({required String table, required String key, required Map<String, dynamic> localPayload, required Map<String, dynamic> remotePayload}) async {
    await db.insert('conflicts', {
      'table_name': table,
      'row_key': key,
      'local_payload': jsonEncode(localPayload),
      'remote_payload': jsonEncode(remotePayload),
      'created_at': DateTime.now().toUtc().toIso8601String(),
      'resolved': 0,
    });
  }

  Future<int> conflictCount() async {
    final result = await db.rawQuery('SELECT COUNT(*) AS c FROM conflicts WHERE resolved = 0');
    return Sqflite.firstIntValue(result) ?? 0;
  }
}
