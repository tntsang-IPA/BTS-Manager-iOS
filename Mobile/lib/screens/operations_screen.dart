import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'dart:math' as math;
import '../services/cloud_service.dart';

class OperationsScreen extends StatelessWidget {
  const OperationsScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Vận hành hiện trường')),
        body: const StationUpdateScreen(),
      );
}

class StationUpdateScreen extends StatefulWidget {
  const StationUpdateScreen({super.key});

  @override
  State<StationUpdateScreen> createState() => _StationUpdateScreenState();
}

class _StationUpdateScreenState extends State<StationUpdateScreen> {
  final cloud = CloudService();
  List<String> codes = [];
  String? selectedCode;
  String? selectedSheet;
  bool loading = true;
  bool finding = false;
  String? error;

  @override
  void initState() {
    super.initState();
    _loadCodes();
  }

  Future<void> _loadCodes() async {
    try {
      // Flush previously failed operational edits before loading stations.
      final report = await cloud.syncPending();
      if (report.failed > 0 && mounted) {
        setState(() => error = 'Còn ${report.failed} thay đổi vận hành chưa đồng bộ Cloud.');
      }
      final result = await cloud.stationCodes();
      if (!mounted) return;
      setState(() {
        codes = result;
        selectedCode = result.isNotEmpty ? result.first : null;
        selectedSheet = CloudService.editableSheets.first;
        loading = false;
      });
    } catch (e) {
      if (mounted) setState(() { loading = false; error = e.toString(); });
    }
  }

  Future<void> _find() async {
    if (selectedCode == null || selectedSheet == null) return;
    setState(() { finding = true; error = null; });
    try {
      final rows = await cloud.findSheetRows(selectedSheet!, selectedCode!);
      if (!mounted) return;
      if (rows.isEmpty) {
        _message('Không tìm thấy dữ liệu của mã trạm ${selectedCode!} trong sheet ${selectedSheet!}.');
        return;
      }
      final changed = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (_) => SheetEditDialog(
          sheet: selectedSheet!,
          stationCode: selectedCode!,
          rows: rows,
          cloud: cloud,
        ),
      );
      if (changed == true && mounted) {
        final report = await cloud.syncPending();
        if (report.failed > 0) {
          _message('Đã lưu nhưng còn ${report.failed} thay đổi chưa đồng bộ Cloud.');
        } else {
          _message('Đã cập nhật và đồng bộ Cloud ${selectedSheet!}.');
        }
      }
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => finding = false);
    }
  }

  void _message(String text) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

  @override
  Widget build(BuildContext context) {
    if (loading) return const Center(child: CircularProgressIndicator());
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const NearestStationsPanel(),
        const SizedBox(height: 12),
        const Text('Chọn dữ liệu cần cập nhật', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 14),
        DropdownButtonFormField<String>(
          value: selectedCode,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Mã trạm', border: OutlineInputBorder()),
          items: codes.map((c) => DropdownMenuItem(value: c, child: Text(c))).toList(),
          onChanged: (v) => setState(() => selectedCode = v),
        ),
        const SizedBox(height: 14),
        DropdownButtonFormField<String>(
          value: selectedSheet,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Sheet dữ liệu', border: OutlineInputBorder()),
          items: CloudService.editableSheets.map((s) => DropdownMenuItem(value: s, child: Text(s))).toList(),
          onChanged: (v) => setState(() => selectedSheet = v),
        ),
        const SizedBox(height: 18),
        SizedBox(
          height: 48,
          child: FilledButton.icon(
            onPressed: finding || selectedCode == null || selectedSheet == null ? null : _find,
            icon: const Icon(Icons.search),
            label: Text(finding ? 'ĐANG TÌM...' : 'TÌM VÀ CHỈNH SỬA'),
          ),
        ),
        if (error != null) ...[
          const SizedBox(height: 12),
          Text(error!, style: const TextStyle(color: Colors.red)),
        ],
        const SizedBox(height: 18),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(14),
            child: Text(
              'Chọn mã trạm → chọn sheet → nhấn TÌM. Cửa sổ chỉnh sửa sẽ hiển thị toàn bộ các trường dữ liệu của sheet đó cho mã trạm đã chọn.',
            ),
          ),
        ),
      ],
    );
  }
}

class NearestStationsPanel extends StatefulWidget {
  const NearestStationsPanel({super.key});
  @override State<NearestStationsPanel> createState() => _NearestStationsPanelState();
}

class _NearestStationsPanelState extends State<NearestStationsPanel> {
  final cloud = CloudService();
  List<Map<String, dynamic>> rows = [];
  bool loading = false;
  String? error;

  Future<void> findNearest() async {
    setState(() { loading = true; error = null; });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) throw Exception('Vui lòng bật GPS/Vị trí trên điện thoại.');
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) throw Exception('Chưa được cấp quyền truy cập vị trí.');
      final pos = await Geolocator.getCurrentPosition(locationSettings: const LocationSettings(accuracy: LocationAccuracy.high));
      final data = await cloud.nearestStations(pos.latitude, pos.longitude, limit: 4);
      if (mounted) setState(() => rows = data);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally { if (mounted) setState(() => loading = false); }
  }

  @override Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.my_location, size: 21), const SizedBox(width: 8),
          const Expanded(child: Text('4 TRẠM GẦN VỊ TRÍ HIỆN TẠI', style: TextStyle(fontWeight: FontWeight.w800))),
          FilledButton.tonalIcon(onPressed: loading ? null : findNearest, icon: const Icon(Icons.gps_fixed), label: Text(loading ? 'ĐANG TÌM...' : 'TÌM 4 TRẠM')),
        ]),
        const SizedBox(height: 8),
        if (error != null) Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        if (rows.isEmpty && error == null) const Text('Nhấn “TÌM 4 TRẠM” để lấy vị trí GPS và tính khoảng cách.'),
        ...rows.asMap().entries.map((e) {
          final i=e.key; final r=e.value; final d=(r['_distance_km'] as num?)?.toDouble() ?? 0;
          return ListTile(
            dense: true, contentPadding: EdgeInsets.zero, leading: CircleAvatar(radius: 15, child: Text('${i+1}')),
            title: Text('${r['code'] ?? ''} • ${r['name'] ?? ''}', maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text('${r['address'] ?? 'Chưa có địa chỉ'}\n${d.toStringAsFixed(2)} km'), isThreeLine: true,
          );
        }),
      ]),
    ),
  );
}

class SheetEditDialog extends StatefulWidget {
  final String sheet;
  final String stationCode;
  final List<Map<String, dynamic>> rows;
  final CloudService cloud;

  const SheetEditDialog({super.key, required this.sheet, required this.stationCode, required this.rows, required this.cloud});

  @override
  State<SheetEditDialog> createState() => _SheetEditDialogState();
}

class _SheetEditDialogState extends State<SheetEditDialog> {
  late List<Map<String, dynamic>> rows;
  final Map<String, TextEditingController> controllers = {};
  bool saving = false;
  String? error;

  static const hidden = {'created_at', 'updated_at', 'id'};

  @override
  void initState() {
    super.initState();
    rows = widget.rows.map((r) => Map<String, dynamic>.from(r)).toList();
  }

  @override
  void dispose() {
    for (final c in controllers.values) c.dispose();
    super.dispose();
  }

  String _label(String key) {
    const labels = {
      'code': 'Mã trạm', 'station_code': 'Mã trạm', 'name': 'Tên trạm', 'area': 'Khu vực / UPE',
      'upe': 'UPE trạm', 'type': 'Loại trạm', 'status': 'Trạng thái', 'address': 'Địa chỉ',
      'latitude': 'Vĩ độ', 'longitude': 'Kinh độ', 'owner_contact': 'Người liên hệ', 'owner_phone': 'SĐT liên hệ',
      'technician': 'KTV quản lý', 'phone': 'SĐT KTV', 'note': 'Ghi chú', 'meter_code': 'Mã điện kế',
      'pole_type': 'Loại trụ', 'csht_type': 'Loại CSHT', 'contract_no': 'Số hợp đồng', 'contract_type': 'Loại hợp đồng',
      'lessor': 'Bên cho thuê', 'sign_date': 'Ngày ký', 'start_date': 'Ngày bắt đầu', 'end_date': 'Ngày hết hạn',
      'rent_amount': 'Giá thuê', 'payment_cycle': 'Chu kỳ thanh toán', 'contact_name': 'Người liên hệ', 'contact_phone': 'SĐT liên hệ',
      'file_name': 'Tên file hợp đồng', 'equipment_group': 'Nhóm thiết bị', 'vendor': 'Hãng', 'model': 'Model',
      'serial_no': 'Serial', 'part_no': 'Part Number', 'ip_address': 'Địa chỉ IP', 'mac_address': 'MAC Address',
      'software_version': 'Phiên bản phần mềm', 'location': 'Vị trí lắp đặt', 'install_date': 'Ngày lắp',
      'link_type': 'Loại truyền dẫn', 'path_role': 'Vai trò tuyến', 'device_a': 'Thiết bị đầu A', 'port_a': 'Port đầu A',
      'device_b': 'Thiết bị đầu B', 'port_b': 'Port đầu B', 'media': 'Tốc độ / Media', 'fiber_core': 'Fiber Core',
      'sfp_a': 'SFP A', 'sfp_a_wavelength': 'Bước sóng SFP A', 'sfp_a_speed': 'Tốc độ SFP A', 'sfp_b': 'SFP B',
      'sfp_b_wavelength': 'Bước sóng SFP B', 'sfp_b_speed': 'Tốc độ SFP B', 'vlan': 'VLAN', 'wan_ip': 'IP WAN',
      'lan_ip': 'IP LAN', 'gateway': 'Gateway', 'network': 'Network', 'lacp': 'LACP', 'main_backup': 'Tuyến chính/Backup',
      'provider': 'Nhà cung cấp', 'power_vendor': 'Hãng tủ nguồn', 'power_model': 'Model tủ nguồn', 'capacity_a': 'Công suất (A)',
      'dc_voltage': 'Điện áp DC (V)', 'dc_load_a': 'Dòng tải DC (A)', 'ac_voltage': 'Điện áp AC (V)', 'ac_load_a': 'Dòng tải AC (A)',
      'rectifier_count': 'Số Rectifier', 'rectifier_working': 'Rectifier hoạt động', 'llvd1_v': 'LLVD1 (V)', 'llvd2_v': 'LLVD2 (V)',
      'blvd_v': 'BLVD (V)', 'controller_ip': 'IP Controller', 'snmp': 'SNMP', 'modbus': 'Modbus', 'battery_type': 'Loại Battery',
      'voltage_v': 'Điện áp (V)', 'capacity_ah': 'Dung lượng (Ah)', 'cell_count': 'Số Cell', 'soc_percent': 'SOC (%)',
      'soh_percent': 'SOH (%)', 'voltage_online': 'Điện áp Online', 'current_a': 'Dòng tải (A)', 'category': 'Loại thiết bị',
      'specification': 'Thông số kỹ thuật', 'quantity': 'Số lượng', 'scope': 'Phạm vi', 'work_type': 'Loại công việc',
      'work_date': 'Ngày thực hiện', 'content': 'Nội dung', 'condition_before': 'Tình trạng trước BTBD', 'result': 'Kết quả',
      'materials': 'Vật tư thay thế', 'cost': 'Chi phí', 'work_id': 'Mã công việc', 'month': 'Tháng', 'dept': 'Đơn vị',
      'cb_type': 'CB Type', 'g5': '5G', 'g3': '3G', 'g4': '4G', 'start_time': 'Giờ bắt đầu', 'end_time': 'Giờ kết thúc',
      'downtime_min': 'Thời gian MLL (phút)', 'handler': 'Người xử lý', 'error_code': 'Mã lỗi', 'error_content': 'Nguyên nhân',
      'resolution': 'Xử lý', 'bsc_min': 'MLL BSC (phút)', 'layer_min': 'MLL Layer (phút)', 'csht_code': 'Mã CSHT',
    };
    return labels[key] ?? key.replaceAll('_', ' ');
  }

  dynamic _coerce(dynamic original, String text) {
    if (text.trim().isEmpty) return null;
    if (original is int) return int.tryParse(text.trim()) ?? original;
    if (original is double) return double.tryParse(text.trim()) ?? original;
    if (original is num) return double.tryParse(text.trim()) ?? original;
    return text.trim();
  }

  String _keyForRow(Map<String, dynamic> row) {
    final table = CloudService.sheetToTable[widget.sheet]!;
    final pk = CloudService.tablePrimaryKey[table]!;
    return (row[pk] ?? '').toString();
  }

  Future<void> _saveAll() async {
    setState(() { saving = true; error = null; });
    try {
      for (var i = 0; i < rows.length; i++) {
        final original = widget.rows[i];
        final edited = Map<String, dynamic>.from(rows[i]);
        for (final key in original.keys) {
          if (hidden.contains(key)) continue;
          if (key == CloudService.tablePrimaryKey[CloudService.sheetToTable[widget.sheet]]) continue;
          final controller = controllers['$i:$key'];
          if (controller != null) edited[key] = _coerce(original[key], controller.text);
        }
        await widget.cloud.updateSheetRow(widget.sheet, widget.stationCode, edited);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Widget _field(int rowIndex, String key, dynamic value, {bool readOnly = false}) {
    final id = '$rowIndex:$key';
    final controller = controllers.putIfAbsent(id, () => TextEditingController(text: value?.toString() ?? ''));
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: TextField(
        controller: controller,
        readOnly: readOnly,
        maxLines: key == 'address' || key == 'note' || key == 'content' || key == 'resolution' || key == 'error_content' ? 3 : 1,
        decoration: InputDecoration(labelText: _label(key), border: const OutlineInputBorder()),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final table = CloudService.sheetToTable[widget.sheet]!;
    final pk = CloudService.tablePrimaryKey[table]!;
    return AlertDialog(
      title: Text('Chỉnh sửa ${widget.sheet}\nMã trạm: ${widget.stationCode}'),
      content: SizedBox(
        width: 620,
        height: MediaQuery.of(context).size.height * .72,
        child: ListView(
          children: [
            Text('Có ${rows.length} dòng dữ liệu. Tất cả trường của sheet được hiển thị bên dưới.', style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            ...rows.asMap().entries.map((entry) {
              final index = entry.key;
              final row = entry.value;
              final keys = row.keys.where((k) => !hidden.contains(k)).toList();
              return Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: ExpansionTile(
                    initiallyExpanded: rows.length == 1 || index == 0,
                    title: Text('Dòng ${index + 1}${row[pk] != null ? ' • ${row[pk]}' : ''}', style: const TextStyle(fontWeight: FontWeight.bold)),
                    children: keys.map((key) => _field(index, key, row[key], readOnly: key == 'station_code' || key == 'code' || key == pk)).toList(),
                  ),
                ),
              );
            }),
            if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: saving ? null : () => Navigator.pop(context, false), child: const Text('HỦY')),
        FilledButton.icon(onPressed: saving ? null : _saveAll, icon: const Icon(Icons.save), label: Text(saving ? 'ĐANG LƯU...' : 'LƯU TẤT CẢ')),
      ],
    );
  }
}

class NearbyStationsScreen extends StatefulWidget {
  const NearbyStationsScreen({super.key});
  @override
  State<NearbyStationsScreen> createState() => _NearbyStationsScreenState();
}

class _NearbyStationsScreenState extends State<NearbyStationsScreen> {
  final cloud = CloudService();
  bool busy = false;
  String? error;
  Position? current;
  List<Map<String, dynamic>> stations = const [];

  Future<void> _findNearest() async {
    setState(() { busy = true; error = null; });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) throw Exception('Hãy bật dịch vụ vị trí trên điện thoại.');
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) throw Exception('Chưa được cấp quyền vị trí.');
      final position = await Geolocator.getCurrentPosition(locationSettings: const LocationSettings(accuracy: LocationAccuracy.high));
      final result = await cloud.nearestStations(position.latitude, position.longitude, limit: 4);
      if (!mounted) return;
      setState(() { current = position; stations = result; });
    } catch (e) { if (mounted) setState(() => error = e.toString()); }
    finally { if (mounted) setState(() => busy = false); }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('4 trạm gần nhất')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Vị trí hiện tại', style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text(current == null ? 'Chưa lấy vị trí' : '${current!.latitude.toStringAsFixed(6)}, ${current!.longitude.toStringAsFixed(6)}'),
              const SizedBox(height: 12),
              SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: busy ? null : _findNearest, icon: const Icon(Icons.my_location), label: Text(busy ? 'ĐANG TÍNH...' : 'CHỌN VỊ TRÍ HIỆN TẠI'))),
            ]))),
            if (error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(error!, style: const TextStyle(color: Colors.red))),
            if (!busy && current != null && stations.isEmpty) const Padding(padding: EdgeInsets.only(top: 20), child: Center(child: Text('Chưa có trạm nào có tọa độ GPS để tính khoảng cách.'))),
            if (stations.isNotEmpty) ...[
              const SizedBox(height: 12),
              const Text('4 trạm gần nhất', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              ...stations.asMap().entries.map((entry) { final index = entry.key + 1; final s = entry.value; final km = (s['_distance_km'] as num).toDouble(); return Card(child: ListTile(leading: CircleAvatar(child: Text('$index')), title: Text((s['code'] ?? '').toString(), style: const TextStyle(fontWeight: FontWeight.bold)), subtitle: Text('${s['name'] ?? ''}\n${s['address'] ?? ''}'), isThreeLine: true, trailing: Text(km < 1 ? '${(km * 1000).round()} m' : '${km.toStringAsFixed(2)} km', style: const TextStyle(fontWeight: FontWeight.bold)))); }),
            ],
          ],
        ),
      );
}
