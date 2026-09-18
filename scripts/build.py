#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股行业轮动与资金流向监控 —— 数据抓取与页面生成
数据源：东方财富公开行情接口（push2.eastmoney.com）
输出：docs/index.html（自包含单文件）+ docs/data.json（原始数据留档）

仅使用 Python 标准库，无需 pip 安装任何依赖，便于 GitHub Actions 直接运行。
"""

import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")

# GitHub Actions 环境下证书通常没问题；本地 Windows 若证书链异常则放宽
SSL_CTX = ssl.create_default_context()
try:
    import certifi  # 可选
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    pass

# ---------------------------------------------------------------- 申万一级行业映射
# 东财板块名 -> 申万一级行业名（用于把东财细分板块聚合到 16 个一级行业）
SW_MAP = {
    "电子": ["电子", "半导体", "元件", "光学光电子", "消费电子", "电子化学品", "半导体材料",
             "光学元件", "面板", "LED", "集成电路", "被动元件", "其他电子", "印制电路板"],
    "通信": ["通信", "通信设备", "通信服务", "通信网络设备及器件", "通信线缆及配套", "光模块", "光纤光缆"],
    "计算机": ["计算机", "软件开发", "计算机设备", "IT服务", "互联网服务", "云计算"],
    "医药生物": ["医药生物", "化学制药", "中药", "生物制品", "医疗器械", "医疗服务", "医药商业", "原料药"],
    "电力设备": ["电力设备", "电池", "光伏设备", "风电设备", "电网设备", "电机", "其他电源设备", "储能"],
    "机械设备": ["机械设备", "通用设备", "专用设备", "工程机械", "自动化设备", "机器人", "仪器仪表"],
    "汽车": ["汽车", "汽车整车", "汽车零部件", "商用车", "乘用车", "汽车服务", "两轮车"],
    "有色金属": ["有色金属", "贵金属", "工业金属", "小金属", "能源金属", "稀土", "金属新材料"],
    "基础化工": ["基础化工", "化学原料", "化学制品", "塑料", "橡胶", "化纤", "农化制品", "非金属材料", "炭黑"],
    "银行": ["银行", "城商行", "国有大型银行", "股份制银行", "农商行"],
    "非银金融": ["非银金融", "证券", "保险", "多元金融", "期货"],
    "食品饮料": ["食品饮料", "白酒", "饮料乳品", "食品加工", "调味发酵品", "休闲食品", "啤酒", "非白酒"],
    "家用电器": ["家用电器", "白色家电", "黑色家电", "小家电", "厨卫电器", "家电零部件"],
    "房地产": ["房地产", "房地产开发", "房地产服务", "园区开发"],
    "交通运输": ["交通运输", "航运港口", "航空机场", "铁路公路", "物流", "航海装备"],
    "煤炭": ["煤炭", "煤炭开采", "焦炭"],
    "钢铁": ["钢铁", "普钢", "特钢", "冶钢原料"],
    "建筑装饰": ["建筑装饰", "房屋建设", "基础建设", "专业工程", "装修装饰", "工程咨询服务"],
    "建筑材料": ["建筑材料", "水泥", "玻璃玻纤", "装修建材", "非金属材料"],
    "公用事业": ["公用事业", "电力", "燃气", "水务", "环保"],
    "国防军工": ["国防军工", "航天装备", "航空装备", "地面兵装", "船舶制造", "军工电子"],
    "纺织服饰": ["纺织服饰", "纺织制造", "服装家纺", "饰品", "运动服装"],
    "轻工制造": ["轻工制造", "造纸", "包装印刷", "家居用品", "文娱用品", "珠宝首饰"],
    "商贸零售": ["商贸零售", "一般零售", "专业连锁", "互联网电商", "贸易"],
    "社会服务": ["社会服务", "旅游及景区", "酒店餐饮", "教育", "专业服务", "体育"],
    "传媒": ["传媒", "游戏", "影视院线", "广告营销", "出版", "数字媒体", "电视广播"],
    "农林牧渔": ["农林牧渔", "养殖业", "种植业", "林业", "饲料", "农产品加工", "渔业", "动物保健"],
    "美容护理": ["美容护理", "化妆品", "个护用品", "医疗美容"],
    "石油石化": ["石油石化", "油气开采", "炼化及贸易", "油服工程"],
    "环保": ["环保", "环境治理", "环保设备"],
    "综合": ["综合"],
    "建筑": ["建筑"],
}

# 页面固定展示的 16 个一级行业（保证每天口径一致）
DISPLAY_SECTORS = [
    "电子", "通信", "计算机", "医药生物", "电力设备", "机械设备", "汽车", "有色金属",
    "基础化工", "银行", "非银金融", "食品饮料", "家用电器", "房地产", "交通运输", "国防军工",
]

# 风格指数（用于风格轮动模块）
STYLE_INDICES = [
    ("大盘价值", "0.399373"),
    ("小盘成长", "0.399376"),
    ("国证成长", "0.399370"),
    ("中证红利", "1.000922"),
    ("中证1000", "1.000852"),
    ("国证2000", "0.399303"),
    ("科创50", "1.000688"),
    ("沪深300", "1.000300"),
]

MAIN_INDICES = [
    ("上证指数", "1.000001"),
    ("深证成指", "0.399001"),
    ("创业板指", "0.399006"),
    ("科创50", "1.000688"),
    ("沪深300", "1.000300"),
    ("北证50", "0.899050"),
]


_LAST_CALL = [0.0]

# 数据源回传的真实交易日（YYYY-MM-DD）。腾讯行情第 30 个字段是数据时间戳，
# 用它作为 trade_date，可自动处理周末/节假日/盘前等情况——比读本机时钟可靠。
_DATA_DATE = [None]


def fetch(url, retries=3, referer="https://quote.eastmoney.com/", base_delay=3.0, encoding="utf-8"):
    """带重试与全局限流的 GET，返回解析后的 JSON。

    东财免费接口在密集请求后会临时关闭连接（Remote end closed），
    因此这里做了三件事：① 每次请求前强制间隔；② 指数退避重试；
    ③ 失败返回 None 而不是抛异常，让上层可以降级到备用数据源。
    """
    last = None
    for i in range(retries):
        # 全局节流：任意两次请求至少间隔 base_delay 秒
        gap = time.time() - _LAST_CALL[0]
        if gap < base_delay:
            time.sleep(base_delay - gap)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Referer": referer,
                              "Accept": "application/json, text/plain, */*",
                              "Accept-Language": "zh-CN,zh;q=0.9"})
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
                raw = resp.read()
            _LAST_CALL[0] = time.time()
            txt = raw.decode(encoding, "replace")
            if not txt.strip():
                raise ValueError("empty response")
            return json.loads(txt)
        except Exception as e:  # noqa: BLE001
            _LAST_CALL[0] = time.time()
            last = e
            time.sleep(base_delay * (i + 1) * 2)
    print(f"  [warn] fetch failed: {url[:90]}... -> {last}", file=sys.stderr)
    return None


def fetch_text(url, referer=None, encoding="gbk", retries=3):
    """GET 纯文本（用于新浪/腾讯行情接口）。"""
    last = None
    for i in range(retries):
        gap = time.time() - _LAST_CALL[0]
        if gap < 3.0:
            time.sleep(3.0 - gap)
        try:
            h = {"User-Agent": UA}
            if referer:
                h["Referer"] = referer
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
                raw = resp.read()
            _LAST_CALL[0] = time.time()
            try:
                return raw.decode(encoding, "replace")
            except Exception:
                return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            _LAST_CALL[0] = time.time()
            last = e
            time.sleep(3.0 * (i + 1))
    print(f"  [warn] fetch_text failed: {url[:90]}... -> {last}", file=sys.stderr)
    return None


def get_indices_em(secids):
    """东方财富批量指数行情。"""
    ids = ",".join(s for _, s in secids)
    url = ("https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=" + ids +
           "&fields=f2,f3,f4,f12,f14")
    js = fetch(url)
    out = {}
    if not js or not js.get("data") or not js["data"].get("diff"):
        return out
    for row in js["data"]["diff"]:
        out[row.get("f14", "")] = {
            "price": row.get("f2"),
            "chg_pct": row.get("f3"),
            "chg": row.get("f4"),
        }
    return out


# 腾讯行情代码映射（备份源，稳定性好、限流宽松）
TX_CODE = {
    "上证指数": "sh000001", "深证成指": "sz399001", "创业板指": "sz399006",
    "科创50": "sh000688", "沪深300": "sh000300", "北证50": "bj899050",
    "大盘价值": "sz399373", "小盘成长": "sz399376", "国证成长": "sz399370",
    "中证红利": "sh000922", "中证1000": "sh000852", "国证2000": "sz399303",
}


def get_indices_tx(names):
    """腾讯行情备份源：v_sh000001="1~上证指数~000001~现价~昨收~今开~..."。"""
    codes = [TX_CODE[n] for n in names if n in TX_CODE]
    if not codes:
        return {}
    txt = fetch_text("https://qt.gtimg.cn/q=" + ",".join(codes),
                     referer="https://gu.qq.com/", encoding="gbk")
    if not txt:
        return {}
    out = {}
    for line in txt.split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        try:
            payload = line.split("=", 1)[1].strip().strip('"')
            parts = payload.split("~")
            if len(parts) < 33:
                continue
            name = parts[1]
            price = safe_num(parts[3])
            prev = safe_num(parts[4])
            chg = safe_num(parts[31])
            chg_pct = safe_num(parts[32])
            # parts[30] 形如 20260918161402 —— 数据源回传的行情时间戳
            if _DATA_DATE[0] is None and len(parts) > 30:
                ts = (parts[30] or "").strip()
                if len(ts) >= 8 and ts[:8].isdigit():
                    _DATA_DATE[0] = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
            if name and price is not None:
                out[name] = {"price": price, "chg": chg, "chg_pct": chg_pct,
                             "_prev": prev, "_src": "tencent"}
        except Exception:
            continue
    return out


def get_indices(secids):
    """先试东财，失败降级到腾讯。"""
    out = get_indices_em(secids)
    if len(out) >= 3:
        for v in out.values():
            v["_src"] = "eastmoney"
        return out
    print("  [info] 东财指数接口不可用，降级到腾讯行情源", file=sys.stderr)
    return get_indices_tx([n for n, _ in secids])


def get_sector_board_tx():
    """腾讯申万一级行业板块（主数据源）。

    接口对海外 IP 友好，一次返回全部 31 个申万一级行业，字段包含：
      name      行业名
      zdf       当日涨跌幅(%)
      zdf_d5    近5日涨跌幅(%)
      zdf_d20   近20日涨跌幅(%)
      zljlr     当日主力净流入(万元)
      zljlr_d5  近5日主力净流入(万元)
      turnover  成交额
    """
    url = ("https://proxy.finance.qq.com/cgi/cgi-bin/rank/pt/getRank"
           "?board_type=hy&sort_type=price&direct=down&offset=0&count=100")
    js = fetch(url, referer="https://gu.qq.com/", base_delay=2.0)
    if not js:
        return []
    rl = (js.get("data") or {}).get("rank_list") or []
    out = []
    for x in rl:
        name = x.get("name")
        if not name:
            continue
        out.append({
            "name": name,
            "chg_pct": safe_num(x.get("zdf")),
            "chg_5d": safe_num(x.get("zdf_d5")),
            "chg_20d": safe_num(x.get("zdf_d20")),
            # 万元 -> 元
            "net_inflow": (safe_num(x.get("zljlr"), 0.0) or 0.0) * 1e4,
            "net_inflow_5d": (safe_num(x.get("zljlr_d5"), 0.0) or 0.0) * 1e4,
            "amount": safe_num(x.get("turnover")),
            "leader": (x.get("lzg") or {}).get("name"),
            "leader_chg": safe_num((x.get("lzg") or {}).get("zdf")),
        })
    return out


def get_sector_board():
    """行业板块数据：优先腾讯（海外可达），失败再试东财。"""
    rows = get_sector_board_tx()
    if rows:
        print(f"      数据源：腾讯行情，行业数 {len(rows)}")
        return rows, "tencent"
    print("  [info] 腾讯行业接口不可用，降级尝试东财 ...", file=sys.stderr)
    rows = get_sector_board_em()
    return rows, "eastmoney"


def get_sector_board_em():
    """东财行业板块（备份源）：小页分页，降低单次请求体量。"""
    rows = []
    page = 1
    page_size = 50
    max_pages = 6
    while page <= max_pages:
        url = ("https://push2.eastmoney.com/api/qt/clist/get?pn=%d&pz=%d&po=1&np=1"
               "&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f12,f13,f14,f3,f62,f6" % (page, page_size))
        js = fetch(url, retries=2, referer="https://data.eastmoney.com/", base_delay=2.0)
        if not js or not js.get("data") or not js["data"].get("diff"):
            break
        chunk = js["data"]["diff"]
        for x in chunk:
            nm = x.get("f14")
            if not nm:
                continue
            rows.append({
                "name": nm,
                "chg_pct": safe_num(x.get("f3")),
                "chg_5d": None,
                "chg_20d": None,
                "net_inflow": safe_num(x.get("f62"), 0.0) or 0.0,
                "net_inflow_5d": None,
                "amount": safe_num(x.get("f6")),
                "leader": None,
                "leader_chg": None,
            })
        total = js["data"].get("total") or 0
        if len(chunk) < page_size or len(rows) >= total:
            break
        page += 1
    # 东财返回的是细分板块，聚合到申万一级
    return aggregate_em_rows(rows)


def aggregate_em_rows(rows):
    """把东财细分板块按申万一级聚合。"""
    agg = {}
    for r in rows:
        name = r["name"]
        for sw, aliases in SW_MAP.items():
            if name == sw or name in aliases:
                d = agg.setdefault(sw, {"chg": [], "net": 0.0, "w": 0.0})
                amt = r.get("amount") or 0
                w = amt if amt > 0 else 1.0
                if r.get("chg_pct") is not None:
                    d["chg"].append((r["chg_pct"], w))
                d["net"] += r.get("net_inflow") or 0.0
                d["w"] += w
                break
    out = []
    for sw, d in agg.items():
        chg = None
        if d["chg"]:
            tot = sum(w for _, w in d["chg"])
            chg = round(sum(c * w for c, w in d["chg"]) / tot, 2) if tot else None
        out.append({
            "name": sw, "chg_pct": chg, "chg_5d": None, "chg_20d": None,
            "net_inflow": d["net"], "net_inflow_5d": None,
            "amount": None, "leader": None, "leader_chg": None,
        })
    return out


def aggregate_to_sw(boards):
    """把东财细分板块按申万一级口径聚合（涨跌幅取成交额加权，资金流求和）。"""
    agg = {}
    for b in boards:
        name = b.get("f14", "")
        chg = b.get("f3")
        net = b.get("f62")          # 主力净流入（元）
        amt = b.get("f6")           # 成交额（元）
        try:
            chg = float(chg)
        except (TypeError, ValueError):
            continue
        try:
            net = float(net) if net not in (None, "-", "") else 0.0
        except (TypeError, ValueError):
            net = 0.0
        try:
            amt = float(amt) if amt not in (None, "-", "") else 0.0
        except (TypeError, ValueError):
            amt = 0.0

        for sw, aliases in SW_MAP.items():
            # 精确匹配优先，避免 "半导体" 被 "半导体材料" 之外的规则误吞
            if name == sw or name in aliases:
                d = agg.setdefault(sw, {"wsum": 0.0, "w": 0.0, "net": 0.0, "amt": 0.0})
                w = amt if amt > 0 else 1.0
                d["wsum"] += chg * w
                d["w"] += w
                d["net"] += net
                d["amt"] += amt
                break
    out = {}
    for sw, d in agg.items():
        out[sw] = {
            "chg_pct": round(d["wsum"] / d["w"], 2) if d["w"] else None,
            "net": d["net"],
            "amt": d["amt"],
        }
    return out


def get_market_breadth():
    """涨跌家数：用沪深京全市场统计接口。"""
    url = ("https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1&po=1&np=1&fltt=2&invt=2"
           "&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048&fields=f12")
    js = fetch(url)
    total = None
    if js and js.get("data"):
        total = js["data"].get("total")
    return total


def safe_num(v, default=None):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return default


def guess_trade_date(now):
    """兜底：按日历推算最近交易日（跳过周六周日）。

    仅在拿不到数据源时间戳时使用；不覆盖法定节假日，
    因此优先级低于 _DATA_DATE。
    """
    d = now
    # 周六 -> 周五；周日 -> 周五
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    # 交易日盘前（15:00 前）当日行情尚未产生，取上一交易日
    if d.weekday() < 5 and now.hour < 15:
        d = d - timedelta(days=1)
        while d.weekday() >= 5:
            d = d - timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def build_dataset():
    print("[1/4] 拉取指数行情 ...")
    main_idx = get_indices(MAIN_INDICES)
    style_idx = get_indices(STYLE_INDICES)

    print("[2/4] 拉取行业板块（涨跌 + 资金流）...")
    boards, src = get_sector_board()

    print(f"[3/4] 整理到申万一级口径（源：{src}）...")
    by_name = {b["name"]: b for b in boards}
    sectors = []
    for name in DISPLAY_SECTORS:
        d = by_name.get(name)
        if not d:
            continue
        sectors.append(d)
    sectors.sort(key=lambda x: (x["chg_pct"] is None, -(x["chg_pct"] or 0)))

    print("[4/4] 组包 ...")
    now = datetime.now(CST)
    # 优先用数据源回传的行情日期（可自动处理周末/节假/盘前），取不到再按日历推算
    trade_date = _DATA_DATE[0] or guess_trade_date(now)
    ds = {
        "trade_date": trade_date,
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S") + " (CST)",
        "_trade_date_src": "datasource" if _DATA_DATE[0] else "calendar",
        "indices": {k: v for k, v in main_idx.items()},
        "style": {k: v for k, v in style_idx.items()},
        "sectors": sectors,
        "source": ("腾讯财经行情接口（proxy.finance.qq.com）" if src == "tencent"
                   else "东方财富公开行情接口（push2.eastmoney.com）"),
        "_data_source_key": src,
    }
    return ds


def fmt_pct(v, digits=2):
    if v is None:
        return "--"
    return f"{'+' if v > 0 else ''}{v:.{digits}f}%"


def fmt_money_yi(v):
    """元 -> 亿元，带正负号。"""
    if v is None:
        return "--"
    yi = v / 1e8
    return f"{'+' if yi > 0 else ''}{yi:,.1f}"


def cls(v):
    if v is None:
        return ""
    return "up" if v > 0 else ("down" if v < 0 else "")


def heat_style(chg):
    """按涨跌幅生成热力块背景色（红涨绿跌，深浅表强度）。"""
    if chg is None:
        return "background:linear-gradient(150deg,#2a2f35,#22272c)", "#c9d2da", "#8b959e"
    a = min(abs(chg), 5.0)
    t = a / 5.0
    if chg >= 0:
        # 红：从暗红到亮红
        c1 = f"rgb({int(90 + 165 * t)},{int(44 + 33 * t)},{int(44 + 33 * t)})"
        c2 = f"rgb({int(60 + 130 * t)},{int(30 + 20 * t)},{int(30 + 20 * t)})"
        fg = "#fff" if t > 0.35 else "#ffd9d9"
        fg2 = "#ffe0e0" if t > 0.35 else "#d4a8a8"
    else:
        c1 = f"rgb({int(40 + 10 * t)},{int(120 + 100 * t)},{int(90 + 60 * t)})"
        c2 = f"rgb({int(30 + 8 * t)},{int(92 + 72 * t)},{int(68 + 45 * t)})"
        fg = "#fff" if t > 0.5 else "#c0eeda"
        fg2 = "#bff0d8" if t > 0.5 else "#90b8a4"
    return f"background:linear-gradient(150deg,{c1},{c2})", fg, fg2


def sparkline(values, color, w=120, h=22):
    """把一串数值画成迷你折线（内联 SVG polyline）。"""
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = w / (len(vals) - 1)
    pts = []
    for i, v in enumerate(vals):
        y = h - 3 - (v - lo) / span * (h - 6)
        pts.append(f"{i * step:.1f},{y:.1f}")
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" '
            f'points="{" ".join(pts)}"/></svg>')


def render_html(ds):
    idx = ds["indices"]
    style = ds["style"]
    sectors = ds["sectors"]

    # 数据日期可能是"最近交易日"（周末 / 盘前刷新时，与页面生成日期不同天），
    # 此时在日期后加标注，避免读者误以为数据是当天的。
    is_fresh_day = ds["trade_date"] == ds["updated_at"][:10]
    date_tag = "" if is_fresh_day else "（最近交易日）"
    lead_tag = "今日主线" if is_fresh_day else "最近交易日主线"

    # ---- 指数条 ----
    idx_order = ["上证指数", "深证成指", "创业板指", "科创50", "沪深300", "北证50"]
    strip = []
    for name in idx_order:
        d = idx.get(name)
        if not d:
            continue
        chg = safe_num(d.get("chg_pct"))
        c = cls(chg)
        color = "#ff4d4d" if (chg or 0) > 0 else ("#19c37d" if (chg or 0) < 0 else "#3fd0e0")
        price = d.get("price")
        price_s = f"{price:,.2f}" if isinstance(price, (int, float)) else str(price)
        chgv = d.get("chg")
        chg_s = f"{chgv:+,.2f}" if isinstance(chgv, (int, float)) else "--"
        strip.append(f'''<div class="idx">
      <div class="name">{name}</div>
      <div class="val {c}">{price_s}</div>
      <div class="chg {c}">{fmt_pct(chg)} &nbsp;{chg_s}</div>
      <svg class="spark" width="120" height="22" viewBox="0 0 120 22"><line x1="0" y1="11" x2="120" y2="11" stroke="#1d232b" stroke-width="1" stroke-dasharray="2 3"/></svg>
    </div>''')

    # ---- 热力网格 ----
    cells = []
    for s in sectors:
        chg = s["chg_pct"]
        bg, fg, fg2 = heat_style(chg)
        arrow = "↑" if (chg or 0) > 0.001 else ("↓" if (chg or 0) < -0.001 else "·")
        cells.append(f'''<div class="cell" style="{bg}">
            <div class="cn">{s["name"]}</div>
            <div><div class="cd" style="color:{fg}">{fmt_pct(chg)}</div>
            <div class="c5" style="color:{fg2}">主力 {fmt_money_yi(s["net_inflow"])}亿</div></div>
            <span class="ci">{arrow}</span>
          </div>''')

    # ---- 主力资金双向条形 ----
    flow_rows = sorted([s for s in sectors if s["net_inflow"] is not None],
                       key=lambda x: -x["net_inflow"])
    inflows = [s for s in flow_rows if s["net_inflow"] > 0][:7]
    outflows = sorted([s for s in flow_rows if s["net_inflow"] < 0], key=lambda x: x["net_inflow"])[:7]
    max_v = max([abs(s["net_inflow"]) / 1e8 for s in flow_rows] or [1])
    SCALE_MAX_PX = 115.0
    AX = 295.0
    k = SCALE_MAX_PX / max_v if max_v else 1

    def bar(s, positive, y):
        yi = s["net_inflow"] / 1e8
        w = max(2.0, abs(yi) * k)
        if positive:
            rect = f'<rect x="{AX:.0f}" y="{y-11}" width="{w:.1f}" height="16" rx="3" fill="#ff4d4d"/>'
            tx = AX + w + 5
            anch = "start"
            col = "#ff4d4d"
        else:
            rect = f'<rect x="{AX-w:.1f}" y="{y-11}" width="{w:.1f}" height="16" rx="3" fill="#19c37d"/>'
            tx = AX - w - 5
            anch = "end"
            col = "#19c37d"
        return (f'<g><text x="88" y="{y+4}" fill="#d8dee6" font-size="11" text-anchor="end">{s["name"]}</text>'
                f'{rect}<text x="{tx:.1f}" y="{y+4}" fill="{col}" font-size="10.5" '
                f'text-anchor="{anch}">{yi:+,.1f}</text></g>')

    flow_svg = []
    y = 34
    gridlines = "".join(
        f'<line x1="{AX + 25*i:.0f}" y1="16" x2="{AX + 25*i:.0f}" y2="386" stroke="#161b21" stroke-width="1"/>'
        for i in range(1, 7))
    gridlines += "".join(
        f'<line x1="{AX - 25*i:.0f}" y1="16" x2="{AX - 25*i:.0f}" y2="386" stroke="#161b21" stroke-width="1"/>'
        for i in range(1, 7))
    flow_svg.append(gridlines)
    step_yi = 50.0 / k if k else 0
    flow_svg.append(f'<text x="{AX+25:.0f}" y="9" fill="#3a4450" font-size="8" text-anchor="middle">+{step_yi:.0f}亿</text>')
    flow_svg.append(f'<text x="{AX-25:.0f}" y="9" fill="#3a4450" font-size="8" text-anchor="middle">-{step_yi:.0f}亿</text>')
    for s in inflows:
        flow_svg.append(bar(s, True, y)); y += 26
    for s in outflows:
        flow_svg.append(bar(s, False, y)); y += 26
    flow_svg.append(f'<text x="{AX:.0f}" y="399" fill="#3a4450" font-size="8" text-anchor="middle">每格约 {step_yi:.0f}亿元 · 主力资金当日净额</text>')
    flow_svg.append(f'<line x1="{AX:.0f}" y1="12" x2="{AX:.0f}" y2="386" stroke="#262e38" stroke-width="1"/>')
    flow_svg.append(f'<text x="{AX:.0f}" y="9" fill="#5e6975" font-size="9" text-anchor="middle">0</text>')

    # ---- 风格轮动 ----
    def sv(name):
        d = style.get(name) or {}
        return safe_num(d.get("chg_pct"))

    style_rows = [
        ("大盘价值 ↔ 小盘成长", "小盘成长", "大盘价值"),
        ("价值红利 ↔ 硬科技", "科创50", "中证红利"),
        ("大盘 ↔ 小盘", "中证1000", "沪深300"),
        ("成长 ↔ 价值", "国证成长", "大盘价值"),
    ]
    style_boxes = []
    for title, left, right in style_rows:
        lv, rv = sv(left), sv(right)
        if lv is None or rv is None:
            continue
        diff = lv - rv
        win = left if diff > 0 else right
        wcls = "up" if diff > 0 else "down"
        # RS 曲线：用两点差值生成一条上扬/下探的示意曲线
        pts = []
        n = 11
        for i in range(n):
            t = i / (n - 1)
            base = 32 - diff * 3.0 * (t - 0.5) * 2
            base = max(6, min(58, base))
            pts.append(f"{t*220:.0f},{base:.1f}")
        color = "#a78bfa" if diff > 0 else "#3fd0e0"
        style_boxes.append(f'''<div class="stylebox">
            <div class="styletitle"><span>{title}</span><span class="win mono {wcls}">{win}占优</span></div>
            <svg width="100%" viewBox="0 0 220 64">
              <line x1="0" y1="32" x2="220" y2="32" stroke="#1d232b" stroke-width="1" stroke-dasharray="3 3"/>
              <text x="2" y="11" fill="#5e6975" font-size="8">{left}强</text>
              <text x="2" y="61" fill="#5e6975" font-size="8">{right}强</text>
              <polyline fill="none" stroke="{color}" stroke-width="2" points="{" ".join(pts)}"/>
              <circle cx="220" cy="{pts[-1].split(',')[1]}" r="2.6" fill="{color}"/>
            </svg>
            <div class="mono" style="font-size:10px;color:var(--ink-3);margin-top:6px">{left} {fmt_pct(lv)} vs {right} {fmt_pct(rv)}<br>价差 <span class="{wcls}">{abs(diff):.2f} pct</span></div>
          </div>''')

    # ---- 渲染热力块 & 表格 ----
    sectors_sorted = sectors
    top_up = [s for s in sectors_sorted if (s["chg_pct"] or 0) > 0][:3]
    top_dn = sorted([s for s in sectors_sorted if (s["chg_pct"] or 0) < 0], key=lambda x: x["chg_pct"])[:3]
    lead_ok = "、".join(s["name"] for s in top_up) or "无"
    lead_bad = "、".join(s["name"] for s in top_dn) or "无"

    inflow_top = [s for s in flow_rows if s["net_inflow"] > 0][:3]
    outflow_top = sorted([s for s in flow_rows if s["net_inflow"] < 0], key=lambda x: x["net_inflow"])[:3]
    inflow_sum = sum(s["net_inflow"] for s in inflow_top) / 1e8

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股行业轮动与资金流向监控终端 · {ds["trade_date"]}</title>
<style>
  :root{{
    --bg:#08090b; --bg-2:#0c0e11; --panel:#101317; --panel-2:#14181d;
    --line:#1d232b; --line-2:#262e38;
    --ink:#d8dee6; --ink-2:#94a0ae; --ink-3:#5e6975;
    --up:#ff4d4d; --up-bg:rgba(255,77,77,.14); --up-dim:#7a2727;
    --down:#19c37d; --down-bg:rgba(25,195,125,.14); --down-dim:#1c5640;
    --amber:#e8b339; --cyan:#3fd0e0; --violet:#a78bfa;
    --mono:"SF Mono",ui-monospace,"JetBrains Mono","Cascadia Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    --r:10px;
  }}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{
    font-family:var(--sans);
    background:radial-gradient(900px 500px at 88% -8%,rgba(255,77,77,.07) 0%,transparent 60%),
      radial-gradient(700px 420px at 5% 105%,rgba(25,195,125,.05) 0%,transparent 55%),var(--bg);
    color:var(--ink);line-height:1.55;padding:20px 16px 56px;min-height:100vh;
    font-variant-numeric:tabular-nums;font-feature-settings:"tnum";-webkit-font-smoothing:antialiased;
  }}
  .wrap{{max-width:1280px;margin:0 auto;position:relative;z-index:1}}
  .mono{{font-family:var(--mono)}}
  body::before{{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
    background:repeating-linear-gradient(0deg,rgba(255,255,255,.012) 0px,rgba(255,255,255,.012) 1px,transparent 1px,transparent 3px);}}
  header{{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:14px;
    padding-bottom:16px;margin-bottom:18px;border-bottom:1px solid var(--line);}}
  .brand{{display:flex;align-items:center;gap:13px}}
  .logo{{width:42px;height:42px;border-radius:10px;flex:none;
    background:linear-gradient(150deg,#211512,#0c1014);border:1px solid var(--line-2);
    display:flex;align-items:center;justify-content:center;
    box-shadow:0 0 0 1px rgba(255,77,77,.12),0 6px 18px rgba(0,0,0,.5);}}
  h1{{font-size:19px;font-weight:700;letter-spacing:.3px}}
  .sub{{font-size:12.5px;color:var(--ink-3);margin-top:2px}}
  .sub b{{color:var(--cyan);font-weight:600}}
  .meta{{display:flex;flex-direction:column;align-items:flex-end;gap:7px}}
  .live{{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11.5px;
    color:var(--down);background:var(--down-bg);border:1px solid var(--down-dim);
    padding:4px 10px;border-radius:999px;letter-spacing:.5px;}}
  .live .dot{{width:7px;height:7px;border-radius:50%;background:var(--down);box-shadow:0 0 8px var(--down);animation:pulse 1.8s infinite}}
  @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
  .stamp{{font-family:var(--mono);font-size:11.5px;color:var(--ink-3)}}
  .strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:1px;
    background:var(--line);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;margin-bottom:14px;}}
  .idx{{background:var(--panel);padding:12px 14px}}
  .idx .name{{font-size:12px;color:var(--ink-2)}}
  .idx .val{{font-family:var(--mono);font-size:21px;font-weight:600;margin-top:4px;letter-spacing:.3px}}
  .idx .chg{{font-family:var(--mono);font-size:12.5px;margin-top:1px}}
  .up{{color:var(--up)}} .down{{color:var(--down)}}
  .spark{{margin-top:6px;display:block}}
  .lead{{background:linear-gradient(90deg,rgba(232,179,57,.07),transparent 70%);
    border:1px solid var(--line);border-left:3px solid var(--amber);border-radius:var(--r);
    padding:12px 16px;margin-bottom:20px;font-size:13.5px;color:var(--ink);}}
  .lead .tag{{font-family:var(--mono);font-size:11px;color:var(--amber);letter-spacing:1px;text-transform:uppercase;margin-right:8px}}
  .lead b{{color:#fff}}
  .grid{{display:grid;grid-template-columns:1.62fr 1fr;gap:16px;align-items:start}}
  @media(max-width:920px){{.grid{{grid-template-columns:1fr}}}}
  .panel{{background:linear-gradient(180deg,var(--panel),var(--bg-2));border:1px solid var(--line);
    border-radius:var(--r);padding:15px 16px;margin-bottom:16px;}}
  .ph{{display:flex;align-items:center;justify-content:space-between;margin-bottom:13px;gap:10px;flex-wrap:wrap}}
  .ph h2{{font-size:14px;font-weight:700;letter-spacing:.3px;display:flex;align-items:center;gap:8px}}
  .ph .hint{{font-family:var(--mono);font-size:10.5px;color:var(--ink-3)}}
  .ic{{width:16px;height:16px;flex:none;color:var(--up)}}
  .hmlegend{{display:flex;align-items:center;gap:4px;font-family:var(--mono);font-size:10px;color:var(--ink-3)}}
  .hmlegend .sw{{width:14px;height:10px;border-radius:2px;display:inline-block}}
  .heat{{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}}
  @media(max-width:600px){{.heat{{grid-template-columns:repeat(2,1fr)}}}}
  .cell{{border-radius:8px;padding:9px 10px 8px;border:1px solid rgba(255,255,255,.04);
    position:relative;overflow:hidden;min-height:78px;display:flex;flex-direction:column;
    justify-content:space-between;transition:transform .12s;}}
  .cell:hover{{transform:translateY(-2px)}}
  .cell .cn{{font-size:12.5px;font-weight:600;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.5)}}
  .cell .cd{{font-family:var(--mono);font-size:18px;font-weight:700;line-height:1;letter-spacing:.3px}}
  .cell .c5{{font-family:var(--mono);font-size:10.5px;opacity:.82;margin-top:3px}}
  .cell .ci{{position:absolute;right:-6px;bottom:-8px;font-family:var(--mono);font-size:40px;font-weight:800;opacity:.07;line-height:1}}
  .flownote{{font-size:11.5px;color:var(--ink-3);margin-top:2px;line-height:1.65}}
  .stylegrid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
  @media(max-width:600px){{.stylegrid{{grid-template-columns:1fr}}}}
  .stylebox{{background:var(--bg-2);border:1px solid var(--line);border-radius:8px;padding:11px 12px}}
  .styletitle{{font-size:11.5px;color:var(--ink-2);margin-bottom:8px;display:flex;justify-content:space-between;gap:6px}}
  .styletitle .win{{font-family:var(--mono);font-size:10.5px}}
  .rankrow{{display:grid;grid-template-columns:84px 1fr 66px;align-items:center;gap:8px;padding:5px 0;border-bottom:1px dashed var(--line)}}
  .rankrow:last-child{{border-bottom:none}}
  .rankrow .rn{{font-size:12px;color:var(--ink)}}
  .rankrow .rv{{font-family:var(--mono);font-size:12px;text-align:right}}
  .bar-track{{position:relative;height:14px;background:var(--bg-2);border-radius:3px;overflow:hidden;border:1px solid var(--line)}}
  .bar-fill{{position:absolute;top:0;bottom:0;border-radius:3px}}
  footer{{margin-top:24px;padding-top:14px;border-top:1px solid var(--line);
    display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;font-size:11.5px;color:var(--ink-3)}}
  .disc{{color:var(--ink-3);font-size:11px;line-height:1.7;margin-top:14px}}
  .disc b{{color:var(--amber)}}
  .srccard{{background:var(--bg-2);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
  .srcgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}}
  .srcgrid .t{{font-size:11.5px;color:var(--cyan);font-weight:600;margin-bottom:4px}}
  .srcgrid .d{{font-size:11px;color:var(--ink-3);line-height:1.6}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      <div class="logo"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ff4d4d" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l5-5 3 3 7-8"/><path d="M14 4h5v5"/></svg></div>
      <div>
        <h1>A股行业轮动与资金流向监控终端</h1>
        <div class="sub">申万一级行业 · 主力资金流 · 风格轮动 · 研究视角研判 · <b>每日自动更新</b></div>
      </div>
    </div>
    <div class="meta">
      <span class="live"><span class="dot"></span>数据已结算</span>
      <span class="stamp">数据日期 {ds["trade_date"]}{date_tag} · 更新于 {ds["updated_at"]}</span>
    </div>
  </header>

  <div class="strip">
    {"".join(strip)}
  </div>

  <div class="lead">
    <span class="tag">{lead_tag}</span>
    行业涨幅前三：<b class="up">{lead_ok}</b>；跌幅前三：<b class="down">{lead_bad}</b>。
    主力资金净流入前三（{ "、".join(s["name"] for s in inflow_top) }）合计 <b class="up">+{inflow_sum:,.1f}亿</b>；
    净流出前三：<b class="down">{ "、".join(s["name"] for s in outflow_top) }</b>。
    <span class="mono" style="color:var(--ink-3)">数据每日自动更新 · 红涨绿跌（A股惯例）。</span>
  </div>

  <div class="grid">
    <div>
      <div class="panel">
        <div class="ph">
          <h2><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>一级行业轮动热力图 · {len(sectors)}行业</h2>
          <div class="hmlegend"><span>跌</span>
            <span class="sw" style="background:#19c37d"></span><span class="sw" style="background:#1c5640"></span>
            <span class="sw" style="background:#22282f"></span>
            <span class="sw" style="background:#7a2727"></span><span class="sw" style="background:#ff4d4d"></span>
            <span>涨</span></div>
        </div>
        <div class="heat">
          {"".join(cells)}
        </div>
        <div class="flownote" style="margin-top:10px">色深=当日涨跌幅绝对值；<span class="up">红=上涨</span>、<span class="down">绿=下跌</span>（A股惯例）。块内第二行为当日主力资金净额。</div>
      </div>

      <div class="panel">
        <div class="ph">
          <h2><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v18"/><path d="M5 10l7-7 7 7"/><path d="M5 14l7 7 7-7"/></svg>主力资金 · 行业净流入 / 净流出排行</h2>
          <span class="hint">单位 ¥亿 · <span class="up">红=净流入</span> / <span class="down">绿=净流出</span></span>
        </div>
        <svg width="100%" viewBox="0 0 640 400" preserveAspectRatio="xMidYMid meet">
          {"".join(flow_svg)}
        </svg>
      </div>
    </div>

    <div>
      <div class="panel">
        <div class="ph">
          <h2><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 2v20"/><path d="M2 12h20"/></svg>风格轮动 · 相对强弱</h2>
          <span class="hint">当日</span>
        </div>
        <div class="stylegrid">
          {"".join(style_boxes)}
        </div>
      </div>

      <div class="panel">
        <div class="ph">
          <h2><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/></svg>行业涨跌与资金全景</h2>
          <span class="hint">按涨跌幅排序</span>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr style="color:var(--ink-3);font-size:11px">
            <th style="text-align:left;padding:5px 4px;font-weight:500">行业</th>
            <th style="text-align:right;padding:5px 4px;font-weight:500">涨跌幅</th>
            <th style="text-align:right;padding:5px 4px;font-weight:500">主力净额(亿)</th>
          </tr></thead>
          <tbody>
          {"".join(f'<tr style="border-top:1px solid var(--line)"><td style="padding:5px 4px">{s["name"]}</td><td class="{cls(s["chg_pct"])} mono" style="text-align:right;padding:5px 4px">{fmt_pct(s["chg_pct"])}</td><td class="{cls(s["net_inflow"])} mono" style="text-align:right;padding:5px 4px">{fmt_money_yi(s["net_inflow"])}</td></tr>' for s in sectors)}
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="ph">
      <h2><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/></svg>数据来源与说明</h2>
      <span class="hint">数据日期 {ds["trade_date"]}{date_tag}</span>
    </div>
    <div class="srcgrid">
      <div class="srccard"><div class="t">数据来源</div><div class="d">{ds["source"]}<br>行业涨跌幅按板块成交额加权聚合到申万一级口径；主力资金净额为同口径求和。</div></div>
      <div class="srccard"><div class="t">更新机制</div><div class="d">GitHub Actions 每交易日收盘后自动抓取并重新生成本页（约 15:30 CST）。全流程无人工干预。</div></div>
      <div class="srccard"><div class="t">口径提示</div><div class="d">不同数据商（Wind / 财联社 / 东财等）的行业分类与资金统计口径存在差异，数值可能不一致，请以官方原始披露为准。</div></div>
    </div>
  </div>

  <div class="disc">
    <b>免责声明：</b>本终端所有数据来自公开行情接口，仅供参考与学习，<b>不构成任何投资建议</b>。市场有风险，决策需独立判断。
  </div>

  <footer>
    <span class="mono">SECTOR ROTATION &amp; CAPITAL FLOW TERMINAL</span>
    <span class="mono">自动生成 · 数据日期 {ds["trade_date"]}{date_tag} · 更新 {ds["updated_at"]}</span>
  </footer>
</div>
</body>
</html>
'''
    return html


def load_seed():
    """兜底数据：当所有接口都不可用时，用一个已知的最近交易日快照，
    保证页面不会变成空白（页面上会显示真实数据日期，用户可自行判断新鲜度）。
    """
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ds = None
    try:
        ds = build_dataset()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 抓取过程异常：{e}", file=sys.stderr)

    fresh = bool(ds and ds.get("sectors"))

    if not fresh:
        print("[warn] 实时抓取失败，尝试使用兜底快照 seed.json", file=sys.stderr)
        seed = load_seed()
        if seed:
            ds = seed
            ds["_stale"] = True
        else:
            print("[error] 无兜底数据，终止（不覆盖已有页面）。", file=sys.stderr)
            sys.exit(1)

    # 保护：如果页面已存在且现有数据更新，不倒退覆盖
    out_html = os.path.join(OUT_DIR, "index.html")
    out_json = os.path.join(OUT_DIR, "data.json")
    if not fresh and os.path.exists(out_json):
        try:
            with open(out_json, encoding="utf-8") as f:
                prev = json.load(f)
            if prev.get("trade_date") == ds.get("trade_date") and not prev.get("_stale"):
                print("[info] 现有页面数据同为最新，跳过覆盖。")
                return
        except Exception:
            pass

    html = render_html(ds)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(ds, f, ensure_ascii=False, indent=2)

    tag = "（兜底快照）" if not fresh else ""
    print(f"[done] 数据日期 {ds['trade_date']}，行业数 {len(ds['sectors'])} {tag}")
    print(f"[done] 已生成 {out_html}")


if __name__ == "__main__":
    main()

