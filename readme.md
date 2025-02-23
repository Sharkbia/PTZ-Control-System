# PTZ 云台控制系统

[![License: MIT](https://img.shields.io/badge/许可证-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 项目描述
基于 Python 的 PTZ 云台控制系统，支持通过串口、TCP、UDP 协议，以 GS-232 协议控制 Pelco-D 云台

## 功能特性
- 图形化配置界面 (ttkbootstrap)
- 多协议支持：串口/TCP/UDP
- 实时命令解析与响应
- 分级日志系统（信息/警告/错误）
- 插件式架构，低耦合设计，易于扩展
- 串口设备自动检测

## 项目结构
```
PTZ-Control-System/
├── core/
│   ├── controller.py      # 核心控制逻辑
│   └── protocols.py       # 协议解析实现
├── hardware/
│   └── interfaces.py      # 硬件通信接口
├── ui/
│   └── main_window.py     # 图形界面实现
├── main.py                # 程序入口
├── requirements.txt       # 依赖清单
└── LICENSE                # 开源协议文件
```

## 快速开始
### 环境要求
- Python 3.8+
- Windows/macOS/Linux

### 克隆仓库
```bash
git clone https://github.com/yourname/PTZ-Control-System.git
```

### 安装依赖
```bash
pip install -r requirements.txt
```

### 启动程序
```bash
python main.py
```

## 使用说明
1. **设备配置**
   - 选择通信协议（串口/TCP/UDP）
   - 填写对应参数：
     - 串口：选择端口号与波特率
     - TCP：填写主机地址和端口号
     - UDP：填写本地端口和远程地址

2. **系统操作**
   - 🟢 <kbd>启动系统</kbd>：初始化硬件连接
   - 🔴 <kbd>停止系统</kbd>：安全断开连接
   - 🧹 <kbd>清除日志</kbd>：一键清空日志窗口

3. **日志系统**
   - 🟢 绿色：普通信息消息
   - 🟠 橙色：警告提示消息
   - 🔴 红色：关键错误信息

## 开源协议
本项目采用 [MIT 许可证](LICENSE)，核心条款包括：
- 允许自由使用、复制、修改、合并、发布
- 保留版权声明和许可声明
- 不承担任何担保责任

## 技术支持
✉️ 联系方式：bg4itd@lhw711.cn  
🐛 问题反馈：https://github.com/Sharkbia/PTZ-Control-System/issues