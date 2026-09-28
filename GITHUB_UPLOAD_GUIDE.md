# 深空巡航助手 - GitHub 上传指南

## 手动上传步骤

### 步骤 1：创建 GitHub 仓库

1. 访问 https://github.com/new
2. 填写仓库信息：
   - Repository name: `shenkong-assistant`
   - Description: `雷霆战机自动化助手`
   - 选择 Public 或 Private
3. **不要**勾选 "Initialize this repository with a README"
4. 点击 "Create repository"

### 步骤 2：上传代码

#### 方法 A：使用 GitHub 网页上传

1. 解压 `shenkong_apk.zip` 文件
2. 在仓库页面点击 "uploading an existing file"
3. 将所有文件拖拽到上传区域
4. 点击 "Commit changes"

#### 方法 B：使用 GitHub Desktop

1. 打开 GitHub Desktop
2. 点击 "File" → "Add local repository"
3. 选择 `D:\chajian\chajian\shenkong_apk` 文件夹
4. 点击 "Publish repository"
5. 填写仓库名称并发布

#### 方法 C：使用 Git 命令行（需要网络）

```bash
cd D:\chajian\chajian\shenkong_apk
git remote add origin https://github.com/YOUR_USERNAME/shenkong-assistant.git
git branch -M main
git push -u origin main
```

### 步骤 3：启用 GitHub Actions

1. 在仓库页面点击 "Actions" 标签
2. 如果提示启用 Actions，点击 "I understand my workflows, go ahead and enable them"
3. 找到 "Build Android APK" workflow
4. 点击 "Run workflow" 手动触发构建

### 步骤 4：下载 APK

1. 等待构建完成（约 30-60 分钟）
2. 点击构建任务
3. 在 "Artifacts" 区域下载 `shenkong-apk`

---

## 网络问题解决方案

如果无法访问 GitHub：

### 方案 1：使用代理

```bash
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890
```

### 方案 2：使用 Gitee 镜像

1. 在 https://gitee.com 创建仓库
2. 使用 Gitee 的 GitHub 导入功能
3. 或使用 Gitee Go（类似 GitHub Actions）

### 方案 3：本地构建

使用 Docker 或 WSL2 在本地构建 APK，详见 BUILD_GUIDE.md

---

## 文件清单

- `main.py` - 原始入口（PC/ADB 版）
- `main_android.py` - Android 入口
- `adb.py` - ADB 通信层
- `vision.py` - 视觉识别层
- `engine.py` - 脚本引擎
- `daily_tasks.py` - 日常任务
- `laser_maze.py` - 激光迷宫
- `meteor_trap.py` - 陨石陷阱
- `missile_field.py` - 导弹猎场
- `equip_enhance.py` - 装备强化
- `ad_manager.py` - 广告管理
- `base_engine.py` - 基础引擎
- `realtime.py` - 实时控制
- `rules.json` - 游戏规则配置
- `buildozer.spec` - APK 构建配置
- `.github/workflows/build.yml` - GitHub Actions 配置

---

## 下一步

1. 上传代码到 GitHub
2. 等待 GitHub Actions 构建完成
3. 下载 APK 并安装到模拟器
4. 测试运行

如有问题，请查看 BUILD_GUIDE.md 或联系开发者。
