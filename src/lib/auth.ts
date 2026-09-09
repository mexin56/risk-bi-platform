// ==================== 登录会话与权限 ====================
// 与 server/auth.py 配套：token 存 localStorage，所有 /api 请求自动附带
// Authorization: Bearer <token>；角色权限由服务端实时下发。

const TOKEN_KEY = 'rc-bi-token';

export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  role_key: string;
  role_name: string;
  permissions: string[];
  enabled: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuthSession {
  token: string;
  user: AuthUser;
}

export interface PermissionInfo {
  key: string;
  label: string;
}

// 页面权限目录：与后端 PERMISSION_CATALOG 保持一致
export const PAGE_PERMISSIONS: PermissionInfo[] = [
  { key: 'overview', label: '大盘数据' },
  { key: 'lifecycle', label: '客户生命周期' },
  { key: 'creditStrategy', label: '提额策略监控' },
  { key: 'attribution', label: '授信归因监控' },
  { key: 'fundMonitor', label: '资金归结监控' },
  { key: 'channel', label: '渠道质量' },
  { key: 'fraud', label: '反欺诈监控' },
  { key: 'vintage', label: 'Vintage 监控' },
  { key: 'model', label: '模型分监控' },
  { key: 'stability', label: '模型稳定性' },
  { key: 'users', label: '权限管理' },
];

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* ignore */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function hasPermission(user: AuthUser | null | undefined, key: string): boolean {
  return Boolean(user && (user.role_key === 'admin' || user.permissions.includes(key)));
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(path, { ...options, headers });
  const body = (await response.json().catch(() => ({}))) as { detail?: string } & T;
  if (!response.ok) {
    throw new Error(body.detail || `请求失败（HTTP ${response.status}）`);
  }
  return body as T;
}

export async function login(username: string, password: string): Promise<AuthSession> {
  const session = await api<AuthSession>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setToken(session.token);
  return session;
}

export async function fetchMe(): Promise<AuthUser> {
  return api<AuthUser>('/api/auth/me');
}

export async function logout(): Promise<void> {
  try {
    await api<{ ok: boolean }>('/api/auth/logout', { method: 'POST' });
  } finally {
    clearToken();
  }
}
