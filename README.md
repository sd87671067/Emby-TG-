# Emby + Telegram 用户管理容器项目

这是一个面向 **Debian / Docker** 的轻量项目，用于：

- 对接 Emby Server API，管理 Emby 用户
- 提供 **管理员 1 号 Telegram Bot**
- 提供 **客户端 2 号 Telegram Bot**
- 使用 **SQLite + WAL** 保存本地用户信息、注册码、到期时间
- 不提供对外 Web 面板，默认只使用两个 Telegram 机器人
- 所有 Emby 操作都走 **HTTP API**，不直接碰 Emby 数据库，避免锁库

## 重要说明

### 1) 不能从 Emby 反向读出明文密码
Emby API 可创建用户、删除用户、改密码、查询用户和会话，但不会返回用户明文密码。  
因此“从 Emby 导入到本地”只能导入 **用户名 / 状态 / 最近活动**，密码会在本地标记为未知。  
如果你需要把本地密码同步回 Emby，本项目支持。

### 2) 模板用户
新注册账号的权限和模板用户 `EMBY_TEMPLATE_USER=testone` 一样。  
项目会在创建新用户后，复制模板用户的 **Policy + Configuration**。

### 3) Telegram 菜单
Telegram 原生 Bot 菜单样式受 Telegram 客户端限制，不能完全自定义成 App Store UI。  
本项目只保留 Telegram Bot 菜单，不再开放对外 Web 面板。

---

## 目录结构

```text
.
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── quick_start.sh
└── app
    ├── main.py
    ├── config.py
    ├── db.py
    ├── models.py
    ├── security.py
    ├── logging_setup.py
    ├── emby.py
    ├── services
    ├── bots
    └── web  # 目录保留，但默认不对外启用
```

## 一键部署命令

### 方式一：Git 直接拉取并部署

```bash
bash -c '
set -Eeuo pipefail
REPO_URL="https://github.com/sd87671067/Emby-TG-.git"
BASE_DIR="/opt/emby_tg_admin"
APP_DIR="$BASE_DIR/Emby-TG-"

if ! command -v git >/dev/null 2>&1; then
  apt-get update && apt-get install -y git
fi

mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
[ -f .env ] || cp .env.example .env

if command -v nano >/dev/null 2>&1; then
  nano .env
else
  vi .env
fi

docker compose up -d --build
docker logs --tail 120 emby_tg_admin || docker compose logs --tail 120
'
```

### 方式二：下载 GitHub 打包文件并解压到本地

```bash
mkdir -p /opt/emby_tg_admin && cd /opt/emby_tg_admin
curl -L -o Emby-TG-main.tar.gz https://codeload.github.com/sd87671067/Emby-TG-/tar.gz/refs/heads/main
tar -xzf Emby-TG-main.tar.gz
mv Emby-TG--main Emby-TG-
cd Emby-TG-
cp .env.example .env
nano .env
docker compose up -d --build
docker logs --tail 120 emby_tg_admin
```

## 首次检查

- 查看容器日志里是否出现：
  - `Emby API Key 校验成功`
  - `管理员机器人 Token 校验成功`
  - `客户端机器人 Token 校验成功`

## 查询更新 / 再次部署

```bash
cd /opt/emby_tg_admin/Emby-TG-
git pull --ff-only
docker compose up -d --build
docker logs --tail 120 emby_tg_admin
```

## 环境变量

复制示例文件并自行填写：

```bash
cp .env.example .env
```

至少要修改这些：

- `EMBY_BASE_URL`
- `EMBY_API_KEY`
- `EMBY_SERVER_PUBLIC_URL`
- `ADMIN_BOT_TOKEN`
- `ADMIN_CHAT_IDS`
- `CLIENT_BOT_TOKEN`
- `ADMIN_CONTACT_TG_USERNAME` / `ADMIN_CONTACT_TG_USER_ID`
- `APP_MASTER_KEY`

## 管理员 Bot 功能

- 🧩 生成注册码/续期码
- 📦 查询注册码库存（显示码值 + 有效期）
- 🗑️ 清空注册码库存
- 🔄 同步 Emby 到本地（本地多余账号会删除，本地默认密码统一写成 1234）
- ⬆️ 同步本地用户到 Emby（慢速串行导入，避免 Emby 锁库；同名账号自动跳过）
- 👥 查询有效账号（按到期时间排序，支持分页）
- ❌ 删除用户
- ⏳ 修改用户到期时间
- 📱 查询登录设备/IP
- ▶️ 查询在线播放人数
- ⏰ 账号过期自动删除并通知管理员
![IMG_8835](https://github.com/sd87671067/picx-images-hosting/raw/master/IMG_8835.4clhcpmf9f.jpeg)
## 客户端 Bot 功能

- 📝 注册账号
- 🎟️ 使用注册码/续期码
- 👤 我的账号
- ▶️ 在线播放人数
- 📞 联系管理员
- 账号到期前 3 天自动提醒一次
- 注册成功 / 续期成功后通知管理员机器人
![IMG_8836](https://github.com/sd87671067/picx-images-hosting/raw/master/IMG_8836.6t7prmtjsd.jpeg)
## 最新修复

### v14
- 修复：客户端注册成功 / 续期成功后的通知错误发给客户端 Bot，而不是管理员 Bot
- 现在统一改为：通知通过 **管理员 Bot** 发给管理员

### v13
- 修复：客户端已有账号时，再点“注册账号”不会进入注册码流程，而是直接提示“您已经存在一个有效账号”
- 优化：本地用户导入 Emby 改为慢速串行导入
- 优化：与 Emby 同名账号自动跳过
- 导入完成后会显示导入成功账号名、跳过账号名和总数量

## 隐私与去敏说明

仓库中的 `.env.example` 已经替换为占位符示例，不包含任何真实的：

- Emby 服务器地址
- Emby API Key
- Telegram Bot Token
- 管理员 Telegram ID / 用户名
- 其他私密配置

## 资源建议

1c2g 完全足够跑这个项目，打赏一下，老板请我喝杯咖啡吗
![IMG_8831](https://github.com/sd87671067/picx-images-hosting/raw/master/IMG_8831.362632xhlz.jpeg)

