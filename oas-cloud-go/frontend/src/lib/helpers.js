export function statusTagType(status) {
  if (status === "active") return "success";
  if (status === "disabled") return "danger";
  if (status === "expired") return "warning";
  return "info";
}

export function keyStatusTagType(status) {
  if (status === "unused") return "success";
  if (status === "used") return "warning";
  if (status === "revoked") return "danger";
  if (status === "deleted") return "danger";
  return "info";
}

export function userTypeLabel(userType) {
  if (userType === "duiyi") return "对弈竞猜";
  if (userType === "shuaka") return "刷卡";
  return "日常";
}

export function patchSummary(target, source, keys) {
  keys.forEach((key) => {
    const value = Number(source?.[key] ?? 0);
    target[key] = Number.isFinite(value) ? value : 0;
  });
}

export function ensureTaskConfig(taskCfg) {
  const merged = {
    enabled: false,
    next_time: "",
    fail_delay: 30,
    ...(taskCfg || {}),
  };
  if (typeof merged.enabled !== "boolean") merged.enabled = false;
  if (typeof merged.next_time !== "string") merged.next_time = "";
  if (typeof merged.fail_delay !== "number") merged.fail_delay = Number(merged.fail_delay || 0);
  return merged;
}

export function parseTaskConfigFromRaw(rawString) {
  try {
    const parsed = JSON.parse(rawString || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export const ASSET_FIELDS = [
  { key: "level", label: "等级" },
  { key: "stamina", label: "体力" },
  { key: "gouyu", label: "勾玉" },
  { key: "lanpiao", label: "蓝票" },
  { key: "gold", label: "金币" },
  { key: "gongxun", label: "功勋" },
  { key: "xunzhang", label: "勋章" },
  { key: "tupo_ticket", label: "突破票" },
  { key: "fanhe_level", label: "饭盒等级" },
  { key: "jiuhu_level", label: "酒壶等级" },
  { key: "liao_level", label: "寮等级" },
];

export const USER_TYPE_OPTIONS = [
  { value: "daily", label: "日常" },
  { value: "duiyi", label: "对弈竞猜" },
  { value: "shuaka", label: "刷卡" },
];

export function formatTime(isoString) {
  if (!isoString || isoString === "-") return "-";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return isoString;
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function statusLabel(status) {
  const map = { active: "活跃", expired: "已过期", disabled: "已禁用" };
  return map[status] || status || "-";
}

export function keyStatusLabel(status) {
  const map = { unused: "未使用", used: "已使用", revoked: "已撤销", deleted: "已删除" };
  return map[status] || status || "-";
}

export function isHHmmPattern(value) {
  return /^\d{2}:\d{2}$/.test(value);
}

export async function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // 降级：HTTP 环境使用 execCommand
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;pointer-events:none;';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {
    if (!document.execCommand('copy')) throw new Error('execCommand failed');
  } finally {
    document.body.removeChild(ta);
  }
}
