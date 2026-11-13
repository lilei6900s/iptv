#!/usr/bin/env python3
"""Rebuild the merged + deduped IPTV playlist from fresh upstreams.

Priority: Guovin (auto-tested CCTV+satellite) > bestK (satellite+HK/MO/TW)
         > iptv-org jp > iptv-org kr.
Dedup by normalized name, one entry per channel, first occurrence wins.
Run daily by GitHub Actions (.github/workflows/daily-rebuild.yml).
2026-11-11: 港澳台组内按香港/澳门/台湾排序；日韩频道名尽量转中文。
"""

import re
import sys
import urllib.request

SOURCES = [
    ("guovin", "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u"),
    ("bestk", "https://raw.githubusercontent.com/bestK/iptv/main/iptv.m3u"),
    ("jp", "https://iptv-org.github.io/iptv/countries/jp.m3u"),
    ("kr", "https://iptv-org.github.io/iptv/countries/kr.m3u"),
    ("hk", "https://iptv-org.github.io/iptv/countries/hk.m3u"),
    ("tw", "https://iptv-org.github.io/iptv/countries/tw.m3u"),
    ("vn", "https://iptv-org.github.io/iptv/countries/vn.m3u"),
    ("la", "https://iptv-org.github.io/iptv/countries/la.m3u"),
    ("ph", "https://iptv-org.github.io/iptv/countries/ph.m3u"),
]

REPLACEMENTS = [
    ("新聞", "新闻"), ("電視", "电视"), ("衛視", "卫视"), ("綜合", "综合"),
    ("娛樂", "娱乐"), ("體育", "体育"), ("電影", "电影"), ("資訊", "资讯"),
    ("財經", "财经"), ("綜藝", "综艺"), ("臺視", "台视"), ("民視", "民视"),
    ("亞洲", "亚洲"), ("鳳凰", "凤凰"), ("華視", "华视"),
    ("臺", "台"), ("鳳", "凤"), ("廣", "广"), ("劇", "剧"), ("亞", "亚"), ("華", "华"),
]


def to_simp(s):
    for a, b in REPLACEMENTS:
        s = s.replace(a, b)
    return s


# Region words kept inside parentheses when normalizing a name: they tell
# apart two different channels that share a base name (e.g. Good TV Taiwan
# vs Good TV South Korea). Resolution/quality parentheticals are still dropped.
REGION_WORDS = ("South Korea", "North Korea", "Taiwan", "Hong Kong", "Japan",
                "China", "Singapore", "Malaysia", "Australia", "USA", "Canada")


def _keep_region_paren(m):
    inner = m.group(1)
    if any(w in inner for w in REGION_WORDS):
        return " " + inner + " "
    return " "


def norm_key(name):
    n = name
    n = re.sub(r"\(([^)]*)\)", _keep_region_paren, n)
    n = re.sub(r"\[[^\]]*\]", "", n)
    n = n.strip()
    n = to_simp(n)
    n = re.sub(r"^TVB(?=[\u4e00-\u9fff])", "", n)
    n = n.replace("RTHK TV", "RTHK")
    n = re.sub(r"\s+(1080p|720p|1080i|4K|真4K|高清|超清|HD)\s*$", "", n, flags=re.I)
    n = re.sub(r"(高清|超清)$", "", n)
    n = re.sub(r"^(CCTV-\d+)综合$", r"\1", n)
    if n.endswith("台"):
        n = n[:-1]
    n = re.sub(r"[\s\-]", "", n)
    return ALIASES.get(n, n)


# English names that are the same channel as a Chinese entry: merge them
# into one entry instead of keeping a duplicate (e.g. TVB Jade = 翡翠台).
ALIASES = {
    "Jade": "翡翠",
    "PhoenixChineseChannel": "凤凰中文",
    "PhoenixInfoNewsChannel": "凤凰资讯",
    "CelestialMovies": "天映频道",
    "TVBSAsia": "TVBS亚洲",
    "TVBSNews": "TVBS新闻",
    "CTiNews": "中天新闻",
    "EBCFinancialNews": "东森财经新闻",
    "EBCForeignMovie": "东森洋片",
    "TaiwanIndigenousTV": "IndigenousTV",
    "ZhejiangSatelliteTV": "浙江卫视",
    "HunanTV": "湖南卫视",
    "XinjiangTV1": "新疆卫视",
    "XizangTVTibetan": "西藏卫视",
    "TTVNews": "台视新闻",
    "MeiAhMovieChannel": "美亚电影",
    "广东大湾区": "大湾区卫视",
    "EBSKids": "韩国EBS少儿",  # upstream added 韩国EBS少儿; same channel as EBS Kids
}


# Show the Chinese name for iptv-org's English-named HK/TW channels.
DISPLAY_NAMES = {
    "FTV": "民视",
    "FTVTaiwan": "民视",
    "FTVOne": "民视一台",
    "TTV": "台视",
    "CTS": "华视",
    "CTSNews": "华视新闻",
    "PTS3": "公视3台",
    "SETNews": "三立新闻",
    "EBCNews": "东森新闻",
    "CTiVariety": "中天综合",
    "DaAi1": "大爱一台",
    "DaAi2": "大爱二台",
    "HakkaTV": "客家电视",
    "IndigenousTV": "原住民电视",
    "MOMOTV": "MOMO亲子台",
    "HOYInfotainment": "HOY资讯台",
    "HongKongInternationalBusinessChannel": "香港国际财经台",
}


# 日韩频道中文名（2026-11-11 用户要求：能改成中文的就改，不能改的保持原样）。
# 键是 norm_key（已去掉清晰度/标记后缀），值是中文核心名；清晰度与 [Not 24/7]
# 等后缀会原样保留。呼号类（HLxx-DTV）与含义不明的缩写不在表里，保持原名。
JP_KR_DISPLAY_NAMES = {
    "NipponTV": "日本电视台",
    "TVTokyo": "东京电视台",
    "Arirang": "阿里郎",
    "ArirangTV": "阿里郎电视台",
    "ArirangRadio": "阿里郎电台",
    "TBSTV": "TBS电视台",
    "EBS1TV": "韩国EBS1台",
    "EBS2TV": "韩国EBS2台",
    "EBSEnglish": "韩国EBS英语台",
    "EBSKids": "韩国EBS少儿台",
    "EBSPlus1": "韩国EBS Plus 1台",
    "EBSPlus2": "韩国EBS Plus 2台",
    "TVChosun": "TV朝鲜",
    "TVChosun2": "TV朝鲜2台",
    "MBCDramaSouthKorea": "MBC电视剧台",
    "MBCGyeongnamTV": "MBC庆南电视台",
    "KTVSouthKorea": "韩国政策电视台",
    "YTN": "YTN新闻台",
    "MTN": "MTN财经台",
    "NationalAssemblyTV": "韩国国会电视台",
    "GugakTV": "韩国国乐电视台",
    "GugbangTV": "韩国国防电视台",
    "BBSTVSouthKorea": "韩国佛教电视台",
    "BTNTVSouthKorea": "BTN佛教电视台",
    "Weathernews": "气象新闻台",
}

_SUFFIX_RE = re.compile(r"^(.*?)((?: \([0-9]+[pi]\))?(?: \[[^\]]*\])?)$")


def rename_jp_kr(k, disp):
    """Rename a JP/KR display name to Chinese when a mapping exists.
    Keeps the resolution / [flag] suffix. NHK General TV is matched by
    prefix because its callsign (JOJG-DTV etc.) varies by station."""
    if k.startswith("NHKGeneralTV"):
        core = "NHK综合电视台"
    elif k in JP_KR_DISPLAY_NAMES:
        core = JP_KR_DISPLAY_NAMES[k]
    else:
        return disp
    m = _SUFFIX_RE.match(disp)
    if m:
        return core + m.group(2)
    return core


# Channels the user asked to leave out (2026-11-11): CCTV pay channels and
# past Spring Festival Gala recordings. Matched on the normalized name, so
# they stay out of every daily rebuild, not just this one snapshot.
EXCLUDE_KEYS = {
    "文化精品", "央视台球", "风云音乐", "第一剧场", "风云剧场", "怀旧剧场",
    "女性时尚", "高尔夫网球", "风云足球", "电视指南", "世界地理", "兵器科技",
    "CHC家庭影院", "CHC动作电影",
    # CGTN channels removed at the user's request (2026-11-11)
    "CGTN英语", "CGTN法语", "CGTN俄语", "CGTN西语", "CGTN阿语", "CGTN记录",
    # premium channels that only exist as raw .ts streams (not m3u8): APTV can't play them
    "AXNAsiaTaiwan", "AnimaxAsiaTaiwan", "CinemaxAsiaTaiwan",
    "DiscoveryAsiaTaiwan", "HBOAsiaTaiwan",
    "爱奇艺",  # not a TV channel
}
EXCLUDE_SUBSTRINGS = ("春晚", "维护内容", "维护时间", "公告说明", "免费订阅")


def excluded(display):
    k = norm_key(display)
    if k in EXCLUDE_KEYS:
        return True
    return any(s in k for s in EXCLUDE_SUBSTRINGS)


# Channels whose first (Guovin/bestK) source is a recording or dead: force a
# verified-live source. Keys are normalized names; values are stable entry
# URLs (gslb redirectors). Applied in the dedup step, so every daily rebuild
# keeps the live source and the merged file still holds all backups.
SOURCE_OVERRIDES = {
    "湖南卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=hnwshd",
    "广东卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=gdwshd",
    "四川卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=scwshd",
    "江西卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=jxwshd",
    "贵州卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=gzwshd",
    "宁夏卫视": "http://107.150.60.122/live/nxws.m3u8",
    "新疆卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=xjws",
    "西藏卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=xzws",
    "内蒙古卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=nmgws",
    "陕西卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=snwshd",
    "山西卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=sxwshd",
    # 美亚电影：bestK 的 php 中继已死，iptv-org 的源是直播
    "美亚电影": "http://103.172.187.30:12000/stream/mytv/null-2/master.m3u8",
    # 原住民电视：tw 源里排前面的 akamaized 源已死，用同文件里直播的那个
    "IndigenousTV": "https://streamipcfapp.akamaized.net/live/_definst_/live_720/key_b1500.m3u8",
    # 2026-11-13 测速换源：避开已死/极慢的中继后端（实测分片速度见注释）。
    # 74.91 中继会跳转到 192.187.115.106，后端只有约 135KB/s；tvbus 与
    # 207.56 已无响应；38.75 的跳转目标不稳定，时快时慢。
    "CCTV2": "http://107.150.60.122/live/cctv2hd.m3u8",  # 原 204.12，654KB/s -> 1307KB/s
    "CCTV4": "http://107.150.60.122/live/cctv4hd.m3u8",  # 原 74.91 慢后端 -> 1929KB/s
    "CCTV5+": "http://120.76.248.139/live/bfgd/4200000246.m3u8",  # 原 38.75，5 秒分片 -> 1085KB/s
    "CCTV6": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=cctv6hd",  # 原 69.30 已死 -> 2559KB/s
    "CCTV7": "http://107.150.60.122/live/cctv7hd.m3u8",  # 原 74.91 慢后端 -> 1861KB/s
    "CCTV8": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=cctv8k",  # 原 tvbus 已死 -> 2465KB/s
    "CCTV11": "http://198.204.228.26/live/cctv11hd.m3u8",  # 原 74.91 慢后端 -> 2821KB/s
    "CCTV13": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=cctv13hd",  # 原 38.75，153KB/s -> 1853KB/s
    "CCTV15": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=cctv15hd",  # 原 204.12 -> 1773KB/s
    "CCTV16": "http://38.75.136.137:98/gslb/dsdqbv/cctv16hd.m3u8?auth=test20251009",  # 原 207.56 已死 -> 230KB/s，唯一备选
    "东方卫视": "http://107.150.60.122/live/dfwshd.m3u8",  # 原 38.75 -> 2436KB/s
    "甘肃卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=gswshd",  # 原 38.75 -> 1874KB/s
    # 港澳台 5 个台的新源（2026-11-11 全表排查后找到，变体列表实测有直播分片）
    "明珠": "http://r.jdshipin.com/jUx8K",  # TVB明珠台，原 163189 中继返回空列表
    "凤凰中文": "http://php.jdshipin.com/TVOD/iptv.php?id=fhzw",  # 与凤凰卫视台同一条流
    "凤凰资讯": "http://php.jdshipin.com/TVOD/iptv.php?id=fhzx",  # 替换原来的 FLV 直连
    "千禧经典": "http://php.jdshipin.com/TVOD/iptv.php?id=tvbc",  # TVB千禧经典台
    "无线星河": "http://php.jdshipin.com/TVOD/iptv.php?id=xinghe",  # TVB无线星河
}

# 越南/老挝/菲律宾只收实测能播的源（用户要求这三个组的台必须是好的）。
# 2026-11-13 逐条验证：120 条里 94 条直播（取到 m3u8 且首个分片能下载），
# 其余 26 条（403/404/超时/非 HLS）不在此表，每天重建也不会把它们加回来。
# 要加新台：先实测能播，再把 URL 加进这张表。
LIVE_SEA_URLS = {
    'http://122.55.252.134:8443/live/bba5b536faeacb9b56a3239f1ee8e3b3/1.m3u8',
    'http://125hvt.ddns.net:21585/vtv2/playlist.m3u8',
    'http://dethich.pw/vtv5tn/index.m3u8',
    'http://tldigital-17th06day-tl9648290.duckdns.org/tv.m3u8',
    'https://618b88f69e53b.streamlock.net/THDT2/thdttv2/chunklist.m3u8',
    'https://67tz1gnwrvxic.cmccdn.net/hls/NGHEANTV/03.m3u8',
    'https://amagi-live.ondemandkorea.com/amgplt0456.m3u8',
    'https://amg00861-amg00861c10-rakuten-uk-3152.playouts.now.amagi.tv/playlist.m3u8',
    'https://amg01868-amg01868c3-tvbanywhere-us-4491.playouts.now.amagi.tv/playlist/amg01868-tvbusa-tvbvietnam-tvbanywhereus/playlist.m3u8',
    'https://amg19223-amg19223c11-amgplt0352.playout.now3.amagi.tv/playlist/amg19223-amg19223c11-amgplt0352/playlist.m3u8',
    'https://amg19223-amg19223c12-amgplt0352.playout.now3.amagi.tv/playlist/amg19223-amg19223c12-amgplt0352/playlist.m3u8',
    'https://amg19223-amg19223c2-amgplt0351.playout.now3.amagi.tv/playlist/amg19223-amg19223c2-amgplt0351/playlist.m3u8',
    'https://amg19223-amg19223c3-amgplt0351.playout.now3.amagi.tv/playlist/amg19223-amg19223c3-amgplt0351/playlist.m3u8',
    'https://amg19223-amg19223c4-amgplt0351.playout.now3.amagi.tv/playlist/amg19223-amg19223c4-amgplt0351/playlist.m3u8',
    'https://dethich.pw/dongnai3/index.m3u8',
    'https://dethich.pw/htv1/index.m3u8',
    'https://dethich.pw/htv2/index.m3u8',
    'https://dethich.pw/htv3/index.m3u8',
    'https://dethich.pw/htv7/index.m3u8',
    'https://dethich.pw/htv9/index.m3u8',
    'https://dethich.pw/htvcphim/index.m3u8',
    'https://dethich.pw/htvcphunu/index.m3u8',
    'https://dethich.pw/thvl1/index.m3u8',
    'https://dethich.pw/thvl4/index.m3u8',
    'https://dethich.pw/vtv1/index.m3u8',
    'https://dethich.pw/vtv10/index.m3u8',
    'https://dethich.pw/vtv3/index.m3u8',
    'https://dethich.pw/vtv4/index.m3u8',
    'https://dethich.pw/vtv5/index.m3u8',
    'https://dethich.pw/vtv5tnb/index.m3u8',
    'https://dethich.pw/vtv6/index.m3u8',
    'https://dethich.pw/vtv7/index.m3u8',
    'https://dethich.pw/vtv8/index.m3u8',
    'https://dethich.pw/vtv9/index.m3u8',
    'https://freem3u.xyz/api/live/play.m3u8?vid=151',
    'https://freem3u.xyz/api/live/play.m3u8?vid=176',
    'https://freem3u.xyz/api/live/play.m3u8?vid=177',
    'https://freem3u.xyz/api/live/play.m3u8?vid=178',
    'https://freem3u.xyz/api/live/play.m3u8?vid=179',
    'https://freem3u.xyz/api/live/play.m3u8?vid=180',
    'https://freem3u.xyz/api/live/play.m3u8?vid=181',
    'https://freem3u.xyz/api/live/play.m3u8?vid=182',
    'https://freem3u.xyz/api/live/play.m3u8?vid=184',
    'https://freem3u.xyz/api/live/play.m3u8?vid=185',
    'https://freem3u.xyz/api/live/play.m3u8?vid=186',
    'https://freem3u.xyz/api/live/play.m3u8?vid=188',
    'https://freem3u.xyz/api/live/play.m3u8?vid=189',
    'https://freem3u.xyz/api/live/play.m3u8?vid=215',
    'https://freem3u.xyz/api/live/play.m3u8?vid=216',
    'https://freem3u.xyz/api/live/play.m3u8?vid=80',
    'https://freem3u.xyz/api/live/play.m3u8?vid=91',
    'https://jstre.am/live/jsl:nX5eC7gQvZb.m3u8',
    'https://live-hq.evgcdn.net/live/2851dc2c9af68834814a89e61db0faee561/chunklist.m3u8',
    'https://live.canthotv.vn/cs2/live.stream/playlist.m3u8',
    'https://live.canthotv.vn/cs3/tv/chunklist.m3u8',
    'https://live.canthotv.vn/live/tv/chunklist.m3u8',
    'https://live.cltv36.tv:5443/LiveApp/streams/cltvlive.m3u8',
    'https://live.mediatech.vn/live/2859145290d0d7947ef88b6240123b62474/chunklist.m3u8',
    'https://live.mediatech.vn/live/285b59a111d76974225a8e3004bfc31a509/chunklist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/briantv.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/hmongstartv.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/ichannel.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/laonet.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/laostv.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/laosvtv.stream/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/laothaius.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/lookthoongtv.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/ningtv.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/ohmuanglao.stream/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/teatv.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/uniquely.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/vatilaotv.stream/playlist.m3u8',
    'https://stream-243529.castr.net/6842a712b68c56f675d988f1/live_b60a96e056fc11f084c05f5d0649296b/rewind-1800.m3u8',
    'https://stream-243529.castr.net/6842a712b68c56f675d988f1/live_f5ac22b0566511f0805217b960326aaa/rewind-1800.m3u8',
    'https://stream.kdlc.click/hls/0/stream.m3u8',
    'https://stream.langsontv.vn/live/2855dfeccb7f49a41a2b0441b3bfeda413c/playlist.m3u8',
    'https://stream.langsontv.vn/live/285c78da0c246524c90917842f8de03bd21/playlist.m3u8',
    'https://stream.thingnet.vn/live/smil:CRTV.smil/chunklist.m3u8',
    'https://streaming.thainguyentv.vn/hls/livestream.m3u8',
    'https://tv.ctvcamau.vn/live/tv/tv.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/bsod999cuteptgyoutuber/1234567890/manifest/sctv3/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv11/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv12/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv13/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv14/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv16/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv18/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv19/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv2/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv20/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv4/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv6/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv7/master.m3u8',
    'https://vtvgolive-sctvdrm.vtvdigital.vn/manifest/sctv9/master.m3u8',
}

# Group order the user asked for (2026-11-11): 央视, 卫视, 港澳台, 日韩,
# then 地方台. Anything that fits none of those (international news,
# Malaysia/Singapore, movie/sports/shopping/documentary specialty channels)
# goes to a trailing 其他 group.
GROUP_ORDER = ["央视", "卫视", "港澳台", "越南", "老挝", "菲律宾", "日韩", "地方台", "其他"]

# 港澳台组内排序（2026-11-11 用户要求）：香港在上，澳门其次，台湾最后，
# 归属不明的（CNA 等海外/综合台）排在末尾、保持原有相对顺序。
HK_TIER = ("凤凰", "翡翠", "明珠", "RTHK", "港台", "有线新闻", "HOY",
           "ViuTV", "香港", "耀才", "NOW NEWS", "星空", "美亚", "无线",
           "千禧", "华丽", "BSTV", "阳光卫视")
# 注意：TVB 与天映不用子串匹配——TVBS（台湾）含 TVB，靖天（台湾）含“天映”，
# 必须用正则排除这两种台湾台。
TW_TIER = ("TVBS", "东森", "EBC", "三立", "台视", "华视", "民视", "中天", "大爱",
           "客家", "原住民", "MOMO", "公视", "Good TV", "GOOD TV", "人间卫视",
           "靖天", "唯心", "纬来", "八大", "ELEVEN", "NTD", "大立", "台湾")


def hkmo_tier(disp):
    if "澳门" in disp or "澳视" in disp or "澳亚" in disp:
        return 1
    if (re.search(r"TVB(?!S)", disp) or re.search(r"(?<!靖)天映", disp)
            or any(m in disp for m in HK_TIER)):
        return 0
    if any(m in disp for m in TW_TIER):
        return 2
    return 3

HK_MARKERS = (
    "凤凰", "TVB", "翡翠", "明珠台", "RTHK", "港台", "TVBS", "中天", "CTi",
    "东森", "EBC", "民视", "FTV", "三立", "SET", "华视", "CTS", "公视", "PTS",
    "台视", "TTV", "澳视", "澳门", "澳門", "澳亚", "香港卫视", "阳光卫视",
    "卫视中文", "纬来", "八大", "年代", "非凡", "壹电视", "寰宇", "东风",
    "超视", "无线", "J2", "Viu", "HOY", "奇妙", "开电视", "有线", "TDM",
    "唯心", "大立", "天才", "NTD", "Taiwan Plus", "耀才",
    "亚洲武侠", "天映", "美亚", "千禧", "新纪实", "星空", "Momo", "MOMO",
    "ET Mall", "东森购物", "DaAi", "大爱", "Hakka", "客家", "Indigenous",
    "原住民", "Jade", "Phoenix", "Celestial", "Golden Jade", "Asian Drama",
    "BSTV", "Mei Ah", "靖天", "Bread", "Beautiful Life", "Angel TV",
    "Supreme Master", "CNA", "NOW NEWS", "WXTV", "SJTV", "Dali TV",
    "人间卫视", "ELEVEN",
)
JP_KR_MARKERS = (
    "NHK", "Nippon", "TV Tokyo", "Fuji", "TV Asahi", "TBS", "MBS", "KBS",
    "SBS", "MBC", "JTBC", "tvN", "Arirang", "EBS", "YTN", "WOWOW", "KPop",
    "韩国", "日本", "JP1", "BS-",
)
# Upstream groups that are specialty content, not local channels.
SPECIALTY_GROUPS = {
    "Shop", "电影", "🎬电影频道", "Religious", "Education", "🏛经典剧场",
    "🎵音乐频道", "少儿", "Kids", "Music", "Entertainment", "Weather",
    "Legislative", "Legislative;News", "General", "General;News", "Undefined",
}
# Keywords that mark a leftover (upstream group "其他") as specialty, not local.
OTHER_KEYWORDS = (
    "电影", "影院", "剧场", "购物", "Shop", "纪实", "纪录", "人文", "科教",
    "少儿", "动画", "卡通", "宗教", "戏曲", "曲艺", "音乐", "综艺", "经典",
    "重温", "武侠", "体育", "足球", "篮球", "宠物", "游戏", "电竞", "收藏",
    "汽车", "旅游", "军事", "农业", "天气", "Weather", "Kids", "Documentary",
    "Sports", "Movies", "Shopping", "Religious", "Entertainment",
    "Legislative", "环球", "围棋", "棋牌",
)
# English-named mainland local channels (would otherwise land in 其他).
LOCAL_ENGLISH = ("Guangzhou", "Siping", "Tonghua", "Anshun", "Chifeng", "Harbin")
# Shopping markers: a jp/kr-source channel with one of these is a shopping
# channel, not a regular Japanese/Korean TV channel.
SHOP_MARKERS = ("购物", "Shopping", "Shop", "OnStyle", "Lotte", "Hyundai",
                "Shinsegae", "QVC", "Home &")


def classify(display, upstream_group, source):
    """Assign one of the six groups. Name rules first, then source, then
    upstream group, then a local-channel default."""
    d = to_simp(display)
    # 越南/老挝/菲律宾按来源分组（放最前：TVB Vietnam 含 TVB，
    # 按名字会被误分到港澳台）。
    if source == "vn":
        return "越南"
    if source == "la":
        return "老挝"
    if source == "ph":
        return "菲律宾"
    if d.startswith("CCTV") or d.startswith("CGTN") or d.startswith("CETV"):
        return "央视"
    # Taiwan's GOOD TV (not Korea's Good TV, which has the same base name)
    if d.startswith("GOOD TV") or d.startswith("Good TV (Taiwan)") or d in ("Good", "Good 2"):
        return "港澳台"
    if any(m in d for m in HK_MARKERS):
        return "港澳台"
    if "卫视" in d or any(m in d for m in ("Satellite TV", "Hunan TV",
                                          "Xinjiang TV", "Xizang TV",
                                          "Zhejiang TV")):
        return "卫视"
    if re.search(r"[\u3040-\u30ff\uac00-\ud7af]", d) or any(
            m in d for m in JP_KR_MARKERS):
        return "日韩"
    if any(k in d for k in ("围棋", "棋牌")):
        return "其他"
    if source in ("hk", "tw"):
        return "港澳台"
    if source in ("jp", "kr"):
        if any(m in d for m in SHOP_MARKERS):
            return "其他"
        return "日韩"
    if d.startswith("QTV") or any(p in d for p in LOCAL_ENGLISH):
        return "地方台"
    if upstream_group in SPECIALTY_GROUPS:
        return "其他"
    if not re.search(r"[\u4e00-\u9fff]", d):
        return "其他"
    if upstream_group == "其他" and any(k in d for k in OTHER_KEYWORDS):
        return "其他"
    return "地方台"


def group_of_extinf(extinf):
    m = re.search(r'group-title="([^"]*)"', extinf)
    return m.group(1) if m else ""


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status != 200:
            raise SystemExit(f"fetch failed {r.status}: {url}")
        return r.read().decode("utf-8", errors="ignore")


def parse(text):
    """Return (header_lines, [(extinf_line, display, url, vlcopts), ...])."""
    lines = text.splitlines()
    header = []
    entries = []
    i = 0
    while i < len(lines) and not lines[i].startswith("#EXTINF"):
        if lines[i].strip():
            header.append(lines[i])
        i += 1
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            display = line.rsplit(",", 1)[-1].strip()
            # skip directive lines (#EXTVLCOPT etc.) until the URL line
            j = i + 1
            vlcopts = []
            while j < len(lines) and lines[j].startswith("#"):
                vlcopts.append(lines[j])
                j += 1
            url = lines[j].strip() if j < len(lines) else ""
            entries.append((line, display, url, vlcopts))
            i = j + 1
        else:
            i += 1
    return header, entries


def main():
    all_entries = []  # (source, extinf, display, url)
    header = ["#EXTM3U"]
    for src, url in SOURCES:
        text = fetch(url)
        h, entries = parse(text)
        if src == "guovin":
            header = [x for x in h if x.startswith("#EXTM3U") or "x-tvg-url" in x] or ["#EXTM3U"]
        print(f"{src}: {len(entries)} entries")
        for extinf, display, u, vlcopts in entries:
            all_entries.append((src, extinf, display, u, vlcopts))

    # merged: drop exact (display, url) duplicates, drop junk entries
    merged = []
    seen_pair = set()
    n_excluded = 0
    for src, extinf, display, url, vlcopts in all_entries:
        if not display or not url.startswith("http"):
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}", display):  # Guovin "update time" pseudo-channel
            continue
        if excluded(display):
            n_excluded += 1
            continue
        # ChiSheng9's m3u8 files are not streams at all: each contains only a
        # YouTube watch URL (verified 2026-11-11, all 17 TV files), which an
        # m3u8 player cannot play. Drop them so they never appear as dead
        # channels (20 entries across 港澳台/日韩/其他）.
        if "raw.githubusercontent.com/ChiSheng9" in url:
            n_excluded += 1
            continue
        if src in ("vn", "la", "ph") and url not in LIVE_SEA_URLS:
            n_excluded += 1
            continue
        key = (display, url)
        if key in seen_pair:
            continue
        seen_pair.add(key)
        merged.append((src, extinf, display, url, vlcopts))
    print(f"merged (exact-dup removed): {len(merged)} (excluded {n_excluded} entries)")

    # deduped: one entry per normalized name, first occurrence wins
    deduped = []
    seen_key = set()
    seen_final = set()
    for src, extinf, display, url, vlcopts in merged:
        k = norm_key(display)
        if not k or k in seen_key:
            continue
        seen_key.add(k)
        disp = to_simp(display)
        disp = DISPLAY_NAMES.get(k, disp)
        disp = rename_jp_kr(k, disp)
        fk = norm_key(disp)
        if fk in seen_final:
            print(f"  skip rename-collision: {display!r} -> {disp!r} (key {fk})")
            continue
        seen_final.add(fk)
        if k in SOURCE_OVERRIDES:
            url = SOURCE_OVERRIDES[k]
            vlcopts = []
        grp = classify(disp, group_of_extinf(extinf), src)
        deduped.append((src, extinf, disp, url, vlcopts, grp))
    # sort into the user's group order, keeping upstream order inside a group
    deduped.sort(key=lambda e: GROUP_ORDER.index(e[5]))
    # 港澳台组内按 香港 > 澳门 > 台湾 > 其他 重排（稳定排序，组内原顺序保留）
    _hkmo_idx = [i for i, e in enumerate(deduped) if e[5] == "港澳台"]
    _hkmo_sub = [deduped[i] for i in _hkmo_idx]
    _hkmo_sub.sort(key=lambda e: hkmo_tier(e[2]))
    for i, e in zip(_hkmo_idx, _hkmo_sub):
        deduped[i] = e
    print(f"deduped: {len(deduped)}")
    for g in GROUP_ORDER:
        print(f"  group {g}: {sum(1 for e in deduped if e[5] == g)}")

    # verification
    _tiers = [hkmo_tier(d) for _, _, d, _, _, g in deduped if g == "港澳台"]
    assert _tiers == sorted(_tiers), "港澳台 tiers out of order!"
    print(f"  港澳台 tiers 香港/澳门/台湾/其他: {[_tiers.count(t) for t in range(4)]}")
    keys = [norm_key(d) for _, _, d, _, _, _ in deduped]
    assert len(keys) == len(set(keys)), "normalized name repeats!"
    disps = [d for _, _, d, _, _, _ in deduped]
    assert len(disps) == len(set(disps)), "display name repeats!"
    assert not any("春晚" in d for d in disps), "春晚 entries remain!"
    assert not any(norm_key(d) in EXCLUDE_KEYS for d in disps), "pay channels remain!"
    for name, want_url in SOURCE_OVERRIDES.items():
        # a display-mapped channel (e.g. 原住民电视) is stored under its
        # Chinese display name, so look it up through the reverse map too
        hit = [u for _, _, d, u, _, _ in deduped
               if norm_key(d) == norm_key(name)
               or {v: k for k, v in DISPLAY_NAMES.items()}.get(d) == norm_key(name)]
        assert hit and hit[0] == want_url, f"override missing for {name}"
    assert [e[5] for e in deduped] == sorted(
        [e[5] for e in deduped], key=lambda g: GROUP_ORDER.index(g)), "groups out of order!"
    for want in ["CCTV-1", "CCTV-5", "CCTV-13", "湖南卫视", "广东卫视", "浙江卫视",
                 "东方卫视", "北京卫视", "江苏卫视", "凤凰卫视", "TVBS新闻台",
                 "东森财经新闻", "NHK综合电视台", "日本电视台", "东京电视台", "阿里郎",
                 "翡翠", "中天新闻", "RTHK31", "VTV1", "HTV7", "LS TV",
                 "Abante TV"]:
        hit = [d for d in disps if norm_key(d) == norm_key(want)]
        print(f"  check {want}: {'OK ' + str(hit) if hit else 'MISSING'}")

    def render(entries, regroup=False):
        out = list(header) + [""]
        for entry in entries:
            if regroup:
                _, extinf, display, url, vlcopts, grp = entry
                base = extinf.rsplit(",", 1)[0]
                if 'group-title="' in base:
                    base = re.sub(r'group-title="[^"]*"', f'group-title="{grp}"', base)
                else:
                    base = base + f' group-title="{grp}"'
            else:
                _, extinf, display, url, vlcopts = entry
                base = extinf.rsplit(",", 1)[0]
            out.append(f"{base},{display}")
            out.extend(vlcopts)
            out.append(url)
        return "\n".join(out) + "\n"

    merged_text = render(merged)
    deduped_text = render(deduped, regroup=True)
    with open("IPTV-全频道-央视卫视港澳台日韩.m3u", "w", encoding="utf-8") as f:
        f.write(merged_text)
    with open("IPTV-全频道-去重版.m3u", "w", encoding="utf-8") as f:
        f.write(deduped_text)
    # ASCII-named copy of the deduped list, for clients that dislike
    # non-ASCII URLs (e.g. some IPTV players).
    with open("iptv.m3u", "w", encoding="utf-8") as f:
        f.write(deduped_text)
    print("written.")


if __name__ == "__main__":
    main()
