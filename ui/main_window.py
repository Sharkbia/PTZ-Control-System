# ui/main_window.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
import json
import os
import queue
import win32api
import win32con
import win32gui
import win32print
import tkinter as tk
from pathlib import Path
from threading import Lock
import ttkbootstrap as ttkb
from tkinter import messagebox
import serial.tools.list_ports
from ttkbootstrap.constants import *
from core.controller import ControlSystem


class MainWindow:
    def __init__(self):
        # 宽高自适应系统缩放
        scale = self._get_scaling()
        base_width = 280
        base_height = 700
        scaled_width = int(base_width * scale)
        scaled_height = int(base_height * scale)

        self.root = ttkb.Window()
        self.root.title("PTZ 云台控制系统")
        self.root.geometry(f"{scaled_width}x{scaled_height}")
        self.root.attributes('-topmost', True)
        # self.root.resizable(False, False)

        # 设置网格行列权重，使日志区域可扩展
        self.root.rowconfigure(0, weight=0)  # 顶部区域不扩展
        self.root.rowconfigure(1, weight=1)  # 日志区域扩展
        self.root.columnconfigure(0, weight=1)

        # 初始化变量
        self.control_system = None
        self.running = False
        self.config_file = self._get_config_path()
        self.log_queue = queue.Queue()
        self._connection_lock = Lock()  # 新增线程锁

        # 初始化配置系统
        self._init_config()
        self._init_ui()
        self._setup_autosave()
        self.root.after(100, self._process_log_queue)

    def _get_config_path(self) -> str:
        """获取跨平台配置文件路径"""
        if os.name == 'nt':
            config_dir = Path(os.getenv('APPDATA')) / 'PTZ_Controller'
        else:
            config_dir = Path.home() / '.config' / 'PTZ_Controller'

        config_dir.mkdir(parents=True, exist_ok=True)
        return str(config_dir / 'config.json')

    def _get_default_config(self) -> dict:
        """生成默认配置"""
        return {
            "gs232b": {
                "protocol": "serial",
                "serial": {
                    "port": "COM1",
                    "baudrate": 9600
                }
            },
            "pelco": {
                "protocol": "serial",
                "serial": {
                    "port": "COM2",
                    "baudrate": 9600
                },
                "angle_correction": {
                    "min_elevation": 0,
                    "max_elevation": 90,
                    "azimuth_offset": 0,
                    "initial_azimuth": 0
                }
            }
        }

    def _init_config(self):
        """初始化配置文件"""
        if not os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'w') as f:
                    json.dump(self._get_default_config(), f, indent=2)
                self.log("[系统] 已创建默认配置文件")
            except Exception as e:
                messagebox.showerror("错误", f"创建配置文件失败: {str(e)}")

    def _init_ui(self):
        """初始化用户界面"""
        # 主框架 - 使用网格布局
        main_frame = ttkb.Frame(self.root)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 设备配置区域
        config_frame = ttkb.Labelframe(main_frame, text="设备配置", bootstyle=INFO)
        config_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # 创建设备面板
        self._create_device_panel(config_frame, "gs232b", 0)
        self._create_device_panel(config_frame, "pelco", 1)

        # 控制按钮区域
        btn_frame = ttkb.Frame(main_frame)
        btn_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        btn_frame.columnconfigure(0, weight=1)  # 左边撑开
        btn_frame.columnconfigure(1, weight=0)  # 按钮
        btn_frame.columnconfigure(2, weight=0)  # 按钮
        btn_frame.columnconfigure(3, weight=1)  # 右边撑开

        # 居中放置按钮
        self.start_btn = ttkb.Button(btn_frame, text="启动系统", command=self.toggle_system,
                                     bootstyle=(SUCCESS, OUTLINE))
        self.start_btn.grid(row=0, column=1, padx=5)

        clear_btn = ttkb.Button(btn_frame, text="清除日志", command=self.clear_log,
                                bootstyle=(WARNING, OUTLINE))
        clear_btn.grid(row=0, column=2, padx=5)

        # 日志区域
        log_frame = ttkb.Labelframe(self.root, text="系统日志", bootstyle=INFO)
        log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        # 设置日志区域的权重
        self.root.rowconfigure(1, weight=1)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        # 日志文本框和滚动条
        self.log_area = tk.Text(log_frame, state=tk.DISABLED, font=('微软雅黑', 10))
        scrollbar = ttkb.Scrollbar(log_frame, command=self.log_area.yview)
        self.log_area.configure(yscrollcommand=scrollbar.set)

        # 使用网格布局放置日志组件
        self.log_area.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # 加载现有配置
        self._load_config_to_ui()

    def _create_device_panel(self, parent, device, row):
        """创建设备配置面板"""
        frame = ttkb.Labelframe(parent, text=f"{device.upper()} 配置", bootstyle=INFO)
        frame.grid(row=row, column=0, sticky="ew", padx=5, pady=5)
        frame.columnconfigure(1, weight=1)  # 使第二列可扩展

        # 协议选择
        ttkb.Label(frame, text="通信协议:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        protocol = ttkb.Combobox(frame, values=["串口", "TCP"], state="readonly", width=8)
        protocol.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        protocol.set("串口")
        setattr(self, f"{device}_protocol", protocol)

        # 参数选项卡
        self._create_settings_notebook(frame, device)

    def _create_settings_notebook(self, parent, device):
        """创建参数配置选项卡"""
        notebook = ttkb.Notebook(parent, bootstyle=INFO)
        notebook.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        parent.columnconfigure(1, weight=1)  # 使第二列可扩展

        # 串口配置
        serial_frame = ttkb.Frame(notebook)
        serial_frame.columnconfigure(1, weight=1)  # 使下拉框可扩展

        ttkb.Label(serial_frame, text="串口号:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        serial_port = ttkb.Combobox(serial_frame, state="readonly")
        serial_port.bind("<Button-1>", lambda e: self._refresh_ports(serial_port))
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

    def _setup_autosave(self):
        """配置自动保存功能"""
        # 为所有输入组件绑定失焦事件
        components = [
            *self._get_all_entries(),
            *self._get_all_comboboxes()
        ]
        for widget in components:
            widget.bind("<FocusOut>", lambda e: self._save_and_reload())

    def _get_all_entries(self):
        """获取所有输入框组件"""
        entries = []
        for device in ["gs232b", "pelco"]:
            entries.extend(getattr(self, f"{device}_tcp"))
            if device == "pelco":
                entries.extend(getattr(self, f"{device}_angle"))
        return entries

    def _get_all_comboboxes(self):
        """获取所有下拉框组件"""
        comboboxes = []
        for device in ["gs232b", "pelco"]:
            comboboxes.append(getattr(self, f"{device}_protocol"))
            comboboxes.extend(getattr(self, f"{device}_serial"))
        return comboboxes

    def _save_and_reload(self):
        """保存配置并热更新"""
        try:
            self._save_config()
        except Exception as e:
            self.log(f"[错误] 配置更新失败: {str(e)}")

    def _save_config(self):
        """保存当前配置到文件"""
        config = {
            "gs232b": self._build_device_config("gs232b"),
            "pelco": self._build_device_config("pelco")
        }
        self._validate_config(config)

        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
        self.log("[系统] 配置已自动保存")

    def _build_device_config(self, device):
        """构建单个设备配置"""
        proto = getattr(self, f"{device}_protocol").get()
        config = {"protocol": "serial" if proto == "串口" else "tcp"}

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
        else:
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
        """验证配置有效性"""
        # 基础协议验证
        for device in ["gs232b", "pelco"]:
            if config[device]["protocol"] == "tcp":
                if not config[device]["tcp"].get("host"):
                    raise ValueError(f"{device} 需要绑定IP地址")
                if not 0 < config[device]["tcp"]["port"] <= 65535:
                    raise ValueError(f"{device} 端口号必须为1-65535")

        # 角度参数验证
        pelco_corr = config["pelco"]["angle_correction"]
        if not (-360 <= pelco_corr["azimuth_offset"] <= 360):
            raise ValueError("方位角偏移必须在±360度之间")
        if not (0 <= pelco_corr["initial_azimuth"] <= 360):
            raise ValueError("初始水平角必须在0-360度之间")
        if pelco_corr["min_elevation"] > pelco_corr["max_elevation"]:
            raise ValueError("最小俯仰角不能大于最大俯仰角")

    def _load_config_to_ui(self):
        """加载配置文件到界面"""
        config = self._load_config()

        # 加载GS232B配置
        self._load_protocol_config("gs232b", config["gs232b"])

        # 加载Pelco-D配置
        self._load_protocol_config("pelco", config["pelco"])
        if "angle_correction" in config["pelco"]:
            entries = getattr(self, "pelco_angle")
            correction = config["pelco"]["angle_correction"]
            for entry, value in zip(entries, correction.values()):
                entry.delete(0, tk.END)
                entry.insert(0, str(value))

    def _load_protocol_config(self, device, config):
        """加载协议配置到UI组件"""
        proto = config["protocol"]
        getattr(self, f"{device}_protocol").set("串口" if proto == "serial" else "TCP")

        if proto == "serial":
            serial_port, baudrate = getattr(self, f"{device}_serial")
            serial_port.set(config["serial"]["port"])
            baudrate.set(str(config["serial"]["baudrate"]))
        else:
            host, port = getattr(self, f"{device}_tcp")
            host.delete(0, tk.END)
            host.insert(0, config["tcp"]["host"])
            port.delete(0, tk.END)
            port.insert(0, str(config["tcp"]["port"]))

    # 日志处理相关方法
    def log(self, message: str):
        """日志记录"""
        self.log_queue.put(message)

    def _process_log_queue(self):
        """处理日志队列"""
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_area.configure(state=tk.NORMAL)

            # 根据日志级别着色
            tag = "info"
            if "[错误]" in msg:
                tag = "error"
                self.log_area.tag_config("error", foreground="red")
            elif "[警告]" in msg:
                tag = "warning"
                self.log_area.tag_config("warning", foreground="orange")
            else:
                self.log_area.tag_config("info", foreground="green")

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
                config = self._load_config()
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

    def _load_config(self):
        """加载并验证配置文件"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            self._validate_config(config)
            return config
        except Exception as e:
            self.log(f"[错误] 配置加载失败: {str(e)}，使用默认配置")
            return self._get_default_config()

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

    def run(self):
        """启动主循环"""
        self.root.mainloop()


if __name__ == "__main__":
    app = MainWindow()
    app.run()