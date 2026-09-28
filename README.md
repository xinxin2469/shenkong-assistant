# 深空巡航助手 - 快速开始

## 项目结构

```
shenkong_apk/
├── .github/workflows/    # GitHub Actions 自动构建
├── main.py               # 原始入口（PC/ADB 版）
├── main_android.py       # Android 入口（APK 版）
├── adb.py                # ADB 通信层
├── vision.py             # 视觉识别层
├── engine.py             # 脚本引擎
├── daily_tasks.py        # 日常任务引擎
├── laser_maze.py         # 激光迷宫
├── meteor_trap.py        # 陨石陷阱
├── missile_field.py      # 导弹猎场
├── equip_enhance.py      # 装备强化
├── ad_manager.py         # 广告管理
├── base_engine.py        # 基础引擎
├── realtime.py           # 实时控制
├── rules.json            # 游戏规则配置
├── buildozer.spec        # APK 构建配置
└── BUILD_GUIDE.md        # 详细构建指南
```

## 快速构建 APK

### 方法 1：GitHub Actions（最简单）

1. 将 `shenkong_apk` 目录推送到 GitHub 仓库
2. GitHub Actions 自动构建
3. 在 Actions 页面下载 APK

### 方法 2：本地 Docker（需要 Docker）

```bash
cd shenkong_apk
docker run --rm -v ${PWD}:/home/user/hostcwd kivy/buildozer android debug
```

### 方法 3：WSL2（需要 WSL2）

```bash
wsl
cd /mnt/d/chajian/chajian/shenkong_apk
pip install buildozer cython==0.29.36
buildozer android debug
```

## 重要说明

### 当前限制

由于 Windows 上无法直接运行 buildozer，且本项目依赖 OpenCV（需要编译），
**直接打包 APK 需要 Linux 环境**。

### 推荐方案

**使用 GitHub Actions 自动构建**：
1. 将代码推送到 GitHub
2. Actions 自动在 Ubuntu 上构建
3. 下载构建好的 APK
4. 安装到模拟器

### 替代方案：不打包 APK

如果只需要在模拟器上运行，可以不打包 APK：

1. 在模拟器中安装 **Termux**
2. `pkg install python`
3. `pip install opencv-python numpy`
4. 复制代码到 Termux
5. `python main.py --mode daily_tasks`

## 功能说明

### 支持的游戏模式

- **daily_tasks**: 日常任务（签到/领奖/商城/寻宝/扫荡等）
- **laser_maze**: 激光迷宫（自动躲避激光束）
- **meteor_trap**: 陨石陷阱（自动打击陨石+复活）
- **missile_field**: 导弹猎场（自动拦截导弹）
- **equip_enhance**: 装备强化（自动强化4个部位）

### 使用方法

```bash
# 日常任务
python main.py --mode daily_tasks --timeout 1800

# 激光迷宫
python main.py --mode laser_maze --timeout 120

# 陨石陷阱
python main.py --mode meteor_trap

# 装备强化
python main.py --mode equip_enhance
```

## 技术架构

```
┌─────────────────┐
│   用户界面层     │  ← main.py / main_android.py
├─────────────────┤
│   游戏引擎层     │  ← daily_tasks.py / laser_maze.py / ...
├─────────────────┤
│   脚本引擎层     │  ← engine.py
├─────────────────┤
│   视觉识别层     │  ← vision.py (OpenCV + OCR)
├─────────────────┤
│   设备控制层     │  ← adb.py (ADB / 无障碍服务)
└─────────────────┘
```

## 常见问题

### Q: 为什么 Windows 上不能直接构建？

A: buildozer 依赖 Linux 工具链（gcc、make 等），Windows 不支持。

### Q: APK 构建需要多长时间？

A: 首次构建约 30-60 分钟（需要下载 SDK/NDK 和编译 OpenCV），后续构建约 5-10 分钟。

### Q: 如何修改游戏配置？

A: 编辑 `rules.json` 文件，修改坐标、颜色等参数。

### Q: APK 闪退怎么办？

A: 查看日志：
```bash
adb logcat | grep python
```

## 联系

如有问题，请查看 `BUILD_GUIDE.md` 获取详细构建指南。
