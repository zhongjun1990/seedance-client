# Seedance 2.0 Desktop App

火山引擎 Seedance 2.0 AI 视频生成桌面工具

## 功能特性

- 🔐 火山引擎身份认证
- ✏️ 文字生成视频
- 🖼️ 图片生成视频
- 🎵 音频参考
- 📐 多种视频比例（16:9 / 9:16 / 1:1）
- ⏱️ 多种时长（6秒 / 10秒）
- 🌐 跨平台支持（Windows / macOS / Linux）

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py

# 打开浏览器访问
# http://localhost:5173
```

## 获取 API Key

1. 访问 [火山引擎控制台](https://console.volcengine.com/visual)
2. 创建 Visual 服务
3. 获取 Access Key 和 Secret Key

## 下载桌面应用

从 [Releases](https://github.com/YOUR_USERNAME/seedance-client/releases) 下载：

- **Windows**: `Seedance2-Windows.exe`
- **macOS**: `Seedance2-macOS.dmg`

## 技术栈

- 后端: Flask + Python
- 前端: Tailwind CSS + 原生 JavaScript
- 打包: PyInstaller
