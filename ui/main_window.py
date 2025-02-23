# ui/main_window.py
# Copyright © 2025 Sharkbia
# MIT License - See LICENSE for details
import queue
import tkinter as tk
import ttkbootstrap as ttkb
import serial.tools.list_ports
from tkinter import messagebox
from ttkbootstrap.constants import *
from core.controller import ControlSystem


class MainWindow:
    def __init__(self):
        # 初始化ttkbootstrap窗口
        self.root = ttkb.Window()
        self.root.title("PTZ 云台控制系统")
        self.root.geometry("300x700")
        self.root.resizable(False, False)

        # 初始化变量
        self.control_system = None
        self.running = False
        self.log_queue = queue.Queue()

        # 创建界面
        self._create_widgets()
        self._setup_logging()
        self.root.after(100, self._process_log_queue)

    def _create_widgets(self):
        # 主框架采用左右分栏布局
        main_frame = ttkb.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ------------------ 设备配置区域 ------------------
        config_frame = ttkb.Labelframe(main_frame, text="设备配置", bootstyle=INFO)
        config_frame.pack(fill=tk.X, pady=5)

        # GS-232B 配置
        self._create_device_config(config_frame, "gs232b", 0)
        # Pelco-D 配置
        self._create_device_config(config_frame, "pelco", 1)

        # ------------------ 控制按钮区域 ------------------
        btn_frame = ttkb.Frame(main_frame)
        btn_frame.pack(pady=10)

        # 启动/停止按钮
        self.start_btn = ttkb.Button(
            btn_frame,
            text="启动系统",
            command=self.toggle_system,
            width=15,
            bootstyle=(SUCCESS, OUTLINE)
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        # 清除日志按钮
        ttkb.Button(
            btn_frame,
            text="清除日志",
            command=self.clear_log,
            width=15,
            bootstyle=(WARNING, OUTLINE)
        ).pack(side=tk.LEFT, padx=5)

        # ------------------ 日志区域 ------------------
        log_frame = ttkb.Labelframe(
            main_frame,
            text="系统日志",
            bootstyle=INFO
        )
        log_frame.pack(fill=tk.BOTH, expand=True)

        # 日志文本框
        self.log_area = tk.Text(
            log_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=('微软雅黑', 10),
            bg='#f8f9fa',  # 背景色匹配主题
            relief=FLAT
        )
        # 滚动条
        scrollbar = ttkb.Scrollbar(
            log_frame,
            command=self.log_area.yview,
            bootstyle=ROUND
        )
        self.log_area.configure(yscrollcommand=scrollbar.set)
        self.log_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _create_device_config(self, parent, device, row):
        """创建设备配置面板"""
        frame = ttkb.Labelframe(
            parent,
            text=f"{device.upper()} 配置",
            bootstyle=INFO
        )
        frame.grid(row=row, column=0, sticky="ew", padx=5, pady=5)

        # 协议选择
        ttkb.Label(frame, text="通信协议:", bootstyle=PRIMARY).grid(row=0, column=0, sticky="w", padx=5)
        protocol = ttkb.Combobox(
            frame,
            values=["串口", "TCP", "UDP"],
            state="readonly",
            bootstyle=INFO
        )
        protocol.grid(row=0, column=1, sticky="ew", padx=5)
        protocol.set("串口")
        setattr(self, f"{device}_protocol", protocol)

        # 参数选项卡
        self._create_parameter_notebook(frame, device)

    def _create_parameter_notebook(self, parent, device):
        """创建协议参数选项卡"""
        notebook = ttkb.Notebook(parent, bootstyle=INFO)
        notebook.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)

        # ------------------ 串口配置 ------------------
        serial_frame = ttkb.Frame(notebook)
        # 串口号选择
        ttkb.Label(serial_frame, text="串口号:", bootstyle=PRIMARY).grid(row=0, column=0, padx=5, pady=2)
        serial_port = ttkb.Combobox(
            serial_frame,
            state="readonly",
            bootstyle=INFO
        )
        serial_port.grid(row=0, column=1, padx=5)
        serial_port.bind("<Button-1>", lambda e: self._update_serial_ports(serial_port))
        # 波特率选择
        ttkb.Label(serial_frame, text="波特率:", bootstyle=PRIMARY).grid(row=1, column=0, padx=5, pady=2)
        baudrate = ttkb.Combobox(
            serial_frame,
            values=["9600", "19200", "38400", "115200"],
            state="readonly",
            bootstyle=INFO
        )
        baudrate.grid(row=1, column=1, padx=5)
        notebook.add(serial_frame, text="串口参数")
        setattr(self, f"{device}_serial", (serial_port, baudrate))

        # ------------------ TCP配置 ------------------
        tcp_frame = ttkb.Frame(notebook)
        ttkb.Label(tcp_frame, text="主机地址:", bootstyle=PRIMARY).grid(row=0, column=0, padx=5, pady=2)
        tcp_host = ttkb.Entry(tcp_frame, bootstyle=INFO)
        tcp_host.grid(row=0, column=1, padx=5)
        ttkb.Label(tcp_frame, text="端口号:", bootstyle=PRIMARY).grid(row=1, column=0, padx=5, pady=2)
        tcp_port = ttkb.Entry(tcp_frame, bootstyle=INFO)
        tcp_port.grid(row=1, column=1, padx=5)
        notebook.add(tcp_frame, text="TCP参数")
        setattr(self, f"{device}_tcp", (tcp_host, tcp_port))

        # ------------------ UDP配置 ------------------
        udp_frame = ttkb.Frame(notebook)
        ttkb.Label(udp_frame, text="IP地址:", bootstyle=PRIMARY).grid(row=0, column=0, padx=5, pady=2)
        udp_host = ttkb.Entry(udp_frame, bootstyle=INFO)
        udp_host.grid(row=0, column=1, padx=5)
        ttkb.Label(udp_frame, text="端口号:", bootstyle=PRIMARY).grid(row=1, column=0, padx=5, pady=2)
        udp_port = ttkb.Entry(udp_frame, bootstyle=INFO)
        udp_port.grid(row=1, column=1, padx=5)
        notebook.add(udp_frame, text="UDP参数")
        setattr(self, f"{device}_udp", (udp_host, udp_port))

    def _setup_logging(self):
        """初始化日志"""
        self.log("系统初始化完成")

    def log(self, message: str):
        """日志记录"""
        self.log_queue.put(message)

    def _process_log_queue(self):
        """处理日志队列"""
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_area.configure(state=tk.NORMAL)

            # 根据日志级别着色
            if "[错误]" in msg:
                tag = "error"
                self.log_area.tag_config("error", foreground="red")
            elif "[警告]" in msg:
                tag = "warning"
                self.log_area.tag_config("warning", foreground="orange")
            else:
                tag = "info"
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

    def toggle_system(self):
        """启停系统"""
        if not self.running:
            try:
                config = self._get_config()
                self.control_system = ControlSystem(config, self.log)
                self.control_system.start()
                self.running = True
                self.start_btn.config(text="停止系统")
                self.log("[系统] 系统启动成功")
            except Exception as e:
                messagebox.showerror("错误", f"系统启动失败：{str(e)}")
        else:
            if self.control_system:
                self.control_system.stop()
                self.control_system = None
            self.running = False
            self.start_btn.config(text="启动系统")
            self.log("[系统] 系统已安全停止")

    def _get_config(self):
        """获取所有设备配置"""
        return {
            "gs232b": self._get_device_config("gs232b"),
            "pelco": self._get_device_config("pelco")
        }

    def _get_device_config(self, device):
        """获取单个设备配置"""
        protocol = getattr(self, f"{device}_protocol").get()
        protocol_map = {
            "串口": "serial",
            "TCP": "tcp",
            "UDP": "udp"
        }
        config = {"protocol": protocol_map[protocol]}

        if protocol == "串口":
            port_combobox, baud_combobox = getattr(self, f"{device}_serial")
            selected_port = port_combobox.get()
            selected_baud = baud_combobox.get()

            if selected_port == "无可用串口":
                raise ValueError("未检测到可用串口设备")

            config["serial"] = {
                "port": selected_port,
                "baudrate": int(selected_baud)
            }
        elif protocol == "TCP":
            host, port = getattr(self, f"{device}_tcp")
            config["tcp"] = {
                "host": host.get(),
                "port": int(port.get())
            }
        elif protocol == "UDP":
            local, remote = getattr(self, f"{device}_udp")
            config["udp"] = {
                "host": "0.0.0.0",
                "port": int(local.get()),
                "remote_host": "127.0.0.1",
                "remote_port": int(remote.get())
            }
        return config

    def _validate_config(self, config):
        """验证配置有效性"""
        for device in ["gs232b", "pelco"]:
            proto = config[device]["protocol"]
            if proto == "serial" and not config[device]["serial"]["port"]:
                raise ValueError(f"{device} 必须配置串口号")
            if proto in ["tcp", "udp"] and not config[device][proto]["port"]:
                raise ValueError(f"{device} 必须配置端口号")

    def _update_serial_ports(self, combobox):
        """动态刷新串口列表"""
        try:
            ports = serial.tools.list_ports.comports()
            port_list = [port.device for port in ports]
            combobox["values"] = port_list
            if not port_list:
                combobox.set("无可用串口")
            elif not combobox.get():
                combobox.set(port_list[0])
        except Exception as e:
            messagebox.showerror("错误", f"获取串口列表失败：{str(e)}")

    def run(self):
        """启动主循环"""
        self.root.mainloop()


if __name__ == "__main__":
    app = MainWindow()
    app.run()