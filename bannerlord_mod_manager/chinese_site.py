import os
import re
import json
import logging
import zipfile
import urllib.request
import urllib.parse
import html as html_lib
from html.parser import HTMLParser
from dataclasses import dataclass, field

logger = logging.getLogger("BannerlordModManager")

BASE_URL = "https://bbs.mountblade.com.cn"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

# ============================================================
# 分类与来源常量
# ============================================================
CATEGORIES = {"全部": 0, "骑砍2:霸主MOD": 1, "骑砍2:战帆MOD": 17, "战团MOD": 2, "原版MOD": 3, "游戏下载": 4, "游戏工具": 5, "其他": 6}
SOURCES = {"全部": 0, "原创": 1, "转载": 2, "二次创作": 3, "汉化": 4}
SORT_MODES = {"默认": "", "按最新": "_xin", "按推荐": "_tj", "按浏览量": "_view", "按下载量": "_down"}

@dataclass
class ChineseModItem:
    title: str = ""
    author: str = ""
    url: str = ""
    category: str = ""
    source: str = ""
    views: int = 0
    downloads: int = 0
    date: str = ""
    description: str = ""
    image_url: str = ""

    def to_dict(self) -> dict:
        return self.__dict__

class SimpleModExtractor:
    @staticmethod
    def extract_from_html(html: str) -> tuple:
        mods = []
        total_match = re.search(r'共有.*?<font color="red">\s*(\d+)\s*</font>', html)
        total = int(total_match.group(1)) if total_match else 0

        items = re.findall(r'<dd class="listItem">(.*?)</dd>', html, re.DOTALL)
        for item in items:
            mod = {"title": "", "url": "", "author": "", "views": 0, "downloads": 0, "date": "", "image_url": "", "description": ""}
            title_m = re.search(r'<h3 class="name">\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', item, re.DOTALL)
            if title_m:
                href = title_m.group(1)
                mod["url"] = href if href.startswith("http") else f"{BASE_URL}/{href}"
                mod["title"] = re.sub(r'<[^>]+>', '', title_m.group(2)).strip()

            author_m = re.search(r'作者[：:]\s*([^<&]+)', item)
            if author_m: mod["author"] = author_m.group(1).strip()

            views_m = re.search(r'浏览[：:]\s*(\d+)', item)
            if views_m: mod["views"] = int(views_m.group(1))

            dl_m = re.search(r'下载[：:]\s*(\d+)', item)
            if dl_m: mod["downloads"] = int(dl_m.group(1))

            date_m = re.search(r'时间[：:]\s*(\d{4}-\d{1,2}-\d{1,2})', item)
            if date_m: mod["date"] = date_m.group(1)

            img_m = re.search(r'<img[^>]*src="([^"]+)"', item)
            if img_m:
                img_url = img_m.group(1)
                mod["image_url"] = img_url if img_url.startswith("http") else f"{BASE_URL}/{img_url}"

            desc_m = re.search(r'简介[：:](.*?)(?:&nbsp;|</div)', item, re.DOTALL)
            if desc_m:
                mod["description"] = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()

            if mod["title"]:
                mods.append(mod)

        return mods, total

class ChineseSiteAPI:
    @staticmethod
    def open_site():
        import webbrowser
        webbrowser.open(BASE_URL)
        
    def __init__(self):
        self._cookies = ""

    def set_cookies(self, cookies: str):
        self._cookies = cookies

    def _make_request(self, url: str, data: bytes = None, method: str = "GET") -> str:
        try:
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("User-Agent", USER_AGENT)
            if self._cookies: req.add_header("Cookie", self._cookies)
            with urllib.request.urlopen(req, timeout=20) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except Exception as exc:
            logger.error("中文站请求失败 [%s]: %s", url, exc)
            return ""

    def search(self, keyword: str) -> tuple:
        url = f"{BASE_URL}/plugin.php?id=xlwsq_down"
        data = urllib.parse.urlencode({"key": keyword}).encode("utf-8")
        return SimpleModExtractor.extract_from_html(self._make_request(url, data=data, method="POST"))

    def browse_category(self, category="全部", source="全部", sort="默认", page=0) -> tuple:
        cat_id = CATEGORIES.get(category, 0)
        src_id = SOURCES.get(source, 0)
        sort_suffix = SORT_MODES.get(sort, "")
        url = f"{BASE_URL}/download_list_{cat_id}_{src_id}_{page}{sort_suffix}.html"
        return SimpleModExtractor.extract_from_html(self._make_request(url))

    def get_mod_detail(self, url: str) -> dict:
        """获取模组详情页信息，包括完整介绍、元数据、评论和评分"""
        html = self._make_request(url)
        if not html: return {}

        detail = {"url": url, "comments": [], "download_links": [], "images": [], "meta": {}}

        # 提取标题
        title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
        if title_m:
            detail["title"] = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()

        # ---- 提取元数据信息卡 ----
        # 作者
        author_m = re.search(r'作者[：:]\s*(?:<[^>]*>)*\s*([^<\s]+)', html)
        if author_m:
            detail["meta"]["author"] = author_m.group(1).strip()

        # 分类
        cat_m = re.search(r'分类[：:]\s*(?:<[^>]*>)*\s*([^<\s]+)', html)
        if cat_m:
            detail["meta"]["category"] = cat_m.group(1).strip()

        # 来源
        src_m = re.search(r'来源[：:]\s*(?:<[^>]*>)*\s*([^<\s]+)', html)
        if src_m:
            detail["meta"]["source"] = src_m.group(1).strip()

        # 浏览量
        views_m = re.search(r'浏览[：:]\s*(\d+)', html)
        if views_m:
            detail["meta"]["views"] = int(views_m.group(1))

        # 下载量
        dl_m = re.search(r'下载[：:]\s*(\d+)', html)
        if dl_m:
            detail["meta"]["downloads"] = int(dl_m.group(1))

        # 推荐
        rec_m = re.search(r'推荐[：:]\s*(\d+)', html)
        if rec_m:
            detail["meta"]["recommends"] = int(rec_m.group(1))

        # 收藏
        fav_m = re.search(r'收藏[：:]\s*(\d+)', html)
        if fav_m:
            detail["meta"]["favorites"] = int(fav_m.group(1))

        # 上传日期
        date_m = re.search(r'时间[：:]\s*(\d{4}-\d{1,2}-\d{1,2})', html)
        if date_m:
            detail["meta"]["date"] = date_m.group(1)

        # 文件大小
        size_m = re.search(r'大小[：:]\s*([\d.]+\s*[KMGT]?B)', html, re.IGNORECASE)
        if size_m:
            detail["meta"]["file_size"] = size_m.group(1).strip()

        # 适用版本
        ver_m = re.search(r'(?:适用版本|游戏版本|兼容版本)[：:]\s*([^<\n]+)', html)
        if ver_m:
            detail["meta"]["game_version"] = ver_m.group(1).strip()

        # ---- 提取评分 ----
        score_m = re.search(r'总体评分[：:]\s*(?:<[^>]*>)*\s*([\d.]+)', html)
        if score_m:
            try:
                detail["meta"]["score"] = float(score_m.group(1))
            except ValueError:
                pass

        # 评分人数
        score_count_m = re.search(r'(\d+)\s*(?:人评分|个评分|人评价)', html)
        if score_count_m:
            detail["meta"]["score_count"] = int(score_count_m.group(1))

        # ---- 提取完整内容描述 ----
        desc_m = re.search(r'<div class="layui-card-header">详细内容</div>(.*?)<(?:div class="layui-card"|style)', html, re.DOTALL)
        if desc_m:
            raw_html = desc_m.group(1)

            # 提取内容中的图片
            for img_m in re.finditer(r'<img[^>]*src="([^"]+)"[^>]*>', raw_html):
                img_url = img_m.group(1)
                if img_url.startswith("http") or img_url.startswith("//"):
                    if img_url.startswith("//"):
                        img_url = "https:" + img_url
                    detail["images"].append(img_url)
                elif not img_url.startswith("data:"):
                    detail["images"].append(f"{BASE_URL}/{img_url}")

            # 剥离脚本和样式
            clean_text = re.sub(r'<style[^>]*>.*?</style>', '', raw_html, flags=re.DOTALL)
            clean_text = re.sub(r'<script[^>]*>.*?</script>', '', clean_text, flags=re.DOTALL)
            # 转换换行标签
            clean_text = re.sub(r'<br\s*/?>', '\n', clean_text)
            clean_text = re.sub(r'<p[^>]*>', '\n', clean_text)
            clean_text = re.sub(r'<li[^>]*>', '\n• ', clean_text)
            clean_text = re.sub(r'<h\d[^>]*>', '\n【', clean_text)
            clean_text = re.sub(r'</h\d>', '】\n', clean_text)
            # 清除所有HTML标签
            clean_text = re.sub(r'<[^>]+>', '', clean_text)
            # 替换HTML实体
            detail["description"] = html_lib.unescape(clean_text).strip()
            # 删除多余空行
            detail["description"] = re.sub(r'\n\s*\n', '\n\n', detail["description"])

        # ---- 提取更新日志/更新记录 ----
        changelog_m = re.search(r'(?:更新日志|更新记录|更新说明|更新内容|changelog)[：:]?\s*(.*?)(?:<div class="layui-card|$)', html, re.DOTALL | re.IGNORECASE)
        if changelog_m:
            cl_text = re.sub(r'<[^>]+>', '', changelog_m.group(1))
            cl_text = html_lib.unescape(cl_text).strip()
            if cl_text and len(cl_text) > 10:
                detail["changelog"] = re.sub(r'\n\s*\n', '\n', cl_text)[:2000]

        # ---- 提取下载链接 ----
        dl_block_m = re.search(r'<div id="down-list">(.*?)</div>', html, re.DOTALL)
        if dl_block_m:
            for a_m in re.finditer(r'<a([^>]+)>([^<]+)</a>', dl_block_m.group(1)):
                attrs = a_m.group(1)
                name = a_m.group(2).strip()
                
                onclick_m = re.search(r'onclick="([^"]+)"', attrs)
                if onclick_m:
                    js_code = onclick_m.group(1)
                    url_m = re.search(r"window\.open\('([^']+)'\)|showWindow\([^,]+,\s*'([^']+)'", js_code)
                    if url_m:
                        dl_url = url_m.group(1) or url_m.group(2)
                        dl_url = dl_url if dl_url.startswith("http") else f"{BASE_URL}/{dl_url}"
                        detail["download_links"].append({"name": name, "url": dl_url.replace('&amp;', '&')})
                        continue
                
                href_m = re.search(r'href="([^"]+)"', attrs)
                if href_m:
                    dl_url = href_m.group(1)
                    if not dl_url.startswith("javascript"):
                        dl_url = dl_url if dl_url.startswith("http") else f"{BASE_URL}/{dl_url}"
                        detail["download_links"].append({"name": name, "url": dl_url.replace('&amp;', '&')})

        # ---- 提取评论 ----
        comment_blocks = re.findall(r'<div class="comments clearfix">(.*?)<div class="clear"></div>', html, re.DOTALL)
        for block in comment_blocks:
            author_m = re.search(r'<h4>(.*?)</h4>', block)
            time_m = re.search(r'<span class="time">\s*(.*?)\s*</span>', block, re.DOTALL)
            
            # 提取评分星级
            rating = 0
            rating_m = re.search(r'总体评[价分][：:]\s*(?:<[^>]*>)*\s*([\d.]+)', block)
            if rating_m:
                try:
                    rating = float(rating_m.group(1))
                except ValueError:
                    pass

            content = ""
            for p in re.findall(r'<p>(.*?)</p>', block, re.DOTALL):
                text = re.sub(r'<[^>]+>', '', p).strip()
                if text and "总体评价" not in text and "总体评分" not in text:
                    content += text + "\n"
            
            if content.strip():
                comment = {
                    "author": author_m.group(1).strip() if author_m else "匿名",
                    "time": re.sub(r'\s+', ' ', time_m.group(1)).strip() if time_m else "",
                    "content": content.strip(),
                }
                if rating > 0:
                    comment["rating"] = rating
                detail["comments"].append(comment)

        return detail

# ============================================================
# 下载与安装器
# ============================================================
class ModInstaller:
    """处理下载判定和本地安装"""
    
    @staticmethod
    def handle_download(url: str, modules_folder_path: str, progress_callback=None) -> bool:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content_type = resp.headers.get_content_type()
                
                if "text/html" in content_type:
                    return False
                
                file_size = int(resp.headers.get("Content-Length", 0))
                temp_file = os.path.join(modules_folder_path, "temp_mod_download.zip")
                
                downloaded = 0
                with open(temp_file, 'wb') as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and file_size > 0:
                            progress_callback(int((downloaded / file_size) * 100))
                
                if zipfile.is_zipfile(temp_file):
                    with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                        zip_ref.extractall(modules_folder_path)
                    os.remove(temp_file)
                    return True
                else:
                    os.rename(temp_file, os.path.join(modules_folder_path, "Downloaded_Mod_Needs_Manual_Extract.rar"))
                    return True

        except Exception as e:
            logger.error(f"本地下载/安装失败: {e}")
            return False