#!/usr/bin/env python3
"""Rebuild the merged + deduped IPTV playlist from fresh upstreams.

Priority: Guovin (auto-tested CCTV+satellite) > bestK (satellite+HK/MO/TW)
         > iptv-org jp > iptv-org kr.
Dedup by normalized name, one entry per channel, first occurrence wins.
Run daily by GitHub Actions (.github/workflows/daily-rebuild.yml).
2026-11-11: 港澳台组内按香港/澳门/台湾排序；日韩频道名尽量转中文。
"""

import json
import re
import sys
import urllib.parse
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
    ("th", "https://iptv-org.github.io/iptv/countries/th.m3u"),
    ("sg", "https://iptv-org.github.io/iptv/countries/sg.m3u"),
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
    "河南梨园": "梨园",  # bestK 的死源与 Guovin 的直播源是同一个台，合并后取先到的直播源
    "湖州公共": "湖州公共民生",  # 同上：bestK 的 freetv 死源与 Guovin 的直播源合并
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


# 东南亚频道中文名（2026-11-14 用户要求：能改成中文的就改，不能改的保持原样）。
# 键是 norm_key，值是中文核心名；清晰度与 [flag] 后缀原样保留。
# 老挝 9 个台（品牌/人名，无可靠译法）与呼号、品牌缩写不在表里，保持原名。
SEA_DISPLAY_NAMES = {
    "3HD": "泰国3台",
    "AmarinTV": "阿玛林电视台",
    "AsianFoodNetworkVietnam": "亚洲美食频道",
    "BilyonaryoNewsChannel": "Bilyonaryo新闻台",
    "CaMauTV": "金瓯电视台",
    "CanThoTV": "芹苴电视台",
    "CanThoTV2": "芹苴电视台2台",
    "CanThoTV3": "芹苴电视台3台",
    "CaoBangTV": "高平电视台",
    "CartoonNetworkAsiaThailand": "卡通频道泰国台",
    "Channel8": "泰国8台",
    "DLTV1": "泰国远程教育1台",
    "DLTV10": "泰国远程教育10台",
    "DLTV11": "泰国远程教育11台",
    "DLTV12": "泰国远程教育12台",
    "DLTV13": "泰国远程教育13台",
    "DLTV14": "泰国远程教育14台",
    "DLTV15": "泰国远程教育15台",
    "DLTV2": "泰国远程教育2台",
    "DLTV3": "泰国远程教育3台",
    "DLTV4": "泰国远程教育4台",
    "DLTV5": "泰国远程教育5台",
    "DLTV6": "泰国远程教育6台",
    "DLTV7": "泰国远程教育7台",
    "DLTV8": "泰国远程教育8台",
    "DLTV9": "泰国远程教育9台",
    "DaNangTV1": "岘港电视台1台",
    "DaNangTV2": "岘港电视台2台",
    "DienBienTV": "奠边电视台",
    "DongNaiTV3": "同奈电视台3台",
    "GiaLaiTV": "嘉莱电视台",
    "HTV1": "胡志明电视台1台",
    "HTV2": "胡志明电视台2台",
    "HTV3": "胡志明电视台3台",
    "HTV5": "胡志明电视台5台",
    "HTV7": "胡志明电视台7台",
    "HTV9": "胡志明电视台9台",
    "HTVCMovies": "HTVC电影台",
    "HTVCWomen": "HTVC女性台",
    "HalalTV": "清真电视台",
    "HopeChannelPhilippines": "希望频道",
    "INCRadio": "INC电台",
    "INCTV": "INC电视台",
    "LangSonTV": "谅山电视台",
    "MCOT": "MCOT电视台",
    "NBT2": "泰国NBT2台",
    "NBTTVChiangMai": "泰国NBT清迈台",
    "NationTV": "民族电视台",
    "NgheAnTV": "义安电视台",
    "ONInfoTV": "ON资讯台",
    "ONKids": "ON少儿台",
    "ONLife": "ON生活台",
    "ONMovies": "ON电影台",
    "ONMusic": "ON音乐台",
    "ONStyleTV": "ON时尚台",
    "ONTrendingTV": "ON潮流台",
    "ONVieDramas": "ON Vie电视剧台",
    "ONVieGiaiTri": "ON Vie娱乐台",
    "OutdoorChannelVietnam": "户外频道",
    "PremierSports": "Premier体育台",
    "PremierSports2": "Premier体育2台",
    "QuangNamTV": "广南电视台",
    "SCTV11": "SCTV11台",
    "SCTV12": "SCTV12台",
    "SCTV13": "SCTV13台",
    "SCTV14": "SCTV14台",
    "SCTV16": "SCTV16台",
    "SCTV18": "SCTV18台",
    "SCTV19": "SCTV19台",
    "SCTV20": "SCTV20台",
    "SCTV2SD": "SCTV2台",
    "SCTV3": "SCTV3台",
    "SCTV4": "SCTV4台",
    "SCTV6": "SCTV6台",
    "SCTV7": "SCTV7台",
    "SCTV9": "SCTV9台",
    "TAPSports": "TAP体育台",
    "TVMuslimThailand": "泰国穆斯林电视台",
    "TayNinhTV": "西宁电视台",
    "ThaiNguyenTV": "太原电视台",
    "ThaiPBS": "泰国公共电视台",
    "ThaiParliamentTelevision": "泰国国会电视台",
    "ThairathTV": "泰叻电视台",
    "TienGiangTV": "前江电视台",
    "VTV1": "越南电视台1台",
    "VTV10": "越南电视台10台",
    "VTV2": "越南电视台2台",
    "VTV3": "越南电视台3台",
    "VTV4": "越南电视台4台",
    "VTV5": "越南电视台5台",
    "VTV5TayNamBo": "越南电视台5台西南部",
    "VTV5TayNguyen": "越南电视台5台西原",
    "VTV6": "越南电视台6台",
    "VTV7": "越南电视台7台",
    "VTV8": "越南电视台8台",
    "VTV9": "越南电视台9台",
    "VinhLongTV1": "永隆电视台1台",
    "VinhLongTV4": "永隆电视台4台",
    "VinhLongTV5": "永隆电视台5台",
}


def rename_sea(k, disp, source):
    """Rename a SEA display name to Chinese when a mapping exists.
    Only for th/vn/la/ph sources; keeps the resolution / [flag] suffix."""
    if source not in ("th", "vn", "la", "ph") or k not in SEA_DISPLAY_NAMES:
        return disp
    m = _SUFFIX_RE.match(disp)
    if m:
        return SEA_DISPLAY_NAMES[k] + m.group(2)
    return SEA_DISPLAY_NAMES[k]


# 新加坡台中文名（2026-11-21 审计，key 为上游原名的 norm_key）。
SG_DISPLAY_NAMES = {
    "CartoonitoAsia": "卡通尼托亚洲",
    "Channel8Singapore": "新加坡8频道",
    "ChannelU": "新加坡U频道",
    "CNASingapore": "CNA亚洲新闻台",
    "CNAOriginals": "CNA原创纪录片",
    "Suria": "苏丽娅频道",
}


def rename_sg(k, disp, source):
    """Rename a Singapore display name to Chinese when a mapping exists.
    Only for sg sources; keeps the resolution / [flag] suffix."""
    if source != "sg" or k not in SG_DISPLAY_NAMES:
        return disp
    m = _SUFFIX_RE.match(disp)
    if m:
        return SG_DISPLAY_NAMES[k] + m.group(2)
    return SG_DISPLAY_NAMES[k]




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
    # 2026-11-20 地方台深查：福建省广播影视集团 2026-04-28 关停 4 个频道
    # （维基“福建省广播影视集团”条目核实）：乡村振兴•公共、电视剧、经济生活
    # （福建经视）停播；文体并入旅游频道改为文旅•体育频道。原名已不存在，
    # 找替补无意义，直接从列表删掉。福建旅游（现文旅•体育）暂留，待找新源。
    "福建乡村振兴公共", "福建电视剧", "福建文体", "福建经视",
    # 2026-11-20 地方台深查白天复查：12 个纯音频台（蜻蜓 FM/广播源，AAC 只有
    # 0.06-0.09Mbps、无视频轨，电视上永远黑屏有声），用户 2026-11-20 09:13
    # 选“删掉”。注意：三明/六安/山东生活等 8 个是帧验确认，灌阳/铜陵/黑龙江/
    # 武汉一台 4 个是分片提不出帧 + 码率 0.08-0.09 的音频特征判定。
    "三明新闻综合", "六安公共", "六安新闻综合", "山东生活",
    "灌阳新闻综合", "衡水公共", "铜陵新闻综合", "长沙新闻综合",
    "陕西公共", "靖江新闻综合", "黑龙江新闻", "武汉一台新闻综合",
    # 2026-11-20 星空卫视：唯一已知源 iot-mqqt.111yao.cn 已死；北邮 RTMP
    # 老源（同站 CCTV-5 源用户已验看不了）、2022 酒店源全死，全网无替补。
    # 用户 2026-11-20 09:28 选删掉。星空国际是另一个台，不动。
    "星空卫视",
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
    "湖南卫视": "http://hlsal-ldvt.qing.mgtv.com/nn_live/nn_x64/dWlwPTEyNy4wLjAuMSZ1aWQ9cWluZy1jbXMmbm5fdGltZXpvbmU9OCZjZG5leF9pZD1hbF9obHNfbGR2dCZ1dWlkPTliODY4NmU5ZTM2YzYwMmMmZT02OTE0NjA0JnY9MSZpZD1ITldTWkdTVCZzPTcwN2RiYTc2YzJjNmJmMTQ4MmUyZGYzOWU2NWM3YWFi/HNWSZGST.m3u8",  # 芒果 4K HEVC 源（3840x2160，沙箱验过是活的）；2026-11-27 用户要 4K 换上后手机超时，加 DIRECT 规则仍超时，重找无其他 4K 源，同日换回 63.141 1080p。勿无证据再换回。
    "广东卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=gdwshd",  # 2026-11-27 用户报标清：原 WCETV 源实测只有 1280x720；63.141/74.91 两路候选帧验均为真广东卫视（台标+《上海滩生死较量》第6集），均为 1920x1080；选 63.141（与重庆/海南/黑龙江/湖南同池），74.91 作备选，107.150 只有 720p 不用。
    "四川卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=scwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "江西卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=jxwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "贵州卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=gzwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "宁夏卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=nxws",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "新疆卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=xjws",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "西藏卫视": "https://live.vtibet.cn/live/ZYWS20261016.stream.m3u8",  # 2026-11-20 帧验官方藏语节目
    "内蒙古卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=nmgws",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "陕西卫视": "http://107.150.60.122/live/snwshd.m3u8",  # 2026-11-20 63.141 换 107.150 中继
    "山西卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=sxwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    # 美亚电影：bestK 的 php 中继已死，iptv-org 的源是直播
    "美亚电影": "http://103.172.187.30:12000/stream/mytv/null-2/master.m3u8",
    # 原住民电视：tw 源里排前面的 akamaized 源已死，用同文件里直播的那个
    "IndigenousTV": "https://streamipcfapp.akamaized.net/live/_definst_/live_720/key_b1500.m3u8",
    # 2026-11-13 测速换源：避开已死/极慢的中继后端（实测分片速度见注释）。
    # 74.91 中继会跳转到 192.187.115.106，后端只有约 135KB/s；tvbus 与
    # 207.56 已无响应；38.75 的跳转目标不稳定，时快时慢。
    # 2026-11-14 13:35 央视广告事件：除 CCTV-1 外所有央视台播同一推销广告，
    # 中继网(63.141/107.150/38.75/198.204/120.76)疑似全线改播广告循环，且其分片
    # 现已拒绝本沙箱请求(404)，无法在此验证内容。以下分两类：
    # [已验] 帧画面确认真实内容：CCTV4->WCETV美洲版，CCTV9->livehwc4(Y77)，
    # CCTV10->SkyGo（2026-11-19 用户报超时，改 txiptv 221.7.175.154）。[待测] 仅播放列表可达、内容待用户实测：其余改 74.91 /
    # 198.204.240 / jdshipin / GITV；用户反馈哪个仍是广告就再换。
    "CCTV2": "http://74.91.26.218:82/live/cctv2hd.m3u8",  # 待测：原 107.150 播广告
    "CCTV3": "http://74.91.26.218:82/live/cctv3hd.m3u8",  # 待测：原 63.141 播广告
    "CCTV4": "https://h5cul1yar48um3t.wcetv.com/hls/cctv4.m3u8",  # 已验：帧确认 CCTV-4 美洲版真实内容
    "CCTV5": "http://120.40.39.246:352/newlive/live/hls/5/live.m3u8",  # 2026-11-18 深度 hunt 帧验证：真CCTV-5直播(CBA)，1920x1080/25fps/~8.6Mbps，整段下载+60秒稳定性复查通过；newlive 家族（同之前能播的 SD 源家族），电信福建。txiptv 223.78.65.165 对 2026-11-18 晚移除：用户反馈所有网络都卡，沙箱测其吞吐 1.85~8.85Mbps 剧烈波动、播放列表 9 秒才返回；该 host 是全单唯一移动(山东济南)源。勿无证据加回 txiptv。旧SD源 http://221.226.51.220:50081/newlive/live/hls/5/live.m3u8 保留作回退备选
    "CCTV5+": "http://183.129.255.66:8480/hls/6/index.m3u8",  # 2026-11-22 run #48：C29（哈尔滨电信 219.147.245.238）今早死（06:30 体检 + 07:06 复测均 HTTP 000）；换 hunt 第 3 名 C25（183.129.255.66:8480，帧验真 CCTV-5+ 直播 1920x1080/25fps ~7.9Mbps，钻石联赛多哈站男子标枪决赛，60 秒 sequence 推进；txiptv 同源 2026-11-18 因一直缓冲移除，勿无证据加回；备选 bfgd 4200000246）
    "CCTV6": "http://74.91.26.218:82/live/cctv6hd.m3u8",  # 待测：原 63.141 播广告
    "CCTV7": "http://74.91.26.218:82/live/cctv7hd.m3u8",  # 待测：原 107.150 播广告
    "CCTV8": "http://74.91.26.218:82/live/cctv8hd.m3u8",  # 待测：原 63.141 播广告
    "CCTV9": "https://xykt-fix.github.io/Y77.m3u8",  # 已验：帧确认 CCTV-9 纪录真实内容
    "CCTV10": "http://221.7.175.154:8445/tsfile/live/1008_1.m3u8?key=txiptv&playlive=1&authid=0",  # 2026-11-19 用户报超时：SkyGo 在沙箱仍能播（双码率分片均 200），超时是用户到蒙古 CDN 的路径问题。改 txiptv 221.7.175.154（与 5/5+ 移除的 223.78.65.165 不同 host），2026-11-19 帧验真 CCTV-10 科教内容（1080p，分片 ~5.4MB/4s）；备选 59.39.89.130:60901 同内容但慢（18s），74.91 cctv10hd 播单活、分片现 404（中继间歇性，同刻 cctv6hd 也 404）；若再卡先回 SkyGo
    "CCTV11": "http://74.91.26.218:82/live/cctv11hd.m3u8",  # 待测：原 198.204.228 播广告
    "CCTV12": "http://74.91.26.218:82/live/cctv12hd.m3u8",  # 待测：原 107.150 播广告
    "CCTV13": "http://74.91.26.218:82/live/cctv13hd.m3u8",  # 待测：原 63.141 播广告
    "CCTV14": "http://74.91.26.218:82/live/cctv14hd.m3u8",  # 待测：原 198.204.228 播广告
    "CCTV15": "http://74.91.26.218:82/live/cctv15hd.m3u8",  # 待测：原 63.141 播广告
    "CCTV16": "http://198.204.240.250:82/live/cctv16hd.m3u8",  # 待测：原 38.75 播广告
    "CCTV17": "http://74.91.26.218:82/live/cctv17hd.m3u8",  # 待测：原 264788 播广告
    "CETV1": "http://117.161.133.51:81/gitv_live/G_CETV-1/G_CETV-1.m3u8?p=GITV",  # 待测：原 198.204.228 播广告；沙箱无法直连
    "CETV2": "http://223.110.241.204:6610/gitv/live1/G_CETV-2/G_CETV-2/",  # 2026-11-20 换 GITV 全国源（陕西 PLTV 直连仍 0 字节；沙箱无法直连，待用户实测）
    # 2026-11-20 海南卫视：原 bfgd 4200000473 播单能拉、分片全超时（整个 bfgd 分片 host 挂了，用户报看不了）。换陕西移动 PLTV 3221225769（xyq254245 live.txt；同文件 CETV1=753/CETV2=756 与已上线的一致，同族邻台四川 768/东南 766/河南 767 印证 ID 映射）；沙箱无法直连，待用户在移动网实测。官方 hnntv 流帧验是真节目但 token 只活 2 小时、没法当静态源用；裸官方 URL 是 token 门（403），不换。2026-11-20 晚：陕西 PLTV 直连移动网仍 0 字节，源本身死/锁，换黑龙江 PLTV 3221226465（沙箱无法验证，待用户实测；若还超时则 PLTV 家族对该机无解）。2026-11-20 晚：黑龙江 PLTV 直连仍 0 字节，PLTV 家族对该机无解，改 GITV 全国源（Hl190909 播单，LYWS 码与深查的 GITV 302 路径一致；CETV-1/2 同换 GITV）。
    "海南卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=lywshd",  # 2026-11-23 run #52：YanG 已停用；测试订阅 6 条候选手机全超时（4G，11:36）后，探 63.141 中继 ?id=lywshd 命中：302 跳 69.30.211.138 签名播单（jsbt/jsbk 按次签发，只写干净入口 URL），序列 30996→31004 推进，分片 5.2MB/1.56s，1920x1080/25fps，帧验海南卫视台标+古装剧真节目。同 20 卫视在用中继，每日体检盯并台。
    "辽宁生活": "http://dassby.qqff.top:99/live/辽宁生活/index.m3u8",  # 2026-11-24 体检：原 120.76.248.139 源 PLAYLIST_ONLY（分片 0 字节，exit 52），已观察满一天；bestK 替源帧验 1920x1080 真节目（生活台标+电视购物广告），播单 200、序列推进、分片 9.7MB。
    "黑龙江卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=hljwshd",  # 2026-11-27 用户报无画面：原 107.150.60.122 源时好时坏（20 分钟内 7 次测 5 次空回复 rc=52，06:30 体检 LIVE 是赶上好的时候）；63.141 替源 1280x720 真视频、独立分流（与重庆分片 md5 不同），两路候选同播 400-1106-678 电视购物广告，节目时段台标待用户实测确认。
    "湖南卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=hnwshd",  # 2026-11-27 换回 1080p：4K 芒果源手机超时（代理和直连都超时），重找无其他 4K 源；63.141 1080p（run #61 已验）
    # 2026-11-20 run #38: 63.141 中继同一共享广告+全超时，25 台换源（8 台帧验替源 + 17 台换同家中继 107.150.60.122，用户手机上东方/河南走它 133/261ms；海南无替源不动）
    "CCTV1": "http://74.91.26.218:82/live/cctv1hd.m3u8",  # 帧验《老农民》
    "浙江卫视": "http://ali-xwl.cztv.com/live/channel011080Plxw.m3u8",  # 2026-11-22 run #49：原 ali-m-l channel001 冻结（序列恒 359977910，PDT 停 2025-12-30），换浙江广电官方另一路 ali-xwl，帧验《津门飞鹰》1080p，序列 101707→101711 推进
    "浙江国际": "http://ali-xwl.cztv.com/live/channel101080Plxw.m3u8",  # 2026-11-22 run #49：原 ali-m-l channel10 同样冻结（序列恒 287140087），换官方 ali-xwl，帧验《孤战迷城》1080p，序列 156835→156840 推进
    "河北卫视": "https://restream.pdtvhd.com/memfs/1db8c005-9365-4b32-94a4-3736987b5646.m3u8",  # 帧验《大决战》；官方 live101 是美丽河北慢直播风景画面，不用
    "吉林卫视": "http://221.7.175.154:8445/tsfile/live/1014_1.m3u8?key=txiptv&playlive=1&authid=0",  # 帧验《薛仁贵传奇》ep41
    "云南卫视": "https://h5cul1yar48um3t.wcetv.com/hls/yunnantv.m3u8",  # 帧验《独立纵队》
    "北京卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=bjwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "重庆卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=cqwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "东南卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=dnwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "广西卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=gxwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "江苏卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=jswshd",  # 2026-11-27 用户报播卖药广告：107.150 中继又并台（帧验 400-788-3916 明慕金丹广告，720p）；换 63.141，帧验真节目《新相亲大会》1080p。74.91 亦 1080p 备选。江苏卫视4K（荔枝真 2160p）仍在列表里，用户实测能看。
    "辽宁卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=lnwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "山东卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=sdwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "天津卫视": "http://107.150.60.122/live/tjwshd.m3u8",  # 2026-11-20 63.141 换 107.150 中继
    "天津体育": "http://107.150.60.122/live/tjtv5.m3u8",  # 2026-11-20 63.141 换 107.150 中继
    "三沙卫视": "https://livessws.hnntv.cn/live/ssws_260111hnntv.m3u8",  # 2026-11-20 换 hnntv 官方 720p（帧验新闻联播）；路径含日期串 260111，若轮换会断，每日体检盯；1080p 全网未找到
    # 2026-11-21 台湾台：61.221.215.25:8800 中继整体冻结——TVBS新闻台/三立戏剧/纬来精采是 40-55 秒循环录像（播单 MEDIA-SEQUENCE 不动、分片逐字节相同），八大戏剧台分片全 404。TVBS新闻台换 modn 4027（2026-11-21 帧验真直播 1080p，序列 189974→189981 推进；沙箱下个别节目段出地域版权 slate，待用户香港节点实测）。大爱二台换 pulltv2（帧验《幸福的青鸟》720p）；大爱一台 URL 不变——pulltv1/pulltv2 裸拉 403、带 Referer: https://www.daai.tv/ 即 200，需另配 daai-referer 插件/模块（与 mov3-referer 同类做法），否则 APTV 仍播不了。7 条 pili 候选沙箱无法验证未上；华视新闻/东森新闻/民视/三立新闻/台视/公视3台/中天综合/纬来精采无替源，留着不动。
    "TVBS新闻": "http://38.64.72.148:80/hls/modn/list/4027/playlist.m3u8",
    "DaAi2": "https://pulltv2.wanfudaluye.com/live/tv2.m3u8",  # key 是上游原名 DaAi2 的 norm_key（不是“大爱二台”，断言已验）
    # 2026-11-19 CCTV-4K 高清：原官方 cctvnews 链接签名过期（auth_key 到期 2026-02-19，403），p.ytelc 404。换 107.150.52.50:82/live/cctv4k.m3u8——中继族中唯一真正出分片的源（同族 38.75/107.150.60.122/192.151.150.154/63.141/104.152.209.49 播单能拉、分片全 404）。2026-11-19 帧验：CCTV 4K 超高清角标、真节目，1080p25 约 15Mbps；注意是 1080p 不是真 2160p。主机不在 256 条强制代理里（美 IP，不走 DIRECT 规则，落 FINAL→代理，无需加规则）。
    "CCTV4K": "http://107.150.52.50:82/live/cctv4k.m3u8",
    # 2026-11-19 CCTV4K真4K：原 xinketongxun 已死（exit 52）。换央视官方阿里云真 4K 流 liveali-tp4k.cctv.cn/live/4K10M.stream/playlist.m3u8——沙箱 403 地域限制（境外出口），未帧验，待用户国内 IP 实测；若播不了，换与 CCTV-4K 高清相同的 107.150.52.50 1080p 源。
    "CCTV4K真4K": "https://liveali-tp4k.cctv.cn/live/4K10M.stream/playlist.m3u8",
    # 2026-11-19 CETV-1：原 GITV 117.161.133.51 已死（2026-11-14 审计 exit 52）。换移动 PLTV 同族源 .../3221225753（CETV-2 已换 .../3221225756 同族），沙箱无法直连，待用户移动网实测；备选未验：txycsbl.centv.cn/zb/0628cetv1.m3u8（CETV 自有 CDN）、charging-rh.ha.chinamobile.com 河南移动 GITV。
    "CETV1": "http://223.110.241.204:6610/gitv/live1/G_CETV-1/G_CETV-1/",  # 2026-11-20 换 GITV 全国源（陕西 PLTV 直连仍 0 字节；沙箱无法直连，待用户实测）
    "东方卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=dfwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "甘肃卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=gswshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "安徽卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=ahwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "深圳卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=szwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "河南卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=hawshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "湖北卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=hbwshd",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    "青海卫视": "http://63.141.230.178:82/gslb/zbdq5.m3u8?id=qhws",  # 2026-11-22 run #48：107.150 中继并台播同一广告，换回 63.141（播单已验各台独立）
    # 2026-11-19 福建海峡卫视：原 Guovin 源 38.64.72.148 modn 404 已死（2026-11-14 审计即死，用户 2026-11-19 04:00 报不能看）。换官方源：r.jdshipin 短链跳转到 live1-fuyun.fjtv.net/haixiapd/hd/live.m3u8（海博TV 官方流，640x360/25fps，分片实测 200）。注意：2026-11-19 04:0x 帧验为“因版权问题暂时无法观看”slate——官方流在部分节目时段黑屏，待用户白天实测内容；短链每次跳转带 _upt 参数，勿写死最终 URL。备选未验：pi.0472.org/hls/hxws.m3u8（沙箱无法直连）。
    "福建海峡卫视": "http://r.jdshipin.com/WtYt3",
    # 2026-11-19 澳门体育/澳门综艺：原 cdn6.163189.xyz 中继已死（200 但无 #EXTM3U，2026-11-14 审计即死，用户 2026-11-19 12:04 报不能看）。先换 TDM 官方流（live3.tdm.com.mo）run #28 上线，但用户刷新后仍超时——TDM 直连疑似限澳门 IP。改换同中继的另一入口 cdn.qd.je/163189/{amty,amzy}（与在播的澳视卫星/澳视澳门同族：jdshipin 短链解析后就是 cdn.qd.je/163189/as、asam），2026-11-19 12:25 沙箱实测：主播单→cdn6.cc.cd 变体→分片 200（~3.5MB/10s），1080p25 h264，帧验真内容（体育=澳门大赛车直播，综艺=电视剧+澳门综艺角标）。
    "澳门体育": "https://cdn.qd.je/163189/amty",
    "澳门综艺": "https://cdn.qd.je/163189/amzy",
    # 2026-11-20 地方台深查换源（371 台全验：真节目 76、死 157、播单活分片死 31、
    # 广告循环 13、夜间测试卡 94；201 个目标猎手 hunt，帧验找到 21 个替补）：
    # 浙江 6 个广告台：原 ali-m-l.cztv.com channel003/004/006 在播同步购物广告
    # （祖信堂天麻，倒计时停 01:14，30 分钟后分片字节相同=冻结循环）；换浙江广电
    # 官方另一路 ali-xwl.cztv.com 同编号 channel，帧验真节目（经济生活=电视剧《上有老
    # 下有小》1080p，民生=篮球赛，教科=直播推进；教科深夜自带招商二维码横幅，是该台
    # 自身编排）。4 个经济生活/经济/经视/生活本就是同一路 channel003 的重复条目。
    "浙江经济生活": "http://ali-xwl.cztv.com/live/channel031080Plxw.m3u8",
    "浙江经济": "http://ali-xwl.cztv.com/live/channel031080Plxw.m3u8",
    "浙江经视": "http://ali-xwl.cztv.com/live/channel031080Plxw.m3u8",
    "浙江生活": "http://ali-xwl.cztv.com/live/channel031080Plxw.m3u8",
    "浙江民生": "http://ali-xwl.cztv.com/live/channel061080Plxw.m3u8",
    "浙江教科": "http://ali-xwl.cztv.com/live/channel041080Plxw.m3u8",
    # 浙江 6 个县级台：原 freetv.fun 全死（522），换浙江广电官方 cztvcloud
    # lantian SX* 720p（?zzhed），帧验真节目；嵊泗帧为停机检修测试卡（无台标，
    # 身份靠路径判定，恢复播出后需复验），其余 5 台均为真节目。
    "兰溪新闻综合": "http://l.cztvcloud.com/channels/lantian/SXlanxi1/720p.m3u8?zzhed",
    "嵊州新闻综合": "http://l.cztvcloud.com/channels/lantian/SXshengzhou1/720p.m3u8?zzhed",
    "嵊泗综合": "http://l.cztvcloud.com/channels/lantian/SXshengsi1/720p.m3u8?zzhed",
    "平湖新闻综合": "http://l.cztvcloud.com/channels/lantian/SXpinghu1/720p.m3u8?zzhed",
    "开化新闻综合": "http://l.cztvcloud.com/channels/lantian/SXkaihua1/720p.m3u8?zzhed",
    "武义新闻综合": "http://l.cztvcloud.com/channels/lantian/SXwuyi1/720p.m3u8?zzhed",
    "永嘉新闻综合": "http://l.cztvcloud.com/channels/lantian/SXyongjia1/720p.m3u8?zzhed",
    # 广东 3 台 + 金鹰卡通：原 38.75 中继播单活、分片 404（两次复测）；换 txiptv
    # 120.198.84.146:9901/tsfile（与 5/5+ 移除的 223.78.65.165 不同 host），帧验
    # 真节目（珠江=电视剧，体育=CBA 俱乐部杯广州龙狮直播，新闻=纪录片，卡通=动画）。
    # 注意是 txiptv 家族，若用户反馈卡，先回 38.75 再找。
    "广东珠江": "http://120.198.84.146:9901/tsfile/live/1012_1.m3u8",
    "广东体育": "http://120.198.84.146:9901/tsfile/live/1015_1.m3u8",
    "广东新闻": "http://120.198.84.146:9901/tsfile/live/1013_1.m3u8",
    "金鹰卡通": "http://120.198.84.146:9901/tsfile/live/1040_1.m3u8",
    # Astro欢喜台：原 QTV DRM 源无法解码；换 cdn3.indevs.in，帧验真节目（《金针缘》）。
    "Astro欢喜": "https://cdn3.indevs.in/stream/live/hxt/",
    # 辽宁影视剧：原 dassby 生路径（中文未编码）分片 404；换同一 URL 的百分号编码版，
    # 帧验真节目（《烽火英雄传》1080p+沈阳本地广告条）。
    "辽宁影视剧": "http://dassby.qqff.top:99/live/%E8%BE%BD%E5%AE%81%E5%BD%B1%E8%A7%86%E5%89%A7/index.m3u8",
    # 辽宁经济、广东民生：帧验真节目，但沙箱测分片极慢（辽宁经济 ~0.1-0.8Mbps，
    # 广东民生 ~0.3Mbps），可能卡；原源一个是购物广告循环、一个已死，先换上，
    # 待用户实测，若卡再撤。
    "辽宁经济": "http://dassby.qqff.top:99/live/辽宁经济/index.m3u8",
    "广东民生": "http://183.11.239.36:808/hls/18/index.m3u8",
    # 2026-11-14 泰国台缓冲降码率：源是单一码率、无低清晰度可降，
    # 节点无关（香港/新加坡/日本都缓冲）。thaimomo -3(2.3M)->-2(1.2M，同 576p)，
    # -1(240p) 13:19 已验证可用但用户认为不是码率问题，先撤回，保留 -2；
    # DLTV 3128k->1328k (SMIL 低码率分片实测可用)；x2/tpchannel 强制 480p。
    # NBT 未换：iiptvcdn chunklist 会话 ID 每次抓取都变，无法固定低码率地址；
    # Vipa 未换：音频是独立 EXT-X-MEDIA，单指视频分片会丢声音。
    "3HD": "https://live-us1.thaimomo.com/live-as/ch3hd-2/playlist.m3u8",
    "AmarinTV": "https://live-us1.thaimomo.com/live-as/chamarin-2/playlist.m3u8",
    "Channel8": "https://live-us1.thaimomo.com/live-as/cheight-2/playlist.m3u8",
    "MCOT": "https://mcothd-streaming-edge-cdn.mcot.net/tencentmcot/smil:tencentmcot.smil/playlist.m3u8",  # 官方源主播放列表，AVPlayer 自适应(500k-3M)
    "NationTV": "https://live-us1.thaimomo.com/live-as/chNation-2/playlist.m3u8",
    "ThairathTV": "https://live-us1.thaimomo.com/live-as/chthairathhd-2/playlist.m3u8",
    "WorkpointTV": "https://live-us1.thaimomo.com/live-as/chworkpointt-2/playlist.m3u8",
    "13SiamThai": "https://live.x2.co.th/live/13livetv-th_480p/index.m3u8",
    "BoonniyomTV": "https://live.x2.co.th/live/bntv_480p/index.m3u8",
    "ThaiParliamentTelevision": "https://tv-live.tpchannel.org/live/tv_480p.m3u8?vhost=tv-live.tpchannel.org",
    # 2026-11-14 13:2x 换源（非码率问题）：CCTV-1 播放正常，证明用户线路没问题，
    # 是 thaimomo 服务器本身脆弱（分片窗口仅 1-3 个、90 秒过期）。以下 3 台换到
    # 其他主机（均实测可用）：ThaiPBS->ByteArk 480p（600 分片大窗口）；
    # News1->live14 低码率（6 分片）。v2h-cdn 全部 403（泰国限定），其余台无替代源。
    "ThaiPBS": "https://thaipbs-live.cdn.byteark.com/live/playlist_480p/index.m3u8",
    "News1": "http://news1.live14.com/stream/news1_low.m3u8",
    "DLTV1": "https://cdn-live.dltv.ac.th/smil:origin01-dltv-01-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV2": "https://cdn-live.dltv.ac.th/smil:origin01-dltv-02-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV3": "https://cdn-live.dltv.ac.th/smil:origin01-dltv-03-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV4": "https://cdn-live.dltv.ac.th/smil:origin01-dltv-04-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV5": "https://cdn-live.dltv.ac.th/smil:origin01-dltv-05-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV6": "https://cdn-live.dltv.ac.th/smil:origin02-dltv-06-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV7": "https://cdn-live.dltv.ac.th/smil:origin02-dltv-07-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV8": "https://cdn-live.dltv.ac.th/smil:origin02-dltv-08-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV9": "https://cdn-live.dltv.ac.th/smil:origin02-dltv-09-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV10": "https://cdn-live.dltv.ac.th/smil:origin02-dltv-10-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV11": "https://cdn-live.dltv.ac.th/smil:origin03-dltv-11-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV12": "https://cdn-live.dltv.ac.th/smil:origin03-dltv-12-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV13": "https://cdn-live.dltv.ac.th/smil:origin03-dltv-13-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV14": "https://cdn-live.dltv.ac.th/smil:origin03-dltv-14-adaptive.smil/chunklist_b1328000_slth.m3u8",
    "DLTV15": "https://cdn-live.dltv.ac.th/smil:origin03-dltv-15-adaptive.smil/chunklist_b1328000_slth.m3u8",
    # 港澳台 5 个台的新源（2026-11-11 全表排查后找到，变体列表实测有直播分片）
    "明珠": "http://r.jdshipin.com/jUx8K",  # TVB明珠台，原 163189 中继返回空列表
    "凤凰中文": "http://php.jdshipin.com/TVOD/iptv.php?id=fhzw",  # 与凤凰卫视台同一条流
    "凤凰资讯": "http://php.jdshipin.com/TVOD/iptv.php?id=fhzx",  # 替换原来的 FLV 直连
    "千禧经典": "http://php.jdshipin.com/TVOD/iptv.php?id=tvbc",  # TVB千禧经典台
    "无线星河": "https://cdn3.indevs.in/stream/live/tvbxh/",  # 2026-11-22 run #48：原 jdshipin/163189 中继冻结循环（sequence 卡 2489），换 indevs（帧验《玫瑰战争》1080p；只推干净 base URL，variant 的 per-fetch token 不写）
    "天映频道": "https://cdn3.indevs.in/stream/live/typd/",  # 2026-11-22 run #51：原 jdshipin smt.php?id=Celestial 死（301→302 后超时；与天映经典同后端下线），换 indevs（帧验《我爱你！》1080p50，序列推进；只推干净 base URL，variant 的 per-fetch token 不写）
    "翡翠": "http://120.198.84.146:9901/tsfile/live/1020_1.m3u8",  # 2026-11-22 run #48：原 jdshipin/163189 中继入口抖动、用户看不了，换 txiptv 120.198.84.146（帧验翡翠台台标 1080p；不是已删的 223.78.65.165）
    # 全量排查修复（2026-11-14）：以下 5 个台的上游源已死，改用实测直播源
    "CCTV6电影": "http://74.91.26.218:82/live/cctv6hd.m3u8",  # 与 CCTV-6 同源；原 1905 PHP 已坏
    "安多卫视": "http://play.kankanlive.com/live/1711956137852982.m3u8",  # DB AndoTV.cn，内容待用户确认
    "新昌新闻综合": "https://l.cztvcloud.com/channels/lantian/SXxinchang1/720p.m3u8",
    "武进生活": "https://live.wjyanghu.com/live/CH2.m3u8",
    "TonghuaTV": "http://139.211.217.79:9004/hls/75/index.m3u8",  # 沙箱测速很慢，唯一直播源
}

# 备用线路：同名同组多一条 URL。注意 2026-11-15 实测：APTV 在同一订阅内
# 不会把同名条目合并成多线路，而是显示成多个同名频道行，所以死线路只会
# 添乱——候选一律先验证再挂，挂上去的必须是能播的。
# gaoma 全族已死：5 个镜像（douzhicloud / 117.144.58.42 / nctv / kmhlzxs / mg）
# 2026-11-15 04:02 用户实测全部超时（家中网+代理），勿再挂。机制保留待用。
EXTRA_LINES = {}

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

# 泰国只收实测能播的源（与越南/老挝/菲律宾同一标准）。
# 2026-11-14 逐条验证：73 条里 56 条直播（取到 m3u8 且首个分片能下载），
# 其余 17 条不在此表：8 条 v2h-cdn 403（Ch7/GMM25/MONO29/One31/JKN18/TNN16/
# Drama/Thaiban，换 UA+Referer 仍 403，疑似泰国境内限定）、ALTV 403、6 条超时无
# 响应、1 条分片 404、1 条裸 TS 流（World Entertainment TV 42）。每天重建也不会
# 把它们加回来；要加新台：先实测能播，再把 URL 加进这张表。
LIVE_TH_URLS = {
    'http://103.253.74.210:7070/stream/118/index.m3u8',
    'http://103.253.74.210:7070/stream/89/index.m3u8',
    'http://122.155.12.107:1935/live/sbt_tv_aac_300/playlist.m3u8',
    'http://180.180.243.239/streams/3/hls',
    'http://dopachannel.truegse.com/live/dopatv03.m3u8',
    'http://symc-cdn.violin.co.th:1935/tndedge/whitechannel/chunklist.m3u8',
    'http://www5.cabletv.co.th/StreamToCTV/cablechannel/playlist.m3u8',
    'https://cdn-edge.iiptvcdn.com/live_event/smil:4f6e-aa34-2034-5492-c82d.smil/playlist.m3u8',
    'https://cdn-edge.iiptvcdn.com/live_event/smil:f180-054a-38d7-ce66-f7cf.smil/playlist.m3u8',
    'https://cdn-live.dltv.ac.th/dltv01.m3u8',
    'https://cdn-live.dltv.ac.th/dltv02.m3u8',
    'https://cdn-live.dltv.ac.th/dltv03.m3u8',
    'https://cdn-live.dltv.ac.th/dltv04.m3u8',
    'https://cdn-live.dltv.ac.th/dltv05.m3u8',
    'https://cdn-live.dltv.ac.th/dltv06.m3u8',
    'https://cdn-live.dltv.ac.th/dltv07.m3u8',
    'https://cdn-live.dltv.ac.th/dltv08.m3u8',
    'https://cdn-live.dltv.ac.th/dltv09.m3u8',
    'https://cdn-live.dltv.ac.th/dltv10.m3u8',
    'https://cdn-live.dltv.ac.th/dltv11.m3u8',
    'https://cdn-live.dltv.ac.th/dltv12.m3u8',
    'https://cdn-live.dltv.ac.th/dltv13.m3u8',
    'https://cdn-live.dltv.ac.th/dltv14.m3u8',
    'https://cdn-live.dltv.ac.th/dltv15.m3u8',
    'https://cdn-th-vip2.livestreaming.in.th/watsanghathan/watsanghathan/playlist.m3u8',
    'https://cdn.liveplustv.com/v1/live/btl-tv/master.m3u8',
    'https://fastly.live.brightcove.com/1846248737588002042/ap-southeast-1/6075037809001/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJob3N0IjoibzRoaGc2LmVncmVzcy5zYjBmOGsiLCJhY2NvdW50X2lkIjoiNjA3NTAzNzgwOTAwMSIsImVobiI6ImZhc3RseS5saXZlLmJyaWdodGNvdmUuY29tIiwiaXNzIjoiYmxpdmUtcGxheWJhY2stc291cmNlLWFwaSIsInN1YiI6InBhdGhtYXB0b2tlbiIsImF1ZCI6WyI2MDc1MDM3ODA5MDAxIl0sImp0aSI6IjE4NDYyNDg3Mzc1ODgwMDIwNDIifQ.HbjGHxGv87ivAdsCtAdEDjj2SVCfRnCUMYWn2fCkVPY/playlist-hls.m3u8',
    'https://live-iptv.cool-channel.com/cool/live-720P.m3u8',
    'https://live-us1.thaimomo.com/live-as/ch3hd-3/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chNation-3/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chThaipbshd-2/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chTrue4u-2/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chamarin-3/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chboomerang-2/chunklist_w135479847.m3u8',
    'https://live-us1.thaimomo.com/live-as/cheight-3/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chlantung-2/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chmcothd-3/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chnews1-2/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chthairathhd-3/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chtsport-1/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chtvb-2/playlist.m3u8',
    'https://live-us1.thaimomo.com/live-as/chworkpointt-3/playlist.m3u8',
    'https://live.bangkokstream.com:19360/suwannabhumi/suwannabhumi.m3u8',
    'https://live.thaichaiyo.tv/tcy/live-transmux.m3u8',
    'https://live.topnews.co.th/hls/topnews_a_720.m3u8',
    'https://live.x2.co.th/live/13livetv-th.m3u8',
    'https://live.x2.co.th/live/bntv.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/laothaius.sdp/playlist.m3u8',
    'https://livefta.malimarcdn.com/ftaedge00/nat.sdp/playlist.m3u8',
    'https://ramach.ddns.net/live/ramalive/index.m3u8',
    'https://stream1.stou.ac.th/live/stou_720p/playlist.m3u8',
    'https://tv-live.tpchannel.org/live/tv.m3u8',
    'https://vdo.plathong.net/Halaltv/Halaltv/playlist.m3u8',
    'https://vdo.plathong.net/flash7057/flash7057/playlist.m3u8',
    'https://vdo.plathong.net/live8794/live8794/playlist.m3u8',
    'https://vdo.plathong.net/tvmuslim/tvmuslim/playlist.m3u8',
}

# Group order the user asked for (2026-11-11): 央视, 卫视, 港澳台, 日韩,
# then 地方台. Anything that fits none of those (international news,
# Malaysia/Singapore, movie/sports/shopping/documentary specialty channels)
# goes to a trailing 其他 group.
# 新加坡：2026-11-21 审计（sg-audit-2026-11-21.json）帧验通过的 5 条真直播；其余 4 条未入选：5频道中继冻结、TechStorm 已死、meWATCH 只有 DASH、Suria 沙箱无法验证待用户新加坡节点实测。
LIVE_SG_URLS = {
    'http://cdn4.skygo.mn/live/disk1/Boomerang/HLSv3-FTA/Boomerang.m3u8',
    'https://cdn.qd.je/163189/ch8',
    'https://cdn.qd.je/163189/chu',
    'https://d2e1asnsl7br7b.cloudfront.net/7782e205e72f43aeb4a48ec97f66ebbe/index.m3u8',
    'https://amg01082-cna-amg01082c1-rlaxx-us-11304.playouts.now.amagi.tv/playlist.m3u8',
}

GROUP_ORDER = ["央视", "卫视", "港澳台", "新加坡", "泰国", "越南", "老挝", "菲律宾", "日韩", "地方台", "其他"]

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
    # 泰国/越南/老挝/菲律宾按来源分组（放最前：TVB Vietnam 含 TVB，
    # 按名字会被误分到港澳台）。
    if source == "th":
        return "泰国"
    if source == "vn":
        return "越南"
    if source == "la":
        return "老挝"
    if source == "ph":
        return "菲律宾"
    if source == "sg":
        return "新加坡"
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
            # 上游 URL 偶带畸形字符：末尾多余的引号、查询串里的原始方括号
            # （微信推广标签），播放器无法解析。只清洗查询串里的方括号，
            # 避免误伤 IPv6 字面量；引号只去末尾的。
            url = url.rstrip('"')
            if "?" in url:
                _base, _, _q = url.partition("?")
                url = _base + "?" + _q.replace("[", "%5B").replace("]", "%5D")
            entries.append((line, display, url, vlcopts))
            i = j + 1
        else:
            i += 1
    return header, entries


# 澳门莲花卫视：官网首页内嵌趣看 (quklive) 直播间，入口带 auth_key 签名。
# 直播间号会换（旧号停推：1780907795235397 已死），签名本身长期有效
# （auth_key 首字段为 2036 年到期）。每天重建时重新解析当前入口；解析
# 失败时用上次的 URL 顶上，不让构建失败。签名不打印到日志。
LOTUSTV_FALLBACK_URL = "https://play-sh-qudao.quklive.com/live/1793853943346050.m3u8?token=c895f7ab6f3ea341861cf4825c764a6c-47975a22899799cd191022ef20f1b334&auth_key=2109213943-baec122a884d0dc319e3c9ab35376f52-0-8d6175cf97efd15869ff5050daa0d867"
LOTUSTV_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _fetch_text_lotus(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": LOTUSTV_UA, "Referer": "https://www.lotustv.mo/",
        "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=20) as r:
        if r.status != 200:
            raise ValueError(f"HTTP {r.status}")
        return r.read().decode("utf-8", errors="ignore")


def resolve_lotustv_url():
    try:
        home = _fetch_text_lotus("https://www.lotustv.mo/")
        tag = re.search(r'<iframe\b[^>]*\bid\s*=\s*["\']onlive["\'][^>]*>',
                        home, re.I).group(0)
        src = re.search(r'\bsrc\s*=\s*["\']([^"\']+)["\']',
                        tag, re.I).group(1).strip()
        if src.startswith("//"):
            src = "https:" + src
        room = re.match(r"https://cloud\.quklive\.com/cloud/a/embed/(\d+)$",
                        src).group(1)
        page = _fetch_text_lotus(src)
        act = json.loads(re.search(
            r"\bvar\s+activity\s*=\s*(\{.*\})\s*;", page, re.S).group(1))
        if str(act.get("id")) != room:
            raise ValueError("room mismatch")
        url = act["urlGroup"]["hlsUrl"]
        u = urllib.parse.urlparse(url)
        if (u.scheme != "https"
                or not re.fullmatch(r"play-[a-z0-9-]+\.quklive\.com",
                                    u.hostname or "")
                or u.path != f"/live/{room}.m3u8"
                or "auth_key" not in urllib.parse.parse_qs(u.query)):
            raise ValueError("unexpected entry")
        print(f"lotustv: resolved room {room}")
        return url
    except Exception as e:
        print(f"lotustv: resolve failed ({e}), using fallback URL")
        return LOTUSTV_FALLBACK_URL


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

    # 澳门莲花卫视（用户 2026-11-19 要求加入澳门栏）：不在任何上游源里，
    # 在此注入一条。display 含“澳门”→ classify 分到港澳台、hkmo_tier 1（澳门栏）。
    _lotus_url = resolve_lotustv_url()
    _lotus_extinf = ('#EXTINF:-1 tvg-id="LotusTV.mo" tvg-name="澳门莲花卫视" '
                     'tvg-logo="https://www.lotustv.mo/view/assets/image/logo.png" '
                     'group-title="港澳台",澳门莲花卫视')
    all_entries.append(("hk", _lotus_extinf, "澳门莲花卫视", _lotus_url, []))

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
        # DASH (.mpd) 无法在 APTV 播放（只支持 HLS）：直接排除，避免列表里
        # 留一个永远播不了的台（目前只有 MNB World 一个，2026-11-14 全量排查）。
        if url.split("?", 1)[0].lower().endswith(".mpd"):
            n_excluded += 1
            continue
        if src in ("vn", "la", "ph") and url not in LIVE_SEA_URLS:
            n_excluded += 1
            continue
        if src == "th" and url not in LIVE_TH_URLS:
            n_excluded += 1
            continue
        if src == "sg" and url not in LIVE_SG_URLS:
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
        disp = rename_sea(k, disp, src)
        disp = rename_sg(k, disp, src)
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

    # RTHK 31-35 聚在一起（2026-11-14 用户要求）：把港澳台组内的 RTHK 31~35
    # 按台号排成连续一块，放回第一个 RTHK 原来的位置，其余顺序不动。
    _rthk_idx = [i for i, e in enumerate(deduped)
                 if e[5] == "港澳台" and re.fullmatch(r"RTHK3[1-5]", norm_key(e[2]))]
    if len(_rthk_idx) > 1:
        _rthk_block = sorted((deduped[i] for i in _rthk_idx),
                             key=lambda e: int(norm_key(e[2])[4:]))
        _first = _rthk_idx[0]
        _rthk_set = set(_rthk_idx)
        deduped = [e for j, e in enumerate(deduped) if j not in _rthk_set]
        deduped[_first:_first] = _rthk_block

    # CETV-1/2/3 按顺序放（2026-11-20 用户要求）：CETV-2 来自另一上游，排在 CETV-3
    # 后面；把央视组内的 CETV-1~3 按台号排成连续一块，放回第一个 CETV 原来的位置。
    _cetv_idx = [i for i, e in enumerate(deduped)
                 if e[5] == "央视" and re.fullmatch(r"CETV[1-3]", norm_key(e[2]))]
    if len(_cetv_idx) > 1:
        _cetv_block = sorted((deduped[i] for i in _cetv_idx),
                             key=lambda e: int(norm_key(e[2])[4:]))
        _first = _cetv_idx[0]
        _cetv_set = set(_cetv_idx)
        deduped = [e for j, e in enumerate(deduped) if j not in _cetv_set]
        deduped[_first:_first] = _cetv_block
    print(f"deduped: {len(deduped)}")
    for g in GROUP_ORDER:
        print(f"  group {g}: {sum(1 for e in deduped if e[5] == g)}")

    # verification
    _tiers = [hkmo_tier(d) for _, _, d, _, _, g in deduped if g == "港澳台"]
    assert _tiers == sorted(_tiers), "港澳台 tiers out of order!"
    print(f"  港澳台 tiers 香港/澳门/台湾/其他: {[_tiers.count(t) for t in range(4)]}")

    _rthk_pos = [i for i, e in enumerate(deduped)
                 if e[5] == "港澳台" and re.fullmatch(r"RTHK3[1-5]", norm_key(e[2]))]
    if _rthk_pos:
        assert _rthk_pos == list(range(_rthk_pos[0], _rthk_pos[0] + len(_rthk_pos))), "RTHK not clustered!"
        assert [int(norm_key(deduped[i][2])[4:]) for i in _rthk_pos] == sorted(
            int(norm_key(deduped[i][2])[4:]) for i in _rthk_pos), "RTHK out of order!"
        print(f"  RTHK cluster: {[deduped[i][2] for i in _rthk_pos]}")
    _cetv_pos = [i for i, e in enumerate(deduped)
                 if e[5] == "央视" and re.fullmatch(r"CETV[1-3]", norm_key(e[2]))]
    if _cetv_pos:
        assert _cetv_pos == list(range(_cetv_pos[0], _cetv_pos[0] + len(_cetv_pos))), "CETV not clustered!"
        assert [int(norm_key(deduped[i][2])[4:]) for i in _cetv_pos] == sorted(
            int(norm_key(deduped[i][2])[4:]) for i in _cetv_pos), "CETV out of order!"
        print(f"  CETV cluster: {[deduped[i][2] for i in _cetv_pos]}")
    keys = [norm_key(d) for _, _, d, _, _, _ in deduped]
    assert len(keys) == len(set(keys)), "normalized name repeats!"
    disps = [d for _, _, d, _, _, _ in deduped]
    assert len(disps) == len(set(disps)), "display name repeats!"
    assert not any("春晚" in d for d in disps), "春晚 entries remain!"
    assert not any(norm_key(d) in EXCLUDE_KEYS for d in disps), "pay channels remain!"
    # overrides are keyed by the ORIGINAL norm_key, but renamed channels are
    # stored under their Chinese display name (suffix kept), so undo renames
    # via the reverse display-name maps before comparing
    _rev = {v: k for k, v in {**DISPLAY_NAMES, **JP_KR_DISPLAY_NAMES, **SEA_DISPLAY_NAMES, **SG_DISPLAY_NAMES}.items()}
    for name, want_url in SOURCE_OVERRIDES.items():
        def _orig_key(d):
            m = _SUFFIX_RE.match(d)
            core = m.group(1) if m else d
            return _rev.get(core, core)
        hit = [u for _, _, d, u, _, _ in deduped
               if norm_key(d) == norm_key(name)
               or norm_key(_orig_key(d)) == norm_key(name)]
        assert hit and hit[0] == want_url, f"override missing for {name}"
    assert [e[5] for e in deduped] == sorted(
        [e[5] for e in deduped], key=lambda g: GROUP_ORDER.index(g)), "groups out of order!"
    for want in ["CCTV-1", "CCTV-5", "CCTV-13", "湖南卫视", "广东卫视", "浙江卫视",
                 "东方卫视", "北京卫视", "江苏卫视", "凤凰卫视", "TVBS新闻台",
                 "东森财经新闻", "NHK综合电视台", "日本电视台", "东京电视台", "阿里郎",
                 "翡翠", "中天新闻", "RTHK31", "VTV1", "HTV7", "LS TV",
                 "Abante TV", "Thai PBS", "MCOT HD", "NBT 2 HD",
                 "Amarin TV", "泰国公共电视台", "越南电视台1台",
                 "胡志明电视台7台", "希望频道"]:
        hit = [d for d in disps if norm_key(d) == norm_key(want)]
        print(f"  check {want}: {'OK ' + str(hit) if hit else 'MISSING'}")

    # 备用线路：在全部校验之后插入（校验要求显示名唯一），紧跟主条目之后，
    # 只进 deduped 列表。APTV 同名同组条目显示为同一频道的多条线路。
    for _key, _urls in EXTRA_LINES.items():
        for _i, _e in enumerate(deduped):
            if norm_key(_e[2]) == norm_key(_key):
                for _j, _u in enumerate(_urls):
                    deduped.insert(_i + 1 + _j, (_e[0], _e[1], _e[2], _u, [], _e[5]))
                print(f"  extra lines for {_e[2]}: {len(_urls)}")
                break
        else:
            raise AssertionError(f"EXTRA_LINES key not found: {_key}")

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
