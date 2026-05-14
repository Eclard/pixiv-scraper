# Pixiv 图片爬虫设计规格

## 概述

一个 Python 脚本，通过 Pixiv API 集中爬取符合指定条件的图片，下载到本地并按标签分类存储。

## 功能需求

### 1. 登录认证
- 使用 `requests` + `requests.Session`
- 通过 cookie 或 Refresh Token 认证
- cookie 优先从配置文件读取 `cookies` 字典
- 支持刷新 token 维持会话

### 2. 搜索条件（YAML 配置）

```yaml
# config.yaml
pixiv:
  cookies:
    session_id: "your_session_id"
  # 或者用 refresh_token
  # refresh_token: "your_refresh_token"

scraper:
  # 标签条件（OR 逻辑，满足任一即下载）
  tags:
    - "illust"
    - "anime"
    - "美少女"
  
  # 排行榜选项
  ranked:
    enabled: true
    mode: "daily"      # daily / weekly / monthly / rookie / original
    content: "all"     # all / male / female / r18
    date: null         # null 表示最新，或 "20240115"
  
  # 画师列表（可选）
  artists:
    - "12345678"
  
  # 收藏数阈值（可选）
  bookmarks_min: 500
  
  # 作品数量上限
  limit: 100

download:
  # 图片规格优先级
  priority:
    - "original"      # 原图
    - "large"         # 大图
    - "medium"        # 中图
    - "square_medium"  # 缩略图
  
  # 存储根目录
  root_dir: "images"
  
  # 文件命名格式
  filename_format: "{artist_id}_{illust_id}_{title}"
  
  # 同一作品多标签处理：只存一份，放第一个匹配标签目录
  multi_tag_strategy: "first_match"

deduplication:
  # 已下载 ID 记录文件
  id_file: "downloaded_ids.json"
  
  # 双重去重：ID 记录 + 文件存在检查
  strategy: "both"
  
rate_limit:
  # 请求间隔（秒）
  delay: 3
  
  # 并发数（固定为 1，串行下载）
  concurrency: 1
```

### 3. 数据存储结构

```
images/
├── illust/
│   ├── 12345_67890_作品名.jpg
│   └── 12345_67891_另一个作品.jpg
├── anime/
│   └── 12345_67900_动画风作品.jpg
└── 美少女/
    └── 12345_67910_美少女作品.jpg

downloaded_ids.json   # 已下载作品 ID 记录
config.yaml           # 配置文件
```

### 4. 核心流程

1. **初始化**
   - 读取 `config.yaml`
   - 加载已下载 ID 记录（如果存在）
   - 创建 Session，设置请求头

2. **认证**
   - 使用 cookie 中的 `session_id`
   - 或使用 Refresh Token 获取新 cookie

3. **获取作品列表**
   - 根据配置组合条件查询：
     - 标签搜索 → `public/v1/search/illust`
     - 排行榜 → `v1/illust/ranking`
     - 画师作品 → `v1/user/illusts`
   - 对结果按收藏数过滤（`bookmark_count >= bookmarks_min`）

4. **遍历作品**
   - 检查去重（ID 记录 + 文件存在）
   - 获取图片 URL 列表
   - 按优先级选择可用规格

5. **下载保存**
   - 确定存储路径（第一个匹配的标签目录）
   - 下载图片
   - 更新 ID 记录
   - 延时后继续下一个

6. **结束**
   - 保存 ID 记录到文件

### 5. 错误处理

| 场景 | 处理方式 |
|------|----------|
| Cookie 过期 | 抛出异常，提示用户更新 cookie |
| 请求失败 | 重试 3 次，间隔 5s |
| 图片下载失败 | 跳过该图片，记录警告 |
| 文件写入失败 | 跳过，记录错误 |
| 标签目录创建失败 | 使用根目录作为 fallback |

### 6. 日志

- 使用 Python `logging` 模块
- 控制台输出 + 可选文件记录
- 日志级别可配置

### 7. 项目结构

```
pixiv_scraper/
├── pixiv_scraper.py   # 主脚本（单文件）
├── config.yaml        # 配置文件
├── downloaded_ids.json # 下载记录（自动生成）
└── images/           # 图片目录（自动生成）
    └── ...
```

## 技术选型

- **语言**: Python 3.9+
- **HTTP**: `requests`
- **并发**: 无（串行）
- **配置**: `PyYAML`
- **JSON**: 内置 `json`

## 依赖

```
requests>=2.28.0
PyYAML>=6.0
```

## 验收标准

1. ✅ 配置文件读取成功，能根据配置执行相应搜索
2. ✅ 登录认证正常（cookie 或 refresh token）
3. ✅ 按标签/排行榜/画师搜索并过滤结果
4. ✅ 图片按优先级下载
5. ✅ 按标签目录存储，同一作品只存一份
6. ✅ 双重去重（ID + 文件检查）正常工作
7. ✅ 串行下载，带延时
8. ✅ 错误处理和日志输出
9. ✅ 配置文件示例完整可用
