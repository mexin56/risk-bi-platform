import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertCircle,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  User as UserIcon,
} from 'lucide-react';
import { login, type AuthSession } from '@/lib/auth';

// ==================== OpenHanako · 暖纸风格 ====================
// 纸色纸感 + 5 级墨色 + 印章青唯一强调 + 利落小圆角 + 0.5px hairline
const SEAL = '#537D96';
const SEAL_DARK = '#3F6179';
const CORAL = '#8B2C1F';

const DEMO_ACCOUNTS = [
  { label: '管理员', username: 'admin', password: 'admin123' },
  { label: '分析师', username: 'analyst', password: 'analyst123' },
  { label: '访客', username: 'viewer', password: 'viewer123' },
];

const FIELD_CLS =
  'w-full h-11 pl-10 rounded-[2px] border text-[13.5px] text-[#2A2622] ' +
  'placeholder:text-[#8F867B] outline-none transition-all backdrop-blur-md ' +
  'bg-[rgba(251,247,238,0.32)] border-[rgba(216,207,190,0.75)] ' +
  'shadow-[0_10px_28px_rgba(42,38,34,0.12)] ' +
  'focus:bg-[rgba(251,247,238,0.55)] focus:border-[#537D96] focus:ring-[3px] focus:ring-[rgba(83,125,150,0.18)]';

export default function Login({ onSuccess }: { onSuccess: (session: AuthSession) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('请输入用户名和密码');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const session = await login(username.trim(), password);
      onSuccess(session);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden flex items-center justify-center p-4">
      {/* 深圳天际线背景图（暖纸调色罩统一色调） */}
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: "url('/login-bg.jpg')" }}
      />
      {/* 暖纸轻叠色（让照片融入纸色主题，同时保证文字可读） */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(135deg, rgba(245,239,228,0.42) 0%, rgba(255,255,255,0.22) 45%, rgba(245,239,228,0.55) 100%)',
        }}
      />

      {/* 顶部品牌条 */}

      {/* 登录卡片 */}
      <motion.div
        initial={{ opacity: 0, y: 26, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        className="relative z-10 w-full max-w-[420px]"
      >
        <div
          className="relative rounded-2xl border p-8 backdrop-blur-xl"
          style={{
            background: 'rgba(251,247,238,0.66)',
            borderColor: 'rgba(216,207,190,0.8)',
            boxShadow: '0 24px 64px rgba(42,38,34,0.16)',
          }}
        >
          {/* 朱砂印章点缀 */}
          <div
            className="absolute -right-2.5 -top-3 w-11 h-11 rounded-[5px] flex flex-col items-center justify-center rotate-6 select-none"
            style={{
              background: CORAL,
              boxShadow: '0 4px 10px rgba(139,44,31,0.28)',
              fontFamily: "'STKaiti','KaiTi','SimSun',serif",
            }}
          >
            <span className="text-[#FBF7EE] text-[13px] font-semibold leading-none tracking-[0.2em]">风控</span>
            <span className="text-[#FBF7EE] text-[6px] leading-none mt-0.5 opacity-85" style={{ fontFamily: 'system-ui, sans-serif' }}>
              BI
            </span>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            {/* 用户名 */}
            <div className="relative">
              <UserIcon size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8F867B]" />
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="请输入用户名"
                autoComplete="username"
                autoFocus
                className={FIELD_CLS}
              />
            </div>
            {/* 密码 */}
            <div className="relative">
              <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#8F867B]" />
              <input
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                autoComplete="current-password"
                className={FIELD_CLS}
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-[#8F867B] hover:text-[#4A433C] transition-colors"
                title={showPw ? '隐藏密码' : '显示密码'}
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>

            {/* 错误提示 */}
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-center gap-2 text-[12px] rounded-[2px] px-3 py-2.5"
                style={{
                  color: CORAL,
                  background: 'rgba(139,44,31,0.06)',
                  border: '1px solid rgba(139,44,31,0.22)',
                }}
              >
                <AlertCircle size={14} className="shrink-0" />
                {error}
              </motion.div>
            )}

            {/* 登录按钮（印章青） */}
            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-[2px] text-[14px] font-medium text-[#FBF7EE] transition-colors disabled:opacity-60 flex items-center justify-center gap-2 hover:brightness-95"
              style={{ background: SEAL, border: `1px solid ${SEAL_DARK}`, boxShadow: `0 2px 0 ${SEAL_DARK}` }}
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Lock size={15} />}
              {loading ? '登录中…' : '登 录'}
            </button>
          </form>

          {/* 演示账号 */}
          <div className="mt-5 pt-4" style={{ borderTop: '1px solid #E4DBC8' }}>
            <div className="text-[10.5px] mb-2 text-[#6B6158]">演示账号（点击快速填充）</div>
            <div className="flex flex-wrap gap-1.5">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.username}
                  type="button"
                  onClick={() => {
                    setUsername(a.username);
                    setPassword(a.password);
                    setError('');
                  }}
                  className="px-2.5 py-1.5 rounded-[2px] text-[11.5px] transition-colors"
                  style={{
                    background: '#F1E9D8',
                    border: '1px solid #D8CFBE',
                    color: '#4A433C',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#E9DFC8')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = '#F1E9D8')}
                >
                  {a.label} · <span className="font-medium">{a.username}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-5 text-center text-[10.5px] tracking-wide text-[#8F867B]">
          © 风控BI监控平台 · 内部系统，仅限授权人员访问
        </div>
      </motion.div>
    </div>
  );
}
