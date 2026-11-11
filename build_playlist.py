#!/usr/bin/env python3
"""Rebuild the merged + deduped IPTV playlist from fresh upstreams.

Priority: Guovin (auto-tested CCTV+satellite) > bestK (satellite+HK/MO/TW)
         > iptv-org jp > iptv-org kr.
Dedup by normalized name, one entry per channel, first occurrence wins.
Run daily by GitHub Actions (.github/workflows/daily-rebuild.yml).
"""

import re
import sys
import urllib.request

SOURCES = [
    ("guovin", "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u"),
    ("bestk", "https://raw.githubusercontent.com/bestK/iptv/main/iptv.m3u"),
    ("jp", "https://iptv-org.github.io/iptv/countries/jp.m3u"),
    ("kr", "https://iptv-org.github.io/iptv/countries/kr.m3u"),
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


def norm_key(name):
    n = name
    n = re.sub(r"\([^)]*\)", "", n)
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
    return n


# Channels the user asked to leave out (2026-11-11): CCTV pay channels and
# past Spring Festival Gala recordings. Matched on the normalized name, so
# they stay out of every daily rebuild, not just this one snapshot.
EXCLUDE_KEYS = {
    "文化精品", "央视台球", "风云音乐", "第一剧场", "风云剧场", "怀旧剧场",
    "女性时尚", "高尔夫网球", "风云足球", "电视指南", "世界地理", "兵器科技",
    "CHC家庭影院", "CHC动作电影",
}
EXCLUDE_SUBSTRINGS = ("春晚",)


def excluded(display):
    k = norm_key(display)
    if k in EXCLUDE_KEYS:
        return True
    return any(s in k for s in EXCLUDE_SUBSTRINGS)


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
        key = (display, url)
        if key in seen_pair:
            continue
        seen_pair.add(key)
        merged.append((src, extinf, display, url, vlcopts))
    print(f"merged (exact-dup removed): {len(merged)} (excluded {n_excluded} pay/春晚 entries)")

    # deduped: one entry per normalized name, first occurrence wins
    deduped = []
    seen_key = set()
    for src, extinf, display, url, vlcopts in merged:
        k = norm_key(display)
        if not k or k in seen_key:
            continue
        seen_key.add(k)
        disp = to_simp(display)
        deduped.append((src, extinf, disp, url, vlcopts))
    print(f"deduped: {len(deduped)}")

    # verification
    keys = [norm_key(d) for _, _, d, _, _ in deduped]
    assert len(keys) == len(set(keys)), "normalized name repeats!"
    disps = [d for _, _, d, _, _ in deduped]
    assert len(disps) == len(set(disps)), "display name repeats!"
    assert not any("春晚" in d for d in disps), "春晚 entries remain!"
    assert not any(norm_key(d) in EXCLUDE_KEYS for d in disps), "pay channels remain!"
    for want in ["CCTV-1", "CCTV-5", "CCTV-13", "湖南卫视", "广东卫视", "浙江卫视",
                 "东方卫视", "北京卫视", "江苏卫视", "凤凰卫视", "TVBS新闻台",
                 "东森财经新闻", "NHK General TV", "Nippon TV", "TV Tokyo", "Arirang",
                 "翡翠", "中天新闻", "RTHK31"]:
        hit = [d for d in disps if norm_key(d) == norm_key(want)]
        print(f"  check {want}: {'OK ' + str(hit) if hit else 'MISSING'}")

    def render(entries):
        out = list(header) + [""]
        for _, extinf, display, url, vlcopts in entries:
            # keep original extinf but swap in the (simplified) display name
            base = extinf.rsplit(",", 1)[0]
            out.append(f"{base},{display}")
            out.extend(vlcopts)
            out.append(url)
        return "\n".join(out) + "\n"

    merged_text = render(merged)
    deduped_text = render(deduped)
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
