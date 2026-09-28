# 深空巡航助手 - APK 构建指南

## 方案概述

由于 Windows 上无法直接运行 buildozer（需要 Linux 环境），本项目提供以下构建方案：

### 方案 1：GitHub Actions 自动构建（推荐）

无需本地环境，代码推送到 GitHub 后自动构建 APK。

### 方案 2：本地 Linux 虚拟机/Docker 构建

### 方案 3：使用 WSL2（需要安装）

---

## 方案 1：GitHub Actions 自动构建

### 步骤 1：创建 GitHub 仓库

```bash
cd shenkong_apk
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/shenkong-assistant.git
git push -u origin main
```

### 步骤 2：添加 GitHub Actions 工作流

创建 `.github/workflows/build.yml`：

```yaml
name: Build Android APK

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install system dependencies
      run: |
        sudo apt-get update
        sudo apt-get install -y \
          build-essential \
          git \
          ffmpeg \
          libsdl2-dev \
          libsdl2-image-dev \
          libsdl2-mixer-dev \
          libsdl2-ttf-dev \
          libportmidi-dev \
          libswscale-dev \
          libavformat-dev \
          libavcodec-dev \
          zlib1g-dev \
          libgstreamer1.0-0 \
          gstreamer1.0-plugins-base \
          gstreamer1.0-plugins-good
    
    - name: Install buildozer
      run: |
        pip install buildozer cython==0.29.36
    
    - name: Build APK
      run: |
        buildozer android debug
      env:
        BUILDOZER_LOG_LEVEL: 2
    
    - name: Upload APK
      uses: actions/upload-artifact@v3
      with:
        name: shenkong-apk
        path: bin/*.apk
```

### 步骤 3：获取 APK

推送代码后，在 GitHub 仓库的 Actions 标签页下载构建好的 APK。

---

## 方案 2：本地 Docker 构建

### 前提条件

- 安装 Docker Desktop for Windows

### 构建步骤

```bash
# 进入项目目录
cd shenkong_apk

# 使用 Kivy 官方 Docker 镜像构建
docker run --rm -v ${PWD}:/home/user/hostcwd kivy/buildozer android debug
```

或者创建 `Dockerfile`：

```dockerfile
FROM kivy/buildozer:latest

WORKDIR /app
COPY . /app

RUN buildozer android debug

CMD ["cp", "bin/*.apk", "/output/"]
```

构建命令：
```bash
docker build -t shenkong-builder .
docker run --rm -v ${PWD}/output:/output shenkong-builder
```

---

## 方案 3：WSL2 构建

### 步骤 1：安装 WSL2

```powershell
wsl --install
```

重启电脑后，设置 Ubuntu 用户名密码。

### 步骤 2：在 WSL2 中构建

```bash
# 进入 WSL2
wsl

# 安装依赖
sudo apt-get update
sudo apt-get install -y python3-pip build-essential git

# 安装 buildozer
pip3 install buildozer cython==0.29.36

# 进入项目目录（Windows 的 D 盘挂载在 /mnt/d）
cd /mnt/d/chajian/chajian/shenkong_apk

# 构建 APK
buildozer android debug
```

构建完成后，APK 文件在 `bin/` 目录下。

---

## 方案 4：手动修改代码（无需完整 APK）

如果只需要在模拟器上运行，可以不打包 APK，直接使用模拟器的 Python 环境：

### 使用 Termux + Python

1. 在模拟器中安装 Termux
2. 安装 Python：`pkg install python`
3. 安装依赖：`pip install opencv-python numpy`
4. 复制代码到 Termux
5. 运行：`python main.py --mode daily_tasks`

---

## 代码适配说明

### 需要修改的文件

1. **vision.py** - 移除 Windows OCR，改用其他 OCR 方案或禁用 OCR 功能
2. **adb.py** - 在 Android 上使用无障碍服务替代 ADB
3. **main.py** - 适配 Android 环境

### 关键修改点

#### 1. 禁用 Windows OCR

```python
# vision.py 中的 ocr 方法
def ocr(self, img, region=None):
    if ANDROID_AVAILABLE:
        # Android 上使用其他 OCR 方案
        return ""
    else:
        # Windows OCR
        ...
```

#### 2. 使用无障碍服务

创建 `android_accessibility.py`：

```python
from jnius import autoclass

class AccessibilityController:
    def __init__(self):
        self.service = None
    
    def tap(self, x, y):
        # 通过无障碍服务点击
        pass
    
    def swipe(self, x1, y1, x2, y2, duration):
        # 通过无障碍服务滑动
        pass
```

---

## 注意事项

1. **OpenCV 编译**：在 Android 上编译 OpenCV 需要较长时间（约 30-60 分钟）
2. **权限问题**：Android 需要申请悬浮窗和无障碍服务权限
3. **性能问题**：Android 设备性能可能不如 PC，需要调整截图频率
4. **分辨率适配**：不同设备分辨率不同，需要适配 rules.json 中的坐标

---

## 测试 APK

构建完成后，将 APK 安装到模拟器：

```bash
adb install bin/shenkong-1.0.0-debug.apk
```

或者直接在模拟器中拖拽 APK 文件安装。

---

## 故障排除

### 问题：buildozer 找不到 SDK/NDK

解决方案：
```bash
buildozer android update
```

### 问题：OpenCV 编译失败

解决方案：使用预编译的 OpenCV 或禁用需要 OpenCV 的功能

### 问题：APK 闪退

查看日志：
```bash
adb logcat | grep python
```
