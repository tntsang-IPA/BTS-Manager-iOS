import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../services/cloud_service.dart';

class MllAnalysisScreen extends StatefulWidget {
  const MllAnalysisScreen({super.key});
  @override
  State<MllAnalysisScreen> createState() => _MllAnalysisScreenState();
}

class _MllAnalysisScreenState extends State<MllAnalysisScreen> {
  final cloud = CloudService();
  int fromMonth = 1;
  int toMonth = 6;
  bool loading = false;
  String? error;
  Map<String, dynamic>? summary;
  List<MllPcMonth> months = const [];
  List<MllReason> reasons = const [];
  List<MllService> services = const [];
  List<MllTopStation> topStations = const [];
  List<MllLongest> longest = const [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { loading = true; error = null; });
    try {
      final row = await cloud.mllAnalysisSummary(fromMonth, toMonth);
      if (row == null) {
        if (mounted) setState(() {
          summary = null;
          months = const [];
          reasons = const [];
          services = const [];
          topStations = const [];
          longest = const [];
          error = 'PC chưa đồng bộ kết quả MLL cho khoảng Tháng $fromMonth → Tháng $toMonth.';
        });
      } else {
        final monthly = _decodeList(row['monthly_json']);
        final reason = _decodeList(row['reason_json']);
        final service = _decodeMap(row['service_json']);
        var station = _decodeList(row['top_station_json']);
        var longRows = _decodeList(row['longest_json']);

        // Older PC rows may already contain the correct KPI/chart JSON but have
        // empty table JSON because they were published before V85.13. Use the
        // same aggregation rules as PC only as a compatibility fallback.
        if (station.isEmpty || longRows.isEmpty) {
          final fallback = await cloud.mllTableFallback(fromMonth, toMonth);
          if (station.isEmpty) station = fallback['top'] ?? const [];
          if (longRows.isEmpty) longRows = fallback['longest'] ?? const [];
        }

        final parsedMonths = monthly
            .map((e) => MllPcMonth.fromJson(Map<String, dynamic>.from(e)))
            .where((e) => e.month > 0)
            .toList()
          ..sort((a, b) => a.month.compareTo(b.month));
        if (mounted) setState(() {
          summary = row;
          months = parsedMonths;
          reasons = reason.map((e) => MllReason.fromJson(e)).whereType<MllReason>().toList();
          services = service.entries.map((e) => MllService(e.key, _toInt(e.value))).where((e) => e.value > 0).toList();
          final parsedTop = station
              .map((e) => MllTopStation.fromJson(Map<String, dynamic>.from(e)))
              .whereType<MllTopStation>()
              .where((e) => e.station.trim().isNotEmpty && e.minutes > 0)
              .toList()
            ..sort((a, b) => b.minutes.compareTo(a.minutes));
          final parsedLongest = longRows
              .map((e) => MllLongest.fromJson(Map<String, dynamic>.from(e)))
              .whereType<MllLongest>()
              .where((e) => e.station.trim().isNotEmpty && e.minutes > 0)
              .toList()
            ..sort((a, b) => b.minutes.compareTo(a.minutes));
          topStations = parsedTop.take(5).toList();
          longest = parsedLongest.take(5).toList();
        });
      }
    } catch (e) {
      if (mounted) setState(() { summary = null; months = const []; error = e.toString(); });
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  List<dynamic> _decodeList(dynamic value) {
    if (value is List) return value;
    if (value is String && value.trim().isNotEmpty) {
      try { final v = jsonDecode(value); return v is List ? v : const []; } catch (_) {}
    }
    return const [];
  }

  Map<String, dynamic> _decodeMap(dynamic value) {
    if (value is Map) return Map<String, dynamic>.from(value);
    if (value is String && value.trim().isNotEmpty) {
      try { final v = jsonDecode(value); if (v is Map) return Map<String, dynamic>.from(v); } catch (_) {}
    }
    return {};
  }

  Future<void> _pickMonth(bool start) async {
    final selected = await showDialog<int>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text(start ? 'Chọn tháng bắt đầu' : 'Chọn tháng kết thúc'),
        children: [for (var m = 1; m <= 12; m++) SimpleDialogOption(
          onPressed: () => Navigator.pop(ctx, m),
          child: Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Text('Tháng $m', style: const TextStyle(fontWeight: FontWeight.w700))),
        )],
      ),
    );
    if (selected == null) return;
    setState(() {
      if (start) { fromMonth = selected; if (fromMonth > toMonth) toMonth = selected; }
      else { toMonth = selected; if (toMonth < fromMonth) fromMonth = selected; }
    });
    await _load();
  }

  int _int(String key) => _toInt(summary?[key]);
  double? _num(String key) {
    final v = summary?[key];
    if (v is num) return v.toDouble();
    return double.tryParse(v?.toString() ?? '');
  }

  String _minutes(String key, {int decimals = 0}) {
    final v = _num(key);
    if (v == null) return '—';
    return '${v.toStringAsFixed(decimals)} phút';
  }

  String _bscDisplay() {
    final v = _num('bsc_avg');
    final t = _num('bsc_target');
    if (v == null) return '—';
    if (t != null) return '${v.toStringAsFixed(2)} / ${t.toStringAsFixed(2)} phút';
    return '${v.toStringAsFixed(2)} phút';
  }

  String _insight() => (summary?['insight'] ?? '').toString().trim();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Phân tích MLL'), actions: [IconButton(onPressed: loading ? null : _load, icon: const Icon(Icons.refresh), tooltip: 'Làm mới')]),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            _filterCard(),
            const SizedBox(height: 10),
            if (error != null) _errorCard(error!),
            _summaryCards(),
            const SizedBox(height: 10),
            _pcDashboard(),
          ],
        ),
      ),
    );
  }

  Widget _filterCard() => Card(
    child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [const Icon(Icons.analytics_outlined, color: Color(0xffd32f2f)), const SizedBox(width: 8), Expanded(child: Text('PHÂN TÍCH MẤT LIÊN LẠC (MLL)', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w900, color: const Color(0xffd32f2f))) )]),
      const SizedBox(height: 10),
      Row(children: [Expanded(child: _monthButton('Thống kê từ', fromMonth, () => _pickMonth(true))), const Padding(padding: EdgeInsets.symmetric(horizontal: 6), child: Text('đến', style: TextStyle(fontWeight: FontWeight.w700))), Expanded(child: _monthButton('Đến tháng', toMonth, () => _pickMonth(false)))]),
      const SizedBox(height: 10),
      SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: loading ? null : _load, icon: const Icon(Icons.bar_chart), label: Text(loading ? 'ĐANG TẢI...' : 'XEM BÁO CÁO'))),
    ])),
  );

  Widget _monthButton(String title, int month, VoidCallback onTap) => OutlinedButton.icon(
    onPressed: onTap,
    icon: const Icon(Icons.calendar_month_outlined, size: 18),
    label: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontSize: 11)), Text('Tháng $month', style: const TextStyle(fontWeight: FontWeight.w800))]),
    style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9), alignment: Alignment.centerLeft),
  );

  Widget _summaryCards() => Column(children: [
    Row(children: [
      Expanded(child: _summary('TỔNG SỰ CỐ (MLL)', summary == null ? '—' : '${_int('cases')}', Icons.warning_amber_rounded, const Color(0xffd32f2f))),
      const SizedBox(width: 7), Expanded(child: _summary('TỔNG PHÚT GIÁN ĐOẠN', _minutes('total_downtime'), Icons.timer_outlined, const Color(0xff173b68))),
      const SizedBox(width: 7), Expanded(child: _summary('MLL TRUNG BÌNH / VỤ', _minutes('avg_per_event', decimals: 1), Icons.show_chart, const Color(0xff173b68))),
    ]),
    const SizedBox(height: 7),
    Row(children: [Expanded(child: _summary('TRẠM BỊ ẢNH HƯỞNG', summary == null ? '—' : '${_int('stations')}', Icons.push_pin_outlined, const Color(0xff173b68))), const SizedBox(width: 7), Expanded(child: _summary('NGUYÊN NHÂN CHÍNH', (summary?['top_reason'] ?? '—').toString(), Icons.track_changes, const Color(0xff173b68)))]),
    const SizedBox(height: 7),
    Card(child: Padding(padding: const EdgeInsets.all(10), child: Row(children: [const Icon(Icons.satellite_alt_outlined, color: Color(0xff7b1fa2)), const SizedBox(width: 8), const Text('TB BSC:', style: TextStyle(fontWeight: FontWeight.w800)), const SizedBox(width: 6), Text(_bscDisplay(), style: const TextStyle(fontWeight: FontWeight.w900, color: Color(0xff7b1fa2)))]))),
  ]);

  Widget _summary(String title, String value, IconData icon, Color color) => Card(child: Padding(padding: const EdgeInsets.all(9), child: Column(children: [Icon(icon, color: color, size: 21), const SizedBox(height: 4), Text(title, maxLines: 2, textAlign: TextAlign.center, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 8.5, fontWeight: FontWeight.w800, color: color)), const SizedBox(height: 3), FittedBox(child: Text(value, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: color)))])));

  Widget _pcDashboard() {
    if (summary == null && !loading) return const SizedBox.shrink();
    return LayoutBuilder(builder: (context, c) {
      final wide = c.maxWidth >= 1100;
      final chart1 = _chartCard(
        '1. Xu hướng MLL & BSC theo tháng',
        SizedBox(width: double.infinity, height: 270, child: CustomPaint(painter: _PcComboPainter(months))),
      );
      final chart2 = _chartCard(
        '2. Phân bố nguyên nhân sự cố',
        SizedBox(width: double.infinity, height: 250, child: CustomPaint(painter: _DonutPainter(reasons.map((e) => _DonutItem(e.label, e.value)).toList(), center: _int('cases')))),
      );
      final chart3 = _chartCard(
        '3. Lớp dịch vụ bị ảnh hưởng',
        SizedBox(width: double.infinity, height: 250, child: CustomPaint(painter: _DonutPainter(services.map((e) => _DonutItem(e.label, e.value)).toList(), center: _int('cases')))),
      );
      final tables = [
        _tableCard('📊 4. Top trạm theo tổng phút gián đoạn', _topStationTable()),
        _tableCard('⏱ 5. 5 sự cố dài nhất', _longestTable()),
      ];
      return Column(children: [
        // Keep chart 1 full-width so its month axis/labels have enough room.
        chart1,
        const SizedBox(height: 10),
        // Charts 2 and 3 are centered. On wide screens they use the same
        // two-column geometry as tables 4 and 5; on narrower screens each
        // card is centered and capped so it does not stretch edge-to-edge.
        if (wide)
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: chart2),
            const SizedBox(width: 8),
            Expanded(child: chart3),
          ])
        else
          Column(children: [
            Align(
              alignment: Alignment.center,
              child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 720), child: chart2),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.center,
              child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 720), child: chart3),
            ),
          ]),
        const SizedBox(height: 10),
        if (wide)
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: tables[0]), const SizedBox(width: 8), Expanded(child: tables[1])
          ])
        else
          Column(children: [tables[0], const SizedBox(height: 8), tables[1]]),
        const SizedBox(height: 8),
        _insightCard(),
      ]);
    });
  }

  Widget _chartCard(String title, Widget chart) => Card(child: Padding(padding: const EdgeInsets.fromLTRB(10, 10, 10, 6), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 13)), const SizedBox(height: 5), chart])));

  Widget _tableCard(String title, Widget table) => Card(child: Padding(padding: const EdgeInsets.fromLTRB(8, 8, 8, 8), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 12, color: Color(0xff8b1e1e))), const SizedBox(height: 6), table])));

  Widget _topStationTable() {
    if (topStations.isEmpty) return const SizedBox(height: 210, child: Center(child: Text('Chưa có dữ liệu')));
    return SingleChildScrollView(scrollDirection: Axis.horizontal, child: DataTable(
      headingRowHeight: 36, dataRowMinHeight: 36, dataRowMaxHeight: 40, columnSpacing: 22,
      headingTextStyle: const TextStyle(fontWeight: FontWeight.w900, fontSize: 11),
      dataTextStyle: const TextStyle(fontSize: 11),
      columns: const [DataColumn(label: Text('STT')), DataColumn(label: Text('TRẠM')), DataColumn(label: Text('VỤ')), DataColumn(label: Text('PHÚT'))],
      rows: [for (var i=0; i<topStations.length; i++) DataRow(cells: [DataCell(Text('${i+1}')), DataCell(Text(topStations[i].station)), DataCell(Text('${topStations[i].cases}')), DataCell(Text('${topStations[i].minutes.toStringAsFixed(0)}p'))])],
    ));
  }

  Widget _longestTable() {
    if (longest.isEmpty) return const SizedBox(height: 210, child: Center(child: Text('Chưa có dữ liệu')));
    return SingleChildScrollView(scrollDirection: Axis.horizontal, child: DataTable(
      headingRowHeight: 36, dataRowMinHeight: 36, dataRowMaxHeight: 42, columnSpacing: 18,
      headingTextStyle: const TextStyle(fontWeight: FontWeight.w900, fontSize: 11), dataTextStyle: const TextStyle(fontSize: 10.5),
      columns: const [DataColumn(label: Text('STT')), DataColumn(label: Text('TRẠM')), DataColumn(label: Text('THÁNG')), DataColumn(label: Text('NGUYÊN NHÂN')), DataColumn(label: Text('PHÚT'))],
      rows: [for (var i=0; i<longest.length; i++) DataRow(cells: [DataCell(Text('${i+1}')), DataCell(Text(longest[i].station)), DataCell(Text(longest[i].month)), DataCell(Text(longest[i].reason)), DataCell(Text('${longest[i].minutes.toStringAsFixed(0)}p'))])],
    ));
  }

  Widget _insightCard() {
    final text = _insight();
    if (text.isEmpty) return const SizedBox.shrink();
    return Card(color: const Color(0xfff0fdf4), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8), side: const BorderSide(color: Color(0xffbbf7d0))), child: Padding(padding: const EdgeInsets.all(9), child: Text(text, style: const TextStyle(fontSize: 12, color: Color(0xff166534), height: 1.35))));
  }

  Widget _errorCard(String text) => Card(child: Padding(padding: const EdgeInsets.all(12), child: Text(text, style: TextStyle(color: Theme.of(context).colorScheme.error))));
}

int _toInt(dynamic value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

double _toDouble(dynamic value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? 0;
}

class MllPcMonth {
  final int month; final int cases; final double downtime; final double bsc;
  const MllPcMonth(this.month, this.cases, this.downtime, this.bsc);
  factory MllPcMonth.fromJson(Map<String, dynamic> json) {
    final raw = (json['month'] ?? '').toString();
    final match = RegExp(r'(\d+)').firstMatch(raw);
    return MllPcMonth(int.tryParse(match?.group(1) ?? '') ?? 0, _toInt(json['cases']), _toDouble(json['minutes'] ?? json['downtime_min']), _toDouble(json['bsc'] ?? json['bsc_avg']));
  }
  String get label => 'Tháng $month';
}

class MllReason { final String label; final int value; const MllReason(this.label, this.value); factory MllReason.fromJson(dynamic v) { if (v is List && v.length >= 2) return MllReason(v[0].toString(), _toInt(v[1])); if (v is Map) return MllReason((v['label'] ?? v['name'] ?? '').toString(), _toInt(v['value'])); return const MllReason('', 0); } }
class MllService { final String label; final int value; const MllService(this.label, this.value); }
class MllTopStation { final String station; final int cases; final double minutes; const MllTopStation(this.station, this.cases, this.minutes); factory MllTopStation.fromJson(Map<String,dynamic> j) => MllTopStation((j['station'] ?? '').toString(), _toInt(j['cases']), _toDouble(j['minutes'])); }
class MllLongest { final String station; final String month; final String reason; final double minutes; const MllLongest(this.station,this.month,this.reason,this.minutes); factory MllLongest.fromJson(Map<String,dynamic> j) => MllLongest((j['station'] ?? '').toString(), (j['month'] ?? '').toString(), (j['reason'] ?? '').toString(), _toDouble(j['minutes'])); }
class _DonutItem { final String label; final int value; const _DonutItem(this.label,this.value); }

class _DonutPainter extends CustomPainter {
  final List<_DonutItem> data; final int center;
  _DonutPainter(this.data, {required this.center});
  @override void paint(Canvas canvas, Size size) {
    final total = data.fold<int>(0, (a,b)=>a+b.value);
    if (total <= 0) { final p=Paint()..color=const Color(0xffe5e7eb); canvas.drawCircle(Offset(size.width*.28,size.height*.52),55,p); return; }
    // Keep the donut + legend group visually centered in the card.
    // The group is approximately 310px wide (donut ~145px + legend).
    final groupW = math.min(330.0, size.width);
    final groupLeft = math.max(0.0, (size.width - groupW) / 2);
    final cx = groupLeft + math.min(78.0, groupW * .24);
    final cy=size.height*.52; final rad=math.min(62.0, size.height*.25);
    final colors=[const Color(0xff1473c9),const Color(0xff0f9aa8),const Color(0xfff59e0b),const Color(0xffef4444),const Color(0xff7c5ce0)];
    double start=-math.pi/2;
    final paint=Paint()..style=PaintingStyle.stroke..strokeWidth=22..strokeCap=StrokeCap.butt;
    for(var i=0;i<data.length;i++){final sweep=2*math.pi*data[i].value/total; paint.color=colors[i%colors.length]; canvas.drawArc(Rect.fromCircle(center:Offset(cx,cy),radius:rad),start,sweep,false,paint); start+=sweep;}
    final tp=TextPainter(text:TextSpan(text:'$center',style:const TextStyle(fontSize:20,fontWeight:FontWeight.w900,color:Color(0xff10233b))),textDirection:TextDirection.ltr)..layout(maxWidth:100);
    tp.paint(canvas,Offset(cx-tp.width/2,cy-16));
    final sub=TextPainter(text:const TextSpan(text:'tổng',style:TextStyle(fontSize:9,color:Color(0xff64748b))),textDirection:TextDirection.ltr)..layout(); sub.paint(canvas,Offset(cx-sub.width/2,cy+7));
    final legendX=math.min(size.width-150.0, cx+rad+22); var y=22.0;
    for(var i=0;i<data.length;i++){final pct=data[i].value/total*100; final sw=Paint()..color=colors[i%colors.length]; canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(legendX,y,8,8),const Radius.circular(2)),sw); final t=TextPainter(text:TextSpan(text:'${data[i].label}  ${pct.toStringAsFixed(0)}%',style:const TextStyle(fontSize:9,fontWeight:FontWeight.w600,color:Color(0xff475569))),textDirection:TextDirection.ltr)..layout(maxWidth:math.max(80,size.width-legendX-4)); t.paint(canvas,Offset(legendX+12,y-3)); final n=TextPainter(text:TextSpan(text:'${data[i].value}',style:const TextStyle(fontSize:9,fontWeight:FontWeight.w900,color:Color(0xff10233b))),textDirection:TextDirection.ltr)..layout(maxWidth:math.max(80,size.width-legendX-4)); n.paint(canvas,Offset(legendX+12,y+11)); y+=31;}
  }
  @override bool shouldRepaint(covariant _DonutPainter old) => old.data != data || old.center != center;
}

class _PcComboPainter extends CustomPainter {
  final List<MllPcMonth> data; _PcComboPainter(this.data);
  @override void paint(Canvas canvas, Size size) {
    if(data.isEmpty){final t=TextPainter(text:const TextSpan(text:'Chưa có dữ liệu PC'),textDirection:TextDirection.ltr)..layout();t.paint(canvas,Offset((size.width-t.width)/2,size.height/2));return;}
    const left=42.0,right=16.0,top=18.0,bottom=34.0; final w=size.width-left-right,h=size.height-top-bottom; final maxCases=math.max(1,data.map((e)=>e.cases).fold<int>(0,(a,b)=>a>b?a:b)); final maxMin=math.max(1.0,data.map((e)=>e.downtime).fold<double>(0,(a,b)=>a>b?a:b)); final maxBsc=math.max(1.0,data.map((e)=>e.bsc).fold<double>(0,(a,b)=>a>b?a:b)); final step=w/data.length; final barW=math.max(12.0,step*.45).toDouble(); final grid=Paint()..color=const Color(0xffdbe4ee)..strokeWidth=1;
    for(var i=0;i<5;i++){final y=top+h*i/4;canvas.drawLine(Offset(left,y),Offset(left+w,y),grid);}
    for(var i=0;i<data.length;i++){final e=data[i]; final x=left+step*i+(step-barW)/2; final bh=h*e.cases.toDouble()/maxCases.toDouble(); final p=Paint()..color=const Color(0xff1473c9);canvas.drawRRect(RRect.fromRectAndRadius(Rect.fromLTWH(x,top+h-bh,barW,bh),const Radius.circular(4)),p); _label(canvas,'${e.month}',Offset(left+step*(i+.5),top+h+4),10,const Color(0xff475569));}
    _line(canvas,data.map((e)=>e.downtime).toList(),maxMin,const Color(0xfff59e0b),false,step,left,top,h,size);
    _line(canvas,data.map((e)=>e.bsc).toList(),maxBsc,const Color(0xff7c5ce0),true,step,left,top,h,size);
  }
  void _line(Canvas c,List<double> vals,double maxV,Color color,bool below,double step,double left,double top,double h,Size size){final paint=Paint()..color=color..strokeWidth=2..style=PaintingStyle.stroke; final dot=Paint()..color=color; Offset? prev; for(var i=0;i<vals.length;i++){final x=left+step*(i+.5); final y=top+h-(h*vals[i]/maxV); final cur=Offset(x,y); if(prev!=null)c.drawLine(prev!,cur,paint); c.drawCircle(cur,3,dot); _label(c,below?vals[i].toStringAsFixed(2):vals[i].toStringAsFixed(0),Offset(x,y+(below?7:-17)),below?8:9,color); prev=cur;}}
  void _label(Canvas c,String text,Offset center,double font,Color color){final tp=TextPainter(text:TextSpan(text:text,style:TextStyle(fontSize:font,fontWeight:FontWeight.w800,color:color)),textDirection:TextDirection.ltr)..layout();tp.paint(c,Offset(center.dx-tp.width/2,center.dy));}
  @override bool shouldRepaint(covariant _PcComboPainter old)=>true;
}
