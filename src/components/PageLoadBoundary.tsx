import { Component, type ReactNode } from 'react';

export default class PageLoadBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    console.error('平台页面加载失败', error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return <div role="alert" className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="max-w-md text-center">
        <h1 className="text-lg font-semibold text-slate-800">页面暂时无法显示</h1>
        <p className="mt-2 text-sm text-slate-500">请重新加载页面后再试。</p>
        <button type="button" onClick={() => window.location.reload()} className="mt-5 rounded-md border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700">重新加载</button>
      </div>
    </div>;
  }
}
