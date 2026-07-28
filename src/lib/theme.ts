// ==================== 主题配色系统 ====================
// 主色通过 CSS 变量 + JS 模块双通道下发：CSS 变量驱动 DOM 元素，JS 驱动 ECharts

export interface ThemePreset {
  key: string;
  name: string;
  brand: string; // 主色
  brand300: string; // 深色背景上的浅色（文字/高光）
  bg: string; // 主区域浅色背景
}

export const THEME_PRESETS: ThemePreset[] = [
  { key: 'blue', name: '经典蓝', brand: '#4e83fd', brand300: '#9db9ff', bg: '#f4f6fa' },
  { key: 'teal', name: '青碧', brand: '#12b5a5', brand300: '#5eead4', bg: '#f2f8f7' },
  { key: 'violet', name: '靛紫', brand: '#7c6cf0', brand300: '#c4b5fd', bg: '#f6f5fb' },
  { key: 'green', name: '松绿', brand: '#22a06b', brand300: '#6ee7b7', bg: '#f3f8f5' },
  { key: 'orange', name: '熔橙', brand: '#ef7d3c', brand300: '#fdba74', bg: '#faf6f2' },
];

function hexToRgb(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

let current: ThemePreset = THEME_PRESETS[0];
try {
  const saved = localStorage.getItem('rc-bi-theme');
  if (saved) {
    const hit = THEME_PRESETS.find((p) => p.key === saved);
    if (hit) current = hit;
  }
} catch {
  /* ignore */
}

export function applyTheme(p: ThemePreset) {
  current = p;
  const root = document.documentElement;
  root.style.setProperty('--brand', p.brand);
  root.style.setProperty('--brand-rgb', hexToRgb(p.brand));
  root.style.setProperty('--brand-300', p.brand300);
  root.style.setProperty('--app-bg', p.bg);
  try {
    localStorage.setItem('rc-bi-theme', p.key);
  } catch {
    /* ignore */
  }
}

export function getTheme(): ThemePreset {
  return current;
}

export function getBrand(): string {
  return current.brand;
}

// ECharts 色板：主色打头，其余为语义色（成功/预警/危险/辅助）
export function getPalette(): string[] {
  return [current.brand, '#36cfc9', '#ffb020', '#f76965', '#7f6bf2', '#37c26b', '#ff8f4d'];
}
