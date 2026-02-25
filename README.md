Lyria Bear 结合了生物传感器、硬件交互和前沿的 AI 音乐生成。

# 🤖 Lyria Bear: Interactive AI Music Robot

**Lyria Bear** 是一款交互式情感机器人。它通过感知用户的**心率变异性 (HRV)**、**肢体晃动**以及**环境光信号**，动态调整自身状态，并利用 Google Gemini Lyria 模型实时生成 AI 音乐，实现人类与机器之间的情感共鸣。

## ✨ 核心功能

* **生物感官**：通过 MAX30102 实时监测用户心跳数据。
* **物理交互**：内置 MPU6050 陀螺仪，感知用户的触摸与摇晃。
* **环境适应**：利用 VEML 传感器感知光照，改变机器人情绪。
* **AI 音乐生成**：基于传感器数据，通过 Gemini Lyria 模型实时创作音乐。
* **视听反馈**：通过 LED 灯带和蓝牙音箱提供沉浸式反馈。

## 🛠️ 硬件清单 (Bill of Materials)

| 组件名称 | 数量 | 参考链接 |
| --- | --- | --- |
| **ESP32 开发板** | 2 | [购买链接](https://www.google.com/search?q=https://item.taobao.com/item.htm%3Fid%3D963968745443) |
| **MAX30102 心率传感器** | 1 | [购买链接](https://www.google.com/search?q=https://item.taobao.com/item.htm%3Fid%3D586401173804) |
| **MPU6050 陀螺仪** | 1 | [购买链接](https://www.google.com/search?q=https://detail.tmall.com/item.htm%3Fid%3D785018191645) |
| **VEML 环境光传感器** | 1 | [购买链接](https://www.google.com/search?q=https://item.taobao.com/item.htm%3Fid%3D683399758793) |
| **WS2812B LED 灯带** | 1 | [购买链接](https://www.google.com/search?q=https://item.taobao.com/item.htm%3Fid%3D916133697114) |
| **SG90 舵机** | 2 | [购买链接](https://www.google.com/search?q=https://detail.tmall.com/item.htm%3Fid%3D678498890304) |
| **蓝牙音频芯片 & 喇叭** | 1套 | [芯片链接](https://www.google.com/search?q=https://item.taobao.com/item.htm%3Fid%3D940590581369) / [喇叭链接](https://www.google.com/search?q=https://item.taobao.com/item.htm%3Fid%3D850286278451) |

> **提示**：此外还需要准备杜邦线、焊接工具及充电宝/电源。

---

## 🚀 快速开始

### 1. 环境准备

* **硬件端**：安装 Arduino IDE，并配置 ESP32 开发环境。
* **软件端**：安装 **PyCharm Pro 3.12** 或更高版本。
* **网络环境**：需要全球模式的 VPN（建议节点：美国），确保能访问 Google AI 服务。

### 2. 获取 API Key

本项目使用 **Gemini Lyria** 模型进行音乐生成：

1. 访问 [Google AI Studio](https://ai.google.dev/gemini-api/docs/api-key)。
2. 导入或创建一个 Google Cloud 项目。
3. 生成 API Key 并将其填入 Python 代码中的 `API_KEY` 变量。

### 3. 配置与连接

在上传代码前，请务必修改以下配置：

* **WiFi 设置**：在两份 Arduino 代码中修改 `ssid` 和 `password` 为你的热点信息。
* **IP 地址绑定**：
* **ESP2 Host IP**：将 ESP2 连上 WiFi 后，从串口监视器查看其显示的 IP，填入 Python 代码。
* **Python Host**：将运行 Python 的电脑与 ESP 保持在同一 WiFi 下，并根据串口提示配置 IP。

* **arduino_esp** :这个才是用于运行的代码版本，记得创建虚拟环境，我的pycharm是pro版本

---

## 📸 项目展示
可以参考images和3D Model文件夹
