
import os, sys, sqlite3, shutil, csv, datetime, unicodedata, json, urllib.parse, time
from pathlib import Path
from PySide6.QtCore import Qt, QDate, QTime, QTimer, QUrl, QStringListModel, QThread, Signal
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QPainter, QPen, QBrush, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolTip,
    QPushButton, QTableWidget, QTableWidgetItem, QLineEdit, QFileDialog,
    QMessageBox, QStackedWidget, QFormLayout, QComboBox, QGroupBox,
    QGridLayout, QFrame, QTabWidget, QScrollArea, QProgressBar, QHeaderView,
    QCalendarWidget, QDateEdit, QTimeEdit, QPlainTextEdit, QCheckBox, QDialog, QDialogButtonBox, QCompleter, QAbstractItemView, QSizePolicy, QInputDialog
)
from PySide6.QtMultimedia import QSoundEffect


# Tách thư mục tài nguyên của EXE khỏi thư mục dữ liệu có thể ghi.
# Khi chạy PyInstaller --onefile, _MEIPASS là thư mục tạm và sẽ bị xóa sau khi thoát.
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BTS_IMPORT_TEMPLATE = RESOURCE_DIR / "BTS_Manager_Import_Template_V85_60_5_EMAIL.xlsx"
if os.name == "nt":
    DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BTS Manager"
else:
    DATA_ROOT = Path.home() / ".bts-manager"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
DB = DATA_ROOT / "bts_manager.db"
CLOUD_CONFIG = DATA_ROOT / "supabase_config.json"

STATION_FIELDS = [
    ("Mã trạm","code"),("Tên trạm","name"),("UPE trạm","upe"),("Loại trạm","type"),
    ("Trạng thái","status"),("Địa chỉ","address"),("Vĩ độ","latitude"),
    ("Kinh độ","longitude"),("Người liên hệ","owner_contact"),("Mã điện kế","meter_code"),
    ("KTV quản lý","technician"),("Loại trụ","pole_type"),("Loại CSHT","csht_type"),("Email","email"),("Ghi chú","note")
]

def connect_db():
    # SQLite tuning: giảm I/O thừa, tăng cache và cho phép đọc ổn định trong lúc ghi.
    con = sqlite3.connect(DB, cached_statements=256)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA cache_size=-20000")
    con.execute("""CREATE TABLE IF NOT EXISTS stations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL,
        name TEXT, area TEXT, type TEXT, status TEXT DEFAULT 'Hoạt động',
        address TEXT, latitude TEXT, longitude TEXT, owner_contact TEXT,
        owner_phone TEXT, technician TEXT, phone TEXT, note TEXT,
        upe TEXT, meter_code TEXT, pole_type TEXT, csht_type TEXT, email TEXT)""")
    con.commit()
    return con

def ensure_indexes(con):
    # Indexes cho các trường được tìm kiếm/lọc thường xuyên.
    indexes = [
        ("idx_stations_code", "stations(code)"),
        ("idx_stations_upe", "stations(upe)"),
        ("idx_stations_type", "stations(type)"),
        ("idx_stations_technician", "stations(technician)"),
        ("idx_stations_email", "stations(email)"),
        ("idx_contracts_station", "contracts(station_code)"),
        ("idx_contracts_no", "contracts(contract_no)"),
        ("idx_equipment_station", "equipment(station_code)"),
        ("idx_equipment_serial", "equipment(serial_no)"),
        ("idx_transmission_station", "transmission(station_code)"),
        ("idx_power_station", "power(station_code)"),
        ("idx_batteries_station", "batteries(station_code)"),
        ("idx_auxiliary_station", "auxiliary(station_code)"),
        ("idx_maintenance_station", "maintenance(station_code)"),
        ("idx_maintenance_date", "maintenance(work_date)"),
        ("idx_mll_station", "mll_events(station_code)"),
        ("idx_mll_month", "mll_events(month)"),
        ("idx_mll_error", "mll_events(error_code)"),
        ("idx_kpi_content", "kpi_targets(content)"),
    ]
    for name, expr in indexes:
        con.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {expr}")

def ensure_schema(con):
    schemas = {
        "contracts": """CREATE TABLE IF NOT EXISTS contracts (
            contract_id TEXT PRIMARY KEY, station_code TEXT, contract_no TEXT,
            contract_type TEXT, lessor TEXT, address TEXT, sign_date TEXT,
            start_date TEXT, end_date TEXT, rent_amount TEXT, payment_cycle TEXT,
            contact_name TEXT, contact_phone TEXT, status TEXT, file_name TEXT, note TEXT)""",
        "equipment": """CREATE TABLE IF NOT EXISTS equipment (
            equipment_id TEXT PRIMARY KEY, station_code TEXT, equipment_group TEXT,
            vendor TEXT, model TEXT, serial_no TEXT, part_no TEXT, ip_address TEXT,
            mac_address TEXT, software_version TEXT, location TEXT, install_date TEXT,
            status TEXT, note TEXT)""",
        "transmission": """CREATE TABLE IF NOT EXISTS transmission (
            transmission_id TEXT PRIMARY KEY, station_code TEXT, link_type TEXT,
            path_role TEXT, device_a TEXT, port_a TEXT, device_b TEXT, port_b TEXT,
            media TEXT, fiber_core TEXT, sfp_a TEXT, sfp_a_wavelength TEXT,
            sfp_a_speed TEXT, sfp_b TEXT, sfp_b_wavelength TEXT, sfp_b_speed TEXT,
            vlan TEXT, wan_ip TEXT, lan_ip TEXT, gateway TEXT, network TEXT,
            lacp TEXT, main_backup TEXT, provider TEXT, status TEXT, note TEXT)""",
        "power": """CREATE TABLE IF NOT EXISTS power (
            power_id TEXT PRIMARY KEY, station_code TEXT, power_vendor TEXT,
            power_model TEXT, capacity_a TEXT, dc_voltage TEXT, dc_load_a TEXT,
            ac_voltage TEXT, ac_load_a TEXT, rectifier_count TEXT,
            rectifier_working TEXT, llvd1_v TEXT, llvd2_v TEXT, blvd_v TEXT,
            controller_ip TEXT, snmp TEXT, modbus TEXT, status TEXT, note TEXT)""",
        "batteries": """CREATE TABLE IF NOT EXISTS batteries (
            battery_id TEXT PRIMARY KEY, station_code TEXT, battery_type TEXT,
            vendor TEXT, model TEXT, serial_no TEXT, voltage_v TEXT,
            capacity_ah TEXT, cell_count TEXT, soc_percent TEXT, soh_percent TEXT,
            voltage_online TEXT, current_a TEXT, install_date TEXT, status TEXT, note TEXT)""",
        "auxiliary": """CREATE TABLE IF NOT EXISTS auxiliary (
            aux_id TEXT PRIMARY KEY, station_code TEXT, category TEXT, vendor TEXT,
            model TEXT, serial_no TEXT, specification TEXT, quantity TEXT,
            location TEXT, install_date TEXT, status TEXT, note TEXT)""",
        "maintenance": """CREATE TABLE IF NOT EXISTS maintenance (
            work_id TEXT PRIMARY KEY, station_code TEXT, area TEXT, scope TEXT,
            work_type TEXT, work_date TEXT, technician TEXT, content TEXT,
            condition_before TEXT, result TEXT, materials TEXT, cost TEXT,
            status TEXT, note TEXT)"""
,
        "mll_events": """CREATE TABLE IF NOT EXISTS mll_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, month TEXT, station_code TEXT, dept TEXT, cb_type TEXT,
            g5 TEXT, g3 TEXT, g4 TEXT, start_date TEXT, start_time TEXT, end_date TEXT, end_time TEXT,
            downtime_min REAL, handler TEXT, error_code TEXT, error_content TEXT, resolution TEXT,
            bsc_min REAL, layer_min REAL, csht_code TEXT, csht_type TEXT)"""
        ,"mll_bsc_summary": """CREATE TABLE IF NOT EXISTS mll_bsc_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT, dept TEXT, month_no INTEGER, value REAL, avg_6m REAL)"""
        ,"kpi_targets": """CREATE TABLE IF NOT EXISTS kpi_targets (
            content TEXT PRIMARY KEY, target TEXT, actual TEXT, updated_at TEXT)"""
    }
    for sql in schemas.values():
        con.execute(sql)
    # Migration cho hồ sơ trạm theo cấu trúc Import mới.
    station_cols={r[1] for r in con.execute("PRAGMA table_info(stations)").fetchall()}
    for col in ("upe","meter_code","pole_type","csht_type","email"):
        if col not in station_cols:
            con.execute(f"ALTER TABLE stations ADD COLUMN {col} TEXT")
    # Migration KPI V69: bổ sung cột “Đã thực hiện” nhưng giữ nguyên dữ liệu cũ.
    kpi_cols={r[1] for r in con.execute("PRAGMA table_info(kpi_targets)").fetchall()}
    if "actual" not in kpi_cols:
        con.execute("ALTER TABLE kpi_targets ADD COLUMN actual TEXT")
    bsc_cols={r[1] for r in con.execute("PRAGMA table_info(mll_bsc_summary)").fetchall()}
    if "avg_6m" not in bsc_cols:
        con.execute("ALTER TABLE mll_bsc_summary ADD COLUMN avg_6m REAL")

    # Đồng bộ dữ liệu trạm với mẫu Import mới nhất: Khu vực/SĐT cũ không còn là
    # trường của sheet TRẠM BTS nên không được tiếp tục xuất hiện trong hồ sơ trạm.
    current_cols={r[1] for r in con.execute("PRAGMA table_info(stations)").fetchall()}
    for deprecated in ("area","owner_phone","phone"):
        if deprecated in current_cols:
            con.execute(f"UPDATE stations SET {deprecated}=NULL")
    ensure_indexes(con)
    con.commit()


MLL_COLUMNS = ('Tháng', 'Mã trạm', 'P.HT', 'Loại CB', '5G', '3G', '4G', 'Ngày BĐ', 'Giờ BĐ', 'Ngày KT', 'Giờ KT', 'TG gián đoạn (phút)', 'Đơn vị xử lý', 'Mã lỗi', 'Nội dung lỗi', 'Nội dung xử lý', 'MLL tính BSC (phút)', 'MLL × số lớp (phút)', 'Mã CSHT', 'Loại CSHT')
MLL_SEED = [('Tháng 1',
  'CCH088M',
  'CCH',
  'ML',
  None,
  None,
  '4G',
  '03/01/2026',
  '06:43',
  '03/01/2026',
  '08:01',
  78,
  'UCTT-CCH',
  22,
  'Lỗi liên quan đến BR (SW, Router, Card BR..)',
  'MLL do bị treo port switch, Bình HT CCH xử lý.',
  78.5,
  78.5,
  'CSHT_HCM_00666',
  'CSHT_L2'),
 ('Tháng 1',
  'CCH097M',
  'CCH',
  'ML',
  None,
  None,
  '4G',
  '03/01/2026',
  '06:43',
  '03/01/2026',
  '08:00',
  77,
  'UCTT-CCH',
  22,
  'Lỗi liên quan đến BR (SW, Router, Card BR..)',
  'MLL do bị treo port switch, Bình HT CCH xử lý.',
  77,
  77,
  'CSHT_HCM_00352',
  'CSHT_L2'),
 ('Tháng 2',
  'CCH096M',
  'CCH',
  'ML',
  None,
  None,
  '4G',
  '03/02/2026',
  '09:16',
  '03/02/2026',
  '09:32',
  16,
  'UCTT-CCH',
  24,
  'Mất liên lạc (MLL)',
  'MLL do hư dây nhảy quang ',
  24,
  24,
  'CSHT_HCM_00675',
  'CSHT_L2'),
 ('Tháng 2',
  'CCH042M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  '21/02/2026',
  '12:26',
  '21/02/2026',
  '13:22',
  56,
  'UCTT-CCH',
  21,
  'Đứt cáp quang FO',
  'MLL do bị cháy cáp, anh Thân HT CCH xử lý.',
  84,
  84,
  'CSHT_HCM_00057',
  'CSHT_L3'),
 ('Tháng 2',
  'CCH190M',
  'CCH',
  'ML',
  None,
  None,
  '4G',
  '25/02/2026',
  '11:12',
  '25/02/2026',
  '11:33',
  21,
  'UCTT-CCH',
  13,
  'Mất liên lạc (MLL)',
  'MLL do mất điện.\n',
  31.5,
  31.5,
  'CSHT_HCM_03833',
  'CSHT_L3'),
 ('Tháng 2',
  'CCH190M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  '25/02/2026',
  '11:20',
  '25/02/2026',
  '11:35',
  15,
  'UCTT-CCH',
  13,
  'Mất liên lạc (MLL)',
  'MLL do mất điện.',
  22.5,
  22.5,
  'CSHT_HCM_03833',
  'CSHT_L3'),
 ('Tháng 3',
  'CCH095M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  '27/03/2026',
  '13:27',
  '27/03/2026',
  '13:47',
  19,
  'UCTT-CCH',
  5,
  'Mất liên lạc (MLL)',
  'MLL do treo DUW',
  30,
  30,
  'CSHT_HCM_01150',
  'CSHT_L2'),
 ('Tháng 3',
  'CCH215M',
  'CCH',
  'ML',
  None,
  None,
  '4G',
  '31/03/2026',
  '09:22',
  '31/03/2026',
  '09:53',
  31,
  'UCTT-CCH',
  22,
  'Lỗi liên quan đến BR (SW, Router, Card BR..)',
  'MLL do lỗi truyền dẫn\nMLL không rõ nguyên nhân\nBáo Hotline CCH kiểm tra',
  46.5,
  46.5,
  'CSHT_HCM_03453',
  'CSHT_L3'),
 ('Tháng 3',
  'CCH215M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  '31/03/2026',
  '09:29',
  '31/03/2026',
  '09:51',
  22,
  'UCTT-CCH',
  22,
  'Lỗi liên quan đến BR (SW, Router, Card BR..)',
  'MLL do lỗi truyền dẫn\nMLL không rõ nguyên nhân\nBáo Hotline CCH kiểm tra',
  33,
  33,
  'CSHT_HCM_03453',
  'CSHT_L3'),
 ('Tháng 4',
  'CCH240M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  '02/04/2026',
  '15:47',
  '02/04/2026',
  '18:18',
  151,
  'UCTT-CCH',
  21,
  'Đứt cáp quang FO',
  'MLL do đứt cáp quang (A Nghĩa)\nMLL do mất điện,báo Hotline CCH xử lý.',
  226.5,
  226.5,
  'CSHT_HCM_04241',
  'CSHT_L2'),
 ('Tháng 4',
  'CCH240M',
  'CCH',
  'ML',
  None,
  None,
  '4G',
  '02/04/2026',
  '15:45',
  '02/04/2026',
  '18:18',
  153,
  'UCTT-CCH',
  21,
  'Đứt cáp quang FO',
  'MLL do đứt cáp quang (A Nghĩa)\nMLL do mất điện,báo Hotline CCH xử lý.',
  229.5,
  229.5,
  'CSHT_HCM_04241',
  'CSHT_L2'),
 ('Tháng 4',
  'CCH001M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  '30/04/2026',
  '14:49',
  '30/04/2026',
  '15:07',
  18,
  'UCTT-CCH',
  5,
  'Lỗi thiết bị',
  'MLL do lỗi thiết bị DUW\n\nBáo Trung (HT CCH) xử lý.',
  27,
  27,
  'CSHT_HCM_00233',
  'CSHT_L2'),
 ('Tháng 4',
  'CCH001M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  '30/04/2026',
  '13:47',
  '30/04/2026',
  '14:04',
  17,
  'UCTT-CCH',
  5,
  'Lỗi thiết bị',
  'MLL do lỗi thiết bị DUW',
  25.5,
  25.5,
  'CSHT_HCM_00233',
  'CSHT_L2'),
 ('Tháng 5',
  'CCH194M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  46143,
  '0532',
  46143,
  '0554',
  22,
  'UCTT-CCH',
  13,
  'Mất liên lạc (MLL)',
  'MLL do mất điện accu yếu - A.Trung',
  11,
  11,
  'CSHT_HCM_03341',
  'CSHT_L2'),
 ('Tháng 5',
  'CCH160M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  46146,
  '0838',
  46146,
  '1150',
  192,
  'UCTT-CCH',
  5,
  'Mất liên lạc (MLL)',
  'MLL do hư thiết bị DUW2001. Phương (HT CCH) đang xin vật tư để xử lý.',
  288,
  288,
  'CSHT_HCM_02860',
  'CSHT_L2'),
 ('Tháng 5',
  'CCH079M',
  'CCH',
  'ML',
  '5G',
  None,
  None,
  46148,
  '1342',
  46148,
  '1421',
  38,
  'UCTT-CCH',
  24,
  'Mất liên lạc (MLL)',
  'Báo hotline PHT CCH hỗ trợ xử lý\n',
  58.5,
  58.5,
  'CSHT_HCM_00658',
  'CSHT_L2'),
 ('Tháng 5',
  'CCH007M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  46161,
  '1042',
  46161,
  '1143',
  60,
  'UCTT-CCH',
  21,
  'Mất liên lạc (MLL)',
  'MLL do đứt cáp quang',
  91.5,
  91.5,
  'CSHT_HCM_01547',
  'CSHT_L2'),
 ('Tháng 5',
  'CCH009M',
  'CCH',
  'ML',
  None,
  '3G',
  None,
  46162,
  '1419',
  46162,
  '1437',
  17,
  'UCTT-CCH',
  22,
  'Mất liên lạc (MLL)',
  'MLL do treo SW',
  27,
  27,
  'CSHT_HCM_01516',
  'CSHT_L2'),
 ('Tháng 5',
  'CCH075M',
  'CCH',
  'ML',
  '5G',
  None,
  None,
  '26/05/2026',
  '0531',
  '26/05/2026',
  '0615',
  44,
  'UCTT-CCH',
  21,
  'Mất liên lạc (MLL)',
  'MLL do đứt cáp ( Thân HTCCH)',
  29.5,
  29.5,
  'CSHT_HCM_00396',
  'CSHT_L2'),
 ('Tháng 6',
  'CCH110M',
  'CCH',
  'ML',
  '5G',
  None,
  None,
  '24/06/2026',
  2207,
  '24/06/2026',
  2242,
  35,
  'UCTT-CCH',
  21,
  'Mất liên lạc (MLL)',
  'MLL do đứt cáp quang. Thân (HT CCH) - 5 - binhphamthanh.hcm - 24/06/2026 22:46:00. Báo Thân (HT CCH) xử lý. - 6 - binhphamthanh.hcm - '
  '24/06/2026 22:13:16',
  34.99999999999987,
  35,
  'CSHT_HCM_02017',
  'CSHT_L1')]

class MLLChartWidget(QWidget):
    """Biểu đồ MLL nhẹ, trực quan, không phụ thuộc matplotlib."""
    def __init__(self, title="", kind="bar", center_label="", parent=None):
        super().__init__(parent); self.title=title; self.kind=kind; self.center_label=center_label; self.data=[]; self.legend_offset=0; self.setMinimumHeight(230)
    def set_data(self,data):
        self.data=data; self.legend_offset=max(0, min(self.legend_offset, max(0, len(data)-1))); self.update()

    def wheelEvent(self,event):
        if self.kind != "donut" or len(self.data) <= 6:
            event.ignore(); return
        delta = event.angleDelta().y()
        step = -1 if delta > 0 else 1
        max_offset=max(0, len(self.data)-6)
        self.legend_offset=max(0, min(max_offset, self.legend_offset+step))
        self.update()
        event.accept()

    def mouseMoveEvent(self,event):
        if self.kind == "donut" and self.data:
            r=self.rect(); cx=min(62, max(50, r.width()//3)); rad=min(52, max(44, r.height()//5))
            legend_x=max(cx+rad+8, r.width()//2)
            legend_w=max(80, r.width()-legend_x-6)
            y0=42; row_h=27
            rel=event.position().y()-y0
            idx=self.legend_offset + int(rel//row_h) if rel >= 0 else -1
            if event.position().x() >= legend_x and 0 <= idx < len(self.data) and idx < self.legend_offset+6:
                QToolTip.showText(event.globalPosition().toPoint(), str(self.data[idx][0]), self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); r=self.rect()
        p.setPen(QPen(QColor("#10233b"))); p.setFont(QFont("Segoe UI",10,QFont.Bold)); p.drawText(12,21,self.title)
        if not self.data:
            p.setPen(QPen(QColor("#64748b"))); p.setFont(QFont("Segoe UI",9)); p.drawText(12,48,"Chưa có dữ liệu"); return
        if self.kind=="donut":
            total=sum(float(v or 0) for _,v in self.data) or 1
            # Card dashboard dùng 5 cột bằng nhau: donut bên trái, legend gọn bên phải.
            cx=min(62, max(50, r.width()//3)); cy=112; rad=min(52, max(44, r.height()//5))
            colors=["#1473c9","#0f9aa8","#f59e0b","#ef4444","#7c5ce0"]
            start=0
            for i,(lab,val) in enumerate(self.data):
                span=360*float(val)/total; p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(colors[i%len(colors)]))); p.drawPie(cx-rad,cy-rad,rad*2,rad*2,int(start*16),int(span*16)); start+=span
            p.setBrush(QBrush(QColor("white"))); p.drawEllipse(cx-27,cy-27,54,54)
            # Trung tâm donut luôn phản ánh ĐÚNG số loại đang có trong chính
            # dữ liệu biểu đồ. Không dùng giá trị cũ/stale từ lần refresh trước.
            distinct_count = len(self.data)
            center_value = distinct_count
            center_label = f"{distinct_count} loại"
            p.setPen(QPen(QColor("#10233b"))); p.setFont(QFont("Segoe UI",14,QFont.Bold)); p.drawText(cx-34,cy-5,68,20,Qt.AlignCenter,str(center_value))
            p.setFont(QFont("Segoe UI",7)); p.setPen(QPen(QColor("#64748b"))); p.drawText(cx-42,cy+10,84,16,Qt.AlignCenter,center_label)
            legend_x=max(cx+rad+8, r.width()//2)
            legend_w=max(80, r.width()-legend_x-6)
            y=42; visible=6 if len(self.data)>6 else len(self.data)
            start_idx=min(self.legend_offset, max(0,len(self.data)-visible))
            end_idx=min(len(self.data), start_idx+visible)
            for i in range(start_idx,end_idx):
                lab,val=self.data[i]; yy=y+(i-start_idx)*27; p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(colors[i%len(colors)]))); p.drawRoundedRect(legend_x,yy,7,7,2,2)
                p.setPen(QPen(QColor("#475569"))); p.setFont(QFont("Segoe UI",7)); pct=float(val)/total*100
                label=str(lab)
                # Keep the visible text compact; hover tooltip shows the full label.
                if len(label)>12: label=label[:11]+"…"
                p.drawText(legend_x+11,yy-2,legend_w-11,15,Qt.AlignLeft,f"{label}  {pct:.0f}%")
                p.setPen(QPen(QColor("#10233b"))); p.setFont(QFont("Segoe UI",7,QFont.Bold)); p.drawText(legend_x+11,yy+11,legend_w-11,13,Qt.AlignLeft,f"{int(val):,}")
            if len(self.data)>visible:
                track_x=r.width()-7; track_y=42; track_h=visible*27-4
                thumb_h=max(16, int(track_h*visible/len(self.data)))
                max_offset=max(1,len(self.data)-visible)
                thumb_y=track_y + int((track_h-thumb_h)*start_idx/max_offset)
                p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor("#cbd5e1"))); p.drawRoundedRect(track_x,track_y,4,track_h,2,2)
                p.setBrush(QBrush(QColor("#64748b"))); p.drawRoundedRect(track_x,thumb_y,4,thumb_h,2,2)
            return
        left,top,right,bottom=38,38,14,30; x0=left; y0=r.height()-bottom; ww=r.width()-left-right; hh=r.height()-top-bottom
        if self.kind=="combo":
            vals=[float(x[1] or 0) for x in self.data]
            times=[float(x[2] or 0) for x in self.data]
            bscs=[float(x[3] or 0) if len(x)>3 else 0 for x in self.data]
            maxv=max(vals) or 1; max_time=max(times) or 1; max_bsc=max(bscs) or 1
            n=len(self.data); step=ww/max(n,1); barw=max(12,step*.45)
            p.setPen(QPen(QColor("#dbe4ee")))
            for i in range(5):
                y=y0-hh*i/4; p.drawLine(x0,int(y),x0+ww,int(y))
            for i,item in enumerate(self.data):
                lab=str(item[0]); val=vals[i]; x=x0+step*i+(step-barw)/2; bh=hh*val/maxv
                p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor("#1473c9"))); p.drawRoundedRect(int(x),int(y0-bh),int(barw),int(bh),4,4)
                p.setPen(QPen(QColor("#64748b"))); p.setFont(QFont("Segoe UI",8)); p.drawText(int(x-step*.15),y0+5,int(step*1.3),20,Qt.AlignCenter,lab.replace("Tháng ","Th."))
            pts=[]; p.setPen(QPen(QColor("#f59e0b"),2))
            for i,item in enumerate(self.data):
                x=x0+step*(i+.5); y=y0-hh*times[i]/max_time; pts.append((x,y))
                if i: p.drawLine(int(pts[i-1][0]),int(pts[i-1][1]),int(x),int(y))
                p.setBrush(QBrush(QColor("#f59e0b"))); p.drawEllipse(int(x-3),int(y-3),6,6)
                p.setPen(QPen(QColor("#d97706"))); p.setFont(QFont("Segoe UI",8,QFont.Bold)); p.drawText(int(x-18),int(y-16),36,14,Qt.AlignCenter,str(int(times[i])))
                p.setPen(QPen(QColor("#f59e0b"),2))
            bpts=[]; p.setPen(QPen(QColor("#7c5ce0"),2))
            for i,item in enumerate(self.data):
                x=x0+step*(i+.5); y=y0-hh*bscs[i]/max_bsc; bpts.append((x,y))
                if i: p.drawLine(int(bpts[i-1][0]),int(bpts[i-1][1]),int(x),int(y))
                p.setBrush(QBrush(QColor("#7c5ce0"))); p.drawEllipse(int(x-3),int(y-3),6,6)
                p.setPen(QPen(QColor("#6d28d9"))); p.setFont(QFont("Segoe UI",7,QFont.Bold)); p.drawText(int(x-20),int(y+6),40,13,Qt.AlignCenter,f"{bscs[i]:.2f}")
                p.setPen(QPen(QColor("#7c5ce0"),2))
            return
        # bar
        vals=[float(v or 0) for _,v in self.data]; maxv=max(vals) or 1; n=len(self.data); step=ww/max(n,1); barw=max(10,step*.58)
        p.setPen(QPen(QColor("#dbe4ee")))
        for i in range(5):
            y=y0-hh*i/4; p.drawLine(x0,int(y),x0+ww,int(y))
        for i,(lab,val) in enumerate(self.data):
            x=x0+step*i+(step-barw)/2; bh=hh*float(val)/maxv; p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor("#1473c9"))); p.drawRoundedRect(int(x),int(y0-bh),int(barw),int(bh),4,4)
            p.setPen(QPen(QColor("#64748b"))); p.setFont(QFont("Segoe UI",8)); label=str(lab); p.drawText(int(x-step*.2),y0+5,int(step*1.4),24,Qt.AlignCenter|Qt.TextWordWrap,label if len(label)<=12 else label[:11]+"…")


class NoticeCalendar(QCalendarWidget):
    """Lịch thông báo với hiệu ứng hover nổi khối và tooltip ngày."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setGridVisible(True)
        self._notice_marked_dates=[]
        self.setStyleSheet("""
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background: #0f6fbe;
            }
            QCalendarWidget QToolButton {
                color: white;
                font-weight: 800;
                background: transparent;
                border: 0;
                padding: 5px 8px;
            }
            QCalendarWidget QToolButton:hover {
                background: rgba(255,255,255,0.16);
                border-radius: 6px;
            }
            QCalendarWidget QAbstractItemView {
                background: white;
                selection-background-color: #1473c9;
                selection-color: white;
                gridline-color: #d9e2ec;
                outline: 0;
                font-size: 13px;
            }
            QCalendarWidget QAbstractItemView::item:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #ffffff, stop:0.45 #dceeff, stop:1 #b9d8f4);
                border: 1px solid #1473c9;
                border-radius: 7px;
                color: #0b4776;
                font-weight: 800;
            }
            QCalendarWidget QAbstractItemView::item:selected {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #2a8fe0, stop:1 #0d62a8);
                border: 1px solid #084d86;
                border-radius: 7px;
                color: white;
                font-weight: 800;
            }
        """)


class CloudLoginDialog(QDialog):
    def __init__(self, parent=None, client=None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("Đăng nhập BTS Manager Cloud")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        title = QLabel("☁  BTS Manager Cloud")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("Đăng nhập Supabase để dùng dữ liệu chung online."))
        form = QFormLayout()
        self.email = QLineEdit(); self.email.setPlaceholderText("email@example.com")
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Mật khẩu Supabase")
        form.addRow("Email:", self.email)
        form.addRow("Mật khẩu:", self.password)
        layout.addLayout(form)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self.login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def login(self):
        email = self.email.text().strip()
        password = self.password.text()
        if not email or not password:
            self.status.setText("Vui lòng nhập email và mật khẩu.")
            return
        try:
            self.status.setText("Đang đăng nhập và kiểm tra database...")
            QApplication.processEvents()
            self.client.sign_in(email, password)
            # Login must not probe every table serially. A single lightweight
            # authenticated request is enough to validate the session; full
            # schema/data checks run during background bootstrap.
            status, payload = self.client._request('GET', '/rest/v1/stations?select=code&limit=1', token=self.client.access_token)
            if status >= 400:
                raise RuntimeError(str(payload))
            self.status.setText("Kết nối Cloud thành công.")
            self.accept()
        except Exception as e:
            self.status.setText(f"Không thể kết nối Cloud: {e}")


class AdminCreateUserDialog(QDialog):
    ADMIN_EMAIL = "tntsang@gmail.com"
    PERMISSIONS = [
        ("dashboard", "📊 Tổng quan / Dashboard"),
        ("stations", "📡 Quản lý trạm BTS"),
        ("contracts", "📄 Hợp đồng"),
        ("equipment", "🔧 Thiết bị"),
        ("transmission", "🔗 Truyền dẫn"),
        ("power", "⚡ Nguồn & Battery"),
        ("maintenance", "🛠 BTBD / Bảo dưỡng"),
        ("mll", "🚨 MLL / Mất liên lạc"),
        ("import_export", "📥 Import / Export dữ liệu"),
        ("edit", "✏️ Thêm / Sửa dữ liệu"),
        ("delete", "🗑 Xóa dữ liệu"),
        ("sync", "☁ Đồng bộ Cloud"),
        ("notifications.create_own", "🔔 Tạo thông báo cá nhân"),
        ("notifications.write", "🔔 Quản lý thông báo"),
    ]

    def __init__(self, parent=None, client=None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("Tạo tài khoản BTS Manager")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        title = QLabel("👤  TẠO TÀI KHOẢN NGƯỜI DÙNG")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel("Chỉ tài khoản Admin mới có quyền tạo user mới."))
        form = QFormLayout()
        self.email = QLineEdit(); self.email.setPlaceholderText("user@example.com")
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.Password); self.password.setPlaceholderText("Mật khẩu tối thiểu 8 ký tự")
        self.password2 = QLineEdit(); self.password2.setEchoMode(QLineEdit.Password); self.password2.setPlaceholderText("Nhập lại mật khẩu")
        form.addRow("Email user:", self.email)
        form.addRow("Mật khẩu:", self.password)
        form.addRow("Xác nhận:", self.password2)
        layout.addLayout(form)

        perm_box = QGroupBox("🔐 Phân quyền user")
        perm_layout = QGridLayout(perm_box)
        self.permission_checks = {}
        for i, (key, label) in enumerate(self.PERMISSIONS):
            cb = QCheckBox(label)
            cb.setChecked(key in {"dashboard", "stations", "mll", "sync", "notifications.create_own"})
            self.permission_checks[key] = cb
            perm_layout.addWidget(cb, i // 2, i % 2)
        self.select_all_btn = QPushButton("☑ Chọn tất cả")
        self.clear_all_btn = QPushButton("☐ Bỏ chọn tất cả")
        self.select_all_btn.clicked.connect(lambda: self._set_all_permissions(True))
        self.clear_all_btn.clicked.connect(lambda: self._set_all_permissions(False))
        perm_layout.addWidget(self.select_all_btn, (len(self.PERMISSIONS)+1)//2, 0)
        perm_layout.addWidget(self.clear_all_btn, (len(self.PERMISSIONS)+1)//2, 1)
        layout.addWidget(perm_box)
        hint = QLabel("Admin hệ thống luôn có toàn quyền. User thường chỉ được sử dụng các chức năng được tích chọn.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748b;")
        layout.addWidget(hint)

        self.status = QLabel(""); self.status.setWordWrap(True); layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self.create_user); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all_permissions(self, checked):
        for cb in self.permission_checks.values():
            cb.setChecked(checked)

    def _selected_permissions(self):
        return [key for key, cb in self.permission_checks.items() if cb.isChecked()]

    def create_user(self):
        email = self.email.text().strip().lower()
        pw = self.password.text()
        pw2 = self.password2.text()
        if not email or '@' not in email:
            self.status.setText("Email không hợp lệ.")
            return
        if len(pw) < 8:
            self.status.setText("Mật khẩu phải có ít nhất 8 ký tự.")
            return
        if pw != pw2:
            self.status.setText("Hai mật khẩu không giống nhau.")
            return
        try:
            self.status.setText("Đang tạo tài khoản trên Supabase...")
            QApplication.processEvents()
            permissions = self._selected_permissions()
            if not permissions:
                self.status.setText("Vui lòng chọn ít nhất 1 quyền cho user.")
                return
            self.client.create_user(email, pw, permissions)
            QMessageBox.information(self, "Tạo user", "Đã tạo tài khoản: %s\n\nQuyền: %s\n\nUser có thể đăng nhập BTS Manager ngay." % (email, ", ".join(permissions)))
            self.accept()
        except Exception as e:
            self.status.setText("Không thể tạo user: %s" % e)


class ChangePasswordDialog(QDialog):
    def __init__(self, parent=None, client=None, target_email=None, admin_reset=False, user_id=None):
        super().__init__(parent); self.client=client; self.target_email=target_email or ""; self.admin_reset=admin_reset; self.user_id=user_id
        self.setWindowTitle("Đổi mật khẩu" if not admin_reset else f"Đặt lại mật khẩu • {self.target_email}")
        self.setMinimumWidth(440)
        layout=QVBoxLayout(self)
        title=QLabel("🔑  ĐỔI MẬT KHẨU" if not admin_reset else "🔐  ĐẶT LẠI MẬT KHẨU USER"); title.setObjectName("pageTitle"); layout.addWidget(title)
        if self.target_email: layout.addWidget(QLabel(f"Tài khoản: {self.target_email}"))
        form=QFormLayout()
        self.password=QLineEdit(); self.password.setEchoMode(QLineEdit.Password); self.password.setPlaceholderText("Tối thiểu 8 ký tự")
        self.password2=QLineEdit(); self.password2.setEchoMode(QLineEdit.Password); self.password2.setPlaceholderText("Nhập lại mật khẩu")
        form.addRow("Mật khẩu mới:",self.password); form.addRow("Xác nhận:",self.password2); layout.addLayout(form)
        self.status=QLabel(""); self.status.setWordWrap(True); layout.addWidget(self.status)
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Ok); buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def submit(self):
        pw=self.password.text(); pw2=self.password2.text()
        if len(pw)<8: self.status.setText("Mật khẩu phải có ít nhất 8 ký tự."); return
        if pw!=pw2: self.status.setText("Hai mật khẩu không giống nhau."); return
        try:
            self.status.setText("Đang cập nhật mật khẩu..."); QApplication.processEvents()
            if self.admin_reset: self.client.admin_reset_password(self.user_id,pw)
            else: self.client.change_my_password(pw)
            QMessageBox.information(self,"Mật khẩu","Đã cập nhật mật khẩu thành công.")
            self.accept()
        except Exception as e: self.status.setText(f"Không thể cập nhật mật khẩu: {e}")


class AdminUserManagementDialog(QDialog):
    def __init__(self, parent=None, client=None):
        super().__init__(parent); self.client=client; self.setWindowTitle("Quản lý người dùng BTS Manager"); self.resize(920,560)
        layout=QVBoxLayout(self)
        title=QLabel("👥  QUẢN LÝ NGƯỜI DÙNG"); title.setObjectName("pageTitle"); layout.addWidget(title)
        layout.addWidget(QLabel("Chỉ Admin hệ thống mới có thể đặt lại mật khẩu hoặc thay đổi quyền của user."))
        top=QHBoxLayout(); self.refresh_btn=QPushButton("↻ Làm mới"); self.create_btn=QPushButton("👤 Tạo user"); top.addWidget(self.refresh_btn); top.addWidget(self.create_btn); top.addStretch(); layout.addLayout(top)
        self.table=QTableWidget(0,4); self.table.setHorizontalHeaderLabels(["Email","Tạo ngày","Quyền","Thao tác"]); self.table.setAlternatingRowColors(True); self.table.horizontalHeader().setStretchLastSection(True); self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch); layout.addWidget(self.table)
        self.status=QLabel(""); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.refresh_btn.clicked.connect(self.load_users); self.create_btn.clicked.connect(self.open_create); self.load_users()
    def load_users(self):
        try:
            self.status.setText("Đang tải danh sách user..."); QApplication.processEvents(); users=self.client.list_users(); self.table.setRowCount(0)
            for u in users:
                r=self.table.rowCount(); self.table.insertRow(r); email=u.get('email','');
                self.table.setItem(r,0,QTableWidgetItem(email)); self.table.setItem(r,1,QTableWidgetItem((u.get('created_at') or '')[:19].replace('T',' ')))
                perms=u.get('permissions') or []; self.table.setItem(r,2,QTableWidgetItem('ADMIN – toàn quyền' if email.lower()==AdminCreateUserDialog.ADMIN_EMAIL else ', '.join(perms)))
                cell=QWidget(); h=QHBoxLayout(cell); h.setContentsMargins(3,2,3,2)
                reset=QPushButton("🔑 Đổi MK"); reset.setEnabled(email.lower()!=AdminCreateUserDialog.ADMIN_EMAIL); reset.clicked.connect(lambda _, uid=u.get('id'), em=email: self.reset_user(uid,em))
                h.addWidget(reset)
                perm=QPushButton("🔐 Quyền"); perm.setEnabled(email.lower()!=AdminCreateUserDialog.ADMIN_EMAIL); perm.clicked.connect(lambda _, uid=u.get('id'), em=email, ps=perms: self.edit_permissions(uid,em,ps)); h.addWidget(perm)
                delete=QPushButton("🗑 Xóa")
                delete.setEnabled(email.lower()!=AdminCreateUserDialog.ADMIN_EMAIL)
                delete.clicked.connect(lambda _, uid=u.get('id'), em=email: self.delete_user(uid,em))
                h.addWidget(delete)
                self.table.setCellWidget(r,3,cell)
            self.status.setText(f"Đã tải {len(users)} tài khoản.")
        except Exception as e: self.status.setText(f"Không tải được danh sách user: {e}")
    def reset_user(self,user_id,email):
        dlg=ChangePasswordDialog(self,self.client,email,True,user_id); dlg.exec(); self.load_users()
    def edit_permissions(self,user_id,email,current):
        dlg=PermissionEditDialog(self,self.client,user_id,email,current); dlg.exec(); self.load_users()
    def delete_user(self,user_id,email):
        if email.lower()==AdminCreateUserDialog.ADMIN_EMAIL:
            QMessageBox.warning(self,"Xóa user","Không thể xóa tài khoản Admin hệ thống.")
            return
        answer=QMessageBox.question(
            self,"Xóa user",
            f"Bạn có chắc muốn xóa tài khoản:\n\n{email}\n\nTài khoản sẽ không thể đăng nhập sau khi xóa.",
            QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            self.status.setText(f"Đang xóa user {email}..."); QApplication.processEvents()
            self.client.delete_user(user_id)
            QMessageBox.information(self,"Xóa user",f"Đã xóa tài khoản: {email}")
            self.load_users()
        except Exception as e:
            QMessageBox.critical(self,"Xóa user",f"Không thể xóa user: {e}")
            self.status.setText(f"Không thể xóa user: {e}")
    def open_create(self):
        if AdminCreateUserDialog(self,self.client).exec()==QDialog.Accepted: self.load_users()


class PermissionEditDialog(QDialog):
    PERMISSIONS=AdminCreateUserDialog.PERMISSIONS
    def __init__(self,parent=None,client=None,user_id=None,email='',current=None):
        super().__init__(parent); self.client=client; self.user_id=user_id; self.email=email; current=set(current or [])
        self.setWindowTitle(f"Phân quyền • {email}"); self.setMinimumWidth(560); layout=QVBoxLayout(self); title=QLabel("🔐  PHÂN QUYỀN USER"); title.setObjectName("pageTitle"); layout.addWidget(title); layout.addWidget(QLabel(email))
        box=QGroupBox("Quyền được phép sử dụng"); grid=QGridLayout(box); self.checks={}
        for i,(key,label) in enumerate(self.PERMISSIONS):
            cb=QCheckBox(label); cb.setChecked(key in current); self.checks[key]=cb; grid.addWidget(cb,i//2,i%2)
        layout.addWidget(box); self.status=QLabel(""); layout.addWidget(self.status); buttons=QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Save); buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def save(self):
        try:
            perms=[k for k,c in self.checks.items() if c.isChecked()]; self.client.update_user_permissions(self.user_id,perms); QMessageBox.information(self,"Phân quyền","Đã cập nhật quyền cho user."); self.accept()
        except Exception as e: self.status.setText(f"Không thể cập nhật quyền: {e}")


class CloudSyncManager:
    TABLE_KEYS = {
        'stations':'code','contracts':'contract_id','equipment':'equipment_id',
        'transmission':'transmission_id','power':'power_id','batteries':'battery_id',
        'auxiliary':'aux_id','maintenance':'work_id','mll_events':'id','kpi_targets':'content','notifications':'sync_key'
    }

    def __init__(self, app, client, db_con=None):
        self.app = app
        self.client = client
        self.con = db_con if db_con is not None else app.con
        self.syncing = False
        self.last_conflicts = []
        self.state_path = DATA_ROOT / 'cloud_sync_state.json'
        self.log_dir = DATA_ROOT / 'cloud_sync_logs'
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_log = self.log_dir / f"sync_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_runtime.log"
        self._diag("SYNC MANAGER START")

    def _diag(self, message):
        """Write runtime Cloud Sync diagnostics immediately, including mid-sync failures."""
        try:
            stamp=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            with self.runtime_log.open('a', encoding='utf-8') as f:
                f.write(f"[{stamp}] {message}\n")
        except Exception:
            pass

    def _local_columns(self, table):
        return [r[1] for r in self.con.execute(f"PRAGMA table_info({table})").fetchall()]

    def _local_rows(self, table):
        return [dict(r) for r in self.con.execute(f"SELECT * FROM {table}").fetchall()]

    @staticmethod
    def _ts(value):
        if not value:
            return 0.0
        try:
            s=str(value).replace('Z','+00:00')
            dt=datetime.datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt=dt.replace(tzinfo=datetime.timezone.utc)
            return dt.timestamp()
        except Exception:
            return 0.0

    def _load_state(self):
        try:
            return json.loads(self.state_path.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _save_state(self, state):
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

    def is_bootstrapped(self):
        state=self._load_state()
        return bool(state.get('cloud_bootstrapped') and state.get('project_url') == getattr(self.client,'url',''))

    def _write_sync_log(self, result):
        tag=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        path=self.log_dir/f'sync_{tag}.json'
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        return path

    def _fetch_cloud_rows(self, table, key):
        rows=[]; offset=0; started=time.monotonic()
        self._diag(f"TABLE {table} START key={key}")
        while True:
            page_started=time.monotonic()
            try:
                page=self.client.select(table, f'select=*&order={urllib.parse.quote(key)}.asc&limit=1000&offset={offset}')
            except Exception as e:
                elapsed=time.monotonic()-page_started
                self._diag(f"TABLE {table} ERROR offset={offset} elapsed={elapsed:.3f}s error={type(e).__name__}: {e}")
                raise RuntimeError(f"Cloud Sync lỗi tại bảng {table}, offset={offset}, sau {elapsed:.1f}s: {e}") from e
            elapsed=time.monotonic()-page_started
            rows.extend(page)
            self._diag(f"TABLE {table} PAGE offset={offset} rows={len(page)} elapsed={elapsed:.3f}s total={len(rows)}")
            if len(page)<1000:
                self._diag(f"TABLE {table} OK rows={len(rows)} elapsed_total={time.monotonic()-started:.3f}s")
                return rows
            offset += 1000

    def _upsert_local(self, table, row, key):
        """Merge a Cloud row into SQLite without allowing notification IDs to collide.

        Notifications are identified across devices by sync_key, NOT by the
        numeric SQLite/Postgres id. A Cloud row can legitimately have id=17
        while this PC already has an unrelated local notification id=17. The
        old generic merge copied Cloud ``id`` into SQLite and could therefore
        fail with UNIQUE constraint failed: notifications.id during bootstrap.

        For notifications we therefore:
          1) match/update by sync_key;
          2) never overwrite the local numeric id;
          3) when inserting a new Cloud row, omit id so SQLite allocates a safe
             local id.
        """
        cols=self._local_columns(table)
        row={k:v for k,v in row.items() if k in cols}
        if key not in row:
            return

        is_notification = (table == 'notifications' and key == 'sync_key')
        is_station = (table == 'stations' and key == 'code')
        existing=self.con.execute(f"SELECT 1 FROM {table} WHERE {key}=?",(row[key],)).fetchone()
        if existing:
            # SQLite station/notification ids are local row identities. Cloud
            # sync is keyed by stations.code / notifications.sync_key, so never
            # overwrite a local numeric id with a Cloud id that may belong to a
            # different local row.
            update_cols=[c for c in row if c != key and not ((is_notification or is_station) and c == 'id')]
            if update_cols:
                self.con.execute(
                    f"UPDATE {table} SET "+','.join(f"{c}=?" for c in update_cols)+f" WHERE {key}=?",
                    [row[c] for c in update_cols]+[row[key]]
                )
        else:
            if is_notification or is_station:
                # Cloud/Postgres id is not the cross-device identity for these
                # tables. Omit it so SQLite allocates a safe local id and cannot
                # fail on an unrelated existing local id.
                row.pop('id', None)
            names=list(row.keys())
            self.con.execute(
                f"INSERT INTO {table} ({','.join(names)}) VALUES ({','.join('?' for _ in names)})",
                [row[c] for c in names]
            )

    def pull(self, cloud_cache=None, bootstrap=False):
        stats=[]
        cache=cloud_cache or {}
        for table,key in self.TABLE_KEYS.items():
            cloud_rows=cache.get(table) if table in cache else self._fetch_cloud_rows(table,key)
            local_rows={str(r[key]):r for r in self._local_rows(table) if r.get(key) is not None}
            changed=0
            for crow in cloud_rows:
                k=str(crow.get(key)); lrow=local_rows.get(k)
                # Cloud is authoritative on first connection. On normal sync,
                # only a strictly newer Cloud row replaces local data.
                if bootstrap or lrow is None or self._ts(crow.get('updated_at')) > self._ts(lrow.get('updated_at')):
                    self._upsert_local(table,crow,key); changed += 1
            stats.append(f"{table}: cloud={len(cloud_rows)} • local cập nhật={changed}")
        self.con.commit()
        return stats

    def push(self, cloud_cache):
        stats=[]; conflicts=[]
        state=self._load_state(); baseline=self._ts(state.get('bootstrap_completed_at'))
        for table,key in self.TABLE_KEYS.items():
            cloud_rows=cloud_cache.get(table,[])
            cloud_map={str(r.get(key)):r for r in cloud_rows if r.get(key) is not None}
            local_rows=self._local_rows(table)
            pushed=0; skipped=0
            cols=self._local_columns(table)
            for r in local_rows:
                k=r.get(key)
                if k is None: continue
                crow=cloud_map.get(str(k))
                local_ts=self._ts(r.get('updated_at'))
                if crow is not None:
                    cloud_ts=self._ts(crow.get('updated_at'))
                    if local_ts <= cloud_ts:
                        skipped += 1
                        continue
                    clean={c:r[c] for c in cols if c in r and c not in {'id','created_at','updated_at'}}
                    try:
                        returned=self.client.update_if_unchanged(table,key,k,crow.get('updated_at'),clean)
                    except Exception as e:
                        conflicts.append({'table':table,'key':k,'reason':str(e)})
                        continue
                    if returned:
                        self._upsert_local(table,returned[0],key); pushed += 1
                    else:
                        conflicts.append({'table':table,'key':k,'reason':'Cloud row changed concurrently'})
                else:
                    # A fresh PC must never seed Cloud. Normal push only occurs
                    # after the local database has completed its first Cloud pull.
                    if not self.is_bootstrapped() or local_ts <= baseline:
                        skipped += 1; continue
                    clean={c:r[c] for c in cols if c in r and c not in {'id','created_at','updated_at'}}
                    try:
                        returned=self.client.insert(table,clean,return_representation=True)
                    except Exception as e:
                        conflicts.append({'table':table,'key':k,'reason':str(e)})
                        continue
                    if returned:
                        self._upsert_local(table,returned[0],key); pushed += 1
            stats.append(f"{table}: push={pushed} • bỏ qua={skipped}")
        self.con.commit()
        return stats, conflicts

    @staticmethod
    def _mll_reason_group(text):
        s=str(text or '').lower()
        if 'br' in s or 'switch' in s or 'router' in s: return 'Lỗi BR / SW'
        if 'quang' in s or 'cáp' in s or 'cap ' in s: return 'Đứt cáp / FO'
        if 'điện' in s or 'nguồn' in s or 'ac' in s: return 'Nguồn điện'
        if 'duw' in s or 'rru' in s or 'bbu' in s or 'thiết bị' in s: return 'Lỗi thiết bị'
        if 'truyền dẫn' in s: return 'Truyền dẫn'
        return 'Khác'

    def _get_kpi_target(self, *names):
        import unicodedata as _ud, re as _re
        def norm(v):
            if v is None: return ''
            s=_ud.normalize('NFKC', str(v)).replace('\u00a0',' ').strip().casefold()
            s=_ud.normalize('NFD', s)
            s=''.join(ch for ch in s if _ud.category(ch)!='Mn')
            return _re.sub(r'[^a-z0-9]+','',s)
        wanted={norm(x) for x in names if norm(x)}
        rows=self.con.execute('SELECT content, target, actual FROM kpi_targets').fetchall()
        for row in rows:
            if norm(row[0]) in wanted and row[1] not in (None,''):
                return row[1]
        return None

    def sync_pc_mll_results(self):
        """Publish PC-authoritative MLL results for Mobile.

        The desktop dashboard remains the single source of truth.  Mobile never
        recomputes these metrics.  We publish:
          - mll_bsc_summary: exact imported BSC TỔNG rows
          - mll_analysis_summary: derived dashboard results for every month range
        """
        # 1) Exact BSC TỔNG rows from the same local table the PC dashboard uses.
        bsc_rows = self.con.execute(
            "SELECT dept, month_no, value, avg_6m FROM mll_bsc_summary "
            "ORDER BY month_no, dept"
        ).fetchall()
        def safe_float(value, default=None):
            """Convert numeric MLL data without letting one malformed cell stop Cloud sync."""
            if value is None or value == "":
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        bad_bsc = []
        bsc_payload = []
        for r in bsc_rows:
            value = safe_float(r[2], None)
            avg_6m = safe_float(r[3], None)
            if r[2] not in (None, "") and value is None:
                bad_bsc.append({"dept": r[0] or "", "month_no": r[1], "value": r[2]})
            try:
                month_no = int(r[1])
            except (TypeError, ValueError):
                continue
            bsc_payload.append({
                "dept": r[0] or "",
                "month_no": month_no,
                "value": value,
                "avg_6m": avg_6m
            })
        if bad_bsc:
            print(f"PC MLL: bỏ qua giá trị BSC không phải số: {bad_bsc[:10]}")

        # 2) Publish all 78 month ranges (1..12).  This lets Mobile select any
        # range without inventing a calculation that could diverge from PC.
        rows = self.con.execute(
            "SELECT month, station_code, g5, g3, g4, downtime_min, "
            "error_content, resolution FROM mll_events"
        ).fetchall()

        bad_event_numeric = []
        for idx, r in enumerate(rows, 1):
            for label, pos in (("g3", 3), ("g4", 4), ("downtime_min", 5)):
                if r[pos] not in (None, "") and safe_float(r[pos], None) is None:
                    bad_event_numeric.append({"row": idx, "field": label, "value": r[pos]})
        if bad_event_numeric:
            print(f"PC MLL: dùng 0 cho dữ liệu sự kiện không phải số: {bad_event_numeric[:10]}")

        def reason_group(text):
            return self._mll_reason_group(text)

        def calc(fm, tm):
            months = [f"Tháng {i}" for i in range(fm, tm + 1)]
            selected = set(months)
            ev = [r for r in rows if str(r[0] or "") in selected]
            cases = len(ev)
            # downtime_min can contain malformed imported text (e.g. "4G").
            # Never let one bad event abort the entire PC-authoritative MLL publish.
            total = sum(safe_float(r[5], 0.0) or 0.0 for r in ev)
            stations = len({str(r[1]).strip() for r in ev if str(r[1] or "").strip()})
            avg = total / cases if cases else 0.0

            reasons = {}
            services = {"3G": 0, "4G": 0, "5G": 0}
            month_map = {m: {"cases": 0, "minutes": 0.0} for m in months}
            for r in ev:
                m = str(r[0] or "")
                month_map[m]["cases"] += 1
                month_map[m]["minutes"] += safe_float(r[5], 0.0) or 0.0
                grp = reason_group(r[6] or r[7])
                reasons[grp] = reasons.get(grp, 0) + 1
                for label, pos in (("3G", 3), ("4G", 4), ("5G", 2)):
                    if str(r[pos] or "").strip():
                        services[label] += 1

            top_reason = max(reasons, key=reasons.get) if reasons else "—"

            # Use the same BSC monthly aggregation as refresh_mll_dashboard().
            bsc_by_month = {i: [] for i in range(fm, tm + 1)}
            for r in bsc_rows:
                try:
                    mn = int(r[1])
                    if fm <= mn <= tm:
                        v = safe_float(r[2], None)
                        if v is not None:
                            bsc_by_month[mn].append(v)
                except Exception:
                    pass
            monthly = []
            for mn in range(fm, tm + 1):
                bsc_vals = bsc_by_month.get(mn, [])
                monthly.append({
                    "month": f"Tháng {mn}",
                    "cases": month_map[f"Tháng {mn}"]["cases"],
                    "minutes": month_map[f"Tháng {mn}"]["minutes"],
                    "bsc": (sum(bsc_vals) / len(bsc_vals)) if bsc_vals else 0.0
                })

            station_map = {}
            for r in ev:
                code = str(r[1] or '').strip() or 'Không rõ'
                item = station_map.setdefault(code, {'cases': 0, 'minutes': 0.0})
                item['cases'] += 1
                item['minutes'] += safe_float(r[5], 0.0) or 0.0
            top_sites = [
                {'station': code, 'cases': int(item['cases']), 'minutes': float(item['minutes'])}
                for code, item in sorted(station_map.items(), key=lambda x: x[1]['minutes'], reverse=True)[:8]
            ]
            longest = [{
                'station': str(r[1] or ''), 'month': str(r[0] or ''),
                'reason': reason_group(r[6] or r[7]), 'minutes': safe_float(r[5], 0.0) or 0.0
            } for r in sorted(ev, key=lambda x: safe_float(x[5], 0.0) or 0.0, reverse=True)[:5]]
            all_bsc = []
            for r in bsc_rows:
                try:
                    mn = int(r[1])
                except (TypeError, ValueError):
                    continue
                if fm <= mn <= tm:
                    v = safe_float(r[2], None)
                    if v is not None:
                        all_bsc.append(v)
            exact_bsc_avg = (int((sum(all_bsc) / len(all_bsc)) * 100) / 100) if all_bsc else None
            bsc_target = None
            try:
                bsc_target = self._get_kpi_target('MLL', 'Mất LL', 'Mất liên lạc', 'Mất LL (TB BSC)')
            except Exception:
                pass
            peak = max(months, key=lambda m: month_map[m]['minutes']) if months else '—'
            peak_mins = month_map.get(peak, {}).get('minutes', 0.0)
            peak_station = top_sites[0]['station'] if top_sites else '—'
            peak_station_mins = top_sites[0]['minutes'] if top_sites else 0.0
            share = reasons.get(top_reason, 0) / cases * 100 if cases else 0.0
            first_m, last_m = months[0], months[-1]
            first_cases, first_mins = month_map[first_m]['cases'], month_map[first_m]['minutes']
            last_cases, last_mins = month_map[last_m]['cases'], month_map[last_m]['minutes']
            def pct_change(a, b):
                if a == 0: return None if b == 0 else 100.0
                return (b-a)/a*100.0
            def trend(delta):
                if delta is None: return 'mới phát sinh'
                if abs(delta) < 0.1: return 'ổn định'
                return f'tăng {delta:.0f}%' if delta > 0 else f'giảm {abs(delta):.0f}%'
            trend_text = (
                f'Số vụ từ {first_m} → {last_m}: {trend(pct_change(first_cases,last_cases))}; '
                f'thời gian gián đoạn: {trend(pct_change(first_mins,last_mins))}.'
                if first_m != last_m else f'Khoảng phân tích chỉ gồm {first_m}.'
            )
            insight = (
                f'Đánh giá: {peak} có thời gian gián đoạn cao nhất ({peak_mins:,.0f} phút). '
                f'Trạm {peak_station} có tổng thời gian gián đoạn lớn nhất ({peak_station_mins:,.0f} phút). '
                f'Nhóm {top_reason} chiếm khoảng {share:.0f}% số vụ. {trend_text}'
            )
            return {
                "range_key": f"{fm}-{tm}",
                "from_month": fm,
                "to_month": tm,
                "cases": cases,
                "total_downtime": total,
                "avg_per_event": avg,
                "total_bsc": sum(safe_float(r[3], 0.0) or 0.0 for r in ev),
                "total_layer": sum(safe_float(r[4], 0.0) or 0.0 for r in ev),
                "stations": stations,
                "top_reason": top_reason,
                "bsc_avg": exact_bsc_avg,
                "bsc_target": bsc_target,
                "monthly_json": monthly,
                "reason_json": sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:5],
                "service_json": {k: v for k, v in services.items() if v},
                "top_station_json": top_sites,
                "longest_json": longest,
                "insight": insight
            }

        analysis_payload = [calc(fm, tm) for fm in range(1, 13) for tm in range(fm, 13)]

        # mll_analysis_summary is sufficient for the Mobile dashboard because
        # monthly_json and bsc_avg carry the PC-authoritative values.  Publish it
        # even when an older Supabase project has not yet created
        # mll_bsc_summary; this prevents one missing compatibility table from
        # blocking the entire MLL sync.
        bsc_published = len(bsc_payload)
        try:
            self.client.replace_rows("mll_bsc_summary", bsc_payload)
        except Exception as e:
            msg = str(e)
            if "42P01" in msg or "mll_bsc_summary" in msg:
                bsc_published = 0
            else:
                raise

        self.client.replace_rows("mll_analysis_summary", analysis_payload)
        return bsc_published, len(analysis_payload)

    def sync(self, bootstrap=False):
        if self.syncing:
            return [], []
        self.syncing=True
        self._diag(f"SYNC START bootstrap={bootstrap}")
        try:
            cloud_cache={}
            for table,key in self.TABLE_KEYS.items():
                cloud_cache[table]=self._fetch_cloud_rows(table,key)
            self._diag("ALL CLOUD TABLES FETCHED")
            pull_stats=self.pull(cloud_cache=cloud_cache, bootstrap=bootstrap)
            # V85.56 diagnostic: notifications are now a first-class synced table.
            try:
                ncloud=self._fetch_cloud_rows('notifications','sync_key')
                nlocal=self._local_rows('notifications')
                mobile_cloud=sum(1 for r in ncloud if str(r.get('sync_key') or '').startswith('MOBILE|'))
                mobile_local=sum(1 for r in nlocal if str(r.get('sync_key') or '').startswith('MOBILE|'))
                pull_stats.append(f"notifications: Cloud={len(ncloud)} • MOBILE Cloud={mobile_cloud} • MOBILE PC={mobile_local}")
            except Exception as e:
                pull_stats.append(f"notifications diagnostic lỗi: {e}")
            # First connection is always Cloud -> Local only. This prevents a
            # fresh PC's demo/cache rows from ever overwriting production data.
            push_stats=[]; conflicts=[]
            if self.is_bootstrapped():
                push_stats,conflicts=self.push(cloud_cache)
                if conflicts:
                    # Re-read conflicted rows so the newer Cloud version wins.
                    for table,key in self.TABLE_KEYS.items():
                        if any(c['table']==table for c in conflicts):
                            rows=self._fetch_cloud_rows(table,key)
                            self.pull({table:rows})
            else:
                state=self._load_state()
                completed=datetime.datetime.now(datetime.timezone.utc).isoformat()
                state.update({'cloud_bootstrapped':True,'bootstrapped_at':completed,'bootstrap_completed_at':completed,
                              'project_url':getattr(self.client,'url','')})
                self._save_state(state)
                push_stats=['First Cloud connection: pull-only bootstrap • không đẩy dữ liệu local lên Cloud']
            mll_sync_note = None
            if self.is_bootstrapped():
                try:
                    bsc_n, analysis_n = self.sync_pc_mll_results()
                    mll_sync_note = f"PC MLL authoritative: BSC={bsc_n} rows • ranges={analysis_n}"
                    push_stats.append(mll_sync_note)
                except Exception as e:
                    push_stats.append(f"PC MLL authoritative sync lỗi: {e}")
            self.last_conflicts=conflicts
            result={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bootstrap':bootstrap,
                    'pull':pull_stats,'push':push_stats,'conflicts':conflicts}
            self._write_sync_log(result)
            self._diag(f"SYNC OK pull={len(pull_stats)} push={len(push_stats)} conflicts={len(conflicts)}")
            return pull_stats+push_stats, conflicts
        except Exception as e:
            self._diag(f"SYNC ERROR {type(e).__name__}: {e}")
            raise
        finally:
            self._diag("SYNC END")
            self.syncing=False

def ensure_cloud_local_columns(con):
    """Adds sync timestamps to local tables without changing existing user data."""
    tables=['stations','contracts','equipment','transmission','power','batteries','auxiliary','maintenance','mll_events','kpi_targets']
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    for table in tables:
        cols={r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if 'updated_at' not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN updated_at TEXT")
            con.execute(f"UPDATE {table} SET updated_at=? WHERE updated_at IS NULL",(now,))
        # SQLite trigger updates the timestamp whenever a local record changes.
        trig=f"trg_{table}_cloud_updated_at"
        con.execute(f"DROP TRIGGER IF EXISTS {trig}")
        con.execute(f"DROP TRIGGER IF EXISTS {trig}_ins")
        con.execute(f"""
            CREATE TRIGGER {trig}_ins
            AFTER INSERT ON {table}
            FOR EACH ROW WHEN NEW.updated_at IS NULL
            BEGIN
              UPDATE {table} SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
              WHERE rowid = NEW.rowid;
            END;
        """)
        con.execute(f"""
            CREATE TRIGGER {trig}
            AFTER UPDATE ON {table}
            FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at OR NEW.updated_at IS NULL
            BEGIN
              UPDATE {table} SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
              WHERE rowid = NEW.rowid;
            END;
        """)
    con.commit()

class CloudSyncWorker(QThread):
    finished_sync = Signal(object, object, object)

    def __init__(self, client, bootstrap=False):
        super().__init__()
        self.client = client
        self.bootstrap = bootstrap

    def run(self):
        con = None
        try:
            # Dedicated SQLite connection: network/database work never touches
            # the UI connection, so a slow Supabase request cannot freeze Qt.
            con = sqlite3.connect(DB, cached_statements=256, timeout=30)
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA busy_timeout=30000')
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('PRAGMA synchronous=NORMAL')
            con.execute('PRAGMA temp_store=MEMORY')
            con.execute('PRAGMA cache_size=-20000')
            mgr = CloudSyncManager(None, self.client, db_con=con)
            last_error = None
            for attempt in range(3):
                try:
                    stats, conflicts = mgr.sync(bootstrap=self.bootstrap)
                    self.finished_sync.emit(stats, conflicts, None)
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    if attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
            if last_error is not None:
                self.finished_sync.emit([], [], str(last_error))
        except Exception as e:
            self.finished_sync.emit([], [], str(e))
        finally:
            if con is not None:
                try: con.close()
                except Exception: pass


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.con = connect_db()
        ensure_schema(self.con)
        ensure_cloud_local_columns(self.con)
        self.seed_mll_data()
        self.cloud_client = None
        self.cloud_sync = None
        self.admin_create_user_btn = None
        self.admin_reset_data_btn = None
        self.cloud_logged_in = False
        self.user_permissions = set()
        self.init_notifications()
        self.notified_ids = set()
        self.notification_timer = QTimer(self)
        self.notification_timer.timeout.connect(self.check_notifications)
        self.notification_timer.start(15000)
        cloud_state = "☁ Supabase" if CLOUD_CONFIG.exists() else "☁ Local"
        self.setWindowTitle(f"BTS Manager • Phòng Hạ tầng Củ Chi • {cloud_state}")
        self.resize(1440, 900)
        self.setMinimumSize(1180, 760)
        self.apply_style()
        self.build_ui()
        self.cloud_timer = QTimer(self)
        self.cloud_timer.timeout.connect(self.sync_cloud_silent)
        # Online Sync: 45-second background refresh after Cloud login.
        # First login is always pull-only; later sync uses optimistic concurrency.
        self.cloud_timer.start(45000)
        # Hiển thị giao diện trước, sau đó mới nạp KPI/MLL. Điều này giúp cửa sổ
        # xuất hiện nhanh và không bị cảm giác treo khi database lớn.
        QTimer.singleShot(0, self._initial_dashboard_refresh)

    def _initial_dashboard_refresh(self):
        try:
            self.refresh_dashboard()
            self.refresh_mll_dashboard()
        except Exception as e:
            # Không để lỗi dữ liệu dashboard làm chậm/không mở được ứng dụng.
            print(f"Initial dashboard refresh warning: {e}")

    def _init_cloud_client(self):
        if not CLOUD_CONFIG.exists():
            return None
        try:
            from cloud_client import SupabaseClient
            return SupabaseClient(CLOUD_CONFIG)
        except Exception as e:
            QMessageBox.warning(self,"Cloud configuration",f"Không đọc được cấu hình Supabase:\n{e}")
            return None


    def update_admin_controls(self):
        is_admin = False
        if self.cloud_logged_in and self.cloud_client and self.cloud_client.user:
            email = str((self.cloud_client.user or {}).get('email', '')).strip().lower()
            is_admin = email == AdminCreateUserDialog.ADMIN_EMAIL
        if self.admin_create_user_btn is not None:
            self.admin_create_user_btn.setVisible(is_admin)
            self.admin_create_user_btn.setEnabled(is_admin)
        if self.admin_manage_users_btn is not None:
            self.admin_manage_users_btn.setVisible(is_admin)
            self.admin_manage_users_btn.setEnabled(is_admin)
        if self.admin_reset_data_btn is not None:
            self.admin_reset_data_btn.setVisible(is_admin)
            self.admin_reset_data_btn.setEnabled(is_admin)
        if self.change_password_btn is not None:
            self.change_password_btn.setVisible(self.cloud_logged_in)
            self.change_password_btn.setEnabled(self.cloud_logged_in)

    def create_cloud_user(self):
        if not self.cloud_logged_in or not self.cloud_client:
            QMessageBox.information(self, "Cloud", "Hãy đăng nhập Supabase trước.")
            return
        email = str((self.cloud_client.user or {}).get('email', '')).strip().lower()
        if email != AdminCreateUserDialog.ADMIN_EMAIL:
            QMessageBox.warning(self, "Không có quyền", "Chỉ tài khoản Admin mới được tạo user.")
            return
        AdminCreateUserDialog(self, self.cloud_client).exec()

    def manage_cloud_users(self):
        if not self.cloud_logged_in or not self.cloud_client:
            QMessageBox.information(self, "Cloud", "Hãy đăng nhập Supabase trước.")
            return
        email = str((self.cloud_client.user or {}).get('email', '')).strip().lower()
        if email != AdminCreateUserDialog.ADMIN_EMAIL:
            QMessageBox.warning(self, "Không có quyền", "Chỉ tài khoản Admin mới được quản lý user.")
            return
        AdminUserManagementDialog(self, self.cloud_client).exec()

    def change_my_password(self):
        if not self.cloud_logged_in or not self.cloud_client:
            QMessageBox.information(self, "Cloud", "Hãy đăng nhập Supabase trước.")
            return
        email = str((self.cloud_client.user or {}).get('email', '')).strip()
        ChangePasswordDialog(self, self.cloud_client, email, False, None).exec()

    def reset_all_data_admin(self):
        """Admin-only destructive reset: clear Cloud + local business data."""
        if not self.cloud_logged_in or not self.cloud_client:
            QMessageBox.warning(self, "Xóa toàn bộ dữ liệu", "Hãy đăng nhập Cloud bằng tài khoản Admin trước khi thực hiện.")
            return
        email = str((self.cloud_client.user or {}).get("email", "")).strip().lower()
        if email != AdminCreateUserDialog.ADMIN_EMAIL.lower():
            QMessageBox.warning(self, "Không có quyền", "Chỉ tài khoản Admin mới được xóa toàn bộ dữ liệu.")
            return

        confirm = QMessageBox(self)
        confirm.setIcon(QMessageBox.Warning)
        confirm.setWindowTitle("XÓA SẠCH TOÀN BỘ DỮ LIỆU")
        confirm.setText("Thao tác này sẽ XÓA SẠCH dữ liệu BTS Manager trên CLOUD và PC.")
        confirm.setInformativeText(
            "Tất cả Trạm BTS, Hợp đồng, Thiết bị, Truyền dẫn, Nguồn, Battery, TB phụ trợ, "
            "BTBD, MLL, KPI, Thông báo và dữ liệu phân tích sẽ bị xóa.\n\n"
            "Tài khoản đăng nhập/Admin và cấu trúc ứng dụng vẫn được giữ lại.\n\n"
            "Không thể hoàn tác."
        )
        yes = confirm.addButton("Xóa sạch toàn bộ", QMessageBox.DestructiveRole)
        confirm.addButton("Hủy", QMessageBox.RejectRole)
        confirm.exec()
        if confirm.clickedButton() is not yes:
            return

        typed, ok = QInputDialog.getText(self, "Xác nhận lần cuối", 'Nhập chính xác "XOA TOAN BO" để xác nhận:')
        if not ok or typed.strip() != "XOA TOAN BO":
            QMessageBox.information(self, "Đã hủy", "Không đúng mã xác nhận. Dữ liệu không bị xóa.")
            return

        tables = [
            "notifications", "auto_alerts", "mll_bsc_summary", "mll_events",
            "maintenance", "auxiliary", "batteries", "power", "transmission",
            "equipment", "contracts", "stations", "kpi_targets"
        ]
        self.cloud_timer.stop()
        self.cloud_sync_btn.setEnabled(False)
        QApplication.processEvents()

        # A background CloudSyncWorker uses a separate SQLite connection.
        # Never start the destructive local DELETE while that worker still has
        # a write transaction open; otherwise SQLite can return
        # "database is locked" even though Cloud deletion succeeded.
        worker = getattr(self, '_cloud_worker', None)
        if worker is not None and worker.isRunning():
            self.cloud_status.setText("☁ Đang chờ đồng bộ nền kết thúc trước khi xóa dữ liệu…")
            QApplication.processEvents()
            if not worker.wait(120000):
                self.cloud_sync_btn.setEnabled(bool(self.cloud_logged_in))
                self.cloud_timer.start(45000)
                QMessageBox.warning(
                    self, "Xóa dữ liệu",
                    "Đồng bộ nền chưa kết thúc sau 120 giây.\n\n"
                    "Chưa xóa dữ liệu PC để tránh lỗi/khóa cơ sở dữ liệu.\n"
                    "Vui lòng thực hiện lại sau khi đồng bộ hoàn tất."
                )
                return

        # Clear any stale transaction on the UI connection before the local wipe.
        try:
            self.con.rollback()
            self.con.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass

        try:
            # Cloud must be wiped first. If this raises, local PC data remains intact.
            self.cloud_client.reset_all_data_admin()
            self.con.execute("BEGIN IMMEDIATE")
            for table in tables:
                self.con.execute(f"DELETE FROM {table}")
            self.con.commit()

            # Reset sync bootstrap state so a wiped installation cannot resurrect stale cache.
            if self.cloud_sync:
                try:
                    if self.cloud_sync.state_path.exists():
                        self.cloud_sync.state_path.unlink()
                except Exception:
                    pass
                self.cloud_sync.last_conflicts = []
            self.notified_ids.clear()
            self.refresh_all()
            QMessageBox.information(self, "Đã xóa sạch",
                "Đã xóa sạch toàn bộ dữ liệu trên Cloud và PC.\n\n"
                "Cấu trúc ứng dụng và tài khoản đăng nhập vẫn được giữ nguyên.")
        except Exception as e:
            try:
                self.con.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Xóa dữ liệu thất bại",
                "Không thể hoàn tất thao tác xóa sạch.\n\n" + str(e) +
                "\n\nDữ liệu PC chỉ được xóa sau khi Cloud xóa thành công.")
        finally:
            if getattr(self, '_cloud_worker', None) is not None and not self._cloud_worker.isRunning():
                self._cloud_worker = None
            self.cloud_sync_btn.setEnabled(bool(self.cloud_logged_in))
            self.cloud_timer.start(45000)

    def toggle_cloud_login(self):
        if self.cloud_logged_in:
            self.logout_cloud()
        else:
            self.login_cloud()

    def login_cloud(self):
        client=self._init_cloud_client()
        if not client:
            return
        dlg=CloudLoginDialog(self,client)
        if dlg.exec()!=QDialog.Accepted:
            return
        self.cloud_client=client
        self.user_permissions = set(getattr(client, "permissions", []) or [])
        self.cloud_sync=CloudSyncManager(self,client)
        self.cloud_logged_in=True
        user_email=(client.user or {}).get('email','')
        self.cloud_status.setText(f"☁ Online: {user_email or 'Đã đăng nhập'} • đang khởi tạo dữ liệu chung")
        self.cloud_login_btn.setText("☁ Đăng xuất")
        self.cloud_sync_btn.setEnabled(True)
        self.cloud_status.setText(f"☁ Online: {user_email or 'Đã đăng nhập'} • đang đồng bộ nền")
        self.cloud_sync_btn.setEnabled(False)
        # Restore role-based controls immediately after successful login.
        # Cloud bootstrap runs in background and must not hide Admin/User actions.
        self.update_admin_controls()
        self._start_cloud_sync(bootstrap=not self.cloud_sync.is_bootstrapped(), notify=False)

    def logout_cloud(self):
        if self.cloud_client:
            try:
                self.cloud_client.sign_out()
            except Exception:
                pass
        self.cloud_client = None
        self.cloud_sync = None
        self.cloud_logged_in = False
        self.cloud_status.setText("☁ Cloud: Chưa đăng nhập")
        self.cloud_login_btn.setText("☁ Đăng nhập")
        self.cloud_sync_btn.setEnabled(False)
        self.update_admin_controls()

    def _start_cloud_sync(self, bootstrap=False, notify=False):
        if not self.cloud_logged_in or not self.cloud_client:
            return
        if getattr(self, '_cloud_worker', None) is not None and self._cloud_worker.isRunning():
            return
        self.cloud_sync_btn.setEnabled(False)
        self.cloud_status.setText("☁ Online • đang đồng bộ nền…")
        self._cloud_notify_sync = notify
        self._cloud_worker = CloudSyncWorker(self.cloud_client, bootstrap=bootstrap)
        self._cloud_worker.finished_sync.connect(self._cloud_sync_finished)
        self._cloud_worker.start()

    def _cloud_sync_finished(self, stats, conflicts, error):
        self.cloud_sync_btn.setEnabled(bool(self.cloud_logged_in))
        if error:
            self.cloud_status.setText("☁ Online • Lỗi đồng bộ tạm thời")
            if getattr(self, '_cloud_notify_sync', False):
                QMessageBox.warning(self, "Cloud Sync", str(error))
            return
        try:
            # Worker has committed to SQLite. Mark modules dirty so the next open
            # reflects Cloud data, while modules not opened are not rebuilt now.
            for _sec, _state in getattr(self, "_module_page_state", {}).items():
                _state["dirty"] = True
            self.refresh_all()
        except Exception as e:
            print(f"Cloud refresh warning: {e}")
        if conflicts:
            self.cloud_status.setText("☁ Online • Xung đột đã xử lý — Cloud mới hơn được ưu tiên")
        else:
            self.cloud_status.setText("☁ Online • Auto Sync • "+datetime.datetime.now().strftime("%H:%M:%S"))
        if getattr(self, '_cloud_notify_sync', False):
            msg="Đồng bộ thành công."
            if conflicts:
                msg += f"\n\nCó {len(conflicts)} xung đột; phiên bản Cloud mới hơn đã được giữ."
            QMessageBox.information(self,"Đồng bộ Cloud",msg)

    def sync_cloud(self, silent=False):
        if not self.cloud_logged_in or not self.cloud_sync:
            if not silent:
                QMessageBox.information(self,"Đồng bộ Cloud","Hãy đăng nhập Supabase trước.")
            return
        self._start_cloud_sync(bootstrap=False, notify=not silent)

    def sync_cloud_silent(self):
        if self.cloud_logged_in and self.cloud_sync:
            self._start_cloud_sync(bootstrap=False, notify=False)

    def apply_style(self):
        self.setStyleSheet("""
        * { font-family: "Segoe UI"; }
        QMainWindow { background:#f4f7fb; }
        QFrame#sidebar { background:#0b2f52; }
        QLabel#brand { color:white; font-size:19px; font-weight:800; padding:10px; }
        QLabel#brandSub { color:#a9c8e5; font-size:11px; padding:0 10px 12px; }
        QPushButton#nav {
            color:#dbeafe; background:transparent; border:0; text-align:left;
            padding:12px 16px; border-radius:8px; font-size:13px;
        }
        QPushButton#nav:hover { background:#164a78; }
        QPushButton#navActive { color:white; background:#1d70b8; border:0;
            text-align:left; padding:12px 16px; border-radius:8px; font-weight:700; }
        QLabel#pageTitle { color:#10233b; font-size:25px; font-weight:800; }
        QLabel#pageSub { color:#64748b; font-size:12px; }
        QFrame#card { background:white; border:1px solid #e2e8f0; border-radius:14px; }
        QFrame#card:hover { border:1px solid #b8cfe5; }
        QLabel#cardLabel { color:#64748b; font-size:12px; font-weight:600; }
        QLabel#cardValue { color:#10233b; font-size:28px; font-weight:800; }
        QLabel#cardIcon { font-size:24px; }
        QLabel#dashSectionTitle { color:#0b63ce; font-size:17px; font-weight:800; letter-spacing:0.3px; padding:3px 0 2px 2px; }
        QLabel#dashFocusTitle { color:#7c3aed; font-size:17px; font-weight:800; letter-spacing:0.3px; padding:3px 0 2px 2px; }
        QLabel#dashMllTitle { color:#dc2626; font-size:17px; font-weight:800; letter-spacing:0.3px; padding:3px 0 2px 2px; }
        QLabel#dashCardLabel { color:#1e3a5f; font-size:12px; font-weight:700; }
        QLabel#dashCardValue { color:#0b2a4a; font-size:22px; font-weight:900; }
        QFrame#dashFocusCard { background:white; border:1px solid #d9e3ef; border-radius:14px; }
        QFrame#dashFocusCard:hover { border:1px solid #b8cfe5; }
        QFrame#dashFocusCard QLabel#dashCardLabel { white-space:nowrap; }
        QFrame#dashFocusCard QLabel#dashCardValue { font-size:22px; white-space:nowrap; }
        QLabel#dashMllCardLabel { color:#7f1d1d; font-size:12px; font-weight:700; }

        QFrame#hero { background:#0f4776; border-radius:16px; }
        QLabel#heroTitle { color:white; font-size:20px; font-weight:800; }
        QLabel#heroText { color:#cde3f7; font-size:12px; }
        QPushButton#primary { background:#1473c9; color:white; border:0; border-radius:8px;
            padding:9px 14px; font-weight:700; }
        QPushButton#primary:hover { background:#0d5da8; }
        QPushButton#secondary { background:white; color:#164a78; border:1px solid #cbd5e1;
            border-radius:8px; padding:8px 12px; font-weight:600; }
        QLineEdit,QComboBox { background:white; border:1px solid #d7e0ea;
            border-radius:8px; padding:9px; }
        QTableWidget { background:white; border:1px solid #e2e8f0; border-radius:10px;
            gridline-color:#edf2f7; alternate-background-color:#f8fafc; }
        QHeaderView::section { background:#edf3f8; color:#334155; padding:9px;
            border:0; font-weight:700; }
        QTabWidget::pane { border:0; }
        QTabBar::tab { background:#e8eef5; padding:10px 16px; margin-right:4px;
            border-radius:8px; color:#334155; font-weight:600; }
        QTabBar::tab:selected { background:#1473c9; color:white; }
        QProgressBar { border:0; background:#e8eef5; border-radius:5px; height:9px; }
        QProgressBar::chunk { background:#2a86d1; border-radius:5px; }
        QScrollArea { border:0; background:transparent; }
        """)

    def build_ui(self):
        root = QWidget()
        main = QHBoxLayout(root); main.setContentsMargins(0,0,0,0); main.setSpacing(0)

        side = QFrame(objectName="sidebar"); side.setFixedWidth(230)
        sl = QVBoxLayout(side); sl.setContentsMargins(12,18,12,12)
        brand = QLabel("📡  BTS MANAGER", objectName="brand")
        sub = QLabel("Phòng Hạ tầng Củ Chi", objectName="brandSub")
        sl.addWidget(brand); sl.addWidget(sub)
        self.cloud_status = QLabel("☁ Cloud: Chưa đăng nhập", objectName="brandSub")
        self.cloud_status.setWordWrap(True)
        sl.addWidget(self.cloud_status)
        cloud_row = QHBoxLayout()
        self.cloud_login_btn = QPushButton("☁ Đăng nhập", objectName="secondary")
        self.cloud_login_btn.clicked.connect(self.toggle_cloud_login)
        self.cloud_sync_btn = QPushButton("↻ Đồng bộ", objectName="secondary")
        self.cloud_sync_btn.clicked.connect(self.sync_cloud)
        self.cloud_sync_btn.setEnabled(False)
        cloud_row.addWidget(self.cloud_login_btn); cloud_row.addWidget(self.cloud_sync_btn)
        sl.addLayout(cloud_row)
        self.change_password_btn = QPushButton("🔑 Đổi mật khẩu", objectName="secondary")
        self.change_password_btn.clicked.connect(self.change_my_password)
        self.change_password_btn.setVisible(False)
        sl.addWidget(self.change_password_btn)
        self.admin_manage_users_btn = QPushButton("👥 Quản lý user", objectName="secondary")
        self.admin_manage_users_btn.clicked.connect(self.manage_cloud_users)
        self.admin_manage_users_btn.setVisible(False)
        sl.addWidget(self.admin_manage_users_btn)
        self.admin_reset_data_btn = QPushButton("🗑️  Xóa sạch dữ liệu", objectName="secondary")
        self.admin_reset_data_btn.setToolTip("Admin: xóa sạch toàn bộ dữ liệu Cloud + PC, giữ nguyên tài khoản và ứng dụng")
        self.admin_reset_data_btn.clicked.connect(self.reset_all_data_admin)
        self.admin_reset_data_btn.setVisible(False)
        sl.addWidget(self.admin_reset_data_btn)

        self.stack = QStackedWidget()
        self.pages = []
        self.navs = []
        self.station_children = []
        # Hàm reload cho từng bảng con Trạm BTS, dùng để cập nhật ngay sau Import Excel.
        self.module_reloaders = {}

        # Tổng quan
        page = self.dashboard_page()
        self.pages.append(page)
        self.stack.addWidget(page)
        b = QPushButton("📊  Tổng quan", objectName="nav")
        b.clicked.connect(lambda checked=False, i=0: self.go_page(i))
        self.navs.append(b)
        sl.addWidget(b)

        # Parent menu: Trạm BTS
        self.station_parent = QPushButton("📡  Trạm BTS  ▾", objectName="navActive")
        self.station_parent.clicked.connect(self.toggle_station_menu)
        sl.addWidget(self.station_parent)

        # Các mục con nằm bên trong Trạm BTS
        child_items = [
            ("📄  Hợp đồng", "contracts"),
            ("📡  Thiết bị", "equipment"),
            ("🔗  Truyền dẫn", "transmission"),
            ("⚡  Nguồn & phụ trợ", "power_aux"),
        ]
        self.child_start = len(self.pages)
        for label, section in child_items:
            page = self.station_section_page(section)
            idx = len(self.pages)
            self.pages.append(page)
            self.stack.addWidget(page)
            if not hasattr(self, "_page_section_map"):
                self._page_section_map = {}
            self._page_section_map[idx] = section
            cb = QPushButton("   └─ " + label, objectName="nav")
            cb.clicked.connect(lambda checked=False, i=idx: self.go_page(i))
            self.navs.append(cb)
            self.station_children.append(cb)
            sl.addWidget(cb)

        # BTBD giữ trong nhóm Trạm BTS nhưng đặt sau 4 mục chính.
        page = self.station_section_page("btbd")
        idx = len(self.pages)
        self.pages.append(page)
        self.stack.addWidget(page)
        if not hasattr(self, "_page_section_map"):
            self._page_section_map = {}
        self._page_section_map[idx] = "btbd"
        cb = QPushButton("   └─ 🔧  BTBD", objectName="nav")
        cb.clicked.connect(lambda checked=False, i=idx: self.go_page(i))
        self.navs.append(cb)
        self.station_children.append(cb)
        sl.addWidget(cb)

        # Tra cứu là mục riêng, nằm ngay dưới BTBD và không nằm bên trong trang BTBD.
        page = self.station_global_lookup_page()
        idx = len(self.pages)
        self.pages.append(page)
        self.stack.addWidget(page)
        if not hasattr(self, "_page_section_map"):
            self._page_section_map = {}
        self._page_section_map[idx] = "station_lookup"
        cb_lookup = QPushButton("   └─ 🔎  Tra cứu trạm", objectName="nav")
        cb_lookup.clicked.connect(lambda checked=False, i=idx: self.go_page(i))
        self.navs.append(cb_lookup)
        self.station_children.append(cb_lookup)
        sl.addWidget(cb_lookup)

        # Thông báo là mục đồng cấp với Trạm BTS, đặt dưới cùng sau toàn bộ nhóm Trạm BTS.
        self.notice_page_index = len(self.pages)
        notice_page = self.notifications_page()
        self.pages.append(notice_page)
        self.stack.addWidget(notice_page)
        self.notice_nav = QPushButton("🔔  Thông báo", objectName="nav")
        self.notice_nav.clicked.connect(
            lambda checked=False, i=self.notice_page_index: self.go_page(i)
        )
        self.navs.append(self.notice_nav)
        sl.addWidget(self.notice_nav)

        sl.addStretch()
        info = QLabel("V9.6.4 • Cloud + Local Cache\nImport Excel tiếng Việt\nSupabase Online")
        info.setStyleSheet("color:#9db8cf;font-size:11px;padding:10px;")
        sl.addWidget(info)

        main.addWidget(side); main.addWidget(self.stack,1)
        self.setCentralWidget(root)
        self.go_page(0)


    def init_notifications(self):
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                notify_date TEXT NOT NULL,
                notify_time TEXT NOT NULL,
                content TEXT,
                sound INTEGER DEFAULT 1,
                popup INTEGER DEFAULT 1,
                done INTEGER DEFAULT 0,
                auto_alert_key TEXT,
                created_at TEXT,
                sync_key TEXT,
                target_email TEXT,
                created_by_email TEXT
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS auto_alerts (
                alert_key TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                station_code TEXT,
                title TEXT,
                content TEXT,
                alert_date TEXT NOT NULL,
                resolved INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        # Migration cho các DB đã tạo từ V47 trở về trước.
        for table, column, definition in [
            ("notifications", "auto_alert_key", "TEXT"),
            ("notifications", "sync_key", "TEXT"),
            ("auto_alerts", "resolved", "INTEGER DEFAULT 0"),
            ("notifications", "target_email", "TEXT"),
            ("notifications", "created_by_email", "TEXT"),
        ]:
            try:
                cols=[r[1] for r in self.con.execute(f"PRAGMA table_info({table})").fetchall()]
                if column not in cols:
                    self.con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except Exception:
                pass
        # V85.56: every PC notification must have a stable cross-device identity.
        # Legacy rows receive a deterministic PC key once; Mobile-created rows
        # arrive from Cloud with their MOBILE|... sync_key and are pulled by the
        # generic CloudSyncManager using notifications:sync_key.
        try:
            self.con.execute("UPDATE notifications SET sync_key='PC|LEGACY|' || id WHERE sync_key IS NULL OR TRIM(sync_key)=''")
        except Exception:
            pass
        self.con.commit()

    def notifications_page(self):
        w=QWidget()
        l=QVBoxLayout(w)
        l.setContentsMargins(28,24,28,24)
        l.setSpacing(12)

        header=QHBoxLayout()
        header.addWidget(self.title_block(
            "🔔 Thông báo",
            "Lập lịch nhắc việc cho nhân viên kỹ thuật theo ngày và giờ"
        ))
        header.addStretch()
        hint=QLabel("💡 Rê chuột để xem hiệu ứng • Click ngày để lập lịch")
        hint.setObjectName("cardLabel")
        header.addWidget(hint)
        export=QPushButton("📊 Xuất Excel",objectName="primary")
        export.clicked.connect(self.export_notifications_excel)
        header.addWidget(export)
        l.addLayout(header)

        stats=QHBoxLayout()
        stats.setSpacing(10)
        self.notice_stat_total=self.make_notice_stat("🔔 Tổng thông báo", "0")
        self.notice_stat_wait=self.make_notice_stat("⏳ Đang chờ", "0")
        self.notice_stat_done=self.make_notice_stat("✅ Đã báo", "0")
        self.notice_stat_contract=self.make_notice_stat("📄 HĐ sắp hết hạn", "0")
        self.notice_stat_btbd=self.make_notice_stat("🔧 BTBD chưa thực hiện", "0")
        stats.addWidget(self.notice_stat_total,1)
        stats.addWidget(self.notice_stat_wait,1)
        stats.addWidget(self.notice_stat_done,1)
        stats.addWidget(self.notice_stat_contract,1)
        stats.addWidget(self.notice_stat_btbd,1)
        l.addLayout(stats)

        body=QHBoxLayout()
        body.setSpacing(14)

        cal_card=QFrame(objectName="card")
        cl=QVBoxLayout(cal_card)
        cal_head=QHBoxLayout()
        cal_head.addWidget(QLabel("📅 Lịch tháng",objectName="cardLabel"))
        cal_head.addStretch()
        self.notice_selected_label=QLabel("Ngày chọn: --/--/----", objectName="cardLabel")
        cal_head.addWidget(self.notice_selected_label)
        cl.addLayout(cal_head)
        self.notice_calendar=NoticeCalendar()
        self.notice_calendar.setGridVisible(True)
        self.notice_calendar.setMinimumWidth(500)
        self.notice_calendar.setMinimumHeight(430)
        self.notice_calendar.clicked.connect(self.notice_date_clicked)
        cl.addWidget(self.notice_calendar)
        body.addWidget(cal_card,1)

        list_card=QFrame(objectName="card")
        rl=QVBoxLayout(list_card)
        month_bar=QHBoxLayout()
        self.notice_day_label=QLabel("📋 Danh sách thông báo theo tháng",objectName="cardLabel")
        month_bar.addWidget(self.notice_day_label)
        month_bar.addStretch()
        month_bar.addWidget(QLabel("Tháng:"))
        self.notice_month_combo=QComboBox()
        self.notice_month_combo.setMinimumWidth(130)
        self.notice_month_combo.setToolTip("Chọn tháng để xem toàn bộ thông báo trong tháng đó")
        self.populate_notice_month_combo()
        self.notice_month_combo.currentIndexChanged.connect(self.notice_month_changed)
        month_bar.addWidget(self.notice_month_combo)
        rl.addLayout(month_bar)

        self.notice_table=QTableWidget(0,7)
        self.notice_table.setHorizontalHeaderLabels(
            ["Ngày giờ","Tiêu đề","Nội dung","Âm thanh","Pop-up","Trạng thái","Chức năng"]
        )
        self.notice_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.notice_table.horizontalHeader().setStretchLastSection(True)
        self.notice_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.notice_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.notice_table.setAlternatingRowColors(True)
        self.notice_table.setShowGrid(True)
        self.notice_table.setGridStyle(Qt.SolidLine)
        # Không tự xuống dòng trong ô: tránh một thông báo dài làm phình chiều cao cả hàng.
        self.notice_table.setWordWrap(False)
        self.notice_table.setTextElideMode(Qt.ElideRight)
        self.notice_table.setStyleSheet("""
            QTableWidget {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                gridline-color: #c7d2df;
                selection-background-color: #dbeafe;
                selection-color: #10233b;
                alternate-background-color: #f8fafc;
            }
            QTableWidget::item {
                border-right: 1px solid #dbe3ec;
                border-bottom: 1px solid #dbe3ec;
                padding: 6px;
            }
            QHeaderView::section {
                background: #edf3f8;
                color: #1e3a56;
                border-right: 1px solid #cbd5e1;
                border-bottom: 1px solid #cbd5e1;
                padding: 9px 6px;
                font-weight: 700;
            }
        """)
        self.notice_table.verticalHeader().setDefaultSectionSize(52)
        self.notice_table.verticalHeader().setMinimumSectionSize(52)
        # Căn cột ổn định, tránh cột Chức năng bị kéo giãn thành một khung rỗng.
        hh=self.notice_table.horizontalHeader()
        for col in range(7):
            hh.setSectionResizeMode(col, QHeaderView.Fixed)
        # Nội dung là cột linh hoạt; các cột còn lại giữ kích thước ổn định.
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.notice_table.setColumnWidth(0, 128)   # Ngày giờ
        self.notice_table.setColumnWidth(1, 135)   # Tiêu đề
        self.notice_table.setColumnWidth(3, 68)    # Âm thanh
        self.notice_table.setColumnWidth(4, 68)    # Pop-up
        self.notice_table.setColumnWidth(5, 82)    # Trạng thái
        self.notice_table.setColumnWidth(6, 178)   # Chức năng
        hh.setDefaultAlignment(Qt.AlignCenter)
        self.notice_table.setMinimumWidth(0)
        self.notice_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        rl.addWidget(self.notice_table,1)

        btns=QHBoxLayout()
        btns.addStretch()
        test=QPushButton("🔊 Test âm thanh",objectName="secondary")
        test.clicked.connect(self.test_notification_sound)
        btns.addWidget(test)
        rl.addLayout(btns)
        body.addWidget(list_card,2)

        l.addLayout(body,1)
        today=QDate.currentDate()
        self.notice_calendar.setSelectedDate(today)
        self.notice_selected_label.setText(f"Ngày chọn: {today.toString('dd/MM/yyyy')}")
        self.set_notice_month(today.toString("yyyy-MM"))
        return w

    def populate_notice_month_combo(self):
        """Nạp danh sách tháng cho combobox, gồm các tháng có dữ liệu và vùng thời gian quanh hiện tại."""
        keys=set()
        now=QDate.currentDate()
        for offset in range(-12,13):
            d=now.addMonths(offset)
            keys.add(d.toString("yyyy-MM"))
        for (value,) in self.con.execute("SELECT DISTINCT substr(notify_date,1,7) FROM notifications WHERE notify_date IS NOT NULL ORDER BY 1").fetchall():
            if value:
                keys.add(value)
        current=self.notice_month_combo.currentData() if hasattr(self,'notice_month_combo') else None
        self.notice_month_combo.blockSignals(True)
        self.notice_month_combo.clear()
        for key in sorted(keys, reverse=True):
            y,m=key.split('-')
            self.notice_month_combo.addItem(f"Tháng {int(m):02d}/{y}", key)
        idx=self.notice_month_combo.findData(current or now.toString("yyyy-MM"))
        if idx>=0:
            self.notice_month_combo.setCurrentIndex(idx)
        self.notice_month_combo.blockSignals(False)

    def set_notice_month(self, month_key):
        idx=self.notice_month_combo.findData(month_key)
        if idx<0:
            self.populate_notice_month_combo()
            idx=self.notice_month_combo.findData(month_key)
        if idx>=0:
            self.notice_month_combo.setCurrentIndex(idx)
        # Luôn nạp lại bảng ngay cả khi tháng không thay đổi.
        # QComboBox không phát currentIndexChanged nếu người dùng vẫn đang ở cùng tháng,
        # vì vậy nếu chỉ setCurrentIndex() thì dữ liệu mới sau khi Save/đổi trạng thái
        # có thể chưa xuất hiện ngay trên lưới.
        self.load_notifications_for_month(month_key)

    def notice_month_changed(self, index):
        key=self.notice_month_combo.itemData(index)
        if key:
            self.load_notifications_for_month(key)

    def load_notifications_for_month(self, month_key):
        """Hiển thị toàn bộ thông báo thuộc tháng đang chọn."""
        try:
            y,m=month_key.split('-')
            title=f"📋 Tất cả thông báo tháng {m}/{y}"
        except Exception:
            title="📋 Tất cả thông báo trong tháng"
        self.notice_day_label.setText(title)
        current_email=str((self.cloud_client.user or {}).get('email','')).strip().lower() if self.cloud_client else ''
        is_admin=current_email == AdminCreateUserDialog.ADMIN_EMAIL
        rows=self.con.execute("""
            SELECT id,notify_date,notify_time,title,content,sound,popup,done,auto_alert_key
            FROM notifications
            WHERE substr(notify_date,1,7)=?
              AND (?=1 OR lower(trim(COALESCE(target_email,'')))=?)
            ORDER BY notify_date,notify_time
        """,(month_key,1 if is_admin else 0,current_email)).fetchall()
        self.notice_table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            nid,dt,tm,title,content,sound,popup,done,auto_alert_key=row
            date_text = QDate.fromString(dt,"yyyy-MM-dd").toString("dd/MM/yyyy") if dt else (dt or "")
            time_text = (tm or "").strip()
            datetime_text = f"{date_text} {time_text}".strip()
            vals=[
                datetime_text, title or "", content or "",
                "Có" if sound else "Không", "Có" if popup else "Không",
                "Đã báo" if done else "Chờ"
            ]
            for c,v in enumerate(vals):
                item=QTableWidgetItem(str(v or ""))
                item.setData(Qt.UserRole,nid)
                item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                item.setToolTip(str(v or ""))
                if c == 5:
                    item.setForeground(QColor("#16803c" if done else "#b76e00"))
                    item.setFont(QFont("Segoe UI", 10, QFont.Bold))
                self.notice_table.setItem(r,c,item)

            # Cột Chức năng giữ toàn bộ thao tác: cảnh báo HĐ có checkbox Hoàn thành,
            # thông báo thường giữ Sửa/Xóa như cấu trúc cũ.
            action_widget=QWidget()
            action_layout=QHBoxLayout(action_widget)
            action_layout.setContentsMargins(8,4,8,4)
            action_layout.setSpacing(8)
            if auto_alert_key:
                done_cb=QCheckBox("Hoàn thành")
                done_cb.setChecked(bool(done))
                done_cb.setToolTip("Đánh dấu đã xử lý. Khi hoàn thành, cảnh báo sẽ biến mất khỏi khung CẢNH BÁO.")
                done_cb.setStyleSheet("QCheckBox{color:#166534;font-weight:700;padding:2px;} QCheckBox::indicator{width:18px;height:18px;}")
                done_cb.clicked.connect(lambda checked, x=nid: self.complete_notification(x, checked))
                action_layout.addWidget(done_cb)
            else:
                editable = self.notification_is_future(nid)
                edit_btn=QPushButton("✏️")
                edit_btn.setToolTip("Sửa thông báo" if editable else "Không thể sửa: cảnh báo đã đến giờ")
                edit_btn.setFixedSize(58,30)
                edit_btn.setEnabled(editable)
                edit_btn.setStyleSheet("QPushButton{background:#e8f3ff;border:1px solid #9bc4e8;border-radius:6px;color:#0b5fa5;font-weight:700;} QPushButton:hover{background:#d7ebff;} QPushButton:disabled{background:#eeeeee;border:1px solid #cccccc;color:#999999;}")
                edit_btn.clicked.connect(lambda checked=False, x=nid: self.edit_notification_by_id(x))
                del_btn=QPushButton("🗑️")
                del_btn.setToolTip("Xóa thông báo" if editable else "Không thể xóa: cảnh báo đã đến giờ")
                del_btn.setFixedSize(58,30)
                del_btn.setEnabled(editable)
                del_btn.setStyleSheet("QPushButton{background:#fff0f0;border:1px solid #e7aaaa;border-radius:6px;color:#b42318;font-weight:700;} QPushButton:hover{background:#ffe0e0;} QPushButton:disabled{background:#eeeeee;border:1px solid #cccccc;color:#999999;}")
                del_btn.clicked.connect(lambda checked=False, x=nid: self.delete_notification_by_id(x))
                action_layout.addWidget(edit_btn)
                action_layout.addWidget(del_btn)
            action_layout.addStretch()
            self.notice_table.setCellWidget(r,6,action_widget)
            self.notice_table.setRowHeight(r, 52)
        self.refresh_notification_stats()
        self.refresh_notification_calendar_marks()

    def make_notice_stat(self, label, value):
        f=QFrame(objectName="card")
        fl=QVBoxLayout(f)
        fl.setContentsMargins(14,10,14,10)
        fl.addWidget(QLabel(label, objectName="cardLabel"))
        v=QLabel(value, objectName="cardValue")
        v.setStyleSheet("font-size:20px;")
        fl.addWidget(v)
        f._value_label=v
        return f

    def refresh_notification_calendar_marks(self):
        """Đánh dấu các ngày có thông báo bằng nền nhẹ và chữ đậm."""
        today=QDate.currentDate()
        # Xóa định dạng các ngày đã đánh dấu ở lần refresh trước.
        for old_date in getattr(self.notice_calendar, "_notice_marked_dates", []):
            self.notice_calendar.setDateTextFormat(old_date, QTextCharFormat())
        self.notice_calendar._notice_marked_dates=[]
        rows=self.con.execute(
            "SELECT notify_date, COUNT(*) FROM notifications WHERE done=0 GROUP BY notify_date"
        ).fetchall()
        auto_rows=self.con.execute(
            "SELECT alert_date, COUNT(*) FROM auto_alerts WHERE resolved=0 GROUP BY alert_date"
        ).fetchall()
        rows += auto_rows
        for row in rows:
            qd=QDate.fromString(row[0], "yyyy-MM-dd")
            if not qd.isValid():
                continue
            fmt=QTextCharFormat()
            fmt.setFontWeight(QFont.Bold)
            fmt.setForeground(QColor("#0b5fa5"))
            fmt.setBackground(QColor("#eaf5ff"))
            self.notice_calendar.setDateTextFormat(qd, fmt)
            self.notice_calendar._notice_marked_dates.append(qd)

        fmt_today=QTextCharFormat()
        fmt_today.setFontWeight(QFont.Bold)
        fmt_today.setForeground(QColor("#0b4776"))
        fmt_today.setBackground(QColor("#fff4cc"))
        # Chỉ áp dụng nếu hôm nay chưa được đánh dấu có thông báo.
        if not any(QDate.fromString(r[0], "yyyy-MM-dd") == today for r in rows):
            self.notice_calendar.setDateTextFormat(today, fmt_today)
            self.notice_calendar._notice_marked_dates.append(today)

    def refresh_notification_stats(self):
        total=self.con.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        done=self.con.execute("SELECT COUNT(*) FROM notifications WHERE done=1").fetchone()[0]
        wait=total-done
        contract_alerts=self.con.execute(
            "SELECT COUNT(*) FROM notifications WHERE auto_alert_key LIKE 'CONTRACT|%' AND done=0"
        ).fetchone()[0]
        btbd_alerts=self.con.execute(
            "SELECT COUNT(*) FROM notifications WHERE auto_alert_key LIKE 'BTBD|%' AND done=0"
        ).fetchone()[0]
        self.notice_stat_total._value_label.setText(str(total))
        self.notice_stat_wait._value_label.setText(str(wait))
        self.notice_stat_done._value_label.setText(str(done))
        self.notice_stat_contract._value_label.setText(str(contract_alerts))
        if hasattr(self,'notice_stat_btbd'):
            self.notice_stat_btbd._value_label.setText(str(btbd_alerts))

    def notice_date_clicked(self,qdate):
        """Click ngày: cập nhật ngày chọn, chuyển bảng về tháng đó và mở popup lập lịch."""
        if hasattr(self, "notice_selected_label"):
            self.notice_selected_label.setText(f"Ngày chọn: {qdate.toString('dd/MM/yyyy')}")
        self.set_notice_month(qdate.toString("yyyy-MM"))
        self.add_notification_dialog(selected_date=qdate)

    def load_notifications_for_date(self,qdate):
        """Tương thích với các luồng cũ: bảng chính luôn hiển thị toàn bộ tháng."""
        self.set_notice_month(qdate.toString("yyyy-MM"))

    def add_notification_dialog(self,edit_id=None,selected_date=None):
        current_email=str((self.cloud_client.user or {}).get('email','')).strip().lower() if self.cloud_client else ''
        is_admin=current_email == AdminCreateUserDialog.ADMIN_EMAIL
        if not is_admin and not (('notifications.create_own' in self.user_permissions) or ('notifications.write' in self.user_permissions) or ('notification.write' in self.user_permissions)):
            QMessageBox.warning(self, "Phân quyền", "Tài khoản không có quyền tạo thông báo cá nhân.")
            return
        dlg=QDialog(self)
        quick=selected_date is not None and edit_id is None
        dlg.setWindowTitle("Thêm thông báo" if not edit_id else "Sửa thông báo")
        dlg.resize(520,320 if quick else 440)
        l=QVBoxLayout(dlg)

        form=QFormLayout()
        date=QDateEdit(selected_date or QDate.currentDate())
        date.setCalendarPopup(True)
        date.setReadOnly(True)
        tm=QTimeEdit(QTime.currentTime())
        tm.setDisplayFormat("HH:mm")
        title=QLineEdit()
        title.setPlaceholderText("Tiêu đề (không bắt buộc)")
        content=QPlainTextEdit()
        content.setPlaceholderText("Nhập nội dung cần thông báo...")
        content.setMinimumHeight(90 if quick else 120)
        sound=QCheckBox("🔊 Phát âm thanh")
        sound.setChecked(True)
        popup=QCheckBox("🪟 Hiện pop-up")
        popup.setChecked(True)

        if quick:
            date.setVisible(False)
            title.setVisible(False)
            form.addRow("Ngày:",QLabel(selected_date.toString("dd/MM/yyyy")))
            form.addRow("Giờ:",tm)
            form.addRow("Nội dung:",content)
            form.addRow("",sound)
            form.addRow("",popup)
        else:
            form.addRow("Ngày:",date)
            form.addRow("Giờ:",tm)
            form.addRow("Tiêu đề:",title)
            form.addRow("Nội dung:",content)
            form.addRow("",sound)
            form.addRow("",popup)
        l.addLayout(form)

        if edit_id:
            row=self.con.execute("""
                SELECT notify_date,notify_time,title,content,sound,popup
                FROM notifications WHERE id=?
            """,(edit_id,)).fetchone()
            if row:
                date.setDate(QDate.fromString(row[0],"yyyy-MM-dd"))
                tm.setTime(QTime.fromString(row[1],"HH:mm"))
                title.setText(row[2] or "")
                content.setPlainText(row[3] or "")
                sound.setChecked(bool(row[4]))
                popup.setChecked(bool(row[5]))

        box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        l.addWidget(box)

        if dlg.exec()!=QDialog.Accepted:
            return

        if not title.text().strip() and not content.toPlainText().strip():
            QMessageBox.warning(self,"Thiếu nội dung","Vui lòng nhập tiêu đề hoặc nội dung.")
            return

        vals=(
            date.date().toString("yyyy-MM-dd"),
            tm.time().toString("HH:mm"),
            title.text().strip(),
            content.toPlainText().strip(),
            1 if sound.isChecked() else 0,
            1 if popup.isChecked() else 0
        )

        if edit_id:
            try:
                new_when=datetime.datetime.strptime(
                    f"{vals[0]} {vals[1]}", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                QMessageBox.warning(self, "Giờ không hợp lệ", "Không thể xác định thời điểm cảnh báo.")
                return
            if new_when <= datetime.datetime.now():
                QMessageBox.warning(
                    self, "Không thể sửa",
                    "Thời gian mới phải lớn hơn thời điểm hiện tại.\n\n"
                    "Cảnh báo đã đến hoặc đã qua giờ hiện tại không được phép sửa."
                )
                return
            self.con.execute("""
                UPDATE notifications
                SET notify_date=?,notify_time=?,title=?,content=?,sound=?,popup=?,done=0
                WHERE id=?
            """,vals+(edit_id,))
        else:
            self.con.execute("""
                INSERT INTO notifications
                (notify_date,notify_time,title,content,sound,popup,done,created_at,sync_key,target_email,created_by_email)
                VALUES (?,?,?,?,?,?,0,?,?,?,?)
            """,vals+(datetime.datetime.now().isoformat(timespec="seconds"),
                      f"PC|{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
                      str((self.cloud_client.user or {}).get('email','')).strip().lower() if self.cloud_client else '',
                      str((self.cloud_client.user or {}).get('email','')).strip().lower() if self.cloud_client else ''))
        self.con.commit()
        # Refresh ngay sau khi nhấn Save: cập nhật lưới tháng, thống kê và dấu ngày.
        self.notice_selected_label.setText(
            f"Ngày chọn: {date.date().toString('dd/MM/yyyy')}"
        )
        self.set_notice_month(date.date().toString("yyyy-MM"))
        self.notice_table.viewport().update()
        self.notice_calendar.updateCells()

    def export_notifications_excel(self):
        """Xuất toàn bộ cảnh báo/thông báo ra Excel, có xử lý lỗi file đang mở."""
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()
        default_path = default_dir / "Danh_sach_thong_bao_BTS.xlsx"
        path,_=QFileDialog.getSaveFileName(
            self,
            "Xuất danh sách thông báo",
            str(default_path),
            "Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
        except Exception as e:
            QMessageBox.critical(
                self,
                "Thiếu thư viện Excel",
                "Không thể xuất Excel vì máy chưa có thư viện openpyxl.\n\n"
                f"Chi tiết: {e}\n\n"
                "Hãy chạy build_windows.bat để cài đầy đủ thư viện rồi đóng gói lại ứng dụng."
            )
            return

        try:
            rows=self.con.execute("""
                SELECT notify_date,notify_time,title,content,sound,popup,done
                FROM notifications
                ORDER BY notify_date,notify_time
            """).fetchall()

            wb=Workbook()
            ws=wb.active
            ws.title="Cảnh báo BTS"
            ws.merge_cells("A1:G1")
            ws["A1"]="DANH SÁCH CẢNH BÁO / THÔNG BÁO BTS"
            ws["A1"].font=Font(bold=True,size=16,color="FFFFFF")
            ws["A1"].fill=PatternFill("solid", fgColor="1473C9")
            ws["A1"].alignment=Alignment(horizontal="center",vertical="center")
            ws.row_dimensions[1].height=30

            ws.append(["Xuất lúc",datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")])
            ws.append([])
            heads=["Ngày giờ","Tiêu đề","Nội dung","Âm thanh","Pop-up","Trạng thái","Hoàn thành"]
            ws.append(heads)
            for cell in ws[4]:
                cell.font=Font(bold=True,color="FFFFFF")
                cell.fill=PatternFill("solid", fgColor="0B4776")
                cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
                cell.border=Border(
                    left=Side(style="thin",color="B8C7D9"),
                    right=Side(style="thin",color="B8C7D9"),
                    top=Side(style="thin",color="B8C7D9"),
                    bottom=Side(style="thin",color="B8C7D9")
                )
            ws.row_dimensions[4].height=25

            for row in rows:
                date_text = row[0] or ""
                time_text = (row[1] or "").strip()
                ws.append([
                    f"{date_text} {time_text}".strip(), row[2] or "", row[3] or "",
                    "Có" if row[4] else "Không",
                    "Có" if row[5] else "Không",
                    "Đã báo" if row[6] else "Chờ",
                    "Có" if row[6] else "Chưa"
                ])

            thin=Side(style="thin", color="D0D9E3")
            border=Border(left=thin,right=thin,top=thin,bottom=thin)
            for row in ws.iter_rows(min_row=5, max_row=ws.max_row, min_col=1, max_col=8):
                for cell in row:
                    cell.border=border
                    cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)

            # Riêng nội dung dài vẫn canh giữa theo yêu cầu, nhưng tăng chiều cao để dễ đọc.
            for r in range(5, ws.max_row + 1):
                ws.row_dimensions[r].height=32

            widths=[14,9,24,55,12,12,14,14]
            for i,w in enumerate(widths,1):
                ws.column_dimensions[get_column_letter(i)].width=w
            ws.freeze_panes="A5"
            ws.auto_filter.ref=f"A4:H{max(4,ws.max_row)}"

            try:
                wb.save(path)
            except PermissionError:
                # Excel đang mở file cũ hoặc Windows không cho ghi đè -> tạo file mới tự động.
                p=Path(path)
                fallback=p.with_name(f"{p.stem}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
                wb.save(fallback)
                path=str(fallback)

            QMessageBox.information(
                self,
                "Xuất Excel thành công",
                f"Đã xuất {len(rows)} cảnh báo/thông báo.\n\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Lỗi xuất Excel",
                "Không thể xuất file cảnh báo.\n\n"
                f"Chi tiết lỗi: {type(e).__name__}: {e}\n\n"
                "Nếu file Excel cũ đang mở, hãy đóng file đó rồi thử lại."
            )

    def notification_is_future(self, nid):
        """Chỉ cho sửa/xóa cảnh báo chưa đến thời điểm hiện tại."""
        row=self.con.execute(
            "SELECT notify_date, notify_time FROM notifications WHERE id=?",
            (nid,)
        ).fetchone()
        if not row:
            return False
        try:
            scheduled=datetime.datetime.strptime(
                f"{row[0]} {row[1]}", "%Y-%m-%d %H:%M"
            )
            return scheduled > datetime.datetime.now()
        except (TypeError, ValueError):
            return False

    def selected_notification_id(self):
        row=self.notice_table.currentRow()
        if row<0 or self.notice_table.item(row,0) is None:
            return None
        return self.notice_table.item(row,0).data(Qt.UserRole)

    def edit_notification_by_id(self, nid):
        if not nid:
            return
        if not self.notification_is_future(nid):
            QMessageBox.information(
                self, "Không thể sửa",
                "Cảnh báo đã đến hoặc đã qua thời điểm hiện tại nên không được phép sửa."
            )
            return
        self.add_notification_dialog(nid)

    def delete_notification_by_id(self, nid):
        if not nid:
            return
        if not self.notification_is_future(nid):
            QMessageBox.information(
                self, "Không thể xóa",
                "Cảnh báo đã đến hoặc đã qua thời điểm hiện tại nên không được phép xóa."
            )
            return
        row=self.con.execute("SELECT notify_date, notify_time, content FROM notifications WHERE id=?",(nid,)).fetchone()
        if not row:
            return
        when=f"{QDate.fromString(row[0], 'yyyy-MM-dd').toString('dd/MM/yyyy')} {row[1]}"
        text=row[2] or "(không có nội dung)"
        if QMessageBox.question(
            self,"Xóa thông báo",
            f"Bạn có chắc muốn xóa thông báo này?\n\n{when}\n{text}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self.con.execute("DELETE FROM notifications WHERE id=?",(nid,))
        self.con.commit()
        self.load_notifications_for_month(self.notice_month_combo.currentData() or self.notice_calendar.selectedDate().toString("yyyy-MM"))

    def edit_selected_notification(self):
        nid=self.selected_notification_id()
        if nid:
            self.add_notification_dialog(nid)

    def delete_selected_notification(self):
        nid=self.selected_notification_id()
        if not nid:
            QMessageBox.information(self,"Thông báo","Vui lòng chọn một thông báo.")
            return
        if QMessageBox.question(
            self,"Xóa thông báo","Bạn có chắc muốn xóa thông báo này?"
        )!=QMessageBox.Yes:
            return
        self.con.execute("DELETE FROM notifications WHERE id=?",(nid,))
        self.con.commit()
        self.load_notifications_for_date(self.notice_calendar.selectedDate())

    def play_notification_sound(self, content="Bạn có một thông báo mới"):
        """Đọc trực tiếp nội dung cảnh báo bằng giọng nói Windows.
        Không đọc câu cố định; khi cảnh báo thực tế đến sẽ chỉ đọc phần Nội dung.
        """
        phrase = str(content or "").strip()
        if not phrase:
            return
        try:
            if sys.platform.startswith("win"):
                import subprocess
                # PowerShell chạy nền để không làm treo giao diện.
                import json
                phrase_ps = json.dumps(phrase, ensure_ascii=False)
                ps = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "$s.Volume=100; $s.Rate=0; "
                    "$vi=$s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'vi-VN' } | Select-Object -First 1; "
                    "if($vi){$s.SelectVoice($vi.VoiceInfo.Name)}; "
                    f"$s.Speak({phrase_ps}); $s.Dispose()"
                )
                subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return

            # Fallback khi chạy môi trường không phải Windows.
            import wave, math, struct, tempfile
            path=Path(tempfile.gettempdir())/"bts_manager_notice.wav"
            rate=44100
            duration=0.45
            freq=880
            with wave.open(str(path),"wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(rate)
                frames=b"".join(
                    struct.pack("<h",int(16000*math.sin(2*math.pi*freq*i/rate)))
                    for i in range(int(rate*duration))
                )
                wf.writeframes(frames)
            self._notice_sound=QSoundEffect(self)
            self._notice_sound.setSource(QUrl.fromLocalFile(str(path)))
            self._notice_sound.setVolume(0.8)
            self._notice_sound.play()
        except Exception:
            pass

    def test_notification_sound(self):
        self.play_notification_sound("Đây là nội dung cảnh báo mẫu để kiểm tra giọng nói")

    def show_notification(self,nid,title,content,sound,popup):
        if nid in self.notified_ids:
            return
        self.notified_ids.add(nid)

        if sound:
            self.play_notification_sound(content)

        if popup:
            QMessageBox.information(
                self,
                "🔔 NHẮC VIỆC BTS",
                f"{title or 'Thông báo'}\n\n{content or ''}"
            )

        auto_row=self.con.execute("SELECT auto_alert_key FROM notifications WHERE id=?",(nid,)).fetchone()
        is_auto=bool(auto_row and auto_row[0])
        # Cảnh báo tự động phải giữ nguyên trạng thái Chờ cho tới khi người dùng
        # tự tích "Hoàn thành". Thông báo lịch thường vẫn tự đánh dấu Đã báo.
        if not is_auto:
            self.con.execute("UPDATE notifications SET done=1 WHERE id=?",(nid,))
            self.con.commit()

        # Trạng thái vừa chuyển sang "Đã báo" -> refresh toàn bộ khung ngay lập tức.
        # Không chỉ cập nhật dữ liệu trong DB mà phải dựng lại các dòng/nút Sửa-Xóa
        # để chúng bị khóa ngay khi cảnh báo đã đến giờ.
        if hasattr(self,"notice_calendar"):
            current_month = (
                self.notice_month_combo.currentData()
                if hasattr(self, "notice_month_combo") else None
            ) or self.notice_calendar.selectedDate().toString("yyyy-MM")
            self.load_notifications_for_month(current_month)
            self.notice_table.viewport().update()
            self.notice_calendar.updateCells()

    def complete_notification(self, nid, checked=True):
        """Đánh dấu thông báo hoàn thành. Với cảnh báo tự động, đồng thời ẩn khỏi khung CẢNH BÁO."""
        if not nid:
            return
        row=self.con.execute("SELECT auto_alert_key FROM notifications WHERE id=?",(nid,)).fetchone()
        auto_key=row[0] if row else None
        self.con.execute("UPDATE notifications SET done=? WHERE id=?",(1 if checked else 0,nid))
        if auto_key:
            self.con.execute("UPDATE auto_alerts SET resolved=? WHERE alert_key=?",(1 if checked else 0,auto_key))
        self.con.commit()
        current_month=(self.notice_month_combo.currentData() if hasattr(self,"notice_month_combo") else None) or QDate.currentDate().toString("yyyy-MM")
        if hasattr(self,"notice_table"):
            self.load_notifications_for_month(current_month)
        if hasattr(self,"dashboard_alert_count"):
            self.refresh_automatic_alerts(show_popup=False)

    def check_notifications(self):
        self.refresh_automatic_alerts(show_popup=True)
        now=datetime.datetime.now()
        date=now.strftime("%Y-%m-%d")
        tm=now.strftime("%H:%M")
        current_email=str((self.cloud_client.user or {}).get('email','')).strip().lower() if self.cloud_client else ''
        is_admin=current_email == AdminCreateUserDialog.ADMIN_EMAIL
        rows=self.con.execute("""
            SELECT id,title,content,sound,popup
            FROM notifications
            WHERE notify_date=? AND notify_time=? AND done=0
              AND (?=1 OR lower(trim(COALESCE(target_email,'')))=?)
        """,(date,tm,1 if is_admin else 0,current_email)).fetchall()
        for row in rows:
            self.show_notification(*row)

    def toggle_station_menu(self):
        visible = bool(self.station_children and self.station_children[0].isVisible())
        for b in self.station_children:
            b.setVisible(not visible)
        self.station_parent.setText("📡  Trạm BTS  ▸" if not visible else "📡  Trạm BTS  ▾")

    @staticmethod
    def _normalize_search_value(value):
        """Chuẩn hóa tìm kiếm: không phân biệt hoa/thường, dấu cách và dấu câu.
        Giữ chữ/số Unicode để các mã như HĐ2020 tìm được ổn định."""
        text=str(value or "").strip().casefold()
        text=unicodedata.normalize("NFKC", text)
        return "".join(ch for ch in text if ch.isalnum())

    def _find_station_codes_global(self, query):
        """Tra cứu toàn bộ dữ liệu liên quan đến trạm.
        - Nhập đúng mã trạm (CCH009/CCH009M) => chỉ trả đúng trạm đó.
        - Nhập số HĐ, mã điện kế, serial, IP, UPE, KTV... => dò toàn bộ trường
          dữ liệu và trả về các mã trạm sở hữu trường đó.
        """
        q=str(query or "").strip()
        if not q:
            return []
        q_norm=self._normalize_search_value(q)
        if not q_norm:
            return []
        codes=set()

        # 1) Ưu tiên mã trạm chính xác/biến thể bỏ hậu tố M.
        try:
            station_rows=self.con.execute("SELECT code FROM stations WHERE code IS NOT NULL").fetchall()
            exact=[]
            for (raw_code,) in station_rows:
                code=str(raw_code or "").strip()
                cn=self._normalize_search_value(code)
                if cn == q_norm or cn == q_norm + "m" or (q_norm.endswith("m") and cn == q_norm[:-1]):
                    exact.append(code)
            if exact:
                return sorted(set(exact), key=str.lower)
        except Exception:
            pass

        # 2) Dò theo từng dòng/cột bằng Python để xử lý Unicode đầy đủ.
        # Không dùng SQLite lower() vì SQLite lower() không chuẩn hóa tốt chữ Đ/đ
        # trong số hợp đồng như 76/HĐ2020-VNPT.TPHCM-VTCC.
        tables=[
            ("stations","code"),("contracts","station_code"),("equipment","station_code"),
            ("transmission","station_code"),("power","station_code"),
            ("batteries","station_code"),("auxiliary","station_code"),
            ("maintenance","station_code"),("mll_events","station_code")
        ]
        for table,code_col in tables:
            try:
                cols=[r[1] for r in self.con.execute(f"PRAGMA table_info({table})").fetchall()]
                if not cols or code_col not in cols:
                    continue
                rows=self.con.execute(f"SELECT * FROM {table}").fetchall()
                for row in rows:
                    matched=False
                    for value in row:
                        if q_norm in self._normalize_search_value(value):
                            matched=True
                            break
                    code_value = row[code_col] if isinstance(row, sqlite3.Row) else None
                    if matched and code_value:
                        codes.add(str(code_value).strip())
            except Exception:
                continue
        return sorted(codes, key=str.lower)

    def _station_global_detail_dialog(self, station_code):
        """Hiển thị toàn bộ trường thông tin của một mã trạm trên mọi module."""
        code=str(station_code or "").strip()
        dlg=QDialog(self)
        dlg.setWindowTitle(f"🔎 Hồ sơ toàn bộ trạm – {code}")
        dlg.resize(1250, 760)
        root=QVBoxLayout(dlg)
        title=QLabel(f"HỒ SƠ TOÀN BỘ TRẠM: {code}")
        title.setStyleSheet("font-size:18px;font-weight:800;color:#0f3d68;padding:4px 0;")
        root.addWidget(title)
        sub=QLabel("Tất cả thông tin liên quan đến mã trạm được gom từ Trạm BTS, Hợp đồng, Thiết bị, Truyền dẫn, Nguồn, Battery, Phụ trợ, BTBD và MLL.")
        sub.setStyleSheet("color:#64748b;padding-bottom:6px;")
        root.addWidget(sub)

        tabs=QTabWidget()
        root.addWidget(tabs,1)
        queries=[
            ("Trạm BTS", "SELECT * FROM stations WHERE code=?"),
            ("Hợp đồng", "SELECT * FROM contracts WHERE station_code=?"),
            ("Thiết bị", "SELECT * FROM equipment WHERE station_code=?"),
            ("Truyền dẫn", "SELECT * FROM transmission WHERE station_code=?"),
            ("Nguồn", "SELECT * FROM power WHERE station_code=?"),
            ("Battery", "SELECT * FROM batteries WHERE station_code=?"),
            ("Phụ trợ", "SELECT * FROM auxiliary WHERE station_code=?"),
            ("BTBD", "SELECT * FROM maintenance WHERE station_code=?"),
            ("MLL", "SELECT * FROM mll_events WHERE station_code=?"),
        ]
        labels={
            "stations": {"code":"Mã trạm","name":"Tên trạm","type":"Loại trạm","status":"Trạng thái","address":"Địa chỉ","latitude":"Vĩ độ","longitude":"Kinh độ","owner_contact":"Người liên hệ","meter_code":"Mã điện kế","technician":"KTV quản lý","pole_type":"Loại trụ","csht_type":"Loại CSHT","upe":"UPE trạm","email":"Email","note":"Ghi chú"},
        }
        for tab_name,sql in queries:
            frame=QWidget(); fl=QVBoxLayout(frame); fl.setContentsMargins(8,8,8,8)
            table=QTableWidget(); table.setObjectName("stationGlobalTable")
            table.setAlternatingRowColors(True); table.setShowGrid(True); table.setWordWrap(True)
            table.setSelectionBehavior(QTableWidget.SelectRows); table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.verticalHeader().setVisible(False); table.verticalHeader().setDefaultSectionSize(38)
            table.setStyleSheet("""
                QTableWidget#stationGlobalTable { background:#fff; alternate-background-color:#f7fafc; border:1px solid #d7e1eb; gridline-color:#d6dee8; }
                QTableWidget#stationGlobalTable QHeaderView::section { background:#e8f0f7; color:#18324d; padding:9px 7px; font-weight:700; border-right:1px solid #cbd5e1; border-bottom:1px solid #cbd5e1; }
                QTableWidget#stationGlobalTable::item { padding:7px 9px; border-right:1px solid #e2e8f0; border-bottom:1px solid #e2e8f0; }
            """)
            try:
                rows=self.con.execute(sql,(code,)).fetchall()
                # Lấy tên cột từ câu SELECT * để bảo đảm hiển thị đầy đủ mọi trường.
                table_name=sql.split("FROM ")[1].split()[0]
                cols=[r[1] for r in self.con.execute(f"PRAGMA table_info({table_name})").fetchall()]
                hidden_station_cols={"id","area","owner_phone","phone"}
                visible_indices=[i for i,c in enumerate(cols) if not (table_name=="stations" and c in hidden_station_cols)]
                display_cols=[labels.get(table_name,{}).get(cols[i],cols[i].replace('_',' ').title()) for i in visible_indices]
                table.setColumnCount(len(display_cols)); table.setHorizontalHeaderLabels(display_cols)
                table.setRowCount(len(rows))
                hh=table.horizontalHeader(); hh.setSectionResizeMode(QHeaderView.ResizeToContents)
                hh.setStretchLastSection(False)
                for r,row in enumerate(rows):
                    for c,src_idx in enumerate(visible_indices):
                        val=row[src_idx]
                        item=QTableWidgetItem("" if val is None else str(val))
                        item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                        table.setItem(r,c,item)
                if not rows:
                    table.setRowCount(1)
                    item=QTableWidgetItem("Không có dữ liệu trong module này.")
                    table.setSpan(0,0,1,max(1,len(display_cols)))
                    item.setTextAlignment(Qt.AlignCenter)
                    table.setItem(0,0,item)
            except Exception as exc:
                table.setColumnCount(1); table.setRowCount(1); table.setHorizontalHeaderLabels(["Thông báo"])
                table.setItem(0,0,QTableWidgetItem(f"Không đọc được dữ liệu: {exc}"))
            fl.addWidget(table)
            tabs.addTab(frame,tab_name)

        close=QPushButton("Đóng")
        close.setObjectName("secondary"); close.clicked.connect(dlg.accept)
        root.addWidget(close,0,Qt.AlignRight)
        dlg.exec()

    def _add_global_station_lookup(self, parent_layout):
        """Khung tra cứu toàn bộ hồ sơ, đặt dưới module BTBD."""
        box=QFrame(objectName="card")
        bl=QVBoxLayout(box); bl.setContentsMargins(14,12,14,12); bl.setSpacing(8)
        h=QHBoxLayout()
        h.addWidget(QLabel("🔎 Tra cứu toàn bộ hồ sơ trạm", objectName="cardLabel"))
        h.addStretch()
        h.addWidget(QLabel("Nhập bất kỳ thông tin nào: mã trạm, số HĐ, mã điện lực/mã điện kế, serial, IP, UPE, KTV, nội dung..."))
        bl.addLayout(h)
        row=QHBoxLayout()
        edit=QLineEdit(); edit.setMinimumHeight(40)
        edit.setPlaceholderText("Ví dụ: CCH088M / số HĐ / mã điện kế / serial / IP / UPE / KTV...")
        row.addWidget(edit,1)
        btn=QPushButton("🔎 Tra cứu")
        btn.setObjectName("primary"); btn.setMinimumHeight(40); btn.setMinimumWidth(115)
        row.addWidget(btn)
        bl.addLayout(row)
        # Khung kết quả được thiết kế riêng: viền rõ, khoảng đệm đều, hàng/cột cân đối.
        result_frame=QFrame()
        result_frame.setObjectName("lookupResultFrame")
        result_frame.setStyleSheet("QFrame#lookupResultFrame{background:#ffffff;border:1px solid #b9c9d8;border-radius:10px;padding:3px;}")
        result_layout=QVBoxLayout(result_frame); result_layout.setContentsMargins(0,0,0,0); result_layout.setSpacing(0)
        result=QTableWidget(0,3); result.setHorizontalHeaderLabels(["Mã trạm","Tên trạm","Địa chỉ"])
        result.setObjectName("stationGlobalResult")
        result.setAlternatingRowColors(True); result.setShowGrid(True); result.setGridStyle(Qt.SolidLine)
        result.setSelectionBehavior(QTableWidget.SelectRows); result.setEditTriggers(QTableWidget.NoEditTriggers)
        result.setWordWrap(False)
        result.verticalHeader().setVisible(False); result.verticalHeader().setDefaultSectionSize(40)
        result.setMinimumHeight(120); result.setMaximumHeight(220)
        rh=result.horizontalHeader(); rh.setMinimumSectionSize(90)
        rh.setSectionResizeMode(0,QHeaderView.Fixed); rh.setSectionResizeMode(1,QHeaderView.Fixed); rh.setSectionResizeMode(2,QHeaderView.Stretch)
        result.setColumnWidth(0,120); result.setColumnWidth(1,310)
        rh.setFixedHeight(38)
        result.setStyleSheet("""
            QTableWidget#stationGlobalResult {
                background:#ffffff;
                alternate-background-color:#f8fbfe;
                border:0;
                gridline-color:#d5dee8;
                selection-background-color:#dceeff;
                selection-color:#102a43;
                outline:0;
            }
            QTableWidget#stationGlobalResult QHeaderView::section {
                background:#e8f1f8;
                color:#17324d;
                padding:8px 10px;
                font-weight:700;
                border-right:1px solid #c5d2df;
                border-bottom:1px solid #b9c9d8;
            }
            QTableWidget#stationGlobalResult QHeaderView::section:last {
                border-right:0;
            }
            QTableWidget#stationGlobalResult::item {
                padding:8px 10px;
                border-right:1px solid #e0e7ef;
                border-bottom:1px solid #e0e7ef;
            }
            QTableWidget#stationGlobalResult::item:hover {
                background:#eef7ff;
            }
        """)
        result_layout.addWidget(result)
        bl.addWidget(result_frame)
        hint=QLabel("Nhấn đúp vào dòng kết quả để xem toàn bộ trường thông tin của trạm đó.")
        hint.setStyleSheet("color:#526579;background:#f7fafc;border:1px solid #dbe5ee;border-radius:7px;padding:7px 10px;font-size:11px;")
        bl.addWidget(hint)
        parent_layout.addWidget(box)

        def do_lookup():
            q=edit.text().strip()
            result.setRowCount(0)
            codes=self._find_station_codes_global(q)
            if not codes:
                if q:
                    result.setRowCount(1); result.setItem(0,0,QTableWidgetItem("Không tìm thấy")); result.setSpan(0,0,1,3)
                return
            rows=[]
            for code in codes:
                r=self.con.execute("SELECT code,name,address FROM stations WHERE code=?",(code,)).fetchone()
                if r: rows.append(r)
            result.setRowCount(len(rows))
            for i,r in enumerate(rows):
                for c,val in enumerate(r): result.setItem(i,c,QTableWidgetItem("" if val is None else str(val)))
                result.item(i,0).setData(Qt.UserRole,r[0])
        def open_result(row,_col=0):
            item=result.item(row,0)
            if item and item.data(Qt.UserRole): self._station_global_detail_dialog(item.data(Qt.UserRole))
        btn.clicked.connect(do_lookup); edit.returnPressed.connect(do_lookup); result.cellDoubleClicked.connect(open_result)
        self.station_global_lookup_edit=edit
        self.station_global_lookup_result=result

    def station_global_lookup_page(self):
        """Trang tra cứu độc lập, nằm dưới BTBD trong nhóm Trạm BTS."""
        w=QWidget()
        l=QVBoxLayout(w)
        l.setContentsMargins(28,24,28,24)
        l.setSpacing(12)
        top=QHBoxLayout()
        top.addWidget(self.title_block("Tra cứu trạm BTS", "Tìm bất kỳ thông tin nào để mở toàn bộ hồ sơ liên quan đến mã trạm"))
        top.addStretch()
        l.addLayout(top)
        self._add_global_station_lookup(l)
        note=QLabel("Có thể tìm bằng Mã trạm, Số HĐ, Mã điện kế/Mã điện lực, Serial, IP, UPE trạm, KTV quản lý, nội dung BTBD/MLL và các trường dữ liệu khác. Nhấn đúp vào mã trạm để xem toàn bộ hồ sơ.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#64748b;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;")
        l.addWidget(note)
        l.addStretch(1)
        return w

    def station_section_page(self, section):
        w=QWidget()
        l=QVBoxLayout(w)
        l.setContentsMargins(28,24,28,24)
        l.setSpacing(12)

        names={
            "contracts":("📄 Hợp đồng","Quản lý, phân loại và theo dõi hạn hợp đồng"),
            "equipment":("📡 Thiết bị","Thống kê theo hãng, nhóm, model và trạng thái"),
            "transmission":("🔗 Truyền dẫn","Theo dõi Main/Backup, SFP, VLAN, IP và nhà cung cấp"),
            "power_aux":("⚡ Nguồn & thiết bị phụ trợ","Theo dõi tủ nguồn, tải DC, Battery và phụ trợ"),
            "btbd":("🔧 BTBD","Theo dõi bảo trì bảo dưỡng Indoor / Outdoor"),
        }
        title,sub=names[section]
        header=QHBoxLayout()
        header.addWidget(self.title_block(title,sub))
        header.addStretch()
        export=QPushButton("📤 Xuất báo cáo",objectName="primary")
        export.clicked.connect(lambda: self.export_module_report(section))
        header.addWidget(export)
        l.addLayout(header)

        # KPI row
        cards=QHBoxLayout()
        module_kpis={}
        self.module_kpis_by_section = getattr(self, "module_kpis_by_section", {})
        kpi_labels={
            "contracts":["Tổng hợp đồng","Sắp hết hạn","Đã hết hạn"],
            "equipment":["Tổng thiết bị","Hoạt động","Cảnh báo"],
            "transmission":["Tổng tuyến","Main","Backup"],
            "power_aux":["Tủ nguồn","Battery","Thiết bị phụ trợ"],
            "btbd":["Tổng BTBD","Indoor","Outdoor"]
        }[section]
        for lab in kpi_labels:
            f=QFrame(objectName="card")
            fl=QVBoxLayout(f)
            fl.addWidget(QLabel(lab,objectName="cardLabel"))
            v=QLabel("0",objectName="cardValue")
            fl.addWidget(v)
            module_kpis[lab]=v
            cards.addWidget(f)
        l.addLayout(cards)
        self.module_kpis_by_section[section] = module_kpis

        filters=QHBoxLayout()
        filters.addWidget(QLabel("Trạng thái:"))
        status=QComboBox()
        status.addItem("Tất cả","")
        status_values={
            "contracts":["Hoạt động","Sắp hết hạn","Đã hết hạn"],
            "equipment":["Hoạt động","Cảnh báo","Không hoạt động"],
            "transmission":["Hoạt động","Cảnh báo","Mất liên lạc"],
            "power_aux":["Hoạt động","Cảnh báo","Sự cố"],
            "btbd":["Hoàn thành","Đang thực hiện","Chưa thực hiện"]
        }[section]
        for x in status_values: status.addItem(x,x)
        filters.addWidget(status)

        filters.addWidget(QLabel("Tìm kiếm:"))
        search=QComboBox()
        search.setEditable(True)
        search.setInsertPolicy(QComboBox.NoInsert)
        search.lineEdit().setPlaceholderText("Mã trạm / hãng / model / nội dung...")
        search.setMinimumHeight(38)
        # Gợi ý từ dữ liệu hiện có; nhập tới đâu combobox lọc tới đó.
        try:
            suggest_rows=self.con.execute({
                "contracts":"SELECT DISTINCT station_code FROM contracts WHERE COALESCE(station_code,'')<>'' ORDER BY station_code",
                "equipment":"SELECT DISTINCT station_code FROM equipment WHERE COALESCE(station_code,'')<>'' ORDER BY station_code",
                "transmission":"SELECT DISTINCT station_code FROM transmission WHERE COALESCE(station_code,'')<>'' ORDER BY station_code",
                "power_aux":"SELECT DISTINCT station_code FROM power WHERE COALESCE(station_code,'')<>'' ORDER BY station_code",
                "btbd":"SELECT DISTINCT station_code FROM maintenance WHERE COALESCE(station_code,'')<>'' ORDER BY station_code"
            }[section]).fetchall()
            suggestions=[str(r[0]) for r in suggest_rows if r[0]]
        except Exception:
            suggestions=[]
        completer=QCompleter(suggestions)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        search.setCompleter(completer)
        filters.addWidget(search,1)
        search_btn=QPushButton("🔎 Tìm kiếm")
        search_btn.setMinimumHeight(38)
        search_btn.setMinimumWidth(110)
        search_btn.setObjectName("secondary")
        filters.addWidget(search_btn)
        l.addLayout(filters)

        table=QTableWidget()
        table.setObjectName("moduleDataTable")
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setGridStyle(Qt.SolidLine)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setWordWrap(True)
        table.setMouseTracking(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(40)
        table.setStyleSheet("""
            QTableWidget#moduleDataTable {
                background:#ffffff;
                alternate-background-color:#f7fafc;
                border:1px solid #cfdbe7;
                border-radius:10px;
                gridline-color:#cbd5e1;
                selection-background-color:#dbeafe;
                selection-color:#0f172a;
                outline:0;
            }
            QTableWidget#moduleDataTable::item {
                padding:8px 10px;
                border-right:1px solid #d8e1ea;
                border-bottom:1px solid #d8e1ea;
            }
            QTableWidget#moduleDataTable::item:hover {
                background:#eef6ff;
            }
            QTableWidget#moduleDataTable QHeaderView::section {
                background:#e8f0f7;
                color:#18324d;
                border-right:1px solid #cbd5e1;
                border-bottom:1px solid #bfcbd8;
                padding:10px 8px;
                font-weight:700;
                min-height:38px;
            }
        """)
        l.addWidget(table,1)

        # Cache trạng thái từng module để chuyển menu tức thời; chỉ reload khi dirty.
        module_state = getattr(self, "_module_page_state", {})
        module_state.setdefault(section, {"loaded": False, "dirty": False})
        self._module_page_state = module_state

        def reload():
            st=status.currentData()
            q=search.currentText().strip().lower()

            if section=="contracts":
                headers=["Mã trạm","Số HĐ","Loại","Bên cho thuê","Ngày hết hạn","Giá thuê","Trạng thái"]
                sql="""SELECT contract_id,station_code,contract_no,contract_type,lessor,end_date,rent_amount,status
                       FROM contracts WHERE 1=1"""
                args=[]
                if st: sql+=" AND status=?"; args.append(st)
                if q: sql+=" AND lower(station_code||' '||contract_no||' '||lessor) LIKE ?"; args.append("%"+q+"%")
                rows=self.con.execute(sql,args).fetchall()
                total=len(rows)
                today=datetime.date.today().isoformat()
                expired=sum(1 for r in rows if str(r[5] or "") and str(r[5])<today)
                soon=sum(1 for r in rows if str(r[5] or "") and today<=str(r[5])<=str(datetime.date.today()+datetime.timedelta(days=90)))
                module_kpis["Tổng hợp đồng"].setText(str(total))
                module_kpis["Sắp hết hạn"].setText(str(soon))
                module_kpis["Đã hết hạn"].setText(str(expired))
            elif section=="equipment":
                headers=["Mã trạm","Nhóm","Hãng","Model","Serial","IP","Trạng thái"]
                sql="""SELECT equipment_id,station_code,equipment_group,vendor,model,serial_no,ip_address,status
                       FROM equipment WHERE 1=1"""
                args=[]
                if st: sql+=" AND status=?"; args.append(st)
                if q: sql+=" AND lower(station_code||' '||vendor||' '||model||' '||serial_no) LIKE ?"; args.append("%"+q+"%")
                rows=self.con.execute(sql,args).fetchall()
                module_kpis["Tổng thiết bị"].setText(str(len(rows)))
                module_kpis["Hoạt động"].setText(str(sum(1 for r in rows if r[7]=="Hoạt động")))
                module_kpis["Cảnh báo"].setText(str(sum(1 for r in rows if r[7]=="Cảnh báo")))
            elif section=="transmission":
                headers=["Mã trạm","Main/Backup","Thiết bị A","Port A","Thiết bị B","Port B","VLAN","IP WAN","LACP","Trạng thái"]
                sql="""SELECT transmission_id,station_code,path_role,device_a,port_a,device_b,port_b,vlan,wan_ip,lacp,status
                       FROM transmission WHERE 1=1"""
                args=[]
                if st: sql+=" AND status=?"; args.append(st)
                if q: sql+=" AND lower(station_code||' '||device_a||' '||device_b||' '||vlan||' '||wan_ip) LIKE ?"; args.append("%"+q+"%")
                rows=self.con.execute(sql,args).fetchall()
                module_kpis["Tổng tuyến"].setText(str(len(rows)))
                module_kpis["Main"].setText(str(sum(1 for r in rows if str(r[2]).lower() in ("main","chính","tuyến chính"))))
                module_kpis["Backup"].setText(str(sum(1 for r in rows if "backup" in str(r[2]).lower())))
            elif section=="power_aux":
                headers=["Mã trạm","Hãng nguồn","Model","Công suất A","Tải DC A","LLVD1","LLVD2","BLVD","Trạng thái"]
                sql="""SELECT power_id,station_code,power_vendor,power_model,capacity_a,dc_load_a,llvd1_v,llvd2_v,blvd_v,status
                       FROM power WHERE 1=1"""
                args=[]
                if st: sql+=" AND status=?"; args.append(st)
                if q: sql+=" AND lower(station_code||' '||power_vendor||' '||power_model) LIKE ?"; args.append("%"+q+"%")
                rows=self.con.execute(sql,args).fetchall()
                module_kpis["Tủ nguồn"].setText(str(len(rows)))
                if q:
                    codes=[r[1] for r in rows]
                    ph=",".join("?" for _ in codes)
                    module_kpis["Battery"].setText(str(self.con.execute(
                        f"SELECT COUNT(*) FROM batteries WHERE station_code IN ({ph})",codes
                    ).fetchone()[0]) if codes else "0")
                    module_kpis["Thiết bị phụ trợ"].setText(str(self.con.execute(
                        f"SELECT COUNT(*) FROM auxiliary WHERE station_code IN ({ph})",codes
                    ).fetchone()[0]) if codes else "0")
                else:
                    module_kpis["Battery"].setText(str(self.con.execute("SELECT COUNT(*) FROM batteries").fetchone()[0]))
                    module_kpis["Thiết bị phụ trợ"].setText(str(self.con.execute("SELECT COUNT(*) FROM auxiliary").fetchone()[0]))
            else:
                headers=["Ngày","Mã trạm","Indoor/Outdoor","Loại","KTV","Nội dung","Kết quả","Trạng thái"]
                sql="""SELECT work_id,work_date,station_code,scope,work_type,technician,content,result,status
                       FROM maintenance WHERE 1=1"""
                args=[]
                if st: sql+=" AND status=?"; args.append(st)
                if q: sql+=" AND lower(station_code||' '||technician||' '||content) LIKE ?"; args.append("%"+q+"%")
                sql+=" ORDER BY work_date DESC"
                rows=self.con.execute(sql,args).fetchall()
                module_kpis["Tổng BTBD"].setText(str(len(rows)))
                module_kpis["Indoor"].setText(str(sum(1 for r in rows if str(r[3]).lower()=="indoor")))
                module_kpis["Outdoor"].setText(str(sum(1 for r in rows if str(r[3]).lower()=="outdoor")))

            # Cột Cập nhật luôn nằm cuối bảng để chỉnh sửa trực tiếp từng dòng.
            data_headers = list(headers) + ["Cập nhật"]
            table.setColumnCount(len(data_headers))
            table.setHorizontalHeaderLabels(data_headers)
            header=table.horizontalHeader()
            header.setDefaultAlignment(Qt.AlignCenter)
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setStretchLastSection(True)
            table.setRowCount(len(rows))

            # Căn chỉnh theo loại dữ liệu: mã/số/ngày/trạng thái ở giữa,
            # nội dung mô tả căn trái để dễ đọc.
            center_cols=set()
            for c,h in enumerate(headers):
                hh=str(h).lower()
                if any(k in hh for k in ("mã", "số hđ", "ngày", "giờ", "port", "vlan", "ip", "công suất", "tải", "llvd", "blvd", "trạng thái", "indoor/outdoor", "loại", "main/backup")):
                    center_cols.add(c)
            for r,row in enumerate(rows):
                # Phần tử đầu tiên là khóa chính nội bộ, không hiển thị trên lưới.
                # Nhờ vậy nút Cập nhật luôn mở đúng bản ghi, kể cả khi Mã trạm xuất hiện nhiều lần.
                record_id = str(row[0] or "")
                display_row = row[1:]
                for c,v in enumerate(display_row):
                    item=QTableWidgetItem(str(v or ""))
                    item.setData(Qt.UserRole, record_id)
                    item.setTextAlignment(Qt.AlignCenter if c in center_cols else (Qt.AlignLeft|Qt.AlignVCenter))
                    table.setItem(r,c,item)

                action=QWidget()
                ah=QHBoxLayout(action); ah.setContentsMargins(4,4,4,4); ah.setSpacing(4)
                btn=QPushButton("✏️ Cập nhật")
                btn.setFixedHeight(30)
                btn.setStyleSheet("QPushButton{background:#e8f3ff;border:1px solid #9bc4e8;border-radius:6px;color:#0b5fa5;font-weight:700;} QPushButton:hover{background:#d7ebff;}")
                btn.clicked.connect(lambda checked=False, sec=section, rid=record_id: self.edit_module_record(sec, rid))
                ah.addWidget(btn)
                table.setCellWidget(r,len(headers),action)

            # Cột nội dung/mô tả rộng hơn; các cột kỹ thuật giữ kích thước gọn.
            for c,h in enumerate(headers):
                hh=str(h).lower()
                if any(k in hh for k in ("nội dung", "bên cho thuê", "ktv", "hãng", "model")):
                    header.setSectionResizeMode(c,QHeaderView.Stretch)
            header.setSectionResizeMode(len(headers),QHeaderView.Fixed)
            table.setColumnWidth(len(headers),125)

        status.currentIndexChanged.connect(reload)
        search_btn.clicked.connect(reload)
        search.lineEdit().returnPressed.connect(reload)
        # Lưu callback để Import Excel / Cloud Sync refresh đúng bảng đang hiển thị.
        def reload_module():
            reload()
            module_state[section]["loaded"] = True
            module_state[section]["dirty"] = False
        self.module_reloaders[section] = reload_module
        reload_module()
        return w

    def _prepare_local_update(self, label="cập nhật dữ liệu"):
        """Tạm dừng Cloud Sync để tránh hai SQLite connection ghi đồng thời.

        Chỉ dùng cho các thao tác cập nhật dữ liệu vận hành trên UI. Worker Cloud
        dùng connection riêng; nếu đang ghi mà UI UPDATE cùng lúc, SQLite có thể
        trả về OperationalError: database is locked.
        """
        timer_was_active = bool(getattr(self, "cloud_timer", None) and self.cloud_timer.isActive())
        if timer_was_active:
            self.cloud_timer.stop()
        worker = getattr(self, "_cloud_worker", None)
        if worker is not None and worker.isRunning():
            try:
                self.cloud_status.setText(f"☁ Đang chờ đồng bộ nền kết thúc trước khi {label}…")
            except Exception:
                pass
            QApplication.processEvents()
            if not worker.wait(30000):
                if timer_was_active and self.cloud_logged_in:
                    self.cloud_timer.start(45000)
                QMessageBox.warning(
                    self, "Cập nhật dữ liệu",
                    "Đồng bộ nền chưa kết thúc sau 30 giây.\n\n"
                    "Chưa ghi dữ liệu để tránh lỗi khóa cơ sở dữ liệu.\n"
                    "Vui lòng thực hiện lại sau khi đồng bộ hoàn tất."
                )
                return False, timer_was_active
        try:
            # Clear any stale UI transaction before acquiring the write lock.
            self.con.rollback()
            self.con.execute("PRAGMA busy_timeout=30000")
            self.con.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        return True, timer_was_active

    def _finish_local_update(self, timer_was_active):
        if timer_was_active and self.cloud_logged_in:
            try:
                self.cloud_timer.start(45000)
            except Exception:
                pass

    def _module_record_id(self, section, row):
        """Khóa chính nội bộ nằm ở phần tử đầu tiên của kết quả SELECT."""
        return str(row[0] or "") if row else ""

    def edit_module_record(self, section, record_id):
        """Mở popup chỉnh sửa toàn bộ trường dữ liệu của một bản ghi."""
        if not record_id:
            QMessageBox.warning(self, "Không có dữ liệu", "Không xác định được mã bản ghi để cập nhật.")
            return
        specs = excel_specs().get({
            "contracts":"HỢP ĐỒNG", "equipment":"THIẾT BỊ", "transmission":"TRUYỀN DẪN",
            "power_aux":"NGUỒN", "btbd":"BTBD"
        }.get(section, ""))
        if not specs:
            return
        table_name=specs["table"]
        key=specs["key"]
        row=self.con.execute(f"SELECT * FROM {table_name} WHERE {key}=?",(record_id,)).fetchone()
        if not row:
            QMessageBox.warning(self,"Không tìm thấy",f"Không tìm thấy bản ghi {record_id}.")
            return

        dlg=QDialog(self)
        dlg.setWindowTitle(f"✏️ Cập nhật {table_name} • {record_id}")
        dlg.resize(620, min(760, 120 + len(specs["cols"])*42))
        root=QVBoxLayout(dlg)
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        form_host=QWidget(); form=QFormLayout(form_host)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        editors={}
        for label,field in specs["cols"].items():
            # Các trường ID kỹ thuật nằm ở cột A của các sheet nghiệp vụ đã bị loại khỏi
            # file Import mới. Chúng vẫn có thể tồn tại trong SQLite để tương thích,
            # nhưng KHÔNG được hiển thị trong form Cập nhật.
            if field == key:
                continue
            value=row[field] if field in row.keys() else ""
            if field == "station_code":
                # Mã trạm là khóa liên kết giữa các sheet: luôn khóa, không cho đổi.
                ed=QLineEdit(str(value or ""))
                ed.setReadOnly(True)
                ed.setStyleSheet("background:#f1f5f9;color:#64748b;font-weight:700;")
                ed.setToolTip("Mã trạm là khóa liên kết và không thể thay đổi tại đây.")
            else:
                ed=QLineEdit(str(value or ""))
                ed.setPlaceholderText(label)
            editors[field]=ed
            form.addRow(QLabel(label+":"), ed)

        scroll.setWidget(form_host); root.addWidget(scroll,1)
        buttons=QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        root.addWidget(buttons)
        if dlg.exec()!=QDialog.Accepted:
            return

        values={}
        for field,ed in editors.items():
            if isinstance(ed,QComboBox): values[field]=ed.currentText().strip()
            else: values[field]=ed.text().strip()
        # Khóa chính không cho sửa; tránh làm mất liên kết dữ liệu.
        values[key]=str(row[key] or record_id)
        assignments=[f"{field}=?" for field in specs["cols"].values() if field != key]
        params=[values[field] for field in specs["cols"].values() if field != key]
        params.append(record_id)
        ok_update, timer_was_active = self._prepare_local_update("cập nhật dữ liệu")
        if not ok_update:
            return
        try:
            # Acquire the local write lock only after the Cloud worker has released
            # its connection. This prevents the intermittent SQLite lock race.
            self.con.execute("BEGIN IMMEDIATE")
            self.con.execute(
                f"UPDATE {table_name} SET {', '.join(assignments)} WHERE {key}=?",
                params
            )
            self.con.commit()
            self.refresh_all()
            QMessageBox.information(self,"Cập nhật thành công",f"Đã cập nhật {record_id}.")
        except sqlite3.IntegrityError as e:
            try: self.con.rollback()
            except Exception: pass
            QMessageBox.critical(self,"Không thể cập nhật",f"Dữ liệu bị trùng hoặc vi phạm ràng buộc.\n\n{e}")
        except sqlite3.OperationalError as e:
            try: self.con.rollback()
            except Exception: pass
            if "locked" in str(e).lower():
                QMessageBox.critical(self,"Lỗi cập nhật",
                    "Không thể cập nhật dữ liệu vì cơ sở dữ liệu vẫn đang bị khóa.\n\n"
                    "Đồng bộ nền đã được tạm dừng trong lúc ghi. Vui lòng thử lại sau vài giây.")
            else:
                QMessageBox.critical(self,"Lỗi cập nhật",f"Không thể cập nhật dữ liệu.\n\n{type(e).__name__}: {e}")
        except Exception as e:
            try: self.con.rollback()
            except Exception: pass
            QMessageBox.critical(self,"Lỗi cập nhật",f"Không thể cập nhật dữ liệu.\n\n{type(e).__name__}: {e}")
        finally:
            self._finish_local_update(timer_was_active)

    def export_module_report(self, section):
        names={
            "contracts":"Bao_cao_Hop_dong.xlsx",
            "equipment":"Bao_cao_Thiet_bi.xlsx",
            "transmission":"Bao_cao_Truyen_dan.xlsx",
            "power_aux":"Bao_cao_Nguon_Phu_tro.xlsx",
            "btbd":"Bao_cao_BTBD.xlsx"
        }
        path,_=QFileDialog.getSaveFileName(
            self,"Xuất báo cáo",str(Path.home()/names[section]),"Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path+=".xlsx"
        try:
            from openpyxl import Workbook
            wb=Workbook()
            ws=wb.active
            titles={
                "contracts":"BÁO CÁO HỢP ĐỒNG BTS",
                "equipment":"BÁO CÁO THIẾT BỊ BTS",
                "transmission":"BÁO CÁO TRUYỀN DẪN BTS",
                "power_aux":"BÁO CÁO NGUỒN & THIẾT BỊ PHỤ TRỢ",
                "btbd":"BÁO CÁO BTBD BTS"
            }
            ws.title="Báo cáo"
            ws.append([titles[section]])
            ws.append(["Thời gian xuất",datetime.datetime.now().strftime("%d/%m/%Y %H:%M")])
            if section=="contracts":
                heads=["Mã HĐ","Mã trạm","Số HĐ","Loại","Bên cho thuê","Ngày bắt đầu","Ngày hết hạn","Giá thuê","Trạng thái"]
                query="SELECT contract_id,station_code,contract_no,contract_type,lessor,start_date,end_date,rent_amount,status FROM contracts"
            elif section=="equipment":
                heads=["Mã TB","Mã trạm","Nhóm","Hãng","Model","Serial","IP","Trạng thái"]
                query="SELECT equipment_id,station_code,equipment_group,vendor,model,serial_no,ip_address,status FROM equipment"
            elif section=="transmission":
                heads=["Mã","Mã trạm","Main/Backup","Thiết bị A","Port A","Thiết bị B","Port B","VLAN","IP WAN","LACP","Trạng thái"]
                query="SELECT transmission_id,station_code,path_role,device_a,port_a,device_b,port_b,vlan,wan_ip,lacp,status FROM transmission"
            elif section=="power_aux":
                heads=["Mã nguồn","Mã trạm","Hãng","Model","Công suất A","Tải DC A","LLVD1","LLVD2","BLVD","Trạng thái"]
                query="SELECT power_id,station_code,power_vendor,power_model,capacity_a,dc_load_a,llvd1_v,llvd2_v,blvd_v,status FROM power"
            else:
                heads=["Mã BTBD","Mã trạm","Phạm vi","Loại","Ngày","KTV","Nội dung","Kết quả","Trạng thái"]
                query="SELECT work_id,station_code,scope,work_type,work_date,technician,content,result,status FROM maintenance ORDER BY work_date DESC"
            ws.append(heads)
            for row in self.con.execute(query).fetchall():
                ws.append(list(row))
            from openpyxl.styles import Font
            ws["A1"].font=Font(bold=True,size=15)
            for cell in ws[3]:
                cell.font=Font(bold=True)
            ws.freeze_panes="A4"
            wb.save(path)
            QMessageBox.information(self,"Xuất báo cáo",f"Đã xuất:\n{path}")
        except Exception as e:
            QMessageBox.critical(self,"Lỗi xuất báo cáo",str(e))


    def open_station_by_combo(self, combo):
        code=combo.currentData()
        if not code:
            QMessageBox.information(self,"Chọn trạm","Vui lòng chọn một trạm BTS.")
            return
        dlg=StationWindow(self,self.con,code)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def go_page(self, i):
        self.stack.setCurrentIndex(i)
        try:
            # Mỗi lần mở mục Thông báo phải nạp lại dữ liệu mới nhất, đặc biệt
            # các cảnh báo HĐ vừa được tạo tự động ở Dashboard.
            if i == getattr(self, "notice_page_index", -1):
                self.refresh_automatic_alerts(show_popup=False)
                current_month = (self.notice_month_combo.currentData()
                                 if hasattr(self, "notice_month_combo") else None)
                if hasattr(self, "notice_table"):
                    self.load_notifications_for_month(current_month or datetime.date.today().strftime("%Y-%m"))
            if hasattr(self, "station_table") and i == getattr(self, "station_page_index", -1):
                self.load_station_list()
            section = getattr(self, "_page_section_map", {}).get(i)
            if section:
                state = getattr(self, "_module_page_state", {}).get(section, {})
                if state.get("dirty") or not state.get("loaded"):
                    reload_fn = getattr(self, "module_reloaders", {}).get(section)
                    if reload_fn:
                        reload_fn()
        except Exception as e:
            print(f"[WARN] refresh page {i}: {e}")
        for n,b in enumerate(self.navs):
            b.setObjectName("navActive" if n==i else "nav")
            b.style().unpolish(b)
            b.style().polish(b)

        child_indices = set(range(self.child_start, len(self.pages))) if hasattr(self,"child_start") else set()
        if i in child_indices:
            self.station_parent.setObjectName("navActive")
        else:
            self.station_parent.setObjectName("nav")
        self.station_parent.style().unpolish(self.station_parent)
        self.station_parent.style().polish(self.station_parent)

    def title_block(self, title, sub):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(0,0,0,0)
        a=QLabel(title, objectName="pageTitle"); b=QLabel(sub, objectName="pageSub")
        l.addWidget(a); l.addWidget(b); return w

    def card(self, icon, label, value="0", key=None):
        f=QFrame(objectName="card"); l=QVBoxLayout(f); l.setContentsMargins(16,13,16,14)
        top=QHBoxLayout()
        if label == "Phát triển mới":
            icon_path = RESOURCE_DIR / "phat_trien_moi.png"
            ic=QLabel(objectName="cardIcon")
            if icon_path.exists():
                pix=QPixmap(str(icon_path))
                ic.setPixmap(pix.scaled(52,52,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            else:
                ic.setText(icon)
        else:
            ic=QLabel(icon, objectName="cardIcon")
        lab=QLabel(label, objectName="cardLabel")
        top.addWidget(ic); top.addWidget(lab); top.addStretch(); l.addLayout(top)
        val=QLabel(str(value), objectName="dashCardValue" if key and str(key).startswith("dash_") else "cardValue")
        if key: setattr(self,key,val)
        if key and str(key).startswith("dash_"):
            lab.setObjectName("dashCardLabel")
            ic.setStyleSheet("font-size:30px;")
        l.addWidget(val); return f

    def dashboard_page(self):
        outer=QScrollArea(); outer.setWidgetResizable(True); outer.setFrameShape(QFrame.NoFrame)
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(24,20,24,20); l.setSpacing(12)

        # ===== HEADER / CÁC NÚT THAO TÁC =====
        header=QHBoxLayout(); header.setSpacing(8)
        header.addWidget(self.title_block(
            "Tổng quan • BTS Manager",
            "Thông tin vận hành BTS • phân tích mất liên lạc (MLL)"
        ))
        header.addStretch()
        template_box=QComboBox(objectName="templateSelector")
        template_box.addItems(["Mẫu Import BTS", "Mẫu MLL", "Mẫu KPI", "Cả 3 mẫu"])
        template_box.setToolTip("Chọn mẫu Import BTS, MLL hoặc KPI")
        template_box.setMinimumWidth(145)
        self.template_selector=template_box
        header.addWidget(template_box)
        template=QPushButton("📄 Tải file mẫu",objectName="secondary"); template.clicked.connect(self.download_selected_template); header.addWidget(template)
        upload=QPushButton("📤 Upload file",objectName="primary"); upload.setToolTip("Tự nhận diện file mẫu BTS, MLL hoặc KPI và nhập dữ liệu"); upload.clicked.connect(self.upload_excel_auto); header.addWidget(upload)
        export=QPushButton("📊 Báo cáo tổng hợp",objectName="secondary"); export.clicked.connect(self.export_dashboard_report); header.addWidget(export)
        refresh=QPushButton("🔄",objectName="secondary"); refresh.setToolTip("Làm mới dữ liệu"); refresh.clicked.connect(self.refresh_all); header.addWidget(refresh)
        l.addLayout(header)

        # ===== KHUNG CẢNH BÁO TỰ ĐỘNG =====
        alert_box=QFrame(objectName="card")
        alert_box.setMinimumHeight(92)
        alert_box.setMaximumHeight(180)
        alert_layout=QVBoxLayout(alert_box)
        alert_layout.setContentsMargins(14,10,14,10)
        alert_layout.setSpacing(6)
        alert_head=QHBoxLayout()
        self.dashboard_alert_title=QLabel("⚠️ CẢNH BÁO", objectName="dashSectionTitle")
        self.dashboard_alert_count=QLabel("0", objectName="cardValue")
        self.dashboard_alert_count.setStyleSheet("font-size:18px;color:#b42318;")
        alert_head.addWidget(self.dashboard_alert_title)
        alert_head.addWidget(self.dashboard_alert_count)
        alert_head.addStretch()
        alert_layout.addLayout(alert_head)
        self.dashboard_alert_list=QLabel("Không có cảnh báo tự động.")
        self.dashboard_alert_list.setWordWrap(True)
        self.dashboard_alert_list.setMinimumHeight(48)
        self.dashboard_alert_list.setMaximumHeight(118)
        self.dashboard_alert_list.setStyleSheet("color:#7a271a;font-size:12px;padding:4px;")
        alert_layout.addWidget(self.dashboard_alert_list)
        l.addWidget(alert_box)

        # ===== THÔNG TIN VẬN HÀNH: 5 biểu đồ donut cân đối, không có hàng KPI trên cùng =====
        l.addWidget(QLabel("📊 THÔNG TIN VẬN HÀNH",objectName="dashSectionTitle"))

        overview_row=QHBoxLayout(); overview_row.setSpacing(10)
        overview_row.setContentsMargins(0,0,0,0)
        overview_specs=[
            ("🏷️ Loại trạm","type_layout","Loại trạm"),
            ("🔗 Kết nối UPE","upe_layout","UPE"),
            ("🏗️ Loại trụ","pole_layout","Trạm"),
            ("🧱 Loại CSHT","csht_layout","Trạm"),
            ("👷 KTV quản lý","ktv_layout","Trạm"),
        ]
        for title,attr,center in overview_specs:
            f=QFrame(objectName="card"); q=QVBoxLayout(f); q.setContentsMargins(8,8,8,8); q.setSpacing(2)
            chart=MLLChartWidget(title,"donut",center)
            chart.setMinimumHeight(230)
            setattr(self,attr,chart)
            q.addWidget(chart)
            overview_row.addWidget(f,1)
        l.addLayout(overview_row)

        # ===== CHỈ SỐ CẦN QUAN TÂM: BTBD Indoor/Outdoor, Mất LL, XL PAKH, Phát triển mới =====
        l.addWidget(QLabel("🎯 CHỈ SỐ CẦN QUAN TÂM",objectName="dashFocusTitle"))
        focus_row=QHBoxLayout(); focus_row.setSpacing(10)
        for ic,lab,key in [
            ("🏢","BTBD Indoor","dash_btbd_indoor"),
            ("🗼","BTBD Outdoor","dash_btbd_outdoor"),
            ("📡","Mất LL (TB MLL)","dash_mll_cases"),
            ("🎯","XL PAKH","dash_xl_pakh"),
            ("🌱","Phát triển mới","dash_new_development"),
        ]:
            focus_card=self.card(ic,lab,"0",key)
            # 5 thẻ phải nằm gọn trên cùng một hàng; không để QLabel tự ép
            # tăng chiều rộng làm mất thẻ bên phải khi cửa sổ hẹp hơn.
            focus_card.setObjectName("dashFocusCard")
            focus_card.setMinimumWidth(0)
            focus_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            focus_card.setMinimumHeight(138)
            fl=focus_card.layout()
            if fl:
                fl.setContentsMargins(11,10,11,10)
                fl.setSpacing(5)
                for child in focus_card.findChildren(QLabel):
                    child.setWordWrap(False)
                    child.setMinimumWidth(0)
                    child.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            focus_row.addWidget(focus_card,1)
        l.addLayout(focus_row)

        # ===== PHÂN TÍCH MLL: KPI chi tiết nằm trong chính khung MLL =====
        mll_box=QFrame(objectName="card"); ml=QVBoxLayout(mll_box); ml.setContentsMargins(12,10,12,12); ml.setSpacing(8)
        ml.addWidget(QLabel("📉 PHÂN TÍCH MẤT LIÊN LẠC (MLL)",objectName="dashMllTitle"))

        # Bộ lọc thời gian: cho phép thống kê/đánh giá từ tháng A đến tháng B.
        period_row=QHBoxLayout(); period_row.setSpacing(8)
        period_row.addWidget(QLabel("📅 Thống kê từ"))
        self.mll_from_month=QComboBox(objectName="mllPeriodCombo")
        self.mll_from_month.addItems([f"Tháng {i}" for i in range(1,13)])
        self.mll_from_month.setCurrentIndex(0)
        self.mll_from_month.setMinimumWidth(105)
        period_row.addWidget(self.mll_from_month)
        period_row.addWidget(QLabel("đến"))
        self.mll_to_month=QComboBox(objectName="mllPeriodCombo")
        self.mll_to_month.addItems([f"Tháng {i}" for i in range(1,13)])
        self.mll_to_month.setCurrentIndex(5)
        self.mll_to_month.setMinimumWidth(105)
        period_row.addWidget(self.mll_to_month)
        period_row.addStretch()
        ml.addLayout(period_row)

        self.mll_from_month.currentIndexChanged.connect(self._on_mll_period_changed)
        self.mll_to_month.currentIndexChanged.connect(self._on_mll_period_changed)

        kpi=QGridLayout(); kpi.setSpacing(8)
        specs=[
            ("⚠️","Tổng sự cố (MLL)","mll_kpi_cases"),
            ("⏱","Tổng phút gián đoạn","mll_kpi_down"),
            ("📈","MLL trung bình / vụ","mll_kpi_avg"),
            ("📍","Trạm bị ảnh hưởng","mll_kpi_stations"),
            ("🎯","Nguyên nhân chính","mll_kpi_reason"),
        ]
        # 5 KPI nằm trên cùng một hàng, tránh "Nguyên nhân chính" bị rơi xuống dòng 2.
        for i,(ic,lab,key) in enumerate(specs):
            card = self.card(ic,lab,"0",key)
            # Thu gọn số liệu để 5 KPI cùng hàng cân đối, không lấn át tổng thể dashboard.
            for value_label in card.findChildren(QLabel):
                if value_label.objectName() == "cardValue":
                    value_label.setStyleSheet("font-size:22px;font-weight:900;color:#0b2a4a;")
                    value_label.setMinimumWidth(0)
                    value_label.setWordWrap(False)
            kpi.addWidget(card, 0, i)
            kpi.setColumnStretch(i, 1)
        ml.addLayout(kpi)
        charts=QGridLayout(); charts.setSpacing(8)
        self.mll_month_chart=MLLChartWidget("1. Xu hướng MLL & BSC theo tháng","combo")
        self.mll_reason_chart=MLLChartWidget("2. Phân bố nguyên nhân sự cố","donut")
        self.mll_service_chart=MLLChartWidget("3. Lớp dịch vụ bị ảnh hưởng","donut")
        charts.addWidget(self._chart_card(self.mll_month_chart),0,0)
        charts.addWidget(self._chart_card(self.mll_reason_chart),0,1)
        charts.addWidget(self._chart_card(self.mll_service_chart),0,2)
        ml.addLayout(charts)

        # ===== HAI BẢNG MLL: STT + lưới rõ + kích thước cân đối =====
        tables=QHBoxLayout(); tables.setSpacing(10)
        table_css="""
            QTableWidget { background:#ffffff; border:1px solid #cbd5e1; border-radius:10px;
                gridline-color:#cbd5e1; alternate-background-color:#f8fafc;
                font-size:12px; color:#17324d; }
            QTableWidget::item { padding:7px 8px; border:0; }
            QTableWidget::item:selected { background:#eaf3ff; color:#17324d; }
            QHeaderView::section { background:#edf4fa; color:#28445f;
                border-right:1px solid #cbd5e1; border-bottom:1px solid #cbd5e1;
                padding:8px 9px; font-weight:700; font-size:11px; }
        """

        top_frame=QFrame(objectName="card"); top_l=QVBoxLayout(top_frame); top_l.setContentsMargins(10,8,10,10); top_l.setSpacing(6)
        top_l.addWidget(QLabel("📊 4. Top trạm theo tổng phút gián đoạn",objectName="dashMllCardLabel"))
        self.mll_station_table=QTableWidget(0,4); self.mll_station_table.setHorizontalHeaderLabels(["STT","TRẠM","VỤ","PHÚT"])
        self._style_mll_table(self.mll_station_table, table_css,
                              [QHeaderView.ResizeToContents,QHeaderView.Stretch,QHeaderView.ResizeToContents,QHeaderView.ResizeToContents])
        top_l.addWidget(self.mll_station_table); tables.addWidget(top_frame,1)

        long_frame=QFrame(objectName="card"); long_l=QVBoxLayout(long_frame); long_l.setContentsMargins(10,8,10,10); long_l.setSpacing(6)
        long_l.addWidget(QLabel("⏱ 5. 5 sự cố dài nhất",objectName="dashMllCardLabel"))
        self.mll_long_table=QTableWidget(0,5); self.mll_long_table.setHorizontalHeaderLabels(["STT","TRẠM","THÁNG","NGUYÊN NHÂN","PHÚT"])
        self._style_mll_table(self.mll_long_table, table_css,
                              [QHeaderView.ResizeToContents,QHeaderView.ResizeToContents,QHeaderView.ResizeToContents,QHeaderView.Stretch,QHeaderView.ResizeToContents])
        long_l.addWidget(self.mll_long_table); tables.addWidget(long_frame,1)
        ml.addLayout(tables)

        self.mll_insight=QLabel("Đang phân tích…"); self.mll_insight.setWordWrap(True)
        self.mll_insight.setStyleSheet("color:#166534;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;font-size:12px;padding:6px 8px;")
        ml.addWidget(self.mll_insight)
        l.addWidget(mll_box)

        outer.setWidget(w); return outer

    def _style_mll_table(self, table, css, modes):
        table.setShowGrid(True)
        table.setGridStyle(Qt.SolidLine)
        table.setAlternatingRowColors(True)
        table.setFocusPolicy(Qt.NoFocus)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.horizontalHeader().setMinimumHeight(38)
        for i,mode in enumerate(modes):
            table.horizontalHeader().setSectionResizeMode(i,mode)
        table.setMinimumHeight(220); table.setMaximumHeight(270)
        table.setStyleSheet(css)

    def add_work(self):
        # Mở trực tiếp module BTBD để tạo công việc.
        idx=getattr(self,"child_start",1)+4
        if idx < len(self.pages): self.go_page(idx)

    def open_equipment_search(self):
        # Mở module Thiết bị trong nhóm Trạm BTS.
        idx=getattr(self,"child_start",1)+1
        if idx < len(self.pages): self.go_page(idx)

    def open_map(self):
        QMessageBox.information(self,"Bản đồ BTS","Module Bản đồ đang được giữ nguyên theo phiên bản V9.6.4 Fix2. Bạn có thể mở từ menu Trạm BTS khi module bản đồ được bật.")

    def open_alert_settings(self):
        if hasattr(self,"notice_page_index"):
            self.go_page(self.notice_page_index)

    def _chart_card(self, chart):
        f=QFrame(objectName="card"); q=QVBoxLayout(f); q.setContentsMargins(6,6,6,6); q.addWidget(chart); return f

    def seed_mll_data(self):
        count=self.con.execute("SELECT COUNT(*) FROM mll_events").fetchone()[0]
        if count: return
        sql="""INSERT INTO mll_events
        (month,station_code,dept,cb_type,g5,g3,g4,start_date,start_time,end_date,end_time,
         downtime_min,handler,error_code,error_content,resolution,bsc_min,layer_min,csht_code,csht_type)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        self.con.executemany(sql, MLL_SEED); self.con.commit()

    def import_mll_excel(self, path=None):
        if not path:
            path,_=QFileDialog.getOpenFileName(self,"Chọn file Excel MLL","","Excel (*.xlsx *.xls)")
            if not path: return
        try:
            from openpyxl import load_workbook
            wb=load_workbook(path,data_only=True)
            ws=wb["MLL"] if "MLL" in wb.sheetnames else wb.active
            values=list(ws.values); header_idx=None
            for i,row in enumerate(values[:20]):
                if row and str(row[0]).strip()=="Tháng": header_idx=i; break
            if header_idx is None: raise ValueError("Không tìm thấy dòng tiêu đề có cột 'Tháng'.")
            headers=[str(x).strip() if x is not None else "" for x in values[header_idx][:20]]; idx={h:i for i,h in enumerate(headers)}
            required=["Tháng","Mã trạm","Ngày BĐ","Giờ BĐ","TG gián đoạn (phút)","Mã lỗi","Nội dung lỗi","Nội dung xử lý","MLL tính BSC (phút)","MLL × số lớp (phút)","Mã CSHT","Loại CSHT"]
            missing=[x for x in required if x not in idx]
            if missing: raise ValueError("Thiếu cột: "+", ".join(missing))
            rows=[]
            for row in values[header_idx+1:]:
                if not row or not row[idx["Mã trạm"]]: continue
                rows.append(tuple(row[idx[k]] if idx.get(k,999)<len(row) else None for k in MLL_COLUMNS))
            if not rows: raise ValueError("File không có dòng dữ liệu MLL.")
            bsc_rows=[]
            if "BSC TỔNG" in wb.sheetnames:
                bws=wb["BSC TỔNG"]; bvals=list(bws.values); bheader=None
                for i,row in enumerate(bvals[:10]):
                    norm=[str(x).strip() if x is not None else "" for x in (row or [])]
                    if norm and norm[0].casefold()=="p.ht": bheader=i; break
                if bheader is not None:
                    hdr=[str(x).strip() if x is not None else "" for x in bvals[bheader]]
                    avg_idx=next((i for i,h in enumerate(hdr) if h.casefold() in ("tb 6 tháng (phút)","tb bsc (phút)","tb bsc")), None)
                    for r in bvals[bheader+1:]:
                        if not r or not r[0]: continue
                        dept=str(r[0]).strip()
                        month_vals=[]
                        for m in range(1,7):
                            if m < len(r):
                                try: val=float(r[m]) if r[m] not in (None,"") else None
                                except (TypeError,ValueError): val=None
                                if val is not None:
                                    month_vals.append(val); bsc_rows.append((dept,m,val,None))
                        avg_val=None
                        if avg_idx is not None and avg_idx < len(r) and r[avg_idx] not in (None,""):
                            try: avg_val=float(r[avg_idx])
                            except (TypeError,ValueError): avg_val=None
                        if avg_val is None and month_vals:
                            # Nếu Excel chưa tính công thức, tính lại đúng TB 6 tháng từ Tháng 1–6.
                            avg_val=sum(month_vals)/len(month_vals)
                        if avg_val is not None:
                            bsc_rows.append((dept,0,None,avg_val))
            self.con.execute("DELETE FROM mll_events")
            self.con.executemany("""INSERT INTO mll_events
                (month,station_code,dept,cb_type,g5,g3,g4,start_date,start_time,end_date,end_time,
                 downtime_min,handler,error_code,error_content,resolution,bsc_min,layer_min,csht_code,csht_type)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",rows)
            # Mỗi lần import, BSC TỔNG của file mới là nguồn chính; tránh giữ số liệu cũ.
            self.con.execute("DELETE FROM mll_bsc_summary")
            if bsc_rows:
                self.con.executemany("INSERT INTO mll_bsc_summary (dept,month_no,value,avg_6m) VALUES (?,?,?,?)",bsc_rows)
            self.con.commit(); wb.close(); self.refresh_mll_dashboard(); self.refresh_dashboard()
            msg=f"Đã nạp {len(rows)} dòng MLL"
            if bsc_rows: msg += f" và {len(bsc_rows)} chỉ tiêu BSC từ sheet BSC TỔNG"
            QMessageBox.information(self,"Import MLL thành công",msg+".")
        except Exception as e: QMessageBox.critical(self,"Lỗi Import MLL",str(e))

    def _mll_reason_group(self,text):
        s=str(text or "").lower()
        if "br" in s or "switch" in s or "router" in s: return "Lỗi BR / SW"
        if "quang" in s or "cáp" in s or "cap " in s: return "Đứt cáp / FO"
        if "điện" in s or "nguồn" in s or "ac" in s: return "Nguồn điện"
        if "duw" in s or "rru" in s or "bbu" in s or "thiết bị" in s: return "Lỗi thiết bị"
        if "truyền dẫn" in s: return "Truyền dẫn"
        return "Khác"

    def _mll_selected_month_range(self):
        """Trả về tháng bắt đầu/kết thúc theo bộ lọc trên Dashboard MLL."""
        start_idx = self.mll_from_month.currentIndex() + 1
        end_idx = self.mll_to_month.currentIndex() + 1
        # Nếu người dùng chọn ngược A > B, tự điều chỉnh B = A để không tạo khoảng rỗng.
        if start_idx > end_idx:
            end_idx = start_idx
            self.mll_to_month.blockSignals(True)
            self.mll_to_month.setCurrentIndex(end_idx - 1)
            self.mll_to_month.blockSignals(False)
        return start_idx, end_idx

    def _on_mll_period_changed(self):
        """Cập nhật ngay toàn bộ KPI, biểu đồ và bảng MLL theo khoảng tháng đã chọn."""
        if hasattr(self, "mll_month_chart"):
            self.refresh_mll_dashboard()

    def _get_kpi_target(self, *names):
        """Lấy đúng giá trị Chỉ tiêu từ dòng KPI theo tên đã chuẩn hóa."""
        import unicodedata as _ud, re as _re
        def norm(v):
            if v is None:
                return ""
            s=_ud.normalize("NFKC", str(v)).replace("\u00a0", " ").strip().casefold()
            s=_ud.normalize("NFD", s)
            s="".join(ch for ch in s if _ud.category(ch)!="Mn")
            return _re.sub(r"[^a-z0-9]+", "", s)
        wanted={norm(x) for x in names if norm(x)}
        rows=self.con.execute("SELECT content, target, actual FROM kpi_targets").fetchall()
        # Ưu tiên khớp tuyệt đối, có dữ liệu Chỉ tiêu.
        for row in rows:
            if norm(row[0]) in wanted and row[1] not in (None, ""):
                return row[1]
        # Fallback cho tên KPI có thêm mô tả.
        for row in rows:
            nr=norm(row[0])
            if nr and any(w in nr or nr in w for w in wanted) and row[1] not in (None, ""):
                return row[1]
        return None

    @staticmethod
    def _format_kpi_target_minutes(value):
        if value is None or str(value).strip()=="":
            return None
        try:
            n=float(str(value).replace(',', '.').strip())
            return f"{n:.2f}"
        except Exception:
            return str(value).strip()

    def refresh_mll_dashboard(self):
        if not hasattr(self, "mll_month_chart"):
            return
        c = self.con
        from_month, to_month = self._mll_selected_month_range()
        selected_months = [f"Tháng {i}" for i in range(from_month, to_month + 1)]
        bsc_rows=c.execute("SELECT dept,month_no,value FROM mll_bsc_summary WHERE month_no BETWEEN ? AND ? ORDER BY dept,month_no",(from_month,to_month)).fetchall()
        bsc_by_month={m:[] for m in range(from_month,to_month+1)}
        for dept,m,v in bsc_rows: bsc_by_month.setdefault(int(m),[]).append(float(v or 0))
        bsc_month_map={f"Tháng {m}":(sum(vals)/len(vals) if vals else 0.0) for m,vals in bsc_by_month.items()}
        all_bsc=[v for vals in bsc_by_month.values() for v in vals]
        bsc_avg=(int((sum(all_bsc)/len(all_bsc))*100)/100) if all_bsc else None
        # Thẻ MLL vẫn tính theo TB BSC như hiện tại, nhưng hiển thị thêm
        # Chỉ tiêu lấy đúng từ cột "Chỉ tiêu" của dòng KPI MLL.
        mll_target=self._get_kpi_target("MLL", "Mất LL", "Mất liên lạc", "Mất LL (TB BSC)")
        mll_target_txt=self._format_kpi_target_minutes(mll_target)
        mll_focus_text=(f"{bsc_avg:.2f} / {mll_target_txt} phút" if bsc_avg is not None and mll_target_txt is not None
                        else (f"{bsc_avg:.2f} / —" if bsc_avg is not None else "—"))
        # Lọc theo tháng đã chọn ngay từ truy vấn, để mọi KPI/biểu đồ/bảng
        # trong khung MLL đều phản ánh cùng một khoảng thời gian.
        placeholders = ",".join("?" for _ in selected_months)
        month_where = f"WHERE month IN ({placeholders})"
        params = tuple(selected_months)

        cases = int(c.execute(
            f"SELECT COUNT(*) FROM mll_events {month_where}", params
        ).fetchone()[0] or 0)

        if hasattr(self,"dash_mll_cases"):
            self.dash_mll_cases.setText(mll_focus_text)
            self.dash_mll_cases.setToolTip(
                f"TB MLL tính BSC trong {selected_months[0]} → {selected_months[-1]}: {bsc_avg:.2f} / Chỉ tiêu MLL: {mll_target_txt} phút"
                if bsc_avg is not None and mll_target_txt is not None else
                (f"TB MLL tính BSC trong {selected_months[0]} → {selected_months[-1]}: {bsc_avg:.2f} phút; chưa có Chỉ tiêu MLL."
                 if bsc_avg is not None else "Chưa có dữ liệu BSC TỔNG."))

        if not cases:
            for key,val in [
                ("mll_kpi_cases",0),
                ("mll_kpi_down","0 phút"),
                ("mll_kpi_stations",0),
                ("mll_kpi_avg","0.0 phút"),
                ("mll_kpi_reason","—")
            ]:
                getattr(self,key).setText(str(val))
            self.mll_month_chart.set_data([(m,0,0,bsc_month_map.get(m,0)) for m in selected_months])
            self.mll_reason_chart.set_data([])
            self.mll_service_chart.set_data([])
            self.mll_station_table.setRowCount(0)
            self.mll_long_table.setRowCount(0)
            self.mll_insight.setText(
                f"Chưa có dữ liệu MLL trong khoảng {selected_months[0]} đến {selected_months[-1]}."
            )
            return

        total = float(c.execute(
            f"SELECT COALESCE(SUM(downtime_min),0) FROM mll_events {month_where}", params
        ).fetchone()[0] or 0)
        total_bsc = float(c.execute(
            f"SELECT COALESCE(SUM(bsc_min),0) FROM mll_events {month_where}", params
        ).fetchone()[0] or 0)
        total_layer = float(c.execute(
            f"SELECT COALESCE(SUM(layer_min),0) FROM mll_events {month_where}", params
        ).fetchone()[0] or 0)
        stations = int(c.execute(
            f"SELECT COUNT(DISTINCT NULLIF(TRIM(station_code),'')) FROM mll_events {month_where}", params
        ).fetchone()[0] or 0)
        avg = total / cases if cases else 0

        # Reason grouping giữ nguyên logic cũ nhưng chỉ đọc dữ liệu trong khoảng đã chọn.
        reason = {}
        reason_rows = c.execute(
            f"SELECT error_content,resolution FROM mll_events {month_where}", params
        ).fetchall()
        for r in reason_rows:
            grp = self._mll_reason_group(r[0] or r[1])
            reason[grp] = reason.get(grp,0) + 1
        top_reason = max(reason, key=reason.get) if reason else "—"

        for key,val in [
            ("mll_kpi_cases",cases),
            ("mll_kpi_down",f"{total:,.0f} phút"),
            ("mll_kpi_stations",stations),
            ("mll_kpi_avg",f"{avg:,.1f} phút"),
            ("mll_kpi_reason",top_reason)
        ]:
            getattr(self,key).setText(str(val))

        month_rows = c.execute(
            f"""SELECT month, COUNT(*) n, COALESCE(SUM(downtime_min),0) mins
                FROM mll_events {month_where} GROUP BY month""", params
        ).fetchall()
        month_map={str(r[0]):(int(r[1]),float(r[2] or 0)) for r in month_rows}
        self.mll_month_chart.set_data(
            [(m,month_map.get(m,(0,0))[0],month_map.get(m,(0,0))[1],bsc_month_map.get(m,0)) for m in selected_months]
        )
        self.mll_reason_chart.set_data(
            sorted(reason.items(),key=lambda x:x[1],reverse=True)[:5]
        )

        services={}
        for label,col in [("3G","g3"),("4G","g4"),("5G","g5")]:
            services[label]=int(c.execute(
                f"SELECT COUNT(*) FROM mll_events {month_where} "
                f"AND TRIM(COALESCE({col},''))<>''", params
            ).fetchone()[0] or 0)
        self.mll_service_chart.set_data([(k,v) for k,v in services.items() if v])

        top_sites=c.execute(
            f"""SELECT COALESCE(NULLIF(TRIM(station_code),''),'Không rõ') code,
                       COUNT(*) cases,
                       COALESCE(SUM(downtime_min),0) mins
                FROM mll_events {month_where}
                GROUP BY code ORDER BY mins DESC LIMIT 8""", params
        ).fetchall()
        self.mll_station_table.setUpdatesEnabled(False)
        self.mll_station_table.setRowCount(len(top_sites))
        for i,r in enumerate(top_sites):
            vals=[i+1,str(r[0]),str(int(r[1] or 0)),f"{float(r[2] or 0):,.0f}p"]
            for j,v in enumerate(vals):
                item=QTableWidgetItem(str(v))
                if j==0: item.setTextAlignment(Qt.AlignCenter)
                elif j in (2,3): item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                self.mll_station_table.setItem(i,j,item)
        self.mll_station_table.setUpdatesEnabled(True)

        longest=c.execute(
            f"""SELECT station_code,month,error_content,resolution,COALESCE(downtime_min,0) mins
                FROM mll_events {month_where}
                ORDER BY downtime_min DESC LIMIT 5""", params
        ).fetchall()
        self.mll_long_table.setUpdatesEnabled(False)
        self.mll_long_table.setRowCount(len(longest))
        for i,r in enumerate(longest):
            vals=[
                i+1,r[0] or "",r[1] or "",
                self._mll_reason_group(r[2] or r[3]),
                f"{float(r[4] or 0):,.0f}p"
            ]
            for j,v in enumerate(vals):
                item=QTableWidgetItem(str(v))
                if j==0: item.setTextAlignment(Qt.AlignCenter)
                elif j==4: item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                self.mll_long_table.setItem(i,j,item)
        self.mll_long_table.setUpdatesEnabled(True)

        peak=max(selected_months,key=lambda m:month_map.get(m,(0,0))[1])
        peak_mins=month_map.get(peak,(0,0))[1]
        peakst=str(top_sites[0][0]) if top_sites else "—"
        peakst_mins=float(top_sites[0][2]) if top_sites else 0
        share=reason.get(top_reason,0)/cases*100 if cases else 0

        # So sánh tháng đầu và tháng cuối trong khoảng đã chọn để phần
        # "Đánh giá" phản ánh xu hướng tăng/giảm, thay vì chỉ nêu tháng cao nhất.
        first_m=selected_months[0]
        last_m=selected_months[-1]
        first_cases,first_mins=month_map.get(first_m,(0,0))
        last_cases,last_mins=month_map.get(last_m,(0,0))
        def _pct_change(a,b):
            if a == 0:
                return None if b == 0 else 100.0
            return (b-a)/a*100.0
        case_delta=_pct_change(first_cases,last_cases)
        min_delta=_pct_change(first_mins,last_mins)
        def _trend(delta):
            if delta is None: return "mới phát sinh"
            if abs(delta) < 0.1: return "ổn định"
            return f"tăng {delta:.0f}%" if delta > 0 else f"giảm {abs(delta):.0f}%"

        trend_text=(
            f"Số vụ từ {first_m} → {last_m}: {_trend(case_delta)}; "
            f"thời gian gián đoạn: {_trend(min_delta)}."
            if first_m != last_m else
            f"Khoảng phân tích chỉ gồm {first_m}."
        )
        self.mll_insight.setText(
            f"<b>Đánh giá:</b> {peak} có thời gian gián đoạn cao nhất "
            f"({peak_mins:,.0f} phút). Trạm <b>{peakst}</b> có tổng thời gian "
            f"gián đoạn lớn nhất ({peakst_mins:,.0f} phút). Nhóm "
            f"<b>{top_reason}</b> chiếm khoảng {share:.0f}% số vụ. "
            f"{trend_text}"
        )

    def clear_layout(self, layout):
        while layout.count():
            item=layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.layout(): self.clear_layout(item.layout())

    def bar_row(self, label, value, total):
        row=QWidget(); h=QHBoxLayout(row); h.setContentsMargins(0,4,0,4)
        a=QLabel(label); a.setFixedWidth(100); h.addWidget(a)
        p=QProgressBar(); p.setRange(0,max(total,1)); p.setValue(value); h.addWidget(p)
        n=QLabel(str(value)); n.setFixedWidth(40); n.setAlignment(Qt.AlignRight); h.addWidget(n)
        return row

    def _parse_date_value(self, value):
        """Chuẩn hóa ngày từ SQLite/Excel, kể cả datetime và số serial của Excel."""
        if value is None:
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # Excel serial date (hệ 1900). Chỉ nhận khoảng ngày hợp lý để tránh
            # biến các mã hợp đồng dạng số thành ngày.
            try:
                serial=float(value)
                if 1 <= serial <= 100000:
                    return (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=serial)).date()
            except Exception:
                pass
        text=str(value).strip()
        if not text:
            return None
        # Một số DB cũ có thể lưu ISO datetime thay vì chỉ YYYY-MM-DD.
        for candidate in (text, text.replace('T',' ')):
            try:
                return datetime.datetime.fromisoformat(candidate).date()
            except ValueError:
                pass
        for fmt in ("%Y-%m-%d","%d/%m/%Y","%Y/%m/%d","%d-%m-%Y","%d.%m.%Y"):
            try:
                return datetime.datetime.strptime(text[:10], fmt).date()
            except ValueError:
                pass
        return None

    def _notification_target_email(self, station_code):
        """Email quản lý trạm từ sheet TRẠM BTS đã import."""
        code=str(station_code or "").strip().upper()
        if not code:
            return ""
        row=self.con.execute(
            "SELECT email FROM stations WHERE UPPER(TRIM(COALESCE(code,'')))=? LIMIT 1",
            (code,)
        ).fetchone()
        return str((row[0] if row else "") or "").strip().lower()

    def refresh_automatic_alerts(self, show_popup=False):
        """Tạo/đồng bộ cảnh báo tự động và hiển thị trên Dashboard + Thông báo.

        Hợp đồng được cảnh báo tự động khi còn đúng 3 ngày đến hạn.
        Nội dung hiển thị không ghi cụm “còn đúng 3 ngày”, nhưng luôn nêu rõ
        ngày hết hạn hợp đồng để người dùng dễ kiểm tra. Cảnh báo được lưu
        chung vào bảng notifications để trang Thông báo và Dashboard dùng cùng nguồn dữ liệu.
        """
        today=datetime.date.today()
        alerts=[]

        # Hợp đồng: kích hoạt từ mốc còn 3 ngày đến hết ngày hết hạn.
        # Cách này không làm mất cảnh báo nếu ứng dụng không chạy đúng vào
        # ngày thứ 3, nhưng vẫn bảo đảm HĐ được cảnh báo ngay từ mốc 3 ngày.
        # Nội dung tuyệt đối không hiển thị cụm “CÒN 3 NGÀY”.
        # Thông tin bắt buộc phải có: mã trạm, số HĐ và ngày hết hạn HĐ.
        for contract_id,station_code,contract_no,end_date in self.con.execute(
            "SELECT contract_id,station_code,contract_no,end_date FROM contracts WHERE TRIM(COALESCE(end_date,''))<>''"
        ).fetchall():
            d=self._parse_date_value(end_date)
            if d and 0 <= (d-today).days <= 3:
                key=f"CONTRACT|{contract_id}|{d.isoformat()}"
                expiry_text=d.strftime('%d/%m/%Y')
                content=(
                    f"Trạm {station_code or '—'}: Hợp đồng {contract_no or contract_id or '—'} "
                    f"hết hạn ngày {expiry_text}."
                )
                alerts.append((key,"HỢP ĐỒNG",station_code,content))

        # BTBD: bắt đầu phát cảnh báo từ ngày 20 hằng tháng.
        # Điều kiện nghiệp vụ: (1) Trạng thái = "Chưa thực hiện";
        # (2) Ngày thực hiện thuộc đúng tháng hiện tại.
        # Đọc từng dòng rồi chuẩn hóa ngày để không phụ thuộc định dạng Excel/SQLite.
        if today.day >= 20:
            month_key=today.strftime("%Y-%m")
            btbd_rows=self.con.execute(
                "SELECT work_id,station_code,work_date,status,scope,work_type FROM maintenance"
            ).fetchall()
            for work_id,station_code,work_date,status,scope,work_type in btbd_rows:
                status_text=' '.join(str(status or '').strip().split()).casefold()
                # Cho phép dữ liệu cũ có khoảng trắng/khác kiểu chữ nhưng vẫn phải
                # đúng nghiệp vụ "Chưa thực hiện".
                if status_text != 'chưa thực hiện':
                    continue
                work_dt=self._parse_date_value(work_date)
                if work_dt is None or work_dt.strftime("%Y-%m") != month_key:
                    continue
                key=f"BTBD|{work_id}|{month_key}"
                month_number=work_dt.month
                btbd_type=str(work_type or scope or '').strip()
                btbd_type=' '.join(btbd_type.split())
                if btbd_type.casefold() in ('indoor','outdoor'):
                    btbd_type=btbd_type.lower()
                else:
                    btbd_type=btbd_type or 'BTBD'
                content=(
                    f"Trạm {station_code or '—'}: chưa thực hiện BTBD {btbd_type} tháng {month_number}."
                )
                alerts.append((key,"BTBD",station_code,content))

        # Lưu cảnh báo tự động để không tạo trùng và để trang Thông báo dùng chung nguồn.
        new_alerts=[]
        for key,atype,station,content in alerts:
            exists=self.con.execute("SELECT 1 FROM auto_alerts WHERE alert_key=?",(key,)).fetchone()
            detect_time=datetime.datetime.now()
            if exists:
                # Đồng bộ cảnh báo tự động hiện có.
                # Nội dung hợp đồng luôn phải có ngày hết hạn HĐ để dùng cho
                # Dashboard, bảng Thông báo và báo cáo Excel.
                self.con.execute(
                    "UPDATE auto_alerts SET station_code=?, title=?, content=? WHERE alert_key=?",
                    (station,"⚠️ "+atype,content,key)
                )

                # Nếu bản ghi Thông báo đã bị thiếu (ví dụ DB cũ/đã xóa bản ghi),
                # tự tạo lại để cảnh báo HĐ luôn xuất hiện trong mục Thông báo.
                notice_exists=self.con.execute(
                    "SELECT id FROM notifications WHERE auto_alert_key=?",(key,)
                ).fetchone()
                if notice_exists:
                    self.con.execute(
                        "UPDATE notifications SET title=?, content=?, target_email=? WHERE auto_alert_key=?",
                        ("⚠️ "+atype,content,self._notification_target_email(station),key)
                    )
                else:
                    self.con.execute(
                        "INSERT INTO notifications(notify_date,notify_time,title,content,sound,popup,done,auto_alert_key,created_at,sync_key,target_email,created_by_email) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (today.isoformat(),detect_time.strftime("%H:%M"),"⚠️ "+atype,content,1,1,0,key,detect_time.isoformat(timespec="seconds"),f"PC|AUTO|{key}",self._notification_target_email(station),"")
                    )
                    new_alerts.append(content)
            else:
                self.con.execute(
                    "INSERT INTO auto_alerts(alert_key,alert_type,station_code,title,content,alert_date,created_at) VALUES(?,?,?,?,?,?,?)",
                    (key,atype,station,"⚠️ "+atype,content,today.isoformat(),detect_time.isoformat(timespec="seconds"))
                )
                # Bắt buộc tạo bản ghi trong Thông báo để có thể thống kê và
                # xuất báo cáo; không phụ thuộc popup có hiển thị hay không.
                self.con.execute(
                    "INSERT INTO notifications(notify_date,notify_time,title,content,sound,popup,done,auto_alert_key,created_at,sync_key,target_email,created_by_email) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (today.isoformat(),detect_time.strftime("%H:%M"),"⚠️ "+atype,content,1,1,0,key,detect_time.isoformat(timespec="seconds"),f"PC|AUTO|{key}",self._notification_target_email(station),"")
                )
                new_alerts.append(content)
        self.con.commit()

        # Đồng bộ ngay bảng Thông báo sau khi tạo/cập nhật cảnh báo.
        # Trước đây cảnh báo được ghi vào DB nhưng lưới Thông báo chỉ nạp dữ liệu
        # khi người dùng đổi tháng, nên có thể thấy KPI nhưng không thấy dòng cảnh báo.
        if hasattr(self, "notice_month_combo"):
            current_month = (self.notice_month_combo.currentData()
                             or today.strftime("%Y-%m"))
            self.load_notifications_for_month(current_month)

        # Khung CẢNH BÁO hiển thị các cảnh báo tự động chưa hoàn thành của tháng hiện tại.
        # Không giới hạn alert_date = hôm nay; nếu người dùng mở ứng dụng sau ngày 20
        # thì cảnh báo BTBD vẫn phải còn trên Dashboard để theo dõi/báo cáo.
        month_start=today.replace(day=1).isoformat()
        current_email=str((self.cloud_client.user or {}).get('email','')).strip().lower() if self.cloud_client else ''
        is_admin=current_email == AdminCreateUserDialog.ADMIN_EMAIL
        active_raw=self.con.execute(
            """SELECT a.alert_type,a.station_code,a.content,n.target_email
               FROM auto_alerts a
               LEFT JOIN notifications n ON n.auto_alert_key=a.alert_key
               WHERE a.resolved=0 AND a.alert_date>=? AND a.alert_date<=?
               ORDER BY CASE WHEN a.alert_type='BTBD' THEN 0 ELSE 1 END, a.alert_type,a.station_code""",
            (month_start,today.isoformat())
        ).fetchall()
        active=[r[:3] for r in active_raw if is_admin or str(r[3] or '').strip().lower() == current_email]
        if hasattr(self,"dashboard_alert_count"):
            self.dashboard_alert_count.setText(str(len(active)))
        if hasattr(self,"dashboard_alert_list"):
            if active:
                lines=[f"• {r[2]}" for r in active]
                self.dashboard_alert_list.setText("\n".join(lines[:8]) + (f"\n… và {len(lines)-8} cảnh báo khác." if len(lines)>8 else ""))
                self.dashboard_alert_list.setStyleSheet("color:#b42318;font-size:12px;padding:4px;")
            else:
                self.dashboard_alert_list.setText("Không có cảnh báo tự động.")
                self.dashboard_alert_list.setStyleSheet("color:#64748b;font-size:12px;padding:4px;")

        if show_popup and new_alerts:
            QMessageBox.warning(self,"⚠️ CẢNH BÁO TỰ ĐỘNG","\n\n".join(new_alerts[:10]))

    def refresh_dashboard(self):
        self.refresh_automatic_alerts(show_popup=False)
        c=self.con
        total=c.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        active=c.execute("SELECT COUNT(*) FROM stations WHERE status='Hoạt động'").fetchone()[0]
        warn=c.execute("SELECT COUNT(*) FROM stations WHERE status='Cảnh báo'").fetchone()[0]
        fault=c.execute("SELECT COUNT(*) FROM stations WHERE status IN ('Sự cố','Không liên lạc')").fetchone()[0]
        eq=c.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]
        trans=c.execute("SELECT COUNT(*) FROM transmission").fetchone()[0]
        power=c.execute("SELECT COUNT(*) FROM power").fetchone()[0]
        # BTBD Indoor/Outdoor: lấy trực tiếp từ file KPI, không lấy từ bảng maintenance.
        # Cho phép các tên tương đương có/không dấu và khác kiểu viết hoa.
        def kpi_norm(v):
            # Chuẩn hóa mạnh tên KPI để không phụ thuộc khoảng trắng, xuống dòng,
            # dấu tiếng Việt hay ký tự trang trí trong file Excel.
            if v is None:
                return ""
            import unicodedata as _ud, re as _re
            s=_ud.normalize("NFKC", str(v)).replace("\u00a0", " ").strip().casefold()
            s=_ud.normalize("NFD", s)
            s="".join(ch for ch in s if _ud.category(ch)!="Mn")
            return _re.sub(r"[^a-z0-9]+", "", s)

        def kpi_raw(content):
            wanted=kpi_norm(content)
            if not wanted:
                return (None, None)
            rows=c.execute("SELECT content, target, actual FROM kpi_targets").fetchall()

            # Ưu tiên khớp tuyệt đối sau chuẩn hóa. Nếu có nhiều dòng trùng tên,
            # ưu tiên dòng có dữ liệu thực tế/chỉ tiêu thay vì lấy nhầm dòng rỗng.
            exact=[]
            for row in rows:
                norm=kpi_norm(row[0])
                if norm==wanted:
                    exact.append(row)
            for row in exact:
                if (row[1] is not None and str(row[1]).strip()!="") or (row[2] is not None and str(row[2]).strip()!=""):
                    return (row[1], row[2])
            if exact:
                return (exact[0][1], exact[0][2])

            # Fallback an toàn cho file KPI cũ có thêm chữ/mô tả quanh tên KPI.
            # Chỉ áp dụng khi chuỗi chuẩn hóa là một phần rõ ràng của tên KPI.
            for row in rows:
                norm=kpi_norm(row[0])
                if norm and (wanted in norm or norm in wanted):
                    if (row[1] is not None and str(row[1]).strip()!="") or (row[2] is not None and str(row[2]).strip()!=""):
                        return (row[1], row[2])
            return (None, None)

        def kpi_actual_number(*names):
            for name in names:
                target, actual = kpi_raw(name)
                if actual is not None and str(actual).strip() != "":
                    try:
                        n=float(str(actual).replace(',', '.').strip())
                        return int(n) if n.is_integer() else n
                    except Exception:
                        continue
            return 0

        # BTBD Indoor/Outdoor hiển thị theo cùng chuẩn với Phát triển mới:
        # Đã thực hiện / Chỉ tiêu + tỷ lệ %. Số thực hiện lấy từ cột "Đã thực hiện"
        # của file KPI, chỉ tiêu lấy từ cột "Chỉ tiêu".
        def kpi_value_with_ratio(*names):
            for name in names:
                target, actual = kpi_raw(name)
                if (target is not None and str(target).strip() != "") or (actual is not None and str(actual).strip() != ""):
                    def num(v):
                        if v is None or str(v).strip()=="": return None
                        try:
                            x=float(str(v).replace(',', '.').strip())
                            return int(x) if x.is_integer() else x
                        except Exception:
                            return None
                    t, a = num(target), num(actual)
                    if a is not None and t is not None:
                        pct=(a/t*100) if t else 0
                        return f"{a} / {t}  ({pct:.0f}%)"
                    if a is not None: return f"{a} / —"
                    if t is not None: return f"— / {t}"
            return "—"

        btbd_indoor_display=kpi_value_with_ratio("BTBD Indoor", "BTBD INDOOR", "BTBD trong nhà")
        btbd_outdoor_display=kpi_value_with_ratio("BTBD Outdoor", "BTBD OUTDOOR", "BTBD ngoài trời")
        # Tổng BTBD vẫn giữ số thực hiện để các thống kê cũ không bị ảnh hưởng.
        btbd_indoor=kpi_actual_number("BTBD Indoor", "BTBD INDOOR", "BTBD trong nhà")
        btbd_outdoor=kpi_actual_number("BTBD Outdoor", "BTBD OUTDOOR", "BTBD ngoài trời")
        btbd=btbd_indoor+btbd_outdoor

        mll_cases=c.execute("SELECT COUNT(*) FROM mll_events").fetchone()[0]
        # MLL trên thẻ CHỈ SỐ CẦN QUAN TÂM lấy đúng cột TB 6 tháng (phút)
        # của sheet BSC TỔNG. Không lấy số vụ MLL và không lấy trung bình cộng
        # của tất cả các ô tháng như phiên bản trước.
        bsc_avg_rows=[float(r[0]) for r in c.execute(
            "SELECT avg_6m FROM mll_bsc_summary WHERE avg_6m IS NOT NULL"
        ).fetchall()]
        mll_bsc_avg=(sum(bsc_avg_rows)/len(bsc_avg_rows)) if bsc_avg_rows else None
        def kpi_display(content):
            row=c.execute(
                "SELECT target, actual FROM kpi_targets WHERE lower(trim(content))=lower(trim(?)) LIMIT 1",
                (content,)
            ).fetchone()
            if not row:
                return "—"
            target, actual = row[0], row[1]
            def clean(v):
                if v is None or str(v).strip()=="": return None
                txt=str(v).strip()
                try:
                    num=float(txt)
                    if num.is_integer(): return str(int(num))
                except Exception: pass
                return txt
            t, a = clean(target), clean(actual)
            if a is not None and t is not None:
                try:
                    pct=(float(a)/float(t)*100) if float(t)!=0 else 0
                    pct_txt=f"{pct:.0f}%"
                except Exception:
                    pct_txt="—"
                return f"{a} / {t}  ({pct_txt})"
            if t is not None: return f"— / {t}"
            if a is not None: return f"{a} / —"
            return "—"

        xl_pakh_value=kpi_display("XL PAKH")
        new_development_value=kpi_display("Trạm phát triển mới")

        def distinct_count(field):
            return c.execute(f"SELECT COUNT(DISTINCT NULLIF(TRIM({field}),'')) FROM stations").fetchone()[0]

        for key,val in [
            ("dash_total",total),("dash_active",active),("dash_warn",warn),
            ("dash_fault",fault),("dash_equipment",eq),("dash_trans",trans),
            ("dash_power",power),("dash_btbd",btbd),
            ("dash_btbd_indoor",btbd_indoor_display),("dash_btbd_outdoor",btbd_outdoor_display),
            ("dash_mll_cases",(f"{mll_bsc_avg:.2f} / {self._format_kpi_target_minutes(self._get_kpi_target('MLL','Mất LL','Mất liên lạc','Mất LL (TB BSC)'))} phút"
                               if mll_bsc_avg is not None and self._get_kpi_target('MLL','Mất LL','Mất liên lạc','Mất LL (TB BSC)') is not None
                               else (f"{mll_bsc_avg:.2f} / —" if mll_bsc_avg is not None else "—"))),
            ("dash_xl_pakh",xl_pakh_value),
            ("dash_new_development",new_development_value),
            ("dash_type_count",distinct_count("type")),
            ("dash_upe_count",distinct_count("upe")),
            ("dash_ktv_count",distinct_count("technician")),
            ("dash_csht_count",distinct_count("csht_type")),
        ]:
            if hasattr(self,key): getattr(self,key).setText(str(val))

        # Chỉ số cần quan tâm: ngắn gọn, ưu tiên các trường vận hành mới.
        upe_connected=c.execute("SELECT COUNT(*) FROM stations WHERE TRIM(COALESCE(upe,''))<>''").fetchone()[0]
        csht_filled=c.execute("SELECT COUNT(*) FROM stations WHERE TRIM(COALESCE(csht_type,''))<>''").fetchone()[0]
        for key,val in [("dash_upe_connected",upe_connected),("dash_csht_filled",csht_filled)]:
            if hasattr(self,key): getattr(self,key).setText(str(val))

        # 5 lát cắt vận hành bằng donut. Với nhóm quá nhiều giá trị, gom phần còn lại thành “Khác”.
        panels=[
            ("type_layout","type"),
            ("upe_layout","upe"),
            ("pole_layout","pole_type"),
            ("csht_layout","csht_type"),
            ("ktv_layout","technician"),
        ]
        for attr,field in panels:
            if not hasattr(self,attr): continue
            # Số ở giữa donut là số lượng giá trị phân loại khác nhau,
            # không phải tổng số BTS. Ví dụ Loại CSHT=3, KTV quản lý=5.
            distinct = c.execute(
                f"SELECT COUNT(DISTINCT NULLIF(TRIM(COALESCE({field},'')),'')) FROM stations"
            ).fetchone()[0] or 0
            if field == "upe":
                getattr(self,attr).center_label = "UPE"
                getattr(self,attr).center_value = int(distinct)
            else:
                getattr(self,attr).center_label = f"{int(distinct)} loại"
                getattr(self,attr).center_value = int(distinct)
            rows=c.execute(
                f"SELECT COALESCE(NULLIF(TRIM({field}),''),'Chưa khai báo'),COUNT(*) n FROM stations GROUP BY {field} ORDER BY n DESC, {field}"
            ).fetchall()
            # Giữ nguyên toàn bộ các loại thực tế; không gom thành "Khác".
            # Legend có thanh cuộn để xem đầy đủ khi có nhiều mục.
            rows=[(str(label),int(n)) for label,n in rows if int(n)>0]
            getattr(self,attr).set_data(rows)

        # Các phần dữ liệu MLL vẫn được giữ nguyên bên dưới.


    def overview_bar_row(self, label, value, total, field=""):
        row=QFrame(); row.setObjectName("overviewRow")
        h=QVBoxLayout(row); h.setContentsMargins(0,3,0,3); h.setSpacing(4)
        top=QHBoxLayout(); top.setSpacing(6)
        a=QLabel(label); a.setStyleSheet("font-weight:650;color:#1e3a5f;")
        n=QLabel(f"{value:,}  •  {(value/total*100):.0f}%"); n.setAlignment(Qt.AlignRight); n.setStyleSheet("font-weight:800;color:#0f5f8f;")
        top.addWidget(a,1); top.addWidget(n)
        h.addLayout(top)
        p=QProgressBar(); p.setRange(0,max(total,1)); p.setValue(value); p.setTextVisible(False); p.setFixedHeight(8)
        p.setStyleSheet("QProgressBar{background:#e8eef5;border:0;border-radius:4px;} QProgressBar::chunk{background:#1496b8;border-radius:4px;}")
        h.addWidget(p)
        return row

    def _search_values_for_stations(self):
        vals=[]
        try:
            rows=self.con.execute("SELECT code,name,upe,type,technician FROM stations ORDER BY code").fetchall()
            for r in rows:
                vals.extend([str(x) for x in r if x not in (None, "")])
        except Exception:
            pass
        return sorted(set(vals), key=str.lower)

    def _update_station_search_suggestions(self):
        if hasattr(self, "station_search_completer"):
            self.station_search_completer.setModel(QStringListModel(self._search_values_for_stations(), self.station_search_completer))

    def stations_page(self):
        w=QWidget(); l=QVBoxLayout(w); l.setContentsMargins(28,24,28,24); l.setSpacing(12)
        top=QHBoxLayout(); top.addWidget(self.title_block("Trạm BTS","Quản lý • Phân loại • Thống kê • Xuất báo cáo"))
        top.addStretch()
        for txt,cb in [("📥 Import Excel",self.import_excel),("📄 Tải file mẫu",self.download_template),("＋ Thêm trạm",self.add_station)]:
            b=QPushButton(txt,objectName="primary"); b.clicked.connect(cb); top.addWidget(b)
        l.addLayout(top)
        search=QComboBox()
        search.setEditable(True)
        search.setInsertPolicy(QComboBox.NoInsert)
        search.lineEdit().setPlaceholderText("🔎  Tìm mã trạm, tên trạm, UPE, loại trạm, KTV...")
        search.setMinimumHeight(38)
        completer=QCompleter(self._search_values_for_stations())
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        search.setCompleter(completer)
        search_row=QHBoxLayout()
        search_row.addWidget(search,1)
        search_btn=QPushButton("🔎 Tìm kiếm")
        search_btn.setObjectName("secondary")
        search_btn.setMinimumHeight(38)
        search_btn.setMinimumWidth(110)
        search_row.addWidget(search_btn)
        l.addLayout(search_row)
        self.search=search; self.station_search_completer=completer
        search_btn.clicked.connect(self.load_station_list)
        search.lineEdit().returnPressed.connect(self.load_station_list)
        summary=QHBoxLayout()
        self.list_total=QLabel("0",objectName="cardValue")
        self.list_active=QLabel("0",objectName="cardValue")
        self.list_bmy=QLabel("0",objectName="cardValue")
        self.list_phd=QLabel("0",objectName="cardValue")
        for label,widget in [
            ("Tổng BTS",self.list_total),("Đang hoạt động",self.list_active),
            ("UPE BMY",self.list_bmy),("UPE PHD",self.list_phd)]:
            f=QFrame(objectName="card"); fl=QVBoxLayout(f)
            fl.addWidget(QLabel(label,objectName="cardLabel")); fl.addWidget(widget)
            summary.addWidget(f)
        l.addLayout(summary)
        self.station_table=QTableWidget(0,7)
        self.station_table.setObjectName("stationTable")
        self.station_table.setHorizontalHeaderLabels(["Mã trạm","Tên trạm","UPE trạm","Loại trạm","Trạng thái","KTV quản lý","Cập nhật"])
        self.station_table.setShowGrid(True)
        self.station_table.setGridStyle(Qt.SolidLine)
        self.station_table.setAlternatingRowColors(True)
        self.station_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.station_table.setSelectionMode(QTableWidget.SingleSelection)
        self.station_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.station_table.setWordWrap(True)
        self.station_table.setMouseTracking(True)
        self.station_table.verticalHeader().setVisible(False)
        self.station_table.verticalHeader().setDefaultSectionSize(42)
        header=self.station_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignCenter)
        header.setMinimumSectionSize(80)
        header.setSectionResizeMode(0,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1,QHeaderView.Stretch)
        header.setSectionResizeMode(2,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5,QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6,QHeaderView.Fixed)
        self.station_table.setColumnWidth(0,125)
        self.station_table.setColumnWidth(2,105)
        self.station_table.setColumnWidth(3,125)
        self.station_table.setColumnWidth(4,135)
        self.station_table.setColumnWidth(5,145)
        self.station_table.setColumnWidth(6,120)
        self.station_table.setStyleSheet("""
            QTableWidget#stationTable {
                background:#ffffff;
                alternate-background-color:#f7fafc;
                border:1px solid #d7e1eb;
                border-radius:10px;
                gridline-color:#d6dee8;
                selection-background-color:#dbeafe;
                selection-color:#0f172a;
                outline:0;
            }
            QTableWidget#stationTable::item {
                padding:7px 10px;
                border-right:1px solid #e2e8f0;
                border-bottom:1px solid #e2e8f0;
            }
            QTableWidget#stationTable::item:hover {
                background:#eef6ff;
            }
            QHeaderView#qt_header {
                background:#edf3f8;
            }
            QTableWidget#stationTable QHeaderView::section {
                background:#e8f0f7;
                color:#18324d;
                border-right:1px solid #d1dbe5;
                border-bottom:1px solid #c7d3df;
                padding:10px 8px;
                font-weight:700;
                min-height:38px;
            }
        """)
        self.station_table.cellDoubleClicked.connect(self.open_station)
        l.addWidget(self.station_table,1)
        hint=QLabel("💡 Double-click vào một trạm để mở hồ sơ chi tiết.")
        hint.setStyleSheet("color:#64748b;font-size:11px;"); l.addWidget(hint)
        return w

    def load_station_list(self):
        q=self.search.currentText().strip() if hasattr(self,"search") and hasattr(self.search,"currentText") else ""
        like=f"%{q}%"
        rows=self.con.execute("""SELECT code,name,upe,type,status,technician FROM stations
            WHERE code LIKE ? OR name LIKE ? OR upe LIKE ? OR type LIKE ? OR status LIKE ? OR technician LIKE ? ORDER BY code""",(like,like,like,like,like,like)).fetchall()
        self.station_table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,val in enumerate(row):
                item=QTableWidgetItem("" if val is None else str(val))
                item.setData(Qt.UserRole, row[0])
                # Canh giữa các trường kỹ thuật; tên trạm/KTV dễ đọc hơn khi canh trái.
                if c in (1,5):
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                self.station_table.setItem(r,c,item)
            action=QWidget()
            ah=QHBoxLayout(action); ah.setContentsMargins(4,4,4,4); ah.setSpacing(4)
            btn=QPushButton("✏️ Cập nhật")
            btn.setFixedHeight(30)
            btn.setStyleSheet("QPushButton{background:#e8f3ff;border:1px solid #9bc4e8;border-radius:6px;color:#0b5fa5;font-weight:700;} QPushButton:hover{background:#d7ebff;}")
            btn.clicked.connect(lambda checked=False, code=row[0]: self.edit_station_by_code(code))
            ah.addWidget(btn)
            self.station_table.setCellWidget(r,6,action)
            self.station_table.resizeRowToContents(r)
        total=self.con.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        active=self.con.execute("SELECT COUNT(*) FROM stations WHERE status='Hoạt động'").fetchone()[0]
        bmy=self.con.execute("SELECT COUNT(*) FROM stations WHERE upe='BMY'").fetchone()[0]
        phd=self.con.execute("SELECT COUNT(*) FROM stations WHERE upe IN ('PHD','PHĐ')").fetchone()[0]
        if hasattr(self,"list_total"):
            self.list_total.setText(str(total)); self.list_active.setText(str(active))
            self.list_bmy.setText(str(bmy)); self.list_phd.setText(str(phd))

    def open_station(self,row,col=0):
        code=self.station_table.item(row,0).text()
        dlg=StationWindow(self, self.con, code)
        dlg.exec()

    def edit_station_by_code(self, code):
        row=self.con.execute("SELECT * FROM stations WHERE code=?",(code,)).fetchone()
        if not row:
            QMessageBox.warning(self,"Không tìm thấy",f"Không tìm thấy trạm {code}.")
            return
        dlg=QDialog(self)
        dlg.setWindowTitle(f"✏️ Cập nhật trạm • {code}")
        dlg.resize(620,720)
        root=QVBoxLayout(dlg)
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        host=QWidget(); form=QFormLayout(host)
        editors={}
        for label,field in STATION_FIELDS:
            ed=QLineEdit(str(row[field] or ""))
            if field=="code":
                ed.setReadOnly(True)
                ed.setStyleSheet("background:#f1f5f9;color:#64748b;")
            editors[field]=ed
            form.addRow(QLabel(label+":"),ed)
        scroll.setWidget(host); root.addWidget(scroll,1)
        box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept); box.rejected.connect(dlg.reject)
        root.addWidget(box)
        if dlg.exec()!=QDialog.Accepted:
            return
        values={f:ed.text().strip() for f,ed in editors.items()}
        assignments=[f"{f}=?" for _,f in STATION_FIELDS if f!="code"]
        params=[values[f] for _,f in STATION_FIELDS if f!="code"]+[code]
        ok_update, timer_was_active = self._prepare_local_update("cập nhật trạm")
        if not ok_update:
            return
        try:
            self.con.execute("BEGIN IMMEDIATE")
            self.con.execute(f"UPDATE stations SET {', '.join(assignments)} WHERE code=?",params)
            self.con.commit()
            self.refresh_all()
            QMessageBox.information(self,"Cập nhật thành công",f"Đã cập nhật trạm {code}.")
        except sqlite3.OperationalError as e:
            try: self.con.rollback()
            except Exception: pass
            if "locked" in str(e).lower():
                QMessageBox.critical(self,"Lỗi cập nhật trạm",
                    "Không thể cập nhật trạm vì cơ sở dữ liệu vẫn đang bị khóa.\n\n"
                    "Đồng bộ nền đã được tạm dừng trong lúc ghi. Vui lòng thử lại sau vài giây.")
            else:
                QMessageBox.critical(self,"Lỗi cập nhật trạm",f"Không thể cập nhật trạm.\n\n{type(e).__name__}: {e}")
        except Exception as e:
            try: self.con.rollback()
            except Exception: pass
            QMessageBox.critical(self,"Lỗi cập nhật trạm",f"Không thể cập nhật trạm.\n\n{type(e).__name__}: {e}")
        finally:
            self._finish_local_update(timer_was_active)

    def add_station(self):
        dlg=QDialog(self)
        dlg.setWindowTitle("＋ Thêm trạm BTS")
        dlg.resize(620,720)
        root=QVBoxLayout(dlg)
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        host=QWidget(); form=QFormLayout(host)
        editors={}
        for label,field in STATION_FIELDS:
            ed=QLineEdit()
            editors[field]=ed
            form.addRow(QLabel(label+":"),ed)
        scroll.setWidget(host); root.addWidget(scroll,1)
        box=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept); box.rejected.connect(dlg.reject)
        root.addWidget(box)
        if dlg.exec()!=QDialog.Accepted:
            return
        values={f:ed.text().strip() for f,ed in editors.items()}
        if not values["code"]:
            QMessageBox.warning(self,"Thiếu mã trạm","Vui lòng nhập Mã trạm.")
            return
        try:
            self.con.execute(
                "INSERT INTO stations (code,name,upe,type,status,address,latitude,longitude,owner_contact,meter_code,technician,pole_type,csht_type,note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [values[f] for _,f in STATION_FIELDS]
            )
            self.con.commit()
            self.refresh_all()
            QMessageBox.information(self,"Thêm trạm thành công",f"Đã thêm trạm {values['code']}.")
        except sqlite3.IntegrityError:
            QMessageBox.warning(self,"Trùng mã trạm",f"Mã trạm {values['code']} đã tồn tại.")
        except Exception as e:
            QMessageBox.critical(self,"Lỗi thêm trạm",f"Không thể thêm trạm.\n\n{type(e).__name__}: {e}")

    def export_dashboard_report(self):
        path,_=QFileDialog.getSaveFileName(
            self,"Xuất báo cáo tổng hợp",
            str(Path.home()/"Bao_cao_tong_hop_BTS.xlsx"),
            "Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment
            wb=Workbook()
            ws=wb.active
            ws.title="Tổng quan"
            ws.append(["BÁO CÁO TỔNG HỢP QUẢN LÝ BTS"])
            ws.append(["Thời gian xuất",datetime.datetime.now().strftime("%d/%m/%Y %H:%M")])
            ws.append([])
            ws.append(["Chỉ tiêu","Giá trị"])
            metrics=[
                ("Tổng BTS",self.con.execute("SELECT COUNT(*) FROM stations").fetchone()[0]),
                ("Hoạt động",self.con.execute("SELECT COUNT(*) FROM stations WHERE status='Hoạt động'").fetchone()[0]),
                ("Cảnh báo",self.con.execute("SELECT COUNT(*) FROM stations WHERE status='Cảnh báo'").fetchone()[0]),
                ("Sự cố/Không liên lạc",self.con.execute("SELECT COUNT(*) FROM stations WHERE status IN ('Sự cố','Không liên lạc')").fetchone()[0]),
                ("Thiết bị",self.con.execute("SELECT COUNT(*) FROM equipment").fetchone()[0]),
                ("Truyền dẫn",self.con.execute("SELECT COUNT(*) FROM transmission").fetchone()[0]),
                ("Nguồn",self.con.execute("SELECT COUNT(*) FROM power").fetchone()[0]),
                ("Battery",self.con.execute("SELECT COUNT(*) FROM batteries").fetchone()[0]),
                ("BTBD",self.con.execute("SELECT COUNT(*) FROM maintenance").fetchone()[0]),
            ]
            for x in metrics: ws.append(list(x))
            ws["A1"].font=Font(bold=True,size=16)
            for cell in ws[4]:
                cell.font=Font(bold=True)
            ws.column_dimensions["A"].width=30
            ws.column_dimensions["B"].width=18

            # Add key data sheets so one export is actually useful for field reporting.
            sheets=[
                ("Trạm BTS","SELECT code,name,upe,type,status,address,owner_contact,meter_code,technician,pole_type,csht_type,note FROM stations",
                 ["Mã trạm","Tên trạm","UPE trạm","Loại trạm","Trạng thái","Địa chỉ","Người liên hệ","Mã điện kế","KTV quản lý","Loại trụ","Loại CSHT","Ghi chú"]),
                ("Thiết bị","SELECT station_code,equipment_group,vendor,model,serial_no,ip_address,status FROM equipment",
                 ["Mã trạm","Nhóm","Hãng","Model","Serial","IP","Trạng thái"]),
                ("Truyền dẫn","SELECT station_code,path_role,device_a,port_a,device_b,port_b,vlan,wan_ip,lacp,status FROM transmission",
                 ["Mã trạm","Main/Backup","Thiết bị A","Port A","Thiết bị B","Port B","VLAN","IP WAN","LACP","Trạng thái"]),
                ("Nguồn","SELECT station_code,power_vendor,power_model,capacity_a,dc_load_a,llvd1_v,llvd2_v,blvd_v,status FROM power",
                 ["Mã trạm","Hãng","Model","Công suất A","Tải DC A","LLVD1","LLVD2","BLVD","Trạng thái"]),
                ("BTBD","SELECT work_date,station_code,scope,work_type,technician,content,result,status FROM maintenance ORDER BY work_date DESC",
                 ["Ngày","Mã trạm","Indoor/Outdoor","Loại","KTV","Nội dung","Kết quả","Trạng thái"])
            ]
            for name,query,headers in sheets:
                s=wb.create_sheet(name)
                s.append(headers)
                for row in self.con.execute(query).fetchall():
                    s.append(list(row))
                for cell in s[1]:
                    cell.font=Font(bold=True)
                s.freeze_panes="A2"
                for col in range(1,len(headers)+1):
                    s.column_dimensions[chr(64+col) if col<=26 else "A"].width=18

            wb.save(path)
            QMessageBox.information(self,"Xuất báo cáo",f"Đã tạo báo cáo:\n{path}")
        except Exception as e:
            QMessageBox.critical(self,"Lỗi xuất báo cáo",str(e))

    def import_excel(self, path=None):
        """Import Excel theo cấu trúc file mẫu hiện hành.

        File mẫu mới không còn các cột ID kỹ thuật (Mã hợp đồng, Mã thiết bị,
        Mã truyền dẫn, Mã nguồn, Mã Battery, Mã TB phụ trợ, Mã BTBD). Vì vậy
        các ID này được hệ thống tự sinh ổn định từ Mã trạm + nội dung dòng.
        Mã trạm là khóa liên kết duy nhất giữa các sheet nghiệp vụ.
        """
        if not path:
            path,_=QFileDialog.getOpenFileName(self,"Import Excel BTS Manager","","Excel (*.xlsx)")
            if not path:
                return
        try:
            from openpyxl import load_workbook
            wb=load_workbook(path, read_only=True, data_only=True)
            specs=excel_specs()
            imported={}; updated={}; skipped={}; errors={}; generated={}

            # V45: kiểm tra mã trạm trùng CSDL trước khi ghi dữ liệu.
            # Người dùng chọn Ghi đè hoặc Bỏ qua cho toàn bộ các mã trạm trùng.
            duplicate_codes=set()
            file_station_codes=set()


            def norm_header(v):
                if v is None:
                    return ""
                txt=unicodedata.normalize("NFC", str(v).replace("\n"," ").strip())
                return " ".join(txt.split()).casefold()

            def value_to_text(v):
                if v is None:
                    return ""
                if isinstance(v,(datetime.datetime,datetime.date)):
                    return v.strftime("%Y-%m-%d")
                if isinstance(v,datetime.time):
                    return v.strftime("%H:%M:%S")
                if isinstance(v,float) and v.is_integer():
                    return str(int(v))
                return str(v).strip()

            aliases={
                "mã trạm":"Mã trạm","ma tram":"Mã trạm",
                "tên trạm":"Tên trạm","ten tram":"Tên trạm",
                "upe trạm":"UPE trạm","upe tram":"UPE trạm","khu vực":"UPE trạm","khu vuc":"UPE trạm",
                "mã điện kế":"Mã điện kế","ma dien ke":"Mã điện kế",
                "loại trụ":"Loại trụ","loai tru":"Loại trụ",
                "loại csht":"Loại CSHT","loai csht":"Loại CSHT",
                "loại trạm":"Loại trạm","loai tram":"Loại trạm",
                "trạng thái":"Trạng thái","trang thai":"Trạng thái",
                "ktv quản lý":"KTV quản lý","ktv quan ly":"KTV quản lý",
                "email":"Email","e-mail":"Email",
                "tốc độ":"Tốc độ","toc do":"Tốc độ"
            }

            import hashlib
            key_prefix={
                "TRẠM BTS":"ST","HỢP ĐỒNG":"HD","THIẾT BỊ":"TB",
                "TRUYỀN DẪN":"TD","NGUỒN":"PWR","PIN - BATTERY":"BAT",
                "THIẾT BỊ PHỤ TRỢ":"AX","BTBD":"BTBD"
            }

            # Quét trước toàn bộ mã trạm trong file để không ghi dữ liệu khi chưa hỏi người dùng.
            for sheet,spec in specs.items():
                if sheet not in wb.sheetnames:
                    continue
                ws=wb[sheet]
                rows=ws.iter_rows(values_only=True)
                try:
                    raw_headers=next(rows)
                except StopIteration:
                    continue
                idx_scan={}
                for i,h in enumerate(raw_headers):
                    nh=norm_header(h)
                    canonical=aliases.get(nh, str(h).strip() if h is not None else "")
                    if canonical:
                        idx_scan[canonical]=i
                pos=idx_scan.get("Mã trạm")
                if pos is None:
                    continue
                for vals in rows:
                    if vals is None or pos >= len(vals):
                        continue
                    code=value_to_text(vals[pos]).strip()
                    if code:
                        file_station_codes.add(" ".join(code.split()).upper())

            if file_station_codes:
                existing_rows=self.con.execute(
                    "SELECT code FROM stations WHERE UPPER(TRIM(COALESCE(code,''))) IN ({})".format(
                        ",".join("?" for _ in file_station_codes)
                    ), tuple(sorted(file_station_codes))
                ).fetchall()
                duplicate_codes={str(r[0]).strip().upper() for r in existing_rows if r[0]}

            import_mode="none"
            if duplicate_codes:
                preview=", ".join(sorted(duplicate_codes)[:20])
                if len(duplicate_codes)>20:
                    preview += f" … và {len(duplicate_codes)-20} mã khác"
                box=QMessageBox(self)
                box.setWindowTitle("Phát hiện mã trạm trùng CSDL")
                box.setIcon(QMessageBox.Warning)
                box.setText(f"File có {len(duplicate_codes)} mã trạm đã tồn tại trong CSDL.")
                box.setInformativeText(
                    "Bạn muốn xử lý dữ liệu trùng như thế nào?\n\n"
                    f"Mã trạm trùng: {preview}\n\n"
                    "• Ghi đè: cập nhật dữ liệu mới cho các mã trùng.\n"
                    "• Ghi và xóa: xóa hồ sơ trạm cũ rồi ghi lại toàn bộ dữ liệu từ file mới.\n"
                    "• Bỏ qua: giữ nguyên dữ liệu cũ, không import các dòng trùng.\n"
                    "• Hủy: dừng import, không thay đổi CSDL."
                )
                overwrite_btn=box.addButton("Ghi đè dữ liệu cũ", QMessageBox.AcceptRole)
                replace_btn=box.addButton("Ghi và xóa dữ liệu cũ", QMessageBox.ActionRole)
                skip_btn=box.addButton("Bỏ qua dữ liệu trùng", QMessageBox.DestructiveRole)
                cancel_btn=box.addButton("Hủy", QMessageBox.RejectRole)
                box.exec()
                clicked=box.clickedButton()
                if clicked is overwrite_btn:
                    import_mode="overwrite"
                elif clicked is replace_btn:
                    import_mode="replace"
                elif clicked is skip_btn:
                    import_mode="skip"
                else:
                    wb.close()
                    return

                # Ghi đè: xóa dữ liệu con của các sheet có trong file, sau đó
                # UPDATE hồ sơ trạm theo Mã trạm. Các dữ liệu không nằm trong
                # file (ví dụ lịch sử MLL) vẫn được giữ nguyên.
                if import_mode in ("overwrite", "replace"):
                    for sheet,spec in specs.items():
                        if sheet not in wb.sheetnames or sheet=="TRẠM BTS":
                            continue
                        try:
                            if "station_code" in {r[1] for r in self.con.execute(f"PRAGMA table_info({spec['table']})").fetchall()}:
                                self.con.executemany(
                                    f"DELETE FROM {spec['table']} WHERE UPPER(TRIM(COALESCE(station_code,'')))=?",
                                    [(code,) for code in sorted(duplicate_codes)]
                                )
                        except Exception:
                            pass

                # Ghi và xóa dữ liệu cũ: xóa toàn bộ hồ sơ TRẠM BTS cũ để khi
                # import file mới sẽ tạo lại record sạch. Dữ liệu MLL lịch sử
                # không bị xóa vì sheet MLL không thuộc file Import này.
                if import_mode=="replace":
                    try:
                        self.con.executemany(
                            "DELETE FROM stations WHERE UPPER(TRIM(COALESCE(code,'')))=?",
                            [(code,) for code in sorted(duplicate_codes)]
                        )
                    except Exception:
                        self.con.rollback()
                        raise

            for sheet,spec in specs.items():
                if sheet not in wb.sheetnames:
                    skipped[sheet]="Không có sheet"
                    continue
                ws=wb[sheet]
                rows=ws.iter_rows(values_only=True)
                try:
                    raw_headers=next(rows)
                except StopIteration:
                    skipped[sheet]="Sheet rỗng"
                    continue

                idx={}
                for i,h in enumerate(raw_headers):
                    nh=norm_header(h)
                    canonical=aliases.get(nh, str(h).strip() if h is not None else "")
                    if canonical:
                        idx[canonical]=i

                # File mẫu hiện hành bỏ ID kỹ thuật ở tất cả sheet nghiệp vụ.
                # Chỉ bắt buộc Mã trạm; ID còn lại được hệ thống tự sinh.
                if sheet != "TRẠM BTS" and "Mã trạm" not in idx:
                    skipped[sheet]="Thiếu cột khóa liên kết: Mã trạm"
                    continue
                if sheet == "TRẠM BTS" and "Mã trạm" not in idx:
                    skipped[sheet]="Thiếu cột khóa: Mã trạm"
                    continue

                existing_cols={r[1] for r in self.con.execute(
                    f"PRAGMA table_info({spec['table']})").fetchall()}
                seen_keys=set()
                n_insert=n_update=n_skip=n_error=n_generated=0

                for excel_row_no,vals in enumerate(rows,start=2):
                    rec={}
                    for h,col in spec["cols"].items():
                        if h in idx and col in existing_cols:
                            pos=idx[h]
                            v=vals[pos] if pos<len(vals) else None
                            rec[col]=value_to_text(v)

                    station_code=rec.get("station_code","").strip()
                    if not station_code and sheet != "TRẠM BTS":
                        n_skip+=1
                        continue

                    # Chuẩn hóa mã trạm để tìm kiếm/liên kết nhất quán.
                    if station_code:
                        station_code=" ".join(station_code.split()).upper()
                        rec["station_code"]=station_code
                    if "email" in rec:
                        rec["email"] = str(rec.get("email") or "").strip().lower()

                    # Nếu mã trạm đã có trong CSDL và người dùng chọn Bỏ qua,
                    # không đụng vào dữ liệu cũ của mã đó.
                    if import_mode=="skip" and station_code in duplicate_codes:
                        n_skip+=1
                        continue

                    raw_key=rec.get(spec["key"],"").strip() if spec.get("key") else ""
                    row_fingerprint="|".join(value_to_text(v) for v in vals)
                    digest=hashlib.sha1(f"{sheet}|{station_code}|{row_fingerprint}".encode("utf-8")).hexdigest()[:10].upper()
                    prefix=key_prefix.get(sheet,"ROW")

                    # Nếu file mẫu không có cột ID, tự tạo ID kỹ thuật.
                    if not raw_key:
                        raw_key=f"{prefix}-{station_code or 'ROW'}-{digest}"
                        rec[spec["key"]]=raw_key
                        n_generated+=1

                    key=rec.get(spec["key"],"").strip()
                    if key in seen_keys:
                        key=f"{prefix}-{station_code or 'ROW'}-{digest}-{excel_row_no}"
                        rec[spec["key"]]=key
                        n_generated+=1
                    seen_keys.add(key)

                    if not key:
                        n_skip+=1
                        continue

                    try:
                        # TRẠM BTS dùng Mã trạm làm khóa nghiệp vụ để Ghi đè đúng record cũ.
                        if sheet=="TRẠM BTS" and station_code:
                            found=self.con.execute(
                                "SELECT 1 FROM stations WHERE UPPER(TRIM(COALESCE(code,'')))=?",
                                (station_code,)
                            ).fetchone()
                        else:
                            found=self.con.execute(
                                f"SELECT 1 FROM {spec['table']} WHERE {spec['key']}=?",(key,)
                            ).fetchone()
                        if found:
                            cols=[c for c in rec if c!=spec["key"]]
                            if cols:
                                if sheet=="TRẠM BTS" and station_code:
                                    self.con.execute(
                                        f"UPDATE {spec['table']} SET "+
                                        ",".join(f"{c}=?" for c in cols)+
                                        " WHERE UPPER(TRIM(COALESCE(code,'')))=?",
                                        [rec[c] for c in cols]+[station_code]
                                    )
                                else:
                                    self.con.execute(
                                        f"UPDATE {spec['table']} SET "+
                                        ",".join(f"{c}=?" for c in cols)+
                                        f" WHERE {spec['key']}=?",
                                        [rec[c] for c in cols]+[key]
                                    )
                            n_update+=1
                        else:
                            cols=list(rec)
                            self.con.execute(
                                f"INSERT INTO {spec['table']} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                                [rec[c] for c in cols]
                            )
                            n_insert+=1
                    except Exception:
                        n_error+=1

                imported[sheet]=n_insert
                updated[sheet]=n_update
                generated[sheet]=n_generated
                if n_skip:
                    skipped[sheet]=f"Bỏ qua {n_skip} dòng thiếu Mã trạm"
                if n_error:
                    errors[sheet]=n_error

            self.con.commit()
            wb.close()
            self.refresh_all()

            lines=[]
            for sheet in specs:
                if sheet in imported:
                    line=f"• {sheet}: {imported[sheet]} thêm mới, {updated.get(sheet,0)} cập nhật"
                    if skipped.get(sheet):
                        line += f", {skipped[sheet]}"
                    if generated.get(sheet,0):
                        line+=f", {generated[sheet]} ID tự tạo"
                    lines.append(line)
                elif sheet in skipped:
                    lines.append(f"• {sheet}: {skipped[sheet]}")
                if sheet in errors:
                    lines.append(f"  ⚠ {errors[sheet]} dòng lỗi")

            verify=[]
            for sheet,spec in specs.items():
                try:
                    n=self.con.execute(f"SELECT COUNT(*) FROM {spec['table']}").fetchone()[0]
                    verify.append(f"{sheet}: {n} dòng trong CSDL")
                except Exception:
                    pass

            mode_text={"overwrite":"Ghi đè dữ liệu trùng", "skip":"Bỏ qua dữ liệu trùng", "none":"Không có mã trạm trùng"}.get(import_mode, "")
            QMessageBox.information(
                self,"Import Excel hoàn tất",
                "Đã nhập/cập nhật dữ liệu từ file:\n"+Path(path).name+"\n"+
                (f"\n🔐 Xử lý mã trùng: {mode_text}\n" if mode_text else "")+"\n"+
                "\n".join(lines)+"\n\n📊 Kiểm tra CSDL sau Import:\n"+
                "\n".join(verify)
            )
        except Exception as e:
            try:
                self.con.rollback()
            except Exception:
                pass
            QMessageBox.critical(self,"Lỗi Import Excel",str(e))

    def download_template(self):
        source=BTS_IMPORT_TEMPLATE
        if not source.exists():
            QMessageBox.warning(self,"Không tìm thấy file mẫu","File Excel mẫu chưa được đóng gói.")
            return
        path,_=QFileDialog.getSaveFileName(self,"Lưu file mẫu Excel",str(Path.home()/"BTS_Manager_Import_Template_V85_60_5_EMAIL.xlsx"),"Excel (*.xlsx)")
        if not path:return
        if not path.lower().endswith(".xlsx"):path+=".xlsx"
        try: shutil.copy2(source,path); QMessageBox.information(self,"Hoàn tất",f"Đã lưu file mẫu:\n{path}")
        except Exception as e: QMessageBox.critical(self,"Lỗi lưu file",str(e))

    def download_selected_template(self):
        """Tải file mẫu theo lựa chọn: BTS, MLL, KPI hoặc cả 3 mẫu."""
        choice = self.template_selector.currentText() if hasattr(self, "template_selector") else "Cả 3 mẫu"
        if choice == "Mẫu Import BTS":
            sources=[BTS_IMPORT_TEMPLATE]
        elif choice == "Mẫu MLL":
            sources=[RESOURCE_DIR/"BTS_Manager_MLL_Template.xlsx"]
        elif choice == "Mẫu KPI":
            sources=[RESOURCE_DIR/"BTS_Manager_KPI_Import_Template.xlsx"]
        else:
            sources=[BTS_IMPORT_TEMPLATE, RESOURCE_DIR/"BTS_Manager_MLL_Template.xlsx", RESOURCE_DIR/"BTS_Manager_KPI_Import_Template.xlsx"]
        missing=[p.name for p in sources if not p.exists()]
        if missing:
            QMessageBox.warning(self,"Không tìm thấy file mẫu","Thiếu file mẫu: "+", ".join(missing))
            return
        if len(sources)==1:
            source=sources[0]
            path,_=QFileDialog.getSaveFileName(self,"Lưu file mẫu",str(Path.home()/source.name),"Excel (*.xlsx)")
            if not path:return
            if not path.lower().endswith(".xlsx"): path += ".xlsx"
            try:
                shutil.copy2(source,path)
                QMessageBox.information(self,"Đã tải file mẫu",f"Đã lưu file mẫu:\n{path}")
            except Exception as e:
                QMessageBox.critical(self,"Lỗi lưu file mẫu",str(e))
            return
        self.download_template_bundle()

    def download_template_bundle(self):
        """Tải đồng thời 3 mẫu Excel: Import BTS, MLL và KPI vào cùng một thư mục."""
        sources=[BTS_IMPORT_TEMPLATE, RESOURCE_DIR/"BTS_Manager_MLL_Template.xlsx", RESOURCE_DIR/"BTS_Manager_KPI_Import_Template.xlsx"]
        missing=[p.name for p in sources if not p.exists()]
        if missing:
            QMessageBox.warning(self,"Không tìm thấy file mẫu","Thiếu file mẫu: "+", ".join(missing))
            return
        folder=QFileDialog.getExistingDirectory(self,"Chọn thư mục lưu 3 file mẫu",str(Path.home()))
        if not folder:
            return
        try:
            out=[]
            for source in sources:
                target=Path(folder)/source.name
                shutil.copy2(source,target)
                out.append(str(target))
            QMessageBox.information(self,"Đã tải file mẫu",
                "Đã lưu đồng thời 3 file mẫu:\n\n"+
                "\n".join("• "+x for x in out)+
                "\n\n📌 Nút Upload file dùng chung sẽ tự nhận diện BTS, MLL hoặc KPI.")
        except Exception as e:
            QMessageBox.critical(self,"Lỗi lưu file mẫu",str(e))

    def import_kpi_excel(self, path):
        """Import file KPI gồm 3 cột: Nội dung, Chỉ tiêu và Đã thực hiện."""
        try:
            from openpyxl import load_workbook
            wb=load_workbook(path, read_only=True, data_only=True)
            ws=None
            for candidate in wb.worksheets:
                for raw in candidate.iter_rows(min_row=1, max_row=min(candidate.max_row,10), values_only=True):
                    headers={unicodedata.normalize("NFC", str(x).replace("\n"," ").strip()).casefold() for x in (raw or []) if x is not None}
                    if {"nội dung","chỉ tiêu","đã thực hiện"}.issubset(headers):
                        ws=candidate; break
                if ws: break
            if ws is None:
                wb.close(); raise ValueError("Không tìm thấy sheet KPI có đủ 3 cột 'Nội dung', 'Chỉ tiêu' và 'Đã thực hiện'.")
            values=list(ws.values); header_idx=None
            for i,row in enumerate(values[:10]):
                norm=[unicodedata.normalize("NFC", str(x).replace("\n"," ").strip()).casefold() if x is not None else "" for x in (row or [])]
                if "nội dung" in norm and "chỉ tiêu" in norm:
                    header_idx=i; break
            if header_idx is None:
                wb.close(); raise ValueError("Không tìm thấy dòng tiêu đề KPI.")
            headers=[unicodedata.normalize("NFC", str(x).replace("\n"," ").strip()).casefold() if x is not None else "" for x in values[header_idx]]
            idx_content=headers.index("nội dung"); idx_target=headers.index("chỉ tiêu"); idx_actual=headers.index("đã thực hiện")
            rows=[]
            for row in values[header_idx+1:]:
                if not row: continue
                content=str(row[idx_content]).strip() if idx_content < len(row) and row[idx_content] is not None else ""
                target=row[idx_target] if idx_target < len(row) else None
                actual=row[idx_actual] if idx_actual < len(row) else None
                if not content: continue
                def norm_num(v):
                    if v is None: return ""
                    if isinstance(v,float) and v.is_integer(): return str(int(v))
                    return str(v).strip()
                rows.append((content,norm_num(target),norm_num(actual)))
            if not rows:
                wb.close(); raise ValueError("File KPI không có dòng dữ liệu.")
            self.con.execute("DELETE FROM kpi_targets")
            now=datetime.datetime.now().isoformat(timespec="seconds")
            self.con.executemany("INSERT INTO kpi_targets(content,target,actual,updated_at) VALUES(?,?,?,?)", [(a,b,d,now) for a,b,d in rows])
            self.con.commit(); wb.close(); self.refresh_dashboard()
            QMessageBox.information(self,"Import KPI thành công",
                f"Đã cập nhật {len(rows)} chỉ tiêu KPI từ file:\n{Path(path).name}\n\n"+
                "\n".join(f"• {a}: {d or '—'} / {b or '—'}" for a,b,d in rows))
        except Exception as e:
            try: self.con.rollback()
            except Exception: pass
            QMessageBox.critical(self,"Lỗi Import KPI",str(e))

    def upload_excel_auto(self):
        """Một nút Upload chung: tự nhận diện file BTS, MLL hoặc KPI."""
        path,_=QFileDialog.getOpenFileName(self,"Upload file Excel","","Excel (*.xlsx *.xls)")
        if not path: return
        try:
            from openpyxl import load_workbook
            wb=load_workbook(path, read_only=True, data_only=True)
            is_mll=False; is_kpi=False
            for ws in wb.worksheets:
                for raw in ws.iter_rows(min_row=1, max_row=min(ws.max_row,12), values_only=True):
                    headers={unicodedata.normalize("NFC", str(x).replace("\n"," ").strip()).casefold() for x in (raw or []) if x is not None}
                    if {"tháng", "mã trạm", "tg gián đoạn (phút)"}.issubset(headers):
                        is_mll=True; break
                    if {"nội dung", "chỉ tiêu", "đã thực hiện"}.issubset(headers):
                        is_kpi=True; break
                if is_mll or is_kpi: break
            wb.close()
            if is_mll: self.import_mll_excel(path)
            elif is_kpi: self.import_kpi_excel(path)
            else: self.import_excel(path)
        except Exception as e:
            QMessageBox.critical(self,"Lỗi đọc file Upload",str(e))

    def refresh_all(self):
        # Refresh phần tổng quan ngay; chỉ refresh bảng đang nhìn thấy để tránh
        # chạy 5-6 truy vấn + dựng lại QTableWidget không cần thiết.
        self.refresh_dashboard()
        self.refresh_mll_dashboard()
        try:
            idx = self.stack.currentIndex()
            if hasattr(self, "station_page_index") and idx == self.station_page_index:
                self.load_station_list()
            section = getattr(self, "_page_section_map", {}).get(idx)
            reload_fn = getattr(self, "module_reloaders", {}).get(section)
            if reload_fn:
                reload_fn()
        except Exception as e:
            print(f"[WARN] refresh current page: {e}")

class StationWindow(QMainWindow):
    def __init__(self,parent,con,code):
        super().__init__(parent)
        self.con=con
        self.code=code
        self.setWindowTitle(f"Hồ sơ trạm BTS • {code}")
        self.resize(1380,860)
        self.setStyleSheet(parent.styleSheet())
        self.build()

    def build(self):
        root=QWidget()
        l=QVBoxLayout(root)
        l.setContentsMargins(24,20,24,20)
        l.setSpacing(14)

        st=self.con.execute("SELECT * FROM stations WHERE code=?",(self.code,)).fetchone()

        # Header
        header=QHBoxLayout()
        title_box=QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(QLabel(f"📡 {self.code}",objectName="pageTitle"))
        title_box.addWidget(QLabel(
            f"{st['name'] or 'Chưa đặt tên'}  •  UPE: {st['upe'] or '—'}",
            objectName="pageSub"
        ))
        header.addLayout(title_box)
        header.addStretch()

        status=QLabel(f"● {st['status'] or 'Chưa xác định'}")
        status.setStyleSheet(
            "color:#15803d;font-weight:800;background:#dcfce7;"
            "padding:7px 12px;border-radius:8px;"
        )
        header.addWidget(status)
        l.addLayout(header)

        # Station information block
        info=QFrame(objectName="card")
        il=QGridLayout(info)
        il.setContentsMargins(16,14,16,14)
        info_items=[
            ("Mã trạm", st["code"]),
            ("Tên trạm", st["name"]),
            ("UPE trạm", st["upe"]),
            ("Loại trạm", st["type"]),
            ("Địa chỉ", st["address"]),
            ("KTV quản lý", st["technician"]),
            ("Loại trụ", st["pole_type"]),
            ("Loại CSHT", st["csht_type"]),
            ("Người liên hệ", st["owner_contact"]),
            ("Mã điện kế", st["meter_code"]),
            ("Tọa độ", f"{st['latitude'] or '—'}, {st['longitude'] or '—'}"),
        ]
        for i,(label,value) in enumerate(info_items):
            r=(i//5)*2
            c=i%5
            lab=QLabel(label,objectName="cardLabel")
            val=QLabel(str(value or "—"))
            val.setStyleSheet("font-weight:650;color:#1e293b;")
            il.addWidget(lab,r,c)
            il.addWidget(val,r+1,c)
        l.addWidget(info)

        # Main station structure exactly following the requested Excel/app structure.
        tabs=QTabWidget()

        tabs.addTab(
            self.table_tab(
                "📄 HỢP ĐỒNG",
                "contracts",
                ["Mã hợp đồng","Số hợp đồng","Loại hợp đồng","Bên cho thuê",
                 "Ngày bắt đầu","Ngày hết hạn","Giá thuê","Trạng thái"],
                ["contract_id","contract_no","contract_type","lessor",
                 "start_date","end_date","rent_amount","status"]
            ),
            "📄 Hợp đồng"
        )

        tabs.addTab(
            self.table_tab(
                "📡 THIẾT BỊ",
                "equipment",
                ["Mã thiết bị","Nhóm thiết bị","Hãng","Model","Serial",
                 "IP","Vị trí","Trạng thái"],
                ["equipment_id","equipment_group","vendor","model","serial_no",
                 "ip_address","location","status"]
            ),
            "📡 Thiết bị"
        )

        tabs.addTab(
            self.transmission_tab(),
            "🔗 Truyền dẫn"
        )

        tabs.addTab(
            self.power_aux_tab(),
            "⚡ Nguồn & phụ trợ"
        )

        tabs.addTab(
            self.btbd_tab(),
            "🔧 BTBD"
        )

        l.addWidget(tabs,1)
        self.setCentralWidget(root)

    def table_tab(self,title,table,headers,cols):
        w=QWidget()
        l=QVBoxLayout(w)
        l.setContentsMargins(8,12,8,8)
        title_row=QHBoxLayout()
        title_row.addWidget(QLabel(title,objectName="cardLabel"))
        title_row.addStretch()
        count=self.con.execute(
            f"SELECT COUNT(*) FROM {table} WHERE station_code=?",(self.code,)
        ).fetchone()[0]
        badge=QLabel(f"{count} bản ghi")
        badge.setStyleSheet(
            "background:#e8f1f8;color:#164a78;padding:5px 9px;border-radius:7px;"
            "font-weight:700;"
        )
        title_row.addWidget(badge)
        l.addLayout(title_row)

        t=QTableWidget()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setAlternatingRowColors(True)

        rows=self.con.execute(
            f"SELECT {','.join(cols)} FROM {table} WHERE station_code=?",
            (self.code,)
        ).fetchall()
        t.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,v in enumerate(row):
                t.setItem(r,c,QTableWidgetItem(str(v or "")))
        l.addWidget(t)
        return w

    def transmission_tab(self):
        w=QWidget()
        l=QVBoxLayout(w)
        l.setContentsMargins(8,12,8,8)

        title=QLabel(
            "🔗 TRUYỀN DẪN  •  Tuyến chính / Backup • Fiber • SFP • Port • VLAN • IP",
            objectName="cardLabel"
        )
        l.addWidget(title)

        cols=[
            "transmission_id","link_type","path_role","device_a","port_a",
            "device_b","port_b","media","fiber_core","sfp_a","sfp_b",
            "vlan","wan_ip","lan_ip","lacp","provider","status"
        ]
        heads=[
            "Mã","Loại","Main/Backup","Thiết bị A","Port A","Thiết bị B","Port B",
            "Môi trường","Sợi quang","SFP A","SFP B","VLAN","IP WAN","IP LAN",
            "LACP","Nhà cung cấp","Trạng thái"
        ]
        t=QTableWidget()
        t.setColumnCount(len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)
        rows=self.con.execute(
            f"SELECT {','.join(cols)} FROM transmission WHERE station_code=?",
            (self.code,)
        ).fetchall()
        t.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,v in enumerate(row):
                t.setItem(r,c,QTableWidgetItem(str(v or "")))
        l.addWidget(t)
        return w

    def power_aux_tab(self):
        w=QWidget()
        l=QVBoxLayout(w)
        l.setContentsMargins(8,12,8,8)

        # Power
        l.addWidget(QLabel("⚡ NGUỒN",objectName="cardLabel"))
        power_cols=[
            "power_id","power_vendor","power_model","capacity_a","dc_voltage",
            "dc_load_a","rectifier_count","rectifier_working",
            "llvd1_v","llvd2_v","blvd_v","controller_ip","snmp","modbus","status"
        ]
        power_heads=[
            "Mã","Hãng","Model","Công suất A","DC V","Tải DC A","Số Rectifier",
            "Rectifier hoạt động","LLVD1","LLVD2","BLVD","Controller IP",
            "SNMP","Modbus","Trạng thái"
        ]
        p=QTableWidget()
        p.setColumnCount(len(power_heads))
        p.setHorizontalHeaderLabels(power_heads)
        p.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        p.horizontalHeader().setStretchLastSection(True)
        rows=self.con.execute(
            f"SELECT {','.join(power_cols)} FROM power WHERE station_code=?",
            (self.code,)
        ).fetchall()
        p.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,v in enumerate(row):
                p.setItem(r,c,QTableWidgetItem(str(v or "")))
        l.addWidget(p,1)

        # Battery
        l.addWidget(QLabel("🔋 PIN - BATTERY",objectName="cardLabel"))
        bcols=["battery_id","battery_type","vendor","model","voltage_v",
               "capacity_ah","soc_percent","soh_percent","voltage_online",
               "current_a","status"]
        bheads=["Mã Battery","Loại","Hãng","Model","V","Ah","SOC %","SOH %",
                "Điện áp Online","Dòng A","Trạng thái"]
        b=QTableWidget()
        b.setColumnCount(len(bheads))
        b.setHorizontalHeaderLabels(bheads)
        b.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        rows=self.con.execute(
            f"SELECT {','.join(bcols)} FROM batteries WHERE station_code=?",
            (self.code,)
        ).fetchall()
        b.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,v in enumerate(row):
                b.setItem(r,c,QTableWidgetItem(str(v or "")))
        l.addWidget(b,1)

        # Auxiliary
        l.addWidget(QLabel("🛠 THIẾT BỊ PHỤ TRỢ",objectName="cardLabel"))
        acols=["aux_id","category","vendor","model","specification",
               "quantity","location","status"]
        aheads=["Mã","Loại thiết bị","Hãng","Model","Thông số kỹ thuật",
                "SL","Vị trí","Trạng thái"]
        a=QTableWidget()
        a.setColumnCount(len(aheads))
        a.setHorizontalHeaderLabels(aheads)
        a.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        rows=self.con.execute(
            f"SELECT {','.join(acols)} FROM auxiliary WHERE station_code=?",
            (self.code,)
        ).fetchall()
        a.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,v in enumerate(row):
                a.setItem(r,c,QTableWidgetItem(str(v or "")))
        l.addWidget(a,1)

        return w

    def btbd_tab(self):
        w=QWidget()
        l=QVBoxLayout(w)
        l.setContentsMargins(8,12,8,8)

        # KPI for BTBD
        top=QHBoxLayout()
        for scope,label in [("Indoor","🏠 Indoor"),("Outdoor","🌐 Outdoor")]:
            n=self.con.execute(
                "SELECT COUNT(*) FROM maintenance WHERE station_code=? AND scope=?",
                (self.code,scope)
            ).fetchone()[0]
            f=QFrame(objectName="card")
            fl=QHBoxLayout(f)
            fl.addWidget(QLabel(label))
            v=QLabel(str(n),objectName="cardValue")
            fl.addWidget(v)
            top.addWidget(f)
        top.addStretch()
        l.addLayout(top)

        t=QTableWidget()
        heads=["Mã BTBD","Phạm vi","Loại công việc","Ngày thực hiện",
               "KTV thực hiện","Nội dung BTBD","Tình trạng trước",
               "Kết quả","Vật tư thay thế","Trạng thái","Ghi chú"]
        cols=["work_id","scope","work_type","work_date","technician","content",
              "condition_before","result","materials","status","note"]
        t.setColumnCount(len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setStretchLastSection(True)

        rows=self.con.execute(
            f"SELECT {','.join(cols)} FROM maintenance WHERE station_code=? ORDER BY work_date DESC",
            (self.code,)
        ).fetchall()
        t.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,v in enumerate(row):
                t.setItem(r,c,QTableWidgetItem(str(v or "")))
        l.addWidget(t,1)
        return w

def excel_specs():
    return {
        "TRẠM BTS":{"table":"stations","key":"code","cols":{"Mã trạm":"code","Tên trạm":"name","UPE trạm":"upe","Loại trạm":"type","Trạng thái":"status","Địa chỉ":"address","Vĩ độ":"latitude","Kinh độ":"longitude","Người liên hệ":"owner_contact","Mã điện kế":"meter_code","KTV quản lý":"technician","Loại trụ":"pole_type","Loại CSHT":"csht_type","Email":"email","Ghi chú":"note"}},
        "HỢP ĐỒNG":{"table":"contracts","key":"contract_id","cols":{"Mã hợp đồng":"contract_id","Mã trạm":"station_code","Số hợp đồng":"contract_no","Loại hợp đồng":"contract_type","Bên cho thuê":"lessor","Địa chỉ":"address","Ngày ký":"sign_date","Ngày bắt đầu":"start_date","Ngày hết hạn":"end_date","Giá thuê":"rent_amount","Chu kỳ thanh toán":"payment_cycle","Người liên hệ":"contact_name","SĐT liên hệ":"contact_phone","Trạng thái":"status","Tên file hợp đồng":"file_name","Ghi chú":"note"}},
        "THIẾT BỊ":{"table":"equipment","key":"equipment_id","cols":{"Mã thiết bị":"equipment_id","Mã trạm":"station_code","Nhóm thiết bị":"equipment_group","Hãng":"vendor","Model":"model","Serial":"serial_no","Part Number":"part_no","Địa chỉ IP":"ip_address","MAC Address":"mac_address","Phiên bản phần mềm":"software_version","Vị trí lắp đặt":"location","Ngày lắp":"install_date","Trạng thái":"status","Ghi chú":"note"}},
        "TRUYỀN DẪN":{"table":"transmission","key":"transmission_id","cols":{"Mã trạm":"station_code","Loại truyền dẫn":"link_type","Vai trò tuyến":"path_role","Thiết bị đầu A":"device_a","Port đầu A":"port_a","Thiết bị đầu B":"device_b","Port đầu B":"port_b","Tốc độ":"sfp_b_speed","VLAN":"vlan","IP WAN":"wan_ip","IP LAN":"lan_ip","Gateway":"gateway","Network":"network","LACP":"lacp","Tuyến chính/Backup":"main_backup","Nhà cung cấp":"provider","Trạng thái":"status","Ghi chú":"note"}},
        "NGUỒN":{"table":"power","key":"power_id","cols":{"Mã nguồn":"power_id","Mã trạm":"station_code","Hãng tủ nguồn":"power_vendor","Model tủ nguồn":"power_model","Công suất (A)":"capacity_a","Điện áp DC (V)":"dc_voltage","Dòng tải DC (A)":"dc_load_a","Điện áp AC (V)":"ac_voltage","Dòng tải AC (A)":"ac_load_a","Số Rectifier":"rectifier_count","Rectifier hoạt động":"rectifier_working","LLVD1 (V)":"llvd1_v","LLVD2 (V)":"llvd2_v","BLVD (V)":"blvd_v","IP Controller":"controller_ip","SNMP":"snmp","Modbus":"modbus","Trạng thái":"status","Ghi chú":"note"}},
        "PIN - BATTERY":{"table":"batteries","key":"battery_id","cols":{"Mã Battery":"battery_id","Mã trạm":"station_code","Loại Battery":"battery_type","Hãng":"vendor","Model":"model","Serial":"serial_no","Điện áp (V)":"voltage_v","Dung lượng (Ah)":"capacity_ah","Số Cell":"cell_count","SOC (%)":"soc_percent","SOH (%)":"soh_percent","Điện áp Online":"voltage_online","Dòng tải (A)":"current_a","Ngày lắp":"install_date","Trạng thái":"status","Ghi chú":"note"}},
        "THIẾT BỊ PHỤ TRỢ":{"table":"auxiliary","key":"aux_id","cols":{"Mã TB phụ trợ":"aux_id","Mã trạm":"station_code","Loại thiết bị":"category","Hãng":"vendor","Model":"model","Serial":"serial_no","Thông số kỹ thuật":"specification","Số lượng":"quantity","Vị trí":"location","Ngày lắp":"install_date","Trạng thái":"status","Ghi chú":"note"}},
        "BTBD":{"table":"maintenance","key":"work_id","cols":{"Mã BTBD":"work_id","Mã trạm":"station_code","Khu vực":"area","Phạm vi":"scope","Loại công việc":"work_type","Ngày thực hiện":"work_date","KTV thực hiện":"technician","Nội dung BTBD":"content","Tình trạng trước BTBD":"condition_before","Kết quả":"result","Vật tư thay thế":"materials","Chi phí":"cost","Trạng thái":"status","Ghi chú":"note"}}
    }

if __name__=="__main__":
    app=QApplication(sys.argv)
    app.setApplicationName("BTS Manager")
    # Application icon is bundled by PyInstaller next to the application resources.
    icon_path = RESOURCE_DIR / "BTS_Manager_Icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    win=App(); win.show()
    sys.exit(app.exec())
