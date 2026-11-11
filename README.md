# IPTV 直播源（每天自动更新）

一个台只留一条的去重版订阅：央视 + 卫视 + 港澳台 + 日韩，约 660 台。

## 订阅链接（APTV 直接用这个）

```
https://raw.githubusercontent.com/lilei6900s/iptv/main/iptv.m3u
```

## 每天自动更新

`.github/workflows/daily-rebuild.yml` 每天 08:00（北京时间）自动从上游重建：

- 央视 + 主流卫视：[Guovin/iptv-api](https://github.com/Guovin/iptv-api)（自动测速）
- 港澳台 + 更多卫视：[bestK/iptv](https://github.com/bestK/iptv)（每小时自检）
- 日本 / 韩国：[iptv-org](https://github.com/iptv-org/iptv)

去重规则见 `build_playlist.py`：按归一化台名去重，每台保留第一条源。

已排除：央视付费频道（风云剧场、第一剧场、怀旧剧场、世界地理、风云音乐、风云足球、女性时尚、电视指南、央视文化精品、兵器科技、央视台球、高尔夫网球、CHC 家庭影院、CHC 动作电影）和历年春晚录像。

## 文件

- `iptv.m3u` — 订阅用这个（去重版，约 700 台）
- `IPTV-全频道-去重版.m3u` — 与上面内容相同
- `IPTV-全频道-央视卫视港澳台日韩.m3u` — 未去重原版（约 1000 条，某台播不了可以从这里换源）
