"""
Pixiv 图片爬虫
"""
import os
import json
import logging
import re
from pathlib import Path
from typing import Optional, Set

import requests
import yaml

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """加载并验证配置文件"""
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 验证必要配置
    _validate_config(config)
    
    return config


def _validate_config(config: dict) -> None:
    """验证配置完整性"""
    required_sections = ['pixiv', 'scraper', 'download', 'deduplication', 'rate_limit']
    
    for section in required_sections:
        if section not in config:
            raise ValueError(f"配置缺少必需部分: {section}")
    
    # 验证 cookie 或 refresh_token
    cookies = config.get('pixiv', {}).get('cookies', {})
    refresh_token = config.get('pixiv', {}).get('refresh_token')
    
    if not cookies.get('session_id') and not refresh_token:
        raise ValueError("必须提供 session_id cookie 或 refresh_token")


def load_downloaded_ids(id_file: str = "downloaded_ids.json") -> Set[str]:
    """加载已下载的作品 ID"""
    id_file = Path(id_file)
    
    if id_file.exists():
        with open(id_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(data.get('ids', []))
    
    return set()


def save_downloaded_ids(ids: Set[str], id_file: str = "downloaded_ids.json") -> None:
    """保存已下载的作品 ID"""
    id_file = Path(id_file)
    
    with open(id_file, 'w', encoding='utf-8') as f:
        json.dump({'ids': list(ids)}, f, ensure_ascii=False, indent=2)


# ============= Pixiv API 客户端 =============


class PixivClient:
    """Pixiv API 客户端"""
    
    BASE_URL = "https://app-api.pixiv.net"
    HEADERS = {
        "User-Agent": "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    
    def __init__(self, cookies: dict = None, refresh_token: str = None):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.access_token: Optional[str] = None
        
        if cookies:
            # 使用已有的 cookies
            for key, value in cookies.items():
                self.session.cookies.set(key, value)
            self.access_token = cookies.get('access_token')
            if self.access_token:
                self.session.headers['Authorization'] = f'Bearer {self.access_token}'
            
        elif refresh_token:
            self._refresh_access_token(refresh_token)
        else:
            raise ValueError("需要提供 cookies 或 refresh_token")
    
    def _refresh_access_token(self, refresh_token: str) -> None:
        """使用 refresh_token 获取新的 access_token"""
        url = "https://oauth.secure.pixiv.net/auth/token"
        data = {
            "client_id": "MOBrBDS8blbauoSck0ZfDbtuzpyT2Nkg1EG9eRboIbE",
            "client_secret": "W9JZoJe00qPvJ7yMFB99NzLTqFcJnzCIVJDfFwXVpw",
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        
        response = self.session.post(url, data=data)
        response.raise_for_status()
        
        result = response.json()
        self.access_token = result['response']['access_token']
        self.session.headers['Authorization'] = f'Bearer {self.access_token}'
        
        logger.info("成功获取 access_token")
    
    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """统一请求方法，带重试"""
        import time
        
        url = f"{self.BASE_URL}/{endpoint}"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, **kwargs)
                
                if response.status_code == 403:
                    raise PermissionError("Cookie 已过期，请更新")
                
                response.raise_for_status()
                return response.json()
                
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    time.sleep(5)
                else:
                    raise
        
        return {}
    
    def search_illust(self, word: str, limit: int = 30, offset: int = 0) -> list:
        """搜索插画"""
        params = {
            "word": word,
            "search_target": "partial_match_for_tags",
            "sort": "date_desc",
            "filter": "for_ios",
            "limit": limit,
            "offset": offset,
        }
        
        data = self._request("GET", "v1/search/illust", params=params)
        return data.get('illusts', [])
    
    def get_ranked_illust(self, mode: str = "daily", content: str = "all", 
                          date: str = None, offset: int = 0) -> list:
        """获取排行榜"""
        params = {
            "mode": mode,
            "filter": "for_ios",
            "offset": offset,
        }
        
        if date:
            params['date'] = date
        
        # R18 内容使用不同端点
        if content == "r18":
            params['mode'] = f'{mode}_r18'
        
        endpoint = "v1/illust/ranking"
        data = self._request("GET", endpoint, params=params)
        return data.get('illusts', [])
    
    def get_user_illusts(self, user_id: str, limit: int = 30, offset: int = 0) -> list:
        """获取用户作品"""
        params = {
            "user_id": user_id,
            "filter": "for_ios",
            "limit": limit,
            "offset": offset,
        }
        
        data = self._request("GET", "v1/user/illusts", params=params)
        return data.get('illusts', [])
    
    def get_illust_detail(self, illust_id: str) -> dict:
        """获取作品详情"""
        params = {"illust_id": illust_id}
        data = self._request("GET", "v1/illust/detail", params=params)
        return data.get('illust', {})


# ============= 图片下载器 =============


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除非法字符"""
    # 移除或替换非法字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 限制长度
    if len(filename) > 200:
        filename = filename[:200]
    return filename


def get_available_url(illust: dict, priority: list) -> tuple:
    """从作品信息中获取可用的图片 URL
    
    Returns:
        (url, is_multiple_page)
    """
    # 优先从 meta_pages 获取（多页作品）
    meta_pages = illust.get('meta_pages', [])
    
    if meta_pages:
        # 多页作品
        for pref in priority:
            for page in meta_pages:
                image_urls = page.get('image_urls', {})
                if pref in image_urls:
                    return image_urls[pref], True
    else:
        # 单页作品
        meta_single = illust.get('meta_single_page', {})
        image_urls = illust.get('image_urls', {})
        
        for pref in priority:
            # 尝试 medical_ 前缀
            url = meta_single.get(f'medical_{pref}_image')
            if not url:
                url = image_urls.get(pref)
            if url:
                return url, False
    
    return None, False


def download_image(url: str, save_path: Path, delay: float = 0) -> bool:
    """下载图片到指定路径"""
    import time
    
    if delay > 0:
        time.sleep(delay)
    
    save_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"下载成功: {save_path.name}")
        return True
        
    except requests.RequestException as e:
        logger.warning(f"下载失败: {url} - {e}")
        return False
    except IOError as e:
        logger.error(f"文件写入失败: {save_path} - {e}")
        return False


def determine_save_path(
    illust: dict,
    tags: list,
    root_dir: Path,
    filename_format: str,
    multi_tag_strategy: str = "first_match"
) -> tuple:
    """确定文件保存路径
    
    Returns:
        (save_path, matched_tag_dir)
    """
    illust_id = str(illust['id'])
    artist_id = str(illust['user']['id'])
    title = sanitize_filename(illust.get('title', 'untitled'))
    
    # 获取作品标签
    illust_tags = [t.get('name', '') for t in illust.get('tags', [])]
    
    # 找到匹配的标签
    matched_tags = []
    for tag in tags:
        if tag in illust_tags:
            matched_tags.append(tag)
    
    # 根据策略决定目录
    if matched_tags:
        dir_name = matched_tags[0]
    else:
        dir_name = "未分类"
    
    # 构建文件名
    filename = filename_format.format(
        artist_id=artist_id,
        illust_id=illust_id,
        title=title
    )
    
    # 添加扩展名（默认 jpg）
    ext = '.jpg'
    if 'png' in url.lower():
        ext = '.png'
    
    save_dir = root_dir / dir_name
    save_path = save_dir / f"{filename}{ext}"
    
    return save_path, dir_name


# ============= 主爬虫类 =============


class PixivScraper:
    """Pixiv 图片爬虫"""
    
    def __init__(self, config: dict):
        self.config = config
        self.downloaded_ids = load_downloaded_ids(config['deduplication']['id_file'])
        
        # 初始化 API 客户端
        cookies = config['pixiv'].get('cookies', {})
        refresh_token = config['pixiv'].get('refresh_token')
        self.client = PixivClient(cookies=cookies, refresh_token=refresh_token)
        
        # 配置
        self.tags = config['scraper']['tags']
        self.ranked_config = config['scraper']['ranked']
        self.artists = config['scraper'].get('artists', [])
        self.bookmarks_min = config['scraper'].get('bookmarks_min')
        self.limit = config['scraper']['limit']
        
        self.priority = config['download']['priority']
        self.root_dir = Path(config['download']['root_dir'])
        self.filename_format = config['download']['filename_format']
        self.multi_tag_strategy = config['download']['multi_tag_strategy']
        
        self.delay = config['rate_limit']['delay']
        self.strategy = config['deduplication']['strategy']
        
        # 确保目录存在
        self.root_dir.mkdir(parents=True, exist_ok=True)
    
    def is_duplicate(self, illust_id: int) -> bool:
        """检查是否重复"""
        illust_id = str(illust_id)
        
        if self.strategy in ('both', 'id'):
            if illust_id in self.downloaded_ids:
                return True
        
        if self.strategy in ('both', 'file'):
            # 检查文件是否存在
            if list(self.root_dir.rglob(f"*{illust_id}*")):
                return True
        
        return False
    
    def filter_by_bookmarks(self, illusts: list) -> list:
        """按收藏数过滤"""
        if not self.bookmarks_min:
            return illusts
        
        return [
            illust for illust in illusts
            if illust.get('total_bookmarks', 0) >= self.bookmarks_min
        ]
    
    def fetch_illusts(self) -> list:
        """获取所有符合条件的作品"""
        all_illusts = []
        seen_ids = set()
        
        # 1. 标签搜索
        for tag in self.tags:
            logger.info(f"搜索标签: {tag}")
            offset = 0
            
            while len(all_illusts) + len(seen_ids) < self.limit * 2:
                illusts = self.client.search_illust(tag, limit=30, offset=offset)
                
                if not illusts:
                    break
                
                for illust in illusts:
                    if illust['id'] not in seen_ids:
                        seen_ids.add(illust['id'])
                        all_illusts.append(illust)
                
                offset += 30
                
                if len(illusts) < 30:
                    break
        
        # 2. 排行榜
        if self.ranked_config.get('enabled'):
            logger.info(f"获取排行榜: {self.ranked_config['mode']}")
            offset = 0
            
            while len(all_illusts) + len(seen_ids) < self.limit * 2:
                illusts = self.client.get_ranked_illust(
                    mode=self.ranked_config['mode'],
                    content=self.ranked_config['content'],
                    date=self.ranked_config.get('date'),
                    offset=offset
                )
                
                if not illusts:
                    break
                
                for illust in illusts:
                    if illust['id'] not in seen_ids:
                        seen_ids.add(illust['id'])
                        all_illusts.append(illust)
                
                offset += 30
        
        # 3. 指定画师
        for artist_id in self.artists:
            logger.info(f"获取画师 {artist_id} 作品")
            offset = 0
            
            while len(all_illusts) + len(seen_ids) < self.limit * 2:
                illusts = self.client.get_user_illusts(artist_id, limit=30, offset=offset)
                
                if not illusts:
                    break
                
                for illust in illusts:
                    if illust['id'] not in seen_ids:
                        seen_ids.add(illust['id'])
                        all_illusts.append(illust)
                
                offset += 30
        
        # 4. 过滤收藏数
        all_illusts = self.filter_by_bookmarks(all_illusts)
        
        # 5. 去重
        all_illusts = [i for i in all_illusts if not self.is_duplicate(i['id'])]
        
        # 6. 限制数量
        all_illusts = all_illusts[:self.limit]
        
        logger.info(f"共找到 {len(all_illusts)} 个待下载作品")
        return all_illusts
    
    def run(self) -> None:
        """运行爬虫"""
        logger.info("=" * 50)
        logger.info("Pixiv 图片爬虫启动")
        logger.info("=" * 50)
        
        # 获取作品列表
        illusts = self.fetch_illusts()
        
        if not illusts:
            logger.info("没有找到需要下载的作品")
            return
        
        # 下载作品
        success_count = 0
        for i, illust in enumerate(illusts, 1):
            illust_id = illust['id']
            title = illust.get('title', 'N/A')
            logger.info(f"[{i}/{len(illusts)}] 处理作品 {illust_id}: {title}")
            
            # 获取图片 URL
            url, is_multiple = get_available_url(illust, self.priority)
            
            if not url:
                logger.warning(f"无法获取图片 URL，作品 ID: {illust_id}")
                continue
            
            # 确定保存路径
            save_path, matched_dir = determine_save_path(
                illust, self.tags, self.root_dir,
                self.filename_format, self.multi_tag_strategy
            )
            
            # 下载
            if download_image(url, save_path, delay=self.delay):
                success_count += 1
                self.downloaded_ids.add(str(illust_id))
                save_downloaded_ids(self.downloaded_ids, self.config['deduplication']['id_file'])
        
        logger.info("=" * 50)
        logger.info(f"下载完成！成功: {success_count}/{len(illusts)}")
        logger.info("=" * 50)


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Pixiv 图片爬虫')
    parser.add_argument('-c', '--config', default='config.yaml', help='配置文件路径')
    args = parser.parse_args()
    
    try:
        # 加载配置
        config = load_config(args.config)
        
        # 运行爬虫
        scraper = PixivScraper(config)
        scraper.run()
        
    except Exception as e:
        logger.error(f"程序出错: {e}")
        raise


if __name__ == '__main__':
    main()
