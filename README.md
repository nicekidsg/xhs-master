# 小红书内容生成与定时发布系统

本项目是一个本地 Web 控制台，面向 AI/效率工具赛道，串起热点、主题、图文文案、短视频脚本、素材、审核、排期和小红书创作服务平台发布准备。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。

## 第一版流程

1. 在工作台刷新默认公开热点，或手动补充小红书站内观察。
2. 进入“新建主题”，输入核心主题，选择热点，生成图文文案和短视频脚本。
3. 在审核页生成 3:4 图文素材和 9:16 短视频分镜包。
4. 审核通过后创建排期，默认是 `20:30 Asia/Shanghai`。
5. 在发布准备页启动浏览器自动化。系统会打开小红书创作服务平台并尝试填入内容，停在最终确认前。

## 重要边界

- 不使用小红书非官方逆向接口。
- 不保存小红书账号密码；登录态只保存在本地 Playwright browser profile。
- 没有 OpenAI 密钥时使用本地 mock Provider，方便先跑通运营流程。
- 短视频第一版生成分镜帧、字幕和发布包；安装视频渲染链路后可升级为 MP4。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

