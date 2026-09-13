# ui/main_window.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
import os
import queue
import win32api
import win32con
import win32gui
import win32print
import configparser
import tkinter as tk
from threading import Lock
import ttkbootstrap as ttkb
from tkinter import messagebox
import serial.tools.list_ports
from ttkbootstrap.constants import *
from core.controller import ControlSystem

appdata_path = os.getenv('APPDATA') if os.getenv('APPDATA') is not None else ''
config_dir = os.path.join(appdata_path, 'PTZ_Controller')
config_path = os.path.join(config_dir, 'config.ini')

config = configparser.ConfigParser()
config.read(config_path)

# 检查配置文件并添加缺失的部分
for section in ['GS232B', 'PELCO']:
    if section not in config:
        config[section] = {}
    if 'PROTOCOL' not in config[section]:
        config[section]['PROTOCOL'] = 'serial'
    if 'SERIAL_PORT' not in config[section]:
        config[section]['SERIAL_PORT'] = 'COM1'
    if 'BAUDRATE' not in config[section]:
        config[section]['BAUDRATE'] = '9600'
    if 'HOST' not in config[section]:
        config[section]['HOST'] = '127.0.0.1'
    if 'PORT' not in config[section]:
        config[section]['PORT'] = '5000'
    if 'UDP_LOCAL_PORT' not in config[section]:
        config[section]['UDP_LOCAL_PORT'] = '5000'
    if 'UDP_REMOTE_HOST' not in config[section]:
        config[section]['UDP_REMOTE_HOST'] = '127.0.0.1'
    if 'UDP_REMOTE_PORT' not in config[section]:
        config[section]['UDP_REMOTE_PORT'] = '5000'
if 'ANGLE_CORRECTION' not in config:
    config['ANGLE_CORRECTION'] = {}
if 'MIN_ELEVATION' not in config['ANGLE_CORRECTION']:
    config['ANGLE_CORRECTION']['MIN_ELEVATION'] = '0'
if 'MAX_ELEVATION' not in config['ANGLE_CORRECTION']:
    config['ANGLE_CORRECTION']['MAX_ELEVATION'] = '90'
if 'AZIMUTH_OFFSET' not in config['ANGLE_CORRECTION']:
    config['ANGLE_CORRECTION']['AZIMUTH_OFFSET'] = '0'
if 'INITIAL_AZIMUTH' not in config['ANGLE_CORRECTION']:
    config['ANGLE_CORRECTION']['INITIAL_AZIMUTH'] = '0'
if 'UI' not in config:
    config['UI'] = {}
if 'TOPMOST' not in config['UI']:
    config['UI']['TOPMOST'] = 'True'
if 'OTHER' not in config:
    config['OTHER'] = {}
if 'PTZ_MODE' not in config['OTHER']:
    config['OTHER']['PTZ_MODE'] = 'YAAN'


class MainWindow:
    def __init__(self):
        # 宽高自适应系统缩放
        scale = self._get_scaling()
        base_width = 380
        base_height = 850
        scaled_width = int(base_width * scale)
        scaled_height = int(base_height * scale)

        self.root = ttkb.Window()
        self.root.title("PTZ 云台控制系统 v2.1.0")
        self.root.geometry(f"{scaled_width}x{scaled_height}")
        self.root.minsize(int(350 * scale), int(500 * scale))
        self.root.attributes('-topmost', True)
        self.root.resizable(False, True)
        self.root.protocol('WM_DELETE_WINDOW', self.on_closing)

        # 初始化变量
        self.control_system = None
        self.running = False
        self.log_queue = queue.Queue()
        self._connection_lock = Lock()

        # 初始化配置系统
        self._init_ui()
        self.root.after(100, self._process_log_queue)

    def _init_ui(self):
        """初始化用户界面"""
        # 使用 pack 实现垂直布局：配置区 -> 按钮区 -> 日志区
        # 设备配置区域
        config_frame = ttkb.Labelframe(self.root, text="设备配置", bootstyle=INFO)
        config_frame.pack(fill=X, padx=10, pady=(10, 5))

        # 创建设备面板
        self._create_device_panel(config_frame, "gs232b", 0)
        self._create_device_panel(config_frame, "pelco", 1)

        # 创建俯仰角手动调整区域
        self._create_device_panel(config_frame, "AZ/EL", 2)

        # 创建其他功能区域
        self._create_device_panel(config_frame, "其他功能", 3)

        # 控制按钮区域
        btn_frame = ttkb.Frame(self.root)
        btn_frame.pack(fill=X, padx=10, pady=5)

        # 按钮均匀排列
        self.start_btn = ttkb.Button(btn_frame, text="启动系统", command=self.toggle_system,
                                     bootstyle=(SUCCESS, OUTLINE))
        self.start_btn.pack(side=LEFT, padx=3, expand=True)

        clear_btn = ttkb.Button(btn_frame, text="清除日志", command=self.clear_log,
                                bootstyle=(WARNING, OUTLINE))
        clear_btn.pack(side=LEFT, padx=3, expand=True)

        save_btn = ttkb.Button(btn_frame, text="保存配置", command=self.save_config,
                               bootstyle=(PRIMARY, OUTLINE))
        save_btn.pack(side=LEFT, padx=3, expand=True)

        # 置顶按钮
        self.topmost_btn = ttkb.Button(btn_frame, text="窗口置顶", command=self.toggle_topmost,
                                       bootstyle=(PRIMARY, OUTLINE))
        self.topmost_btn.pack(side=LEFT, padx=3, expand=True)

        # 判断配置文件中是否设置了置顶
        if config['UI']['topmost']:
            self.root.attributes('-topmost', True)
            self.topmost_btn.config(bootstyle=(PRIMARY, OUTLINE))
        else:
            self.root.attributes('-topmost', False)
            self.topmost_btn.config(bootstyle=(SECONDARY, OUTLINE))

        # 日志区域 - 占据剩余空间
        log_frame = ttkb.Labelframe(self.root, text="系统日志", bootstyle=INFO)
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=(5, 10))

        # 日志文本框和滚动条
        self.log_area = tk.Text(log_frame, state=tk.DISABLED, font=('微软雅黑', 10))
        scrollbar = ttkb.Scrollbar(log_frame, command=self.log_area.yview)
        self.log_area.configure(yscrollcommand=scrollbar.set)

        self.log_area.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # 初始化日志标签颜色（只设置一次）
        self.log_area.tag_config("info", foreground="green")
        self.log_area.tag_config("warning", foreground="orange")
        self.log_area.tag_config("error", foreground="red")

        # 加载现有配置
        self._load_config_to_ui()

    def _create_device_panel(self, parent, device, row):
        """创建设备配置面板"""
        frame = ttkb.Labelframe(parent, text=f"{device.upper()}", bootstyle=INFO)
        frame.grid(row=row, column=0, sticky="ew", padx=5, pady=5)
        frame.columnconfigure(1, weight=1)  # 使第二列可扩展

        if device == "AZ/EL":  # 俯仰角手动调整
            self._create_az_el_panel(frame)
        elif device == "其他功能":  # 其他功能面板
            self._other_panel(frame)
        else:
            # 协议选择
            ttkb.Label(frame, text="通信协议:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
            protocol = ttkb.Combobox(frame, values=["串口", "TCP", "UDP"], state="readonly", width=8)
            protocol.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
            protocol.set("串口")
            setattr(self, f"{device}_protocol", protocol)

            # 绑定协议切换事件
            protocol.bind("<<ComboboxSelected>>", lambda e, dev=device: self._on_protocol_changed(dev))

            # 参数选项卡
            self._create_settings_notebook(frame, device)

    def _create_az_el_panel(self, parent):  # 俯仰角手动调整
        """创建俯仰角手动调整面板"""
        # 水平角调整按钮
        ttkb.Label(parent, text="水平角度:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        azimuth_entry = ttkb.Entry(parent)
        azimuth_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        azimuth_btn = ttkb.Button(parent, text="执行",
                                  command=lambda: self.set_az_el(azimuth_entry.get(), 0x4B))
        azimuth_btn.grid(row=0, column=2, padx=5)

        # 俯仰角调整按钮
        ttkb.Label(parent, text="俯仰角度:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        elevation_entry = ttkb.Entry(parent)
        elevation_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        elevation_btn = ttkb.Button(parent, text="执行",
                                    command=lambda: self.set_az_el(elevation_entry.get(), 0x4D))
        elevation_btn.grid(row=1, column=2, padx=5)

    def _other_panel(self, parent):
        """创建其他面板"""
        # 云台类型选择
        ttkb.Label(parent, text="云台类型:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.PTZ_mode_combo = ttkb.Combobox(parent, values=["YAAN", "FY-SP2018LM-W"], state="readonly", width=8)
        self.PTZ_mode_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

    def _create_settings_notebook(self, parent, device):
        """创建参数配置选项卡"""
        notebook = ttkb.Notebook(parent, bootstyle=INFO)
        notebook.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        parent.columnconfigure(1, weight=1)  # 使第二列可扩展

        # 保存引用，方便协议切换时切换页签
        setattr(self, f"{device}_notebook", notebook)

        # 串口配置
        serial_frame = ttkb.Frame(notebook)
        serial_frame.columnconfigure(1, weight=1)  # 使下拉框可扩展

        ttkb.Label(serial_frame, text="串口号:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        serial_port = ttkb.Combobox(serial_frame, state="readonly")
        serial_port.bind("<Button-1>", lambda e: self._refresh_ports(serial_port))
        # 选择后设置config内对应的值
        serial_port.bind("<<ComboboxSelected>>", lambda e, dev=device: self._on_config_changed(serial_port, dev, "serial_port"))
        serial_port.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttkb.Label(serial_frame, text="波特率:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        baudrate = ttkb.Combobox(serial_frame, values=["2400", "9600", "19200", "38400", "115200"])
        baudrate.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        notebook.add(serial_frame, text="串口参数")
        setattr(self, f"{device}_serial", (serial_port, baudrate))

        # TCP配置
        tcp_frame = ttkb.Frame(notebook)
        tcp_frame.columnconfigure(1, weight=1)  # 使输入框可扩展

        ttkb.Label(tcp_frame, text="IP地址:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        tcp_host = ttkb.Entry(tcp_frame)
        tcp_host.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttkb.Label(tcp_frame, text="端口号:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        tcp_port = ttkb.Entry(tcp_frame)
        tcp_port.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        notebook.add(tcp_frame, text="TCP参数")
        setattr(self, f"{device}_tcp", (tcp_host, tcp_port))

        # UDP配置
        udp_frame = ttkb.Frame(notebook)
        udp_frame.columnconfigure(1, weight=1)

        ttkb.Label(udp_frame, text="本地端口:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        udp_local_port = ttkb.Entry(udp_frame)
        udp_local_port.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttkb.Label(udp_frame, text="远程主机:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        udp_remote_host = ttkb.Entry(udp_frame)
        udp_remote_host.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        ttkb.Label(udp_frame, text="远程端口:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        udp_remote_port = ttkb.Entry(udp_frame)
        udp_remote_port.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        notebook.add(udp_frame, text="UDP参数")
        setattr(self, f"{device}_udp", (udp_local_port, udp_remote_host, udp_remote_port))

        # 角度修正配置（仅Pelco）
        if device == "pelco":
            angle_frame = ttkb.Frame(notebook)
            angle_frame.columnconfigure(1, weight=1)  # 使输入框可扩展

            fields = [
                ("最小俯仰角:", "min_elevation"),
                ("最大俯仰角:", "max_elevation"),
                ("方位角偏移:", "azimuth_offset"),
                ("初始水平角:", "initial_azimuth")
            ]
            for i, (label, _) in enumerate(fields):
                ttkb.Label(angle_frame, text=label).grid(row=i, column=0, padx=5, pady=2, sticky="w")
                entry = ttkb.Entry(angle_frame)
                entry.grid(row=i, column=1, padx=5, pady=2, sticky="ew")
                setattr(angle_frame, f"entry_{i}", entry)

            notebook.add(angle_frame, text="角度修正")
            setattr(self, f"{device}_angle", [getattr(angle_frame, f"entry_{i}") for i in range(4)])

    def _on_protocol_changed(self, device):
        """协议切换时自动切换参数页签"""
        proto = getattr(self, f"{device}_protocol").get()
        notebook = getattr(self, f"{device}_notebook")

        # 根据协议选择切换页签索引
        if proto == "串口":
            notebook.select(0)
            config[device.upper()]["PROTOCOL"] = "serial"
        elif proto == "TCP":
            notebook.select(1)
            config[device.upper()]["PROTOCOL"] = "tcp"
        else:
            notebook.select(2)
            config[device.upper()]["PROTOCOL"] = "udp"

    def _build_device_config(self, device):
        """构建单个设备配置"""
        proto = getattr(self, f"{device}_protocol").get()
        proto_map = {"串口": "serial", "TCP": "tcp", "UDP": "udp"}
        config = {"protocol": proto_map.get(proto, "serial")}

        if proto == "串口":
            port, baud = getattr(self, f"{device}_serial")
            port_value = port.get().strip()
            baud_value = baud.get().strip()
            if not port_value or not baud_value:
                raise ValueError(f"{device} 串口参数不能为空")
            config["serial"] = {
                "port": port_value,
                "baudrate": int(baud_value)
            }
        elif proto == "TCP":
            host, port = getattr(self, f"{device}_tcp")
            host_value = host.get().strip()
            port_value = port.get().strip()
            if not host_value or not port_value:
                raise ValueError(f"{device} TCP参数不能为空")
            try:
                port_num = int(port_value)
            except ValueError:
                raise ValueError(f"{device} 端口号必须是整数")
            config["tcp"] = {
                "host": host_value,
                "port": port_num
            }
        else:  # UDP
            local_port_entry, remote_host_entry, remote_port_entry = getattr(self, f"{device}_udp")
            local_port_val = local_port_entry.get().strip()
            remote_host_val = remote_host_entry.get().strip()
            remote_port_val = remote_port_entry.get().strip()
            if not local_port_val or not remote_host_val or not remote_port_val:
                raise ValueError(f"{device} UDP参数不能为空")
            try:
                local_port_num = int(local_port_val)
                remote_port_num = int(remote_port_val)
            except ValueError:
                raise ValueError(f"{device} UDP端口号必须是整数")
            config["udp"] = {
                "local_port": local_port_num,
                "remote_host": remote_host_val,
                "remote_port": remote_port_num
            }

        if device == "pelco":
            entries = getattr(self, f"{device}_angle")
            config["angle_correction"] = {
                "min_elevation": float(entries[0].get()),
                "max_elevation": float(entries[1].get()),
                "azimuth_offset": float(entries[2].get()),
                "initial_azimuth": float(entries[3].get())
            }
        return config

    def _validate_config(self, config):
        """验证配置有效性和完整性"""
        # 必填字段检查
        required_keys = {
            "gs232b": ["protocol", "serial"],
            "pelco": ["protocol", "serial", "angle_correction"],
            "ui": ["topmost"]
        }

        for section, keys in required_keys.items():
            if section not in config:
                # 补全缺少的配置
                config[section] = {}
            for key in keys:
                if key not in config[section]:
                    config[section][key] = None

        # 协议字段检查
        for device in ["gs232b", "pelco"]:
            protocol = config[device].get("protocol")
            if protocol not in ("serial", "tcp"):
                raise ValueError(f"{device} 协议设置无效: {protocol}")

            if protocol == "serial":
                serial_cfg = config[device]["serial"]
                if "port" not in serial_cfg or not serial_cfg["port"]:
                    raise ValueError(f"{device} 串口配置缺少 port")
                if "baudrate" not in serial_cfg or not isinstance(serial_cfg["baudrate"], int):
                    raise ValueError(f"{device} 串口配置缺少或非法 baudrate")

            if protocol == "tcp":
                tcp_cfg = config[device].get("tcp", {})
                if "host" not in tcp_cfg or not tcp_cfg["host"]:
                    raise ValueError(f"{device} TCP配置缺少 host")
                if "port" not in tcp_cfg or not (0 < tcp_cfg["port"] <= 65535):
                    raise ValueError(f"{device} TCP端口号必须为 1-65535")

        # Pelco 角度校正参数验证
        pelco_corr = config["pelco"]["angle_correction"]
        if not (-360 <= pelco_corr["azimuth_offset"] <= 360):
            raise ValueError("方位角偏移必须在 ±360 度之间")
        if not (0 <= pelco_corr["initial_azimuth"] <= 360):
            raise ValueError("初始水平角必须在 0-360 度之间")
        if pelco_corr["min_elevation"] > pelco_corr["max_elevation"]:
            raise ValueError("最小俯仰角不能大于最大俯仰角")

    def _load_config_to_ui(self):
        """加载配置文件到界面"""
        # 加载GS232B配置
        self._load_protocol_config("gs232b", config["GS232B"])

        # 加载Pelco-D配置
        self._load_protocol_config("pelco", config["PELCO"])

        # 加载角度修正配置
        entries = getattr(self, "pelco_angle")
        angle_values = [
            config.get("ANGLE_CORRECTION", "MIN_ELEVATION", fallback="0"),
            config.get("ANGLE_CORRECTION", "MAX_ELEVATION", fallback="90"),
            config.get("ANGLE_CORRECTION", "AZIMUTH_OFFSET", fallback="0"),
            config.get("ANGLE_CORRECTION", "INITIAL_AZIMUTH", fallback="0"),
        ]
        for entry, value in zip(entries, angle_values):
            entry.delete(0, tk.END)
            entry.insert(0, str(value))

        # 加载界面配置
        self._apply_ui_settings(config['UI'])

        # 加载其他配置
        self._other_settings()

    def _load_protocol_config(self, device, ptz_config):
        """加载协议配置到UI组件"""
        proto = ptz_config["protocol"]
        proto_map = {"serial": "串口", "tcp": "TCP", "udp": "UDP"}
        getattr(self, f"{device}_protocol").set(proto_map.get(proto, "串口"))
        notebook = getattr(self, f"{device}_notebook")

        if proto == "serial":
            serial_port, baudrate = getattr(self, f"{device}_serial")
            serial_port.set(ptz_config["serial_port"])
            baudrate.set(str(ptz_config["baudrate"]))
            notebook.select(0)
        elif proto == "tcp":
            host, port = getattr(self, f"{device}_tcp")
            host.delete(0, tk.END)
            host.insert(0, ptz_config["host"])
            port.delete(0, tk.END)
            port.insert(0, str(ptz_config["port"]))
            notebook.select(1)
        elif proto == "udp":
            local_port, remote_host, remote_port = getattr(self, f"{device}_udp")
            local_port.delete(0, tk.END)
            local_port.insert(0, str(ptz_config.get("udp_local_port", "5000")))
            remote_host.delete(0, tk.END)
            remote_host.insert(0, ptz_config.get("udp_remote_host", "127.0.0.1"))
            remote_port.delete(0, tk.END)
            remote_port.insert(0, str(ptz_config.get("udp_remote_port", "5000")))
            notebook.select(2)

    def _apply_ui_settings(self, ui_config):
        """应用 UI 配置（如窗口置顶按钮状态）"""
        topmost = ui_config.get("topmost", False)
        self.root.attributes("-topmost", topmost)
        self.topmost_btn.config(text="取消置顶" if topmost else "窗口置顶",
                                bootstyle=(PRIMARY, OUTLINE) if topmost else (SECONDARY, OUTLINE))

    def _other_settings(self):
        """应用其他配置"""
        # 设置PTZ_mode_combo
        if "PTZ_mode" in config["OTHER"]:
            self.PTZ_mode_combo.set(str(config["OTHER"]["ptz_mode"]))

    # 日志处理相关方法
    def log(self, message: str):
        """日志记录"""
        self.log_queue.put(message)

    def _process_log_queue(self):
        """处理日志队列"""
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_area.configure(state=tk.NORMAL)

            # 根据日志级别选择标签
            if "[错误]" in msg:
                tag = "error"
            elif "[警告]" in msg:
                tag = "warning"
            else:
                tag = "info"

            self.log_area.insert(tk.END, f">> {msg}\n", tag)
            self.log_area.configure(state=tk.DISABLED)
            self.log_area.see(tk.END)
        self.root.after(100, self._process_log_queue)

    def clear_log(self):
        """清空日志"""
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.configure(state=tk.DISABLED)

    # 系统启停控制
    def toggle_system(self):
        """启停系统"""
        if not self.running:
            try:
                self.control_system = ControlSystem(config, self.log)
                self.control_system.start()
                self.running = True
                self.start_btn.config(text="停止系统")
                self.log("[系统] 系统启动成功")
            except Exception as e:
                messagebox.showerror("错误", f"系统启动失败：{str(e)}")
        else:
            with self._connection_lock:
                self.running = False
                if self.control_system:
                    self.control_system.stop()
                    self.control_system = None
                self.start_btn.config(text="启动系统")
                self.log("[系统] 系统已安全停止")

    def _refresh_ports(self, combobox):
        """刷新串口列表"""
        try:
            ports = [port.device for port in serial.tools.list_ports.comports()]
            combobox['values'] = ports
            if ports and not combobox.get():
                combobox.set(ports[0])
        except Exception as e:
            self.log(f"[错误] 刷新串口失败: {str(e)}")

    def _get_scaling(self):
        """获取屏幕的缩放比例"""
        try:
            scaling = round(
                win32print.GetDeviceCaps(win32gui.GetDC(0), win32con.DESKTOPHORZRES) / win32api.GetSystemMetrics(0), 2)
            return scaling
        except Exception as e:
            return 1.0

    def save_config(self):
        """保存当前配置到文件"""
        try:
            # 收集 GS232B 配置
            gs232b_dev = self._build_device_config("gs232b")
            config.set("GS232B", "PROTOCOL", gs232b_dev["protocol"])
            if gs232b_dev["protocol"] == "serial":
                config.set("GS232B", "SERIAL_PORT", gs232b_dev["serial"]["port"])
                config.set("GS232B", "BAUDRATE", str(gs232b_dev["serial"]["baudrate"]))
            elif gs232b_dev["protocol"] == "tcp":
                config.set("GS232B", "HOST", gs232b_dev["tcp"]["host"])
                config.set("GS232B", "PORT", str(gs232b_dev["tcp"]["port"]))
            else:
                config.set("GS232B", "UDP_LOCAL_PORT", str(gs232b_dev["udp"]["local_port"]))
                config.set("GS232B", "UDP_REMOTE_HOST", gs232b_dev["udp"]["remote_host"])
                config.set("GS232B", "UDP_REMOTE_PORT", str(gs232b_dev["udp"]["remote_port"]))

            # 收集 Pelco 配置
            pelco_dev = self._build_device_config("pelco")
            config.set("PELCO", "PROTOCOL", pelco_dev["protocol"])
            if pelco_dev["protocol"] == "serial":
                config.set("PELCO", "SERIAL_PORT", pelco_dev["serial"]["port"])
                config.set("PELCO", "BAUDRATE", str(pelco_dev["serial"]["baudrate"]))
            elif pelco_dev["protocol"] == "tcp":
                config.set("PELCO", "HOST", pelco_dev["tcp"]["host"])
                config.set("PELCO", "PORT", str(pelco_dev["tcp"]["port"]))
            else:
                config.set("PELCO", "UDP_LOCAL_PORT", str(pelco_dev["udp"]["local_port"]))
                config.set("PELCO", "UDP_REMOTE_HOST", pelco_dev["udp"]["remote_host"])
                config.set("PELCO", "UDP_REMOTE_PORT", str(pelco_dev["udp"]["remote_port"]))

            # 收集角度修正配置
            ac = pelco_dev["angle_correction"]
            config.set("ANGLE_CORRECTION", "MIN_ELEVATION", str(ac["min_elevation"]))
            config.set("ANGLE_CORRECTION", "MAX_ELEVATION", str(ac["max_elevation"]))
            config.set("ANGLE_CORRECTION", "AZIMUTH_OFFSET", str(ac["azimuth_offset"]))
            config.set("ANGLE_CORRECTION", "INITIAL_AZIMUTH", str(ac["initial_azimuth"]))

            # 保存到文件
            if not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            with open(config_path, 'w') as configfile:
                config.write(configfile)
            self.log("[配置] 配置已保存")
        except Exception as e:
            self.log(f"[错误] 保存配置失败: {str(e)}")

    def toggle_topmost(self):
        """切换窗口置顶状态并更新按钮显示"""
        current = self.root.attributes("-topmost")
        new_state = not current
        self.root.attributes("-topmost", new_state)
        self.topmost_btn.config(text="取消置顶" if new_state else "窗口置顶",
                                bootstyle=(PRIMARY, OUTLINE) if new_state else (SECONDARY, OUTLINE))
        config.set("UI", "TOPMOST", str(new_state))
        self.log(f"[UI] 窗口置顶状态已切换至{'置顶' if new_state else '取消置顶'}")

    def set_az_el(self, angle, set_cmd):
        """设置角度"""
        if not self.running:
            self.log("[错误] 系统未启动，无法设置角度")
            return
        if not angle or not angle.strip():
            self.log("[警告] 角度值不能为空")
            return
        try:
            angle_value = float(angle)
        except ValueError:
            self.log(f"[错误] 无效的角度值: {angle}")
            return
        self.control_system.select_angle(angle_value, set_cmd)

    def on_closing(self):
        os.makedirs(config_dir, exist_ok=True)
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        self.root.destroy()

    def run(self):
        """启动主循环"""
        self.root.mainloop()


if __name__ == "__main__":
    app = MainWindow()
    app.run()
