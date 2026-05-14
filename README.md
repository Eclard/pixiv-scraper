# Pixiv 图片爬虫

从 Pixiv 集中爬取符合指定条件的图片，按标签分类存储。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

编辑 `config.yaml`：

```yaml
pixiv:
  cookies:
    session_id: "YOUR_SESSION_ID"  # 从浏览器获取
  # 或使用 refresh_token
  # refresh_token: "YOUR_REFRESH_TOKEN"

scraper:
  tags:
    - "illust"
    - "anime"
  ranked:
    enabled: true
    mode: "daily"
    content: "all"
  artists: []
  bookmarks_min: 500
  limit: 100

download:
  root_dir: "images"
  priority:
    - "original"
    - "large"
    - "medium"
```

## 使用

```bash
python pixiv_scraper.py
```

## 获取 Cookie

1. 在浏览器登录 [Pixiv](https://www.pixiv.net)
2. 打开开发者工具 (F12) → Network 标签
3. 刷新页面，找到任意请求
4. 在请求头中复制 `cookie` 字段
5. 提取其中的 `PHPSESSID` 或 `session_id` 值填入配置

## 输出结构

```
images/
├── illust/
│   ├── 12345_67890_作品名.jpg
│   └── ...
├── anime/
│   └── ...
└── ...

downloaded_ids.json  # 已下载 ID 记录
```

## 配置说明

| 参数 | 说明 |
|------|------|
| `tags` | 搜索标签，OR 逻辑 |
| `ranked.enabled` | 是否启用排行榜 |
| `ranked.content` | `all` / `r18` |
| `bookmarks_min` | 最低收藏数 |
| `limit` | 最大下载数量 |
| `priority` | 图片规格优先级 |
