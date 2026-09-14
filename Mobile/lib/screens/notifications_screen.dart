import 'dart:async';
import 'package:flutter/material.dart';
import '../services/cloud_service.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});
  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  final cloud = CloudService();
  List<Map<String, dynamic>> rows = [];
  bool loading = true;
  String? error;
  Timer? _refreshTimer;

  DateTime? fromDate;
  DateTime? toDate;
  String statusFilter = 'Tất cả';
  String search = '';
  final searchController = TextEditingController();
  int page = 0;
  int pageSize = 20;

  @override
  void initState() {
    super.initState();
    load();
    _refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) => load(silent: true));
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    searchController.dispose();
    super.dispose();
  }

  Future<void> load({bool silent = false}) async {
    if (!silent) setState(() { loading = true; error = null; });
    try {
      // Always flush Mobile -> Cloud pending notification changes before reading
      // Cloud. This makes edits/completion/deletion from this screen immediately
      // visible on PC without requiring a trip through the Home screen.
      final report = await cloud.syncPending();
      final data = await cloud.notifications(limit: 500);
      if (mounted) {
        setState(() {
          rows = data;
          page = 0;
          error = report.failed > 0
              ? 'Còn ${report.failed} thay đổi thông báo chưa đồng bộ Cloud.'
              : null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  List<Map<String, dynamic>> get filteredRows {
    final q = search.trim().toLowerCase();
    final out = rows.where((r) {
      final dt = _rowDate(r);
      if (fromDate != null && dt != null && _dateOnly(dt).isBefore(_dateOnly(fromDate!))) return false;
      if (toDate != null && dt != null && _dateOnly(dt).isAfter(_dateOnly(toDate!))) return false;
      if (statusFilter != 'Tất cả' && _status(r) != statusFilter) return false;
      if (q.isNotEmpty) {
        final hay = [r['title'], r['content']].map((v) => (v ?? '').toString().toLowerCase()).join(' ');
        if (!hay.contains(q)) return false;
      }
      return true;
    }).toList();
    out.sort((a, b) => (_rowDate(b) ?? DateTime(1900)).compareTo(_rowDate(a) ?? DateTime(1900)));
    return out;
  }

  List<Map<String, dynamic>> get pageRows {
    final all = filteredRows;
    final start = page * pageSize;
    if (start >= all.length) return const [];
    final end = (start + pageSize).clamp(0, all.length);
    return all.sublist(start, end);
  }

  Future<void> pickDate({required bool from}) async {
    final base = from
        ? (fromDate ?? DateTime.now())
        : (toDate ?? fromDate ?? DateTime.now());
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime(base.year, base.month, base.day),
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
      helpText: from ? 'Chọn Từ ngày' : 'Chọn Đến ngày',
    );
    if (picked == null || !mounted) return;
    if (from && toDate != null && picked.isAfter(_dateOnly(toDate!))) {
      _message('Từ ngày không được lớn hơn Đến ngày.');
      return;
    }
    if (!from && fromDate != null && picked.isBefore(_dateOnly(fromDate!))) {
      _message('Đến ngày không được nhỏ hơn Từ ngày.');
      return;
    }
    setState(() {
      if (from) {
        fromDate = _dateOnly(picked);
      } else {
        toDate = _dateOnly(picked);
      }
      page = 0;
    });
  }

  Future<DateTime?> _pickNotificationDateTime(BuildContext dialogContext, DateTime current) async {
    final date = await showDatePicker(
      context: dialogContext,
      initialDate: DateTime(current.year, current.month, current.day),
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
      helpText: 'Chọn ngày thông báo',
    );
    if (date == null) return null;
    final time = await showTimePicker(
      context: dialogContext,
      initialTime: TimeOfDay.fromDateTime(current),
      helpText: 'Chọn giờ thông báo',
    );
    if (time == null) return null;
    return DateTime(date.year, date.month, date.day, time.hour, time.minute);
  }

  Future<void> add() async {
    if (!cloud.canCreateOwnNotification()) {
      _message('Tài khoản không có quyền tạo thông báo cá nhân.');
      return;
    }
    final title = TextEditingController();
    final content = TextEditingController();
    final station = TextEditingController();
    DateTime when = DateTime.now().add(const Duration(minutes: 10));

    final ok = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Tạo mới thông báo'),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                TextField(controller: title, decoration: const InputDecoration(labelText: 'Tiêu đề')),
                const SizedBox(height: 10),
                TextField(controller: content, maxLines: 4, decoration: const InputDecoration(labelText: 'Nội dung')),
                const SizedBox(height: 10),
                TextField(controller: station, decoration: const InputDecoration(labelText: 'Mã trạm (không bắt buộc)')),
                const SizedBox(height: 8),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Thời gian thông báo'),
                  subtitle: Text(_formatDateTime(when)),
                  trailing: const Icon(Icons.calendar_month_outlined),
                  onTap: () async {
                    final picked = await _pickNotificationDateTime(dialogContext, when);
                    if (picked != null) setDialogState(() => when = picked);
                  },
                ),
              ]),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('HỦY')),
            FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('LƯU')),
          ],
        ),
      ),
    );
    final titleText = title.text.trim();
    final contentText = content.text.trim();
    final stationText = station.text.trim();
    title.dispose(); content.dispose(); station.dispose();
    if (ok != true) return;
    if (titleText.isEmpty || contentText.isEmpty) { _message('Vui lòng nhập tiêu đề và nội dung.'); return; }
    try {
      await cloud.addNotification(when: when, title: titleText, content: contentText, sound: false, popup: false, stationCode: stationText.isEmpty ? null : stationText);
      await load();
      _message('Đã tạo thông báo.');
    } catch (e) { _message(e.toString()); }
  }

  Future<void> _edit(Map<String, dynamic> row) async {
    if (!cloud.can('notifications.write') && !cloud.can('notification.write')) {
      _message('Tài khoản không có quyền sửa thông báo.');
      return;
    }
    final title = TextEditingController(text: '${row['title'] ?? ''}');
    final content = TextEditingController(text: '${row['content'] ?? ''}');
    DateTime when = _rowDate(row) ?? DateTime.now();
    final ok = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(builder: (context, setDialogState) => AlertDialog(
        title: const Text('Sửa thông báo'),
        content: SizedBox(width: 520, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: title, decoration: const InputDecoration(labelText: 'Tiêu đề')),
          const SizedBox(height: 10),
          TextField(controller: content, maxLines: 4, decoration: const InputDecoration(labelText: 'Nội dung')),
          const SizedBox(height: 10),
          ListTile(contentPadding: EdgeInsets.zero, title: const Text('Thời gian thông báo'), subtitle: Text(_formatDateTime(when)), trailing: const Icon(Icons.calendar_month_outlined), onTap: () async {
            final picked = await _pickNotificationDateTime(dialogContext, when);
            if (picked != null) setDialogState(() => when = picked);
          }),
        ]))),
        actions: [TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('HỦY')), FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('LƯU'))],
      )),
    );
    final titleText = title.text.trim(); final contentText = content.text.trim();
    title.dispose(); content.dispose();
    if (ok != true) return;
    if (titleText.isEmpty || contentText.isEmpty) { _message('Vui lòng nhập tiêu đề và nội dung.'); return; }
    try {
      await cloud.updateNotification(row, when: when, title: titleText, content: contentText);
      await load();
      _message('Đã cập nhật thông báo.');
    } catch (e) { _message(e.toString()); }
  }

  Future<void> _action(String action, Map<String, dynamic> row) async {
    try {
      final done = row['done'] == true;
      if (action == 'done') await cloud.completeNotification(row, !done);
      if (action == 'delete') await cloud.deleteNotification(row);
      // Direct write may succeed; queued/offline writes are retried immediately.
      await cloud.syncPending();
      await load(silent: true);
    } catch (e) { _message(e.toString()); }
  }

  void _message(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  DateTime? _rowDate(Map<String, dynamic> r) {
    final raw = r['created_at']?.toString();
    if (raw != null && raw.isNotEmpty) {
      final parsed = DateTime.tryParse(raw);
      if (parsed != null) return parsed.toLocal();
    }
    final d = r['notify_date']?.toString() ?? '';
    final t = r['notify_time']?.toString() ?? '00:00';
    return DateTime.tryParse('${d}T$t');
  }

  DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

  String _type(Map<String, dynamic> r) {
    final raw = '${r['type'] ?? r['notification_type'] ?? r['category'] ?? r['auto_alert_key'] ?? ''}'.toUpperCase();
    final title = '${r['title'] ?? ''}'.toUpperCase();
    if (raw.contains('HOP') || raw.contains('CONTRACT') || title.contains('HỢP ĐỒNG')) return 'Hợp đồng';
    if (raw.contains('BTBD') || title.contains('BTBD')) return 'BTBD';
    if (raw.contains('SỰ CỐ') || raw.contains('INCIDENT')) return 'Sự cố';
    if (raw.contains('MLL')) return 'Mất liên lạc';
    return 'Chung';
  }

  String _priority(Map<String, dynamic> r) {
    final raw = '${r['priority'] ?? r['muc_do'] ?? r['level'] ?? ''}'.toLowerCase();
    if (raw.contains('cao') || raw == 'high' || raw == '3') return 'Cao';
    if (raw.contains('thấp') || raw == 'low' || raw == '1') return 'Thấp';
    if (raw.contains('tb') || raw.contains('trung') || raw == 'medium' || raw == '2') return 'TB';
    final t = _type(r);
    return (t == 'Hợp đồng' || t == 'BTBD' || t == 'Mất liên lạc') ? 'Cao' : 'Thấp';
  }

  String _status(Map<String, dynamic> r) => r['done'] == true || r['done'] == 1 || r['done'] == '1' ? 'Đã thông báo' : 'Chưa thông báo';

  bool _canDelete(Map<String, dynamic> r) {
    final title = '${r['title'] ?? ''}'.trim().toUpperCase();
    // BTBD and HỢP ĐỒNG alerts are system-generated; keep them and do not expose delete.
    if (title.contains('BTBD') || title.contains('HỢP ĐỒNG') || title.contains('HOP DONG')) return false;
    return cloud.can('notifications.write') || cloud.can('notification.write');
  }

  String _dateText(Map<String, dynamic> r) {
    final d = _rowDate(r);
    if (d == null) return '-';
    return '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}/${d.year}\n${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  }

  String _formatDateTime(DateTime value) => '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year} ${value.hour.toString().padLeft(2, '0')}:${value.minute.toString().padLeft(2, '0')}';

  Widget _dateButton(String label, DateTime? value, VoidCallback onTap) {
    return SizedBox(
      height: 56,
      child: Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(6),
        child: InkWell(
          borderRadius: BorderRadius.circular(6),
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey.shade300),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(label, style: TextStyle(fontSize: 11, color: Colors.grey.shade700)),
                      const SizedBox(height: 2),
                      Text(
                        value == null ? 'Chọn ngày' : '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year}',
                        style: const TextStyle(fontSize: 14),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.calendar_month_outlined, size: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _filterBox(String label, String value, List<String> items, ValueChanged<String?> onChanged) {
    return DropdownButtonFormField<String>(
      value: value,
      isDense: true,
      decoration: InputDecoration(labelText: label, border: const OutlineInputBorder(), contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8), filled: true, fillColor: Colors.white),
      items: items.map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
      onChanged: onChanged,
    );
  }

  Widget _priorityBadge(String p) {
    final bg = p == 'Cao' ? Colors.red : p == 'TB' ? Colors.amber.shade100 : Colors.green.shade100;
    final fg = p == 'Cao' ? Colors.white : p == 'TB' ? Colors.orange.shade900 : Colors.green.shade800;
    return Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4), decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(4)), child: Text(p, style: TextStyle(fontWeight: FontWeight.w700, color: fg, fontSize: 12)));
  }

  Widget _statusBadge(String s) {
    final sent = s == 'Đã thông báo';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: sent ? Colors.green.shade50 : Colors.blue.shade50,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: sent ? Colors.green.shade300 : Colors.blue.shade300),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(sent ? Icons.notifications_active : Icons.notifications_none_outlined, size: 18, color: sent ? Colors.green.shade700 : Colors.blue.shade700),
        const SizedBox(width: 5),
        Text(s, style: TextStyle(fontWeight: FontWeight.w700, color: sent ? Colors.green.shade700 : Colors.blue.shade700, fontSize: 12)),
      ]),
    );
  }

  Widget _typeCell(String type) {
    final icon = type == 'Hợp đồng' ? Icons.warning_amber_rounded : type == 'BTBD' ? Icons.warning_amber : type == 'Sự cố' ? Icons.block : type == 'Mất liên lạc' ? Icons.wifi_off : Icons.check_circle;
    final color = type == 'Chung' ? Colors.green : type == 'Sự cố' ? Colors.red : type == 'Hợp đồng' || type == 'BTBD' || type == 'Mất liên lạc' ? Colors.orange : Colors.blue;
    return Row(mainAxisSize: MainAxisSize.min, children: [Icon(icon, size: 22, color: color), const SizedBox(width: 6), Text(type)]);
  }

  void _showDetail(Map<String, dynamic> row) {
    showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: Row(children: [
          const Icon(Icons.notifications_outlined),
          const SizedBox(width: 8),
          Expanded(child: Text('${row['title'] ?? 'Thông báo'}')),
          IconButton(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close)),
        ]),
        content: SizedBox(width: 520, child: SingleChildScrollView(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _detail('Thời gian', _dateText(row).replaceAll('\n', ' ')),
          _detail('Tiêu đề', '${row['title'] ?? 'Thông báo'}'),
          _detail('Nội dung', '${row['content'] ?? ''}'),
          _detail('Trạng thái', _status(row)),
        ]))),
        actions: [
          if (row['auto_alert_key'] != null && '${row['auto_alert_key']}'.trim().isNotEmpty)
            Row(mainAxisSize: MainAxisSize.min, children: [
              Checkbox(value: row['done'] == true || row['done'] == 1 || row['done'] == '1', onChanged: (v) { Navigator.pop(context); _action('done', row); }),
              const Text('Hoàn thành'),
            ]),
          OutlinedButton(onPressed: () => Navigator.pop(context), child: const Text('Đóng')),
        ],
      ),
    );
  }

  Widget _detail(String label, String value) => Padding(padding: const EdgeInsets.only(bottom: 10), child: RichText(text: TextSpan(style: DefaultTextStyle.of(context).style, children: [TextSpan(text: '$label: ', style: const TextStyle(fontWeight: FontWeight.w700)), TextSpan(text: value)])));

  @override
  Widget build(BuildContext context) {
    final total = filteredRows.length;
    final totalPages = total == 0 ? 1 : (total / pageSize).ceil();
    if (page >= totalPages) page = totalPages - 1;

    return Scaffold(
      backgroundColor: const Color(0xfff5f7fb),
      appBar: AppBar(
        title: const Text('Thông báo'),
        actions: [
          IconButton(onPressed: () async {
            try {
              final report = await cloud.syncPending();
              await load();
              if (mounted && report.failed > 0) {
                _message('Đồng bộ chưa hoàn tất: còn ${report.failed} thay đổi chờ xử lý.');
              }
            } catch (e) {
              _message(e.toString());
            }
          }, tooltip: 'Đồng bộ Cloud', icon: const Icon(Icons.cloud_sync_outlined)),
          IconButton(onPressed: () => load(), tooltip: 'Làm mới', icon: const Icon(Icons.refresh)),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? Center(child: Padding(padding: const EdgeInsets.all(20), child: Text(error!)))
              : RefreshIndicator(
                  onRefresh: load,
                  child: ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(12, 12, 12, 90),
                    children: [
                      _filters(),
                      const SizedBox(height: 10),
                      _table(total),
                      const SizedBox(height: 8),
                      _pagination(totalPages),
                      const SizedBox(height: 12),
                      _legend(),
                    ],
                  ),
                ),
    );
  }

  Widget _filters() {
    return Card(
      margin: EdgeInsets.zero,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: BorderSide(color: Colors.grey.shade300)),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: LayoutBuilder(builder: (context, c) {
          final wide = c.maxWidth >= 800;
          final children = [
            SizedBox(width: wide ? 190 : 160, child: _dateButton('Từ ngày', fromDate, () => pickDate(from: true))),
            SizedBox(width: wide ? 190 : 160, child: _dateButton('Đến ngày', toDate, () => pickDate(from: false))),
            SizedBox(width: 170, child: _filterBox('Trạng thái', statusFilter, const ['Tất cả', 'Chưa thông báo', 'Đã thông báo'], (v) => setState(() { statusFilter = v!; page = 0; }))),
            SizedBox(width: wide ? 300 : 240, child: TextField(controller: searchController, onChanged: (v) => setState(() { search = v; page = 0; }), decoration: const InputDecoration(labelText: 'Tìm kiếm', hintText: 'Tiêu đề, nội dung...', prefixIcon: Icon(Icons.search), border: OutlineInputBorder(), filled: true, fillColor: Colors.white))),
            SizedBox(width: 118, height: 48, child: OutlinedButton.icon(onPressed: add, icon: const Icon(Icons.add, size: 20), label: const Text('Tạo mới'), style: OutlinedButton.styleFrom(foregroundColor: const Color(0xff075da8), side: const BorderSide(color: Color(0xff075da8)), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6))))),
          ];
          return SingleChildScrollView(scrollDirection: Axis.horizontal, child: Row(children: children.map((w) => Padding(padding: const EdgeInsets.only(right: 8), child: w)).toList()));
        }),
      ),
    );
  }

  Widget _table(int total) {
    if (total == 0) {
      return Card(child: Padding(padding: const EdgeInsets.all(30), child: Center(child: Text('Không có thông báo phù hợp với bộ lọc.'))));
    }
    return Card(
      margin: EdgeInsets.zero,
      elevation: 0,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: BorderSide(color: Colors.grey.shade300)),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          headingRowColor: WidgetStatePropertyAll(const Color(0xff075da8)),
          headingTextStyle: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
          dataRowMinHeight: 66,
          dataRowMaxHeight: 96,
          columnSpacing: 20,
          horizontalMargin: 12,
          border: TableBorder.all(color: const Color(0xffd9e1ea), width: 0.7),
          columns: const [
            DataColumn(label: Text('STT')),
            DataColumn(label: Text('Thời gian ↓')),
            DataColumn(label: Text('Tiêu đề')),
            DataColumn(label: Text('Nội dung')),
            DataColumn(label: Text('Trạng thái')),
            DataColumn(label: Text('Chức năng')),
          ],
          rows: List.generate(pageRows.length, (index) {
            final row = pageRows[index];
            final created = _rowDate(row);
            final title = '${row['title'] ?? 'Thông báo'}';
            final content = '${row['content'] ?? ''}';
            final creator = '${row['created_by_name'] ?? row['user_name'] ?? row['created_by'] ?? 'admin'}';
            final isAuto = row['auto_alert_key'] != null && '${row['auto_alert_key']}'.trim().isNotEmpty;
            return DataRow(
                cells: [
                DataCell(Center(child: Text('${page * pageSize + index + 1}'))),
                DataCell(Text(_dateText(row), textAlign: TextAlign.center)),
                DataCell(SizedBox(width: 170, child: Text(title, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)))),
                DataCell(SizedBox(width: 330, child: Text(content, maxLines: 3, overflow: TextOverflow.ellipsis))),
                DataCell(_statusBadge(_status(row))),
                DataCell(Row(mainAxisSize: MainAxisSize.min, children: [
                  IconButton(tooltip: 'Xem', onPressed: () => _showDetail(row), icon: const Icon(Icons.visibility_outlined)),
                  if (cloud.can('notifications.write') || cloud.can('notification.write'))
                    IconButton(tooltip: 'Sửa', onPressed: () => _edit(row), icon: const Icon(Icons.edit_outlined)),
                  if (cloud.can('notifications.write') || cloud.can('notification.write'))
                    Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                      Checkbox(
                        value: row['done'] == true || row['done'] == 1 || row['done'] == '1',
                        onChanged: (_) => _action('done', row),
                        visualDensity: VisualDensity.compact,
                      ),
                      Text(
                        row['done'] == true || row['done'] == 1 || row['done'] == '1' ? 'Hoàn thành' : 'Chưa hoàn thành',
                        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
                      ),
                    ]),
                  if (_canDelete(row))
                    IconButton(tooltip: 'Xóa', onPressed: () => _action('delete', row), icon: const Icon(Icons.delete_outline, color: Colors.red)),
                ])),
              ],
            );
          }),
        ),
      ),
    );
  }

  Widget _pagination(int totalPages) {
    return Row(children: [
      Text('Tổng số: ${filteredRows.length} thông báo', style: const TextStyle(fontWeight: FontWeight.w600)),
      const Spacer(),
      IconButton(onPressed: page > 0 ? () => setState(() => page = 0) : null, icon: const Icon(Icons.first_page)),
      IconButton(onPressed: page > 0 ? () => setState(() => page--) : null, icon: const Icon(Icons.chevron_left)),
      Container(width: 40, height: 38, alignment: Alignment.center, decoration: BoxDecoration(color: const Color(0xff075da8), borderRadius: BorderRadius.circular(4)), child: Text('${page + 1}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold))),
      IconButton(onPressed: page + 1 < totalPages ? () => setState(() => page++) : null, icon: const Icon(Icons.chevron_right)),
      IconButton(onPressed: page + 1 < totalPages ? () => setState(() => page = totalPages - 1) : null, icon: const Icon(Icons.last_page)),
      const SizedBox(width: 12),
      SizedBox(width: 78, child: DropdownButtonFormField<int>(value: pageSize, isDense: true, decoration: const InputDecoration(border: OutlineInputBorder(), contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 6)), items: const [20, 50, 100].map((e) => DropdownMenuItem(value: e, child: Text('$e'))).toList(), onChanged: (v) => setState(() { pageSize = v!; page = 0; }))),
    ]);
  }

  Widget _legend() {
    return Card(
      margin: EdgeInsets.zero, elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: BorderSide(color: Colors.grey.shade300)),
      child: Padding(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10), child: Wrap(spacing: 20, runSpacing: 8, children: [
        _legendItem(Icons.notifications_active, Colors.green, 'Đã thông báo'),
        _legendItem(Icons.notifications_none_outlined, Colors.blue, 'Chưa thông báo'),
      ])),
    );
  }

  Widget _legendItem(IconData icon, Color color, String text) => Row(mainAxisSize: MainAxisSize.min, children: [Icon(icon, size: 22, color: color), const SizedBox(width: 5), Text(text)]);
}
