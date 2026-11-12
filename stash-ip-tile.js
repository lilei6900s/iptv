// Stash Tile 面板脚本：显示当前出口 IP、运营商和所在地（中文版）
// 数据来源：https://api.ip.sb/geoip
let url = "https://api.ip.sb/geoip";

$httpClient.get(url, function (error, response, data) {
  if (error) {
    $done({
      title: "当前出口 IP",
      content: "获取 IP 信息失败",
      icon: "exclamationmark.triangle.fill",
      backgroundColor: "#FF9500",
    });
    return;
  }

  let jsonData = JSON.parse(data);

  let country = jsonData.country || "未知国家";
  let countryCode = jsonData.country_code || "";
  let emoji = getFlagEmoji(countryCode);
  let city = jsonData.city || jsonData.region || "未知城市";
  let isp = jsonData.organization || "未知运营商";
  let ip = jsonData.ip || "未知 IP";

  $done({
    title: "当前出口 IP",
    content: `${ip}\n${isp}\n${emoji}${country} - ${city}`,
    icon: "network.badge.shield.half.filled",
    backgroundColor: "#0C9DFA",
  });
});

function getFlagEmoji(countryCode) {
  if (!countryCode) return "";
  if (countryCode.toUpperCase() === "TW") {
    countryCode = "CN";
  }
  const codePoints = countryCode
    .toUpperCase()
    .split("")
    .map((char) => 127397 + char.charCodeAt());
  return String.fromCodePoint(...codePoints);
}
