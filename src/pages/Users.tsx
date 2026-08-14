import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
  UserCog,
} from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { api, PAGE_PERMISSIONS, type AuthUser } from '@/lib/auth';

interface UserRow {
  id: number;
  username: string;
  display_name: string;
  role_key: string;
  role_name: string;
  enabled: boolean;
  created_at: string;
  last_login_at: string | null;
}

interface RoleRow {
  key: string;
  name: string;
  permissions: string[];
  builtin: boolean;
  user_count: number;
}

interface UserForm {
  username: string;
  display_name: string;
  password: string;
  role_key: string;
  enabled: boolean;
}

const EMPTY_FORM: UserForm = {
  username: '',
  display_name: '',
  password: '',
  role_key: 'analyst',
  enabled: true,
};

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : '操作失败，请稍后重试';
}

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function roleBadge(roleKey: string): { background: string; color: string } {
  switch (roleKey) {
    case 'admin':
      return { background: 'rgba(var(--brand-rgb),0.12)', color: 'var(--brand)' };
    case 'analyst':
      return { background: 'rgba(16,185,129,0.10)', color: '#059669' };
    case 'viewer':
      return { background: 'rgba(100,116,139,0.10)', color: '#64748b' };
    default:
      return { background: 'rgba(124,108,240,0.10)', color: '#7c6cf0' };
  }
}

const GRADIENT_BTN =
  'inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[12.5px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-60';
const GHOST_BTN =
  'inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-[12px] text-slate-500 hover:text-slate-700 hover:bg-slate-100/80 transition-colors disabled:opacity-40';

export default function UsersPage({ currentUser }: { currentUser: AuthUser }) {
  const [tab, setTab] = useState<'users' | 'roles'>('users');
  const [users, setUsers] = useState<UserRow[]>([]);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');

  const [userDialog, setUserDialog] = useState<'none' | 'create' | 'edit'>('none');
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [form, setForm] = useState<UserForm>(EMPTY_FORM);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<UserRow | null>(null);

  const [roleDialog, setRoleDialog] = useState(false);
  const [roleKey, setRoleKey] = useState('');
  const [roleName, setRoleName] = useState('');
  const [rolePerms, setRolePerms] = useState<string[]>(['overview']);
  const [roleDrafts, setRoleDrafts] = useState<Record<string, string[]>>({});
  const [deleteRoleTarget, setDeleteRoleTarget] = useState<RoleRow | null>(null);

  const flash = (msg: string) => {
    setNotice(msg);
    window.setTimeout(() => setNotice((v) => (v === msg ? '' : v)), 2600);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [u, r] = await Promise.all([
        api<{ users: UserRow[] }>('/api/auth/users'),
        api<{ roles: RoleRow[] }>('/api/auth/roles'),
      ]);
      setUsers(u.users);
      setRoles(r.roles);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        u.username.toLowerCase().includes(q) ||
        u.display_name.toLowerCase().includes(q) ||
        u.role_name.toLowerCase().includes(q),
    );
  }, [users, search]);

  const roleNameOf = (key: string) => roles.find((r) => r.key === key)?.name ?? key;

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM, role_key: roles.find((r) => !r.builtin)?.key ?? 'analyst' });
    setFormError('');
    setUserDialog('create');
  };

  const openEdit = (u: UserRow) => {
    setEditing(u);
    setForm({
      username: u.username,
      display_name: u.display_name,
      password: '',
      role_key: u.role_key,
      enabled: u.enabled,
    });
    setFormError('');
    setUserDialog('edit');
  };

  const handleSaveUser = async () => {
    setSaving(true);
    setFormError('');
    try {
      if (userDialog === 'create') {
        if (!form.username.trim() || !form.password) {
          setFormError('请填写用户名和初始密码');
          return;
        }
        const created = await api<AuthUser>('/api/auth/users', {
          method: 'POST',
          body: JSON.stringify({
            username: form.username.trim(),
            display_name: form.display_name.trim() || form.username.trim(),
            password: form.password,
            role_key: form.role_key,
            enabled: form.enabled,
          }),
        });
        setUsers((prev) => [
          ...prev,
          {
            id: created.id,
            username: created.username,
            display_name: created.display_name,
            role_key: created.role_key,
            role_name: created.role_name,
            enabled: created.enabled,
            created_at: created.created_at,
            last_login_at: created.last_login_at ?? null,
          },
        ]);
        flash(`已创建用户「${created.display_name}」`);
      } else if (editing) {
        const body: Record<string, unknown> = {
          display_name: form.display_name.trim() || editing.username,
          role_key: form.role_key,
          enabled: form.enabled,
        };
        if (form.password) body.password = form.password;
        await api<{ ok: boolean }>(`/api/auth/users/${editing.id}`, {
          method: 'PUT',
          body: JSON.stringify(body),
        });
        setUsers((prev) =>
          prev.map((x) =>
            x.id === editing.id
              ? {
                  ...x,
                  display_name: body.display_name as string,
                  role_key: form.role_key,
                  role_name: roleNameOf(form.role_key),
                  enabled: form.enabled,
                }
              : x,
          ),
        );
        flash('用户信息已更新');
      }
      setUserDialog('none');
    } catch (err) {
      setFormError(errMsg(err));
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEnabled = async (u: UserRow, enabled: boolean) => {
    try {
      await api<{ ok: boolean }>(`/api/auth/users/${u.id}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled }),
      });
      setUsers((prev) => prev.map((x) => (x.id === u.id ? { ...x, enabled } : x)));
      flash(enabled ? `已启用「${u.display_name}」` : `已禁用「${u.display_name}」`);
    } catch (err) {
      setError(errMsg(err));
    }
  };

  const handleDeleteUser = async () => {
    if (!deleteTarget) return;
    try {
      await api<{ ok: boolean }>(`/api/auth/users/${deleteTarget.id}`, { method: 'DELETE' });
      setUsers((prev) => prev.filter((x) => x.id !== deleteTarget.id));
      flash(`已删除用户「${deleteTarget.display_name}」`);
      setDeleteTarget(null);
    } catch (err) {
      setError(errMsg(err));
      setDeleteTarget(null);
    }
  };

  const togglePerm = (role: RoleRow, perm: string, on: boolean) => {
    setRoleDrafts((d) => {
      const base = d[role.key] ?? role.permissions;
      const next = on
        ? base.includes(perm)
          ? base
          : [...base, perm]
        : base.filter((x) => x !== perm);
      return { ...d, [role.key]: next };
    });
  };

  const handleSaveRole = async (role: RoleRow) => {
    const perms = roleDrafts[role.key] ?? role.permissions;
    try {
      await api<{ ok: boolean }>(`/api/auth/roles/${role.key}`, {
        method: 'PUT',
        body: JSON.stringify({ permissions: perms }),
      });
      setRoles((prev) => prev.map((r) => (r.key === role.key ? { ...r, permissions: perms } : r)));
      setRoleDrafts((d) => {
        const next = { ...d };
        delete next[role.key];
        return next;
      });
      flash(`「${role.name}」权限已保存，即时生效`);
    } catch (err) {
      setError(errMsg(err));
    }
  };

  const handleCreateRole = async () => {
    setSaving(true);
    setFormError('');
    try {
      if (!roleKey.trim() || !roleName.trim()) {
        setFormError('请填写角色标识和名称');
        return;
      }
      await api<{ ok: boolean }>('/api/auth/roles', {
        method: 'POST',
        body: JSON.stringify({
          key: roleKey.trim().toLowerCase(),
          name: roleName.trim(),
          permissions: rolePerms,
        }),
      });
      setRoleDialog(false);
      setRoleKey('');
      setRoleName('');
      setRolePerms(['overview']);
      await load();
      flash('角色已创建');
    } catch (err) {
      setFormError(errMsg(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRole = async () => {
    if (!deleteRoleTarget) return;
    try {
      await api<{ ok: boolean }>(`/api/auth/roles/${deleteRoleTarget.key}`, { method: 'DELETE' });
      setRoles((prev) => prev.filter((r) => r.key !== deleteRoleTarget.key));
      flash(`已删除角色「${deleteRoleTarget.name}」`);
      setDeleteRoleTarget(null);
    } catch (err) {
      setError(errMsg(err));
      setDeleteRoleTarget(null);
    }
  };

  const tabBtn = (on: boolean) =>
    `px-3.5 py-1.5 rounded-lg text-[12px] font-medium transition-colors ${
      on ? 'text-white' : 'text-slate-500 hover:text-slate-700'
    }`;

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto">
      {/* ===== 头部 ===== */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: 'rgba(var(--brand-rgb),0.12)', color: 'var(--brand)' }}
          >
            <UserCog size={16} />
          </div>
          <div>
            <div className="text-[15.5px] font-semibold tracking-tight">权限管理</div>
            <div className="text-[11px] text-slate-400 mt-0.5">用户 · 角色 · 页面访问权限</div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2.5">
          <div className="flex items-center gap-1 bg-slate-100/90 rounded-xl p-1">
            <button onClick={() => setTab('users')} className={tabBtn(tab === 'users')} style={tab === 'users' ? { background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' } : undefined}>
              用户管理
            </button>
            <button onClick={() => setTab('roles')} className={tabBtn(tab === 'roles')} style={tab === 'roles' ? { background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' } : undefined}>
              角色权限
            </button>
          </div>
          {tab === 'users' ? (
            <button
              onClick={openCreate}
              className={GRADIENT_BTN}
              style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))', boxShadow: '0 4px 12px rgba(var(--brand-rgb),0.3)' }}
            >
              <Plus size={14} /> 新建用户
            </button>
          ) : (
            <button
              onClick={() => {
                setFormError('');
                setRoleDialog(true);
              }}
              className={GRADIENT_BTN}
              style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))', boxShadow: '0 4px 12px rgba(var(--brand-rgb),0.3)' }}
            >
              <Plus size={14} /> 新建角色
            </button>
          )}
        </div>
      </div>

      {/* ===== 提示条 ===== */}
      {notice && (
        <div className="flex items-center gap-2 text-[12px] text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-xl px-3 py-2">
          <CheckCircle2 size={14} className="shrink-0" /> {notice}
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 text-[12px] text-rose-600 bg-rose-50 border border-rose-100 rounded-xl px-3 py-2">
          <AlertCircle size={14} className="shrink-0" /> {error}
        </div>
      )}

      {/* ===== 内容 ===== */}
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-24 text-[12.5px] text-slate-400">
          <Loader2 size={15} className="animate-spin" /> 正在加载…
        </div>
      ) : tab === 'users' ? (
        <div className="space-y-3">
          {/* 搜索栏 */}
          <div className="flex items-center gap-2 bg-white/60 backdrop-blur-xl rounded-2xl border border-white/60 shadow-[0_1px_2px_rgba(15,23,42,0.04)] px-4 py-3">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索用户名 / 姓名 / 角色"
                className="h-9 w-64 pl-9 pr-3 rounded-lg border border-slate-200 text-[12.5px] outline-none focus:border-[var(--brand)] transition-colors"
              />
            </div>
            <div className="ml-auto text-[11px] text-slate-400">
              共 {users.length} 个账号 · 启用 {users.filter((u) => u.enabled).length} 个
            </div>
          </div>

          {/* 用户表 */}
          <div className="bg-white/60 backdrop-blur-xl rounded-2xl border border-white/60 shadow-[0_1px_2px_rgba(15,23,42,0.04)] overflow-hidden">
            <table className="w-full text-left text-[12.5px]">
              <thead>
                <tr className="text-[11px] text-slate-400 border-b border-slate-100 bg-slate-50/60">
                  <th className="px-4 py-3 font-medium">用户</th>
                  <th className="px-4 py-3 font-medium">角色</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">最近登录</th>
                  <th className="px-4 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => {
                  const isSelf = u.username === currentUser.username;
                  return (
                    <tr key={u.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <div
                            className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold text-white shrink-0"
                            style={{
                              background:
                                u.role_key === 'admin'
                                  ? 'linear-gradient(135deg, var(--brand), var(--brand-300))'
                                  : 'linear-gradient(135deg, #64748b, #94a3b8)',
                            }}
                          >
                            {u.display_name.slice(0, 1)}
                          </div>
                          <div>
                            <div className="font-medium text-slate-800">{u.display_name}</div>
                            <div className="text-[10.5px] text-slate-400">
                              {u.username}
                              {isSelf ? ' · 当前账号' : ''}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className="px-2 py-0.5 rounded-md text-[11px] font-medium"
                          style={roleBadge(u.role_key)}
                        >
                          {u.role_name}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <Switch
                          checked={u.enabled}
                          onCheckedChange={(v) => handleToggleEnabled(u, v)}
                          disabled={isSelf}
                          className="data-[state=checked]:bg-[var(--brand)]"
                        />
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-[11.5px] tabular-nums">{formatTime(u.last_login_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => openEdit(u)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-[var(--brand)] hover:bg-[rgba(var(--brand-rgb),0.08)] transition-colors"
                            title="编辑"
                          >
                            <Pencil size={13} />
                          </button>
                          <button
                            onClick={() => setDeleteTarget(u)}
                            disabled={isSelf}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-colors disabled:opacity-30 disabled:hover:text-slate-400 disabled:hover:bg-transparent"
                            title={isSelf ? '不能删除当前账号' : '删除'}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-[12px] text-slate-400">
                      没有匹配的用户
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {roles.map((role) => {
            const perms = roleDrafts[role.key] ?? role.permissions;
            return (
              <div key={role.key} className="bg-white/60 backdrop-blur-xl rounded-2xl border border-white/60 shadow-[0_1px_2px_rgba(15,23,42,0.04)] p-5">
                <div className="flex items-center gap-2.5 mb-1">
                  <span
                    className="px-2 py-0.5 rounded-md text-[11px] font-semibold text-white"
                    style={{
                      background:
                        role.key === 'admin'
                          ? 'linear-gradient(135deg, var(--brand), var(--brand-300))'
                          : 'linear-gradient(135deg, #64748b, #94a3b8)',
                    }}
                  >
                    {role.name}
                  </span>
                  <code className="text-[10.5px] text-slate-400">{role.key}</code>
                  {role.builtin && (
                    <span className="text-[10px] text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">内置</span>
                  )}
                  <span className="ml-auto text-[10.5px] text-slate-400">{role.user_count} 名用户</span>
                  {!role.builtin && (
                    <button
                      onClick={() => setDeleteRoleTarget(role)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-colors"
                      title="删除角色"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>
                <div className="text-[11px] text-slate-400 mb-3">页面访问权限 · 修改后立即对所有该角色用户生效</div>
                {role.key === 'admin' && (
                  <div className="mb-3 text-[10.5px] text-amber-600/90 bg-amber-50 border border-amber-100 rounded-lg px-2.5 py-1.5">
                    管理员角色始终拥有全部权限（含本页），下方勾选仅作参考展示。
                  </div>
                )}
                <div className="grid grid-cols-2 gap-1.5">
                  {PAGE_PERMISSIONS.map((p) => (
                    <label
                      key={p.key}
                      onClick={() => togglePerm(role, p.key, !perms.includes(p.key))}
                      className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-slate-100 hover:border-slate-200 hover:bg-slate-50/60 transition-colors cursor-pointer select-none"
                    >
                      <span className="pointer-events-none">
                        <Checkbox
                          checked={perms.includes(p.key)}
                          onCheckedChange={() => undefined}
                          className="data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
                        />
                      </span>
                      <span className="text-[12px] text-slate-600 pointer-events-none">{p.label}</span>
                    </label>
                  ))}
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <button
                    onClick={() => {
                      setRoleDrafts((d) => {
                        const next = { ...d };
                        delete next[role.key];
                        return next;
                      });
                    }}
                    className="text-[11.5px] text-slate-400 hover:text-slate-600 px-2 py-1.5 rounded-lg transition-colors"
                  >
                    重置
                  </button>
                  <button
                    onClick={() => handleSaveRole(role)}
                    className="ml-auto px-4 py-1.5 rounded-lg text-[12px] font-medium text-white transition-opacity hover:opacity-90"
                    style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' }}
                  >
                    保存权限
                  </button>
                </div>
              </div>
            );
          })}

          {/* 新建角色 */}
          <button
            onClick={() => {
              setFormError('');
              setRoleDialog(true);
            }}
            className="min-h-[180px] rounded-xl border-2 border-dashed border-slate-200 hover:border-[rgba(var(--brand-rgb),0.45)] hover:bg-white/70 transition-colors flex flex-col items-center justify-center gap-2 text-slate-400 hover:text-[var(--brand)]"
          >
            <Plus size={20} />
            <span className="text-[12.5px] font-medium">新建角色</span>
          </button>
        </div>
      )}

      {/* ===== 新建/编辑用户弹窗 ===== */}
      <Dialog
        open={userDialog !== 'none'}
        onOpenChange={(o) => {
          if (!o) {
            setUserDialog('none');
            setFormError('');
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{userDialog === 'create' ? '新建用户' : '编辑用户'}</DialogTitle>
            <DialogDescription>
              {userDialog === 'create' ? '创建后用户即可使用账号密码登录平台。' : '修改角色或状态后立即生效。'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3.5 mt-1">
            {userDialog === 'create' && (
              <div>
                <label className="text-[11.5px] font-medium text-slate-500 mb-1.5 block">用户名</label>
                <Input
                  value={form.username}
                  onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                  placeholder="字母 / 数字 / 下划线，2-32 位"
                  autoFocus
                />
              </div>
            )}
            <div>
              <label className="text-[11.5px] font-medium text-slate-500 mb-1.5 block">显示名称</label>
              <Input
                value={form.display_name}
                onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                placeholder="例如：风控分析师 · 张三"
              />
            </div>
            <div>
              <label className="text-[11.5px] font-medium text-slate-500 mb-1.5 block">角色</label>
              <Select value={form.role_key} onValueChange={(v) => setForm((f) => ({ ...f, role_key: v }))}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择角色" />
                </SelectTrigger>
                <SelectContent>
                  {roles.map((r) => (
                    <SelectItem key={r.key} value={r.key}>
                      {r.name}（{r.key}）
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-[11.5px] font-medium text-slate-500 mb-1.5 block">
                {userDialog === 'create' ? '初始密码' : '重置密码（留空则不修改）'}
              </label>
              <Input
                type="password"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                placeholder="至少 6 位"
              />
            </div>
            <div className="flex items-center justify-between pt-1">
              <span className="text-[12px] text-slate-600">启用账号</span>
              <Switch
                checked={form.enabled}
                onCheckedChange={(v) => setForm((f) => ({ ...f, enabled: v }))}
                className="data-[state=checked]:bg-[var(--brand)]"
              />
            </div>
            {formError && (
              <div className="flex items-center gap-2 text-[12px] text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-3 py-2">
                <AlertCircle size={13} className="shrink-0" /> {formError}
              </div>
            )}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <button className={GHOST_BTN}>取消</button>
            </DialogClose>
            <button
              onClick={handleSaveUser}
              disabled={saving}
              className={GRADIENT_BTN}
              style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' }}
            >
              {saving ? '保存中…' : '保存'}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ===== 新建角色弹窗 ===== */}
      <Dialog
        open={roleDialog}
        onOpenChange={(o) => {
          setRoleDialog(o);
          if (!o) setFormError('');
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>新建角色</DialogTitle>
            <DialogDescription>创建后可为其勾选页面访问权限。</DialogDescription>
          </DialogHeader>
          <div className="space-y-3.5 mt-1">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11.5px] font-medium text-slate-500 mb-1.5 block">角色标识</label>
                <Input
                  value={roleKey}
                  onChange={(e) => setRoleKey(e.target.value)}
                  placeholder="例如：risk_ops"
                  autoFocus
                />
              </div>
              <div>
                <label className="text-[11.5px] font-medium text-slate-500 mb-1.5 block">角色名称</label>
                <Input
                  value={roleName}
                  onChange={(e) => setRoleName(e.target.value)}
                  placeholder="例如：风控运营"
                />
              </div>
            </div>
            <div>
              <label className="text-[11.5px] font-medium text-slate-500 mb-1.5 block">初始权限</label>
              <div className="grid grid-cols-2 gap-1.5 max-h-52 overflow-y-auto custom-scroll pr-1">
                {PAGE_PERMISSIONS.map((p) => (
                  <label
                    key={p.key}
                    onClick={() =>
                      setRolePerms((prev) =>
                        prev.includes(p.key) ? prev.filter((x) => x !== p.key) : [...prev, p.key],
                      )
                    }
                    className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-slate-100 hover:border-slate-200 transition-colors cursor-pointer select-none"
                  >
                    <span className="pointer-events-none">
                      <Checkbox
                        checked={rolePerms.includes(p.key)}
                        onCheckedChange={() => undefined}
                        className="data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
                      />
                    </span>
                    <span className="text-[12px] text-slate-600 pointer-events-none">{p.label}</span>
                  </label>
                ))}
              </div>
            </div>
            {formError && (
              <div className="flex items-center gap-2 text-[12px] text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-3 py-2">
                <AlertCircle size={13} className="shrink-0" /> {formError}
              </div>
            )}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <button className={GHOST_BTN}>取消</button>
            </DialogClose>
            <button
              onClick={handleCreateRole}
              disabled={saving}
              className={GRADIENT_BTN}
              style={{ background: 'linear-gradient(135deg, var(--brand), var(--brand-300))' }}
            >
              {saving ? '创建中…' : '创建角色'}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ===== 删除用户确认 ===== */}
      <Dialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>删除用户</DialogTitle>
            <DialogDescription>
              确定删除用户「{deleteTarget?.display_name}」？该操作不可恢复，其登录会话将立即失效。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <button className={GHOST_BTN}>取消</button>
            </DialogClose>
            <button
              onClick={handleDeleteUser}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[12.5px] font-medium text-white bg-rose-500 hover:bg-rose-600 transition-colors"
            >
              <Trash2 size={13} /> 确认删除
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ===== 删除角色确认 ===== */}
      <Dialog open={!!deleteRoleTarget} onOpenChange={(o) => !o && setDeleteRoleTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>删除角色</DialogTitle>
            <DialogDescription>
              确定删除角色「{deleteRoleTarget?.name}」？删除后该角色下用户将无法登录，请先为其迁移角色。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <button className={GHOST_BTN}>取消</button>
            </DialogClose>
            <button
              onClick={handleDeleteRole}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-[12.5px] font-medium text-white bg-rose-500 hover:bg-rose-600 transition-colors"
            >
              <Trash2 size={13} /> 确认删除
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
