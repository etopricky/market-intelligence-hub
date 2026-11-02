"""Market Intelligence Center / zero-paid-service collector (Python stdlib only).

Collects metadata from public Google News RSS search feeds. This is NOT an
LLM/verified tender intelligence service. Source links and headlines must be
verified individually before business use.
"""
from __future__ import annotations
import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
DB_PATH = DATA_DIR / 'intelligence.sqlite3'
STATUS_PATH = DATA_DIR / 'status.json'
LOG_DIR = ROOT / 'logs'

CATEGORIES = [
    ('market', '市场需求与行业趋势', 'B', 10),
    ('brand', '品牌动态与潜在客户', 'B', 20),
    ('orders', '采购订单与商业合作', 'B', 25),
    ('channels', '销售渠道与商业模式', 'B', 15),
    ('research', '产品研发与配方原料', 'A', 8),
    ('packaging', '包材工艺与产品设计', 'A', 7),
    ('regulation', '政策法规与合规风险', 'A', 5),
    ('future', '跨行业商机与投资观察', 'C', 10),
]
QUERIES = [
    ('market', '化妆品 消费趋势 洗护 香氛 市场 when:7d', 'zh'),
    ('market', 'beauty personal care fragrance haircare market growth when:7d', 'en'),
    ('brand', '化妆品 美妆 品牌 融资 新品 扩张 when:7d', 'zh'),
    ('brand', 'beauty brand launch funding expansion beauty care when:7d', 'en'),
    ('orders', '化妆品 OEM ODM 采购 招标 供应商 招募 when:14d', 'zh'),
    ('orders', '酒店 客房 洗护用品 供应商 招标 采购 when:14d', 'zh'),
    ('orders', 'beauty OEM ODM contract manufacturing supplier tender when:14d', 'en'),
    ('orders', 'hotel amenities procurement supplier tender shampoo when:14d', 'en'),
    ('channels', '美妆 香氛 渠道 分销 跨境 合作 when:7d', 'zh'),
    ('channels', 'beauty retail distribution partnership expansion when:7d', 'en'),
    ('research', '化妆品 新原料 配方 功效 发酵 科研 when:14d', 'zh'),
    ('research', 'cosmetic ingredients formulation biotechnology research when:14d', 'en'),
    ('packaging', '化妆品 包材 包装 泵头 设计 创新 when:14d', 'zh'),
    ('packaging', 'cosmetics packaging innovation refill dispenser design when:14d', 'en'),
    ('regulation', 'site:nmpa.gov.cn 化妆品 公告 新规 when:30d', 'zh'),
    ('regulation', 'cosmetics regulations FDA EU MoCRA ingredients when:14d', 'en'),
    ('future', '机器人 生物科技 人工智能 创业 商业模式 when:7d', 'zh'),
    ('future', 'emerging industries AI biotechnology business investment when:7d', 'en'),
]
BING_QUERIES = [
    ('market','化妆品 洗护 市场 增长','zh'),
    ('brand','美妆 护肤 品牌 新品 融资','zh'),
    ('orders','化妆品 采购 招标 OEM ODM','zh'),
    ('orders','酒店用品 洗护 招标 采购','zh'),
    ('channels','美妆 香氛 渠道 合作 跨境','zh'),
    ('research','化妆品 原料 配方 生物技术','zh'),
    ('packaging','化妆品 包材 包装设计 泵头','zh'),
    ('regulation','国家药监局 化妆品 新规 公告','zh'),
    ('future','机器人 生物科技 AI 产业发展','zh'),
    ('orders','beauty cosmetics manufacturer supplier procurement tender','en'),
    ('brand','cosmetics brands expanding manufacturing partnership','en'),
    ('packaging','cosmetics packaging innovation sustainable materials','en'),
]
CORE = ('化妆', '美妆', '洗护', '洗发', '护发', '香氛', '香薰', '香水', '护肤', '日化', '包材', '原料', '酒店用品', '美容', '面膜', '香精',
        'cosmetic', 'beauty', 'skin', 'hair', 'fragrance', 'perfume', 'personal care', 'packaging', 'toiletries', 'amenit', 'ingredient')
BUYING = ('采购公告', '采购需求', '招标公告', '中标公告', '征集供应商', '供应商招募', '公开招募', '供应商入围', '招标', '采购', '询价', '寻源',
          'tender', 'rfp', 'supplier search', 'procurement', 'contract manufacturing', 'bidding')
OPEN = ('新品', '上线', '推出', '发布', '成立', '扩张', '融资', '收购', '合作', '上市', 'new launch', 'launches', 'expands', 'partnership',
        'funding', 'investment', 'acquisition', 'collaboration', 'opens')
GUIDANCE = {
  'market': ('识别需求趋势并与现有SKU、产品报价和目标客群交叉验证。', '圆方 · 信弘达 · 源采'),
  'brand': ('核实品牌背景、销量与供应链模式；如匹配，再研究业务拓展路径。', '圆方 · 信弘达'),
  'orders': ('务必寻找正式采购公告、截止时间、资质要求和联系人；媒体报道不等于真实采购需求。', '圆方 · 信弘达'),
  'channels': ('判断渠道门槛、账期、毛利及能否小批量试点。', '信弘达 · 源采 · 半柴'),
  'research': ('核对INCI/原料合规、配方稳定性、功效证据与量产成本。', '圆方 · Q-LAB'),
  'packaging': ('联系包材供应商核实材质、MOQ、兼容性、专利与单价。', '圆方 · 源采 · 半柴'),
  'regulation': ('以主管部门正式文件为准；评估现有配方、标签、备案和出口文件。', '圆方 · 信弘达'),
  'future': ('先研究实际付费需求、盈利模式和竞争壁垒，不形成投资建议。', '跨行业观察'),
}

def db_connect():
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('''CREATE TABLE IF NOT EXISTS articles (
      id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL,
      link TEXT NOT NULL, source TEXT, published TEXT, added TEXT NOT NULL,
      group_type TEXT NOT NULL, score INTEGER DEFAULT 1, status TEXT NOT NULL,
      guidance TEXT NOT NULL, related TEXT NOT NULL, is_core INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS notes (
      id TEXT PRIMARY KEY, state TEXT DEFAULT 'unread', memo TEXT DEFAULT '',
      updated TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)''')
    c.commit()
    return c

def google_feed(query, lang):
    locale = 'hl=zh-CN&gl=CN&ceid=CN%3Azh-Hans' if lang == 'zh' else 'hl=en-US&gl=US&ceid=US%3Aen'
    return 'https://news.google.com/rss/search?q=' + urllib.parse.quote(query) + '&' + locale

def bing_feed(query, lang):
    clean_query = re.sub(r'\bwhen:\d+[dhmw]\b','',query).strip()
    return 'https://www.bing.com/news/search?q=' + urllib.parse.quote(clean_query) + '&format=rss&setmkt=' + ('zh-CN' if lang=='zh' else 'en-US')

def fetch_feed(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; MarketIntel/1.0; personal non-commercial RSS reader)',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    })
    with urllib.request.urlopen(request, timeout=14) as response:
        data = response.read(2_000_000)
    root = ET.fromstring(data)
    return root.findall('./channel/item')

def inner(item, tag):
    node = item.find(tag)
    return (node.text or '').strip() if node is not None else ''

def parse_date(value):
    try:
        d = email.utils.parsedate_to_datetime(value)
        if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc).isoformat(timespec='seconds')
    except Exception:
        return ''

def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', s or ''))).strip()

def score_for(category, title, source):
    t = title.lower()
    core = any(w in t for w in CORE)
    buy = any(w in t for w in BUYING)
    new = any(w in t for w in OPEN)
    val = 2 + (1 if core else 0) + (1 if new else 0)
    if category == 'orders' and buy: val += 1
    if category == 'future' and not core: val = min(val, 3)
    return min(5, val), core

def item_data(item, category, group):
    title = clean(inner(item, 'title'))
    link = inner(item, 'link')
    # Bing RSS often wraps the publisher URL inside a redirect URL.
    if 'bing.com/news/apiclick.aspx' in link:
        target = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get('url', [])
        if target and target[0].startswith('https://'): link = target[0]
    source = inner(item, 'source') or 'Google News 收录媒体'
    date = parse_date(inner(item, 'pubDate'))
    if not title or not link or not link.startswith('https://'): return None
    # Remove the source suffix sometimes appended by Google News RSS.
    if source and title.endswith(' - ' + source): title = title[:-(len(source) + 3)]
    title = title[:240]
    score, core = score_for(category, title, source)
    if group == 'C' and core: return None
    digest = hashlib.sha256((re.sub(r'[^\w]', '', title).lower()).encode('utf-8')).hexdigest()[:18]
    guidance, related = GUIDANCE[category]
    if category == 'orders': status = '采购线索·待官方核实'
    elif category == 'regulation': status = '法规线索·核对原文'
    else: status = '公开报道·待独立核实'
    return (digest, category, title, link[:1500], source[:130], date,
            dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            group, score, status, guidance, related, int(core))

def get_status():
    try: return json.loads(STATUS_PATH.read_text(encoding='utf-8'))
    except Exception: return {}

def write_status(data):
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    STATUS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def collect():
    LOG_DIR.mkdir(exist_ok=True, parents=True)
    conn = db_connect()
    start = dt.datetime.now().astimezone().isoformat(timespec='seconds')
    previous = get_status()
    status = {'last_attempt':start, 'last_success':previous.get('last_success'),
              'fetched_sources': 0,'failed_sources':0,'new_items':0,'errors':[],'running':True}
    write_status(status)
    try:
        group_map = {c:g for c,_,g,_ in CATEGORIES}
        now = dt.datetime.now(dt.timezone.utc)
        # Network requests are parallelized so blocked/unreachable feeds fail promptly.
        def one_feed(job):
            category, query, lang, provider = job
            url = bing_feed(query,lang) if provider=='bing' else google_feed(query,lang)
            return fetch_feed(url)
        jobs=[(*job,'google') for job in QUERIES]+[(*job,'bing') for job in BING_QUERIES]
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures={pool.submit(one_feed,job):job for job in jobs}
            for future in as_completed(futures):
                category, query, lang,provider=futures[future]
                try:
                    items=future.result()
                    status['fetched_sources'] += 1
                    for item in items[:65]:
                        row=item_data(item,category, group_map[category])
                        if not row: continue
                        if row[5]:
                            try:
                                published=dt.datetime.fromisoformat(row[5])
                                if published > now + dt.timedelta(days=1) or published < now - dt.timedelta(days=35): continue
                            except ValueError: pass
                        count=conn.execute('''INSERT OR IGNORE INTO articles
                          (id,category,title,link,source,published,added,group_type,score,status,guidance,related,is_core)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', row).rowcount
                        status['new_items'] += max(0,count)
                    conn.commit()
                except Exception as e:
                    status['failed_sources'] += 1
                    status['errors'].append({'category':category, 'provider':provider, 'query':query, 'message':str(e)[:160]})
        if status['fetched_sources']:
            status['last_success'] = dt.datetime.now().astimezone().isoformat(timespec='seconds')
            conn.execute('INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)', ('last_success_day',dt.datetime.now().strftime('%Y-%m-%d')))
            conn.commit()
        status['running'] = False
        write_status(status)
        return status
    finally:
        conn.close()

if __name__ == '__main__':
    out = collect()
    print(json.dumps(out,ensure_ascii=False,indent=2))
    if out['fetched_sources'] == 0:
        sys.exit(2)
