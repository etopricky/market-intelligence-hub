"""Produce public JSON for static site. Stores article headlines/links only, no personal notes."""
from pathlib import Path
import datetime as dt
import json
import sqlite3
from collector import DB_PATH, STATUS_PATH
ROOT=Path(__file__).resolve().parent
DEST=ROOT/'data.json'
existing={}
try:
  existing=json.loads(DEST.read_text(encoding='utf-8'))
except (FileNotFoundError,ValueError): pass
items={item['id']: item for item in existing.get('items',[]) if isinstance(item,dict) and item.get('id')}
if DB_PATH.exists():
  with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory=sqlite3.Row
    for row in conn.execute('SELECT id,category,title,link,source,published,group_type,score,status,guidance,related,is_core FROM articles'):
      r=dict(row)
      items[r['id']]=r
threshold=dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=120)
clean=[]
for item in items.values():
  try:
    published=dt.datetime.fromisoformat(item.get('published','').replace('Z','+00:00'))
    if published.tzinfo is None: published=published.replace(tzinfo=dt.timezone.utc)
    if published<threshold:continue
  except (ValueError,TypeError):pass
  clean.append(item)
clean.sort(key=lambda x:(x.get('published') or '',x.get('score') or 0),reverse=True)
clean=clean[:2000]
status=existing.get('status') or {}
try:
  new=json.loads(STATUS_PATH.read_text(encoding='utf-8'))
  if new.get('fetched_sources',0)>0:
    status=new
except (FileNotFoundError,ValueError):pass
DEST.write_text(json.dumps({'total':len(clean),'items':clean,'status':status},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Exported {len(clean)} public items')
