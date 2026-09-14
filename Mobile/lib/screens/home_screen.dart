import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../services/cloud_service.dart';
import '../services/network_status.dart';
import 'station_search_screen.dart';
import 'profile_screen.dart';
import 'notifications_screen.dart';
import 'operations_screen.dart';
import 'mll_analysis_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final cloud = CloudService();
  bool loading = true;
  String? error;
  int stations = 0;
  List<Map<String, dynamic>> kpis = [];
  Map<String, List<Map<String, dynamic>>> overview = {};
  double? mllAvg;
  int pendingNotifications = 0;
  int pendingSync = 0;
  int conflicts = 0;
  Map<String, dynamic> dashboardMetrics = {};

  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    setState(() => loading = true);
    try {
      // Flush local pending station edits first, then read the authoritative
      // Cloud station distribution for the five operational charts.
      await cloud.syncPending();
      final results = await Future.wait([
        cloud.stationCount(),
        cloud.kpis(),
        cloud.overviewStats(),
        cloud.notifications(pendingOnly: true),
        cloud.pendingSyncCount(),
        cloud.conflictCount(),
        cloud.dashboardMetrics(),
      ]);
      if (!mounted) return;
      setState(() {
        stations = results[0] as int;
        kpis = results[1] as List<Map<String, dynamic>>;
        overview = results[2] as Map<String, List<Map<String, dynamic>>>;
        mllAvg = null;
        pendingNotifications = (results[3] as List).length;
        pendingSync = results[4] as int;
        conflicts = results[5] as int;
        dashboardMetrics = results[6] as Map<String, dynamic>;
        error = null;
      });
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  String metric(List<String> aliases) {
    final wanted = aliases.map(_norm).toSet();
    Map<String, dynamic>? pick;
    if (wanted.contains(_norm('BTBD Indoor'))) pick = dashboardMetrics['indoor'] is Map ? Map<String,dynamic>.from(dashboardMetrics['indoor']) : null;
    if (wanted.contains(_norm('BTBD Outdoor'))) pick = dashboardMetrics['outdoor'] is Map ? Map<String,dynamic>.from(dashboardMetrics['outdoor']) : null;
    if (wanted.contains(_norm('XL PAKH'))) pick = dashboardMetrics['pakh'] is Map ? Map<String,dynamic>.from(dashboardMetrics['pakh']) : null;
    if (wanted.contains(_norm('KPI'))) pick ??= dashboardMetrics['pakh'] is Map ? Map<String,dynamic>.from(dashboardMetrics['pakh']) : null;
    if (wanted.contains(_norm('Trạm phát triển mới')) || wanted.contains(_norm('Phát triển mới'))) pick = dashboardMetrics['development'] is Map ? Map<String,dynamic>.from(dashboardMetrics['development']) : null;
    if (pick != null) return _ratio(pick['actual'], pick['target']);
    for (final row in kpis) {
      final label = _norm(row['content']?.toString() ?? '');
      if (wanted.any((a) => label == a || label.contains(a) || a.contains(label))) return _ratio(row['actual'], row['target']);
    }
    return '—';
  }
  String _ratio(dynamic actual, dynamic target) {
    num? n(dynamic v) => v == null || v.toString().trim().isEmpty ? null : num.tryParse(v.toString().trim().replaceAll(',', '.'));
    final a=n(actual), t=n(target);
    if(a!=null&&t!=null){final pct=t==0?0:a/t*100;return '${_fmt(a)} / ${_fmt(t)} (${pct.toStringAsFixed(0)}%)';}
    if(a!=null)return '${_fmt(a)} / —'; if(t!=null)return '— / ${_fmt(t)}'; return '—';
  }
  String _fmt(num v) => v == v.roundToDouble() ? v.toInt().toString() : v.toStringAsFixed(2);
  String _norm(String s) => s.toLowerCase().replaceAll(RegExp(r'[\s_\-]+'), ' ').trim();
  String mllDisplay() {
    // V85.26: Dashboard card is 'Chỉ tiêu MLL'.
    // Source is exactly KPI!B6 = row MLL / column Chỉ tiêu.
    // Never combine it with actual MLL, TB BSC, avg_6m or event minutes.
    final target = dashboardMetrics['mllTarget'] ?? dashboardMetrics['mll'];
    if (target is! num) return '—';
    return '${target.toStringAsFixed(2)} phút';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BTS Manager'),
        actions: [
          IconButton(
            tooltip: 'Thông báo',
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const NotificationsScreen())).then((_) => load()),
            icon: Badge(label: Text('$pendingNotifications'), isLabelVisible: pendingNotifications > 0, child: const Icon(Icons.notifications_outlined)),
          ),
          IconButton(onPressed: load, tooltip: 'Làm mới', icon: const Icon(Icons.refresh)),
          IconButton(onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ProfileScreen())), icon: const Icon(Icons.account_circle_outlined)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
          children: [
            if (error != null) _errorCard(error!),
            _connectionCard(),
            const _SectionTitle('THÔNG TIN VẬN HÀNH'),
            _overviewGrid(),
            const SizedBox(height: 12),
            const _SectionTitle('CHỈ SỐ CẦN QUAN TÂM'),
            _focusGrid(),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const MllAnalysisScreen()),
                ).then((_) => load()),
                icon: const Icon(Icons.analytics_outlined),
                label: const Text('PHÂN TÍCH MẤT LIÊN LẠC (MLL)'),
              ),
            ),
            const SizedBox(height: 12),
            const _SectionTitle('VẬN HÀNH HIỆN TRƯỜNG'),
            FilledButton.icon(
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const OperationsScreen())),
              icon: const Icon(Icons.build_circle_outlined),
              label: const Text('Cập nhật thông tin trạm • 4 trạm gần nhất'),
            ),
            const SizedBox(height: 12),
            const _SectionTitle('TRA CỨU TRẠM'),
            FilledButton.icon(
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const StationSearchScreen())),
              icon: const Icon(Icons.search),
              label: const Text('Mã trạm • Tên • Địa chỉ • UPE • Mã điện kế • Hợp đồng • KTV'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _connectionCard() {
    return StreamBuilder<bool>(
      stream: NetworkStatus.instance.stream,
      initialData: NetworkStatus.instance.online,
      builder: (context, snapshot) {
        final online = snapshot.data ?? NetworkStatus.instance.online;
        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(children: [
              Icon(online ? Icons.cloud_done : Icons.cloud_off, size: 22),
              const SizedBox(width: 8),
              Expanded(child: Text(online ? 'ONLINE • Cloud' : 'OFFLINE • Dữ liệu đã lưu', style: const TextStyle(fontWeight: FontWeight.w700))),
              if (pendingSync > 0) Text('Chờ $pendingSync', style: const TextStyle(fontSize: 12)),
              if (conflicts > 0) Padding(padding: const EdgeInsets.only(left: 8), child: Text('Xung đột $conflicts', style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.error))),
              IconButton(tooltip: 'Đồng bộ', onPressed: online ? () async { await cloud.syncPending(); await load(); } : null, icon: const Icon(Icons.sync, size: 20)),
            ]),
          ),
        );
      },
    );
  }

  Widget _overviewGrid() {
    const specs = [
      ('Loại trạm', 'type', Icons.category_outlined),
      ('Kết nối UPE', 'upe', Icons.hub_outlined),
      ('Loại trụ', 'pole_type', Icons.foundation_outlined),
      ('Loại CSHT', 'csht_type', Icons.domain_outlined),
      ('KTV quản lý', 'technician', Icons.engineering_outlined),
    ];
    return Column(children: [
      for (var i = 0; i < specs.length; i += 2)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: _OverviewCard(title: specs[i].$1, icon: specs[i].$3, rows: overview[specs[i].$2] ?? const [])),
            const SizedBox(width: 8),
            Expanded(child: i + 1 < specs.length ? _OverviewCard(title: specs[i + 1].$1, icon: specs[i + 1].$3, rows: overview[specs[i + 1].$2] ?? const []) : const SizedBox()),
          ]),
        ),
    ]);
  }

  Widget _focusGrid() {
    final items = [
      _Metric(title: 'Tổng trạm', value: loading ? '…' : '$stations', subtitle: 'Tổng số trạm', icon: Icons.cell_tower, color: const Color(0xff1565c0)),
      _Metric(title: 'BTBD Indoor', value: metric(['BTBD Indoor', 'BTBD INDOOR', 'BTBD trong nhà']), subtitle: 'Đã thực hiện / Chỉ tiêu', emoji: '🏢', color: const Color(0xff1976d2)),
      _Metric(title: 'BTBD Outdoor', value: metric(['BTBD Outdoor', 'BTBD OUTDOOR', 'BTBD ngoài trời']), subtitle: 'Đã thực hiện / Chỉ tiêu', emoji: '🗼', color: const Color(0xff2e7d32)),
      _Metric(title: 'CHỈ TIÊU MLL', value: mllDisplay(), subtitle: 'Theo bảng KPI – ô B6', emoji: '📡', color: const Color(0xff7b1fa2)),
      _Metric(title: 'XL PAKH', value: metric(['XL PAKH', 'KPI']), subtitle: 'Đã thực hiện / Chỉ tiêu', emoji: '🎯', color: const Color(0xffd84315)),
      _Metric(title: 'PHÁT TRIỂN MỚI', value: metric(['Trạm phát triển mới', 'Phát triển mới']), subtitle: 'Đã thực hiện / Chỉ tiêu', imageAsset: 'assets/phat_trien_moi.png', color: const Color(0xff00897b)),
    ];
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: items.length,
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount: 2, crossAxisSpacing: 8, mainAxisSpacing: 8, childAspectRatio: 1.65),
      itemBuilder: (_, i) => items[i],
    );
  }

  Widget _errorCard(String text) => Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(text, style: TextStyle(color: Theme.of(context).colorScheme.error))));
}

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);
  @override
  Widget build(BuildContext context) => Padding(padding: const EdgeInsets.fromLTRB(2, 4, 2, 8), child: Text(text, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)));
}

class _Metric extends StatelessWidget {
  final String title;
  final String value;
  final String subtitle;
  final IconData? icon;
  final String? emoji;
  final String? imageAsset;
  final Color color;
  const _Metric({required this.title, required this.value, required this.subtitle, this.icon, this.emoji, this.imageAsset, required this.color});
  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(11, 10, 11, 9),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(width: 38, height: 38, decoration: BoxDecoration(color: color.withOpacity(.10), borderRadius: BorderRadius.circular(12)), child: imageAsset != null ? Padding(padding: const EdgeInsets.all(5), child: Image.asset(imageAsset!, fit: BoxFit.contain)) : emoji != null ? Center(child: Text(emoji!, style: const TextStyle(fontSize: 23))) : Icon(icon, size: 22, color: color)),
          const Spacer(),
          Icon(Icons.chevron_right, size: 18, color: color.withOpacity(.65)),
        ]),
        const Spacer(),
        Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: color)),
        const SizedBox(height: 2),
        FittedBox(alignment: Alignment.centerLeft, fit: BoxFit.scaleDown, child: Text(value, maxLines: 1, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: color))),
        const SizedBox(height: 2),
        Text(subtitle, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 9.5, fontWeight: FontWeight.w600, color: Colors.grey.shade600)),
      ]),
    ),
  );
}

class _OverviewCard extends StatelessWidget {
  final String title; final IconData icon; final List<Map<String, dynamic>> rows;
  const _OverviewCard({required this.title, required this.icon, required this.rows});
  @override Widget build(BuildContext context) {
    final total=rows.fold<int>(0,(a,r)=>a+((r['count'] as num?)?.toInt()??0));
    return Card(margin:EdgeInsets.zero,child:Padding(padding:const EdgeInsets.all(10),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
      Row(children:[Icon(icon,size:19),const SizedBox(width:6),Expanded(child:Text(title,maxLines:1,overflow:TextOverflow.ellipsis,style:const TextStyle(fontWeight:FontWeight.w700)))]),
      const SizedBox(height:8),
      if(rows.isEmpty) const SizedBox(height:80,child:Center(child:Text('Chưa có dữ liệu',style:TextStyle(fontSize:12))))
      else Row(crossAxisAlignment:CrossAxisAlignment.start,children:[
        SizedBox(width:78,height:78,child:CustomPaint(painter:_DonutPainter(rows))),
        const SizedBox(width:8),
        Expanded(child:SizedBox(height:96,child:Scrollbar(child:SingleChildScrollView(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:rows.asMap().entries.map((entry){final idx=entry.key;final r=entry.value;final c=(r['count'] as num?)?.toInt()??0;final pct=total==0?0:c*100/total;final label='${r['label']}';return Padding(padding:const EdgeInsets.symmetric(vertical:2),child:Tooltip(message:label,waitDuration:const Duration(milliseconds:250),child:Row(children:[Container(width:8,height:8,decoration:BoxDecoration(shape:BoxShape.circle,color:_chartColor(idx))),const SizedBox(width:5),Expanded(child:Text(label,maxLines:1,overflow:TextOverflow.ellipsis,style:const TextStyle(fontSize:10))),Text('$c (${pct.toStringAsFixed(0)}%)',style:const TextStyle(fontSize:10,fontWeight:FontWeight.w700))])));}).toList())))))
      ])
    ])));
  }
}
Color _chartColor(int i){const c=[Color(0xff1976d2),Color(0xff2e7d32),Color(0xff7b1fa2),Color(0xffef6c00),Color(0xff00838f)];return c[i%c.length];}
class _DonutPainter extends CustomPainter{final List<Map<String,dynamic>> rows;_DonutPainter(this.rows);@override void paint(Canvas canvas,Size size){final total=rows.fold<double>(0,(a,r)=>a+((r['count'] as num?)?.toDouble()??0));final p=Paint()..style=PaintingStyle.stroke..strokeWidth=13;double start=-math.pi/2;for(var i=0;i<rows.length;i++){final v=(rows[i]['count'] as num?)?.toDouble()??0;if(total<=0||v<=0)continue;final sweep=v/total*math.pi*2;p.color=_chartColor(i);canvas.drawArc(Offset.zero&size,start,sweep,false,p);start+=sweep;}final center=size.center(Offset.zero);p.style=PaintingStyle.fill;p.color=Colors.white;canvas.drawCircle(center,22,p);final tp=TextPainter(text:TextSpan(text:'${rows.length}',style:const TextStyle(fontSize:14,fontWeight:FontWeight.w900,color:Color(0xff10233b))),textDirection:TextDirection.ltr);tp.layout();tp.paint(canvas,center-Offset(tp.width/2,tp.height/2+5));final lp=TextPainter(text:TextSpan(text:'loại',style:const TextStyle(fontSize:7,fontWeight:FontWeight.w600,color:Color(0xff64748b))),textDirection:TextDirection.ltr);lp.layout();lp.paint(canvas,center-Offset(lp.width/2,-7));}@override bool shouldRepaint(covariant _DonutPainter old)=>true;}
