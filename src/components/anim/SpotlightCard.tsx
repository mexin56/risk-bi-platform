import { useRef, type ReactNode, type MouseEvent } from 'react';

// React Bits 风格鼠标追光卡片：光标处泛起品牌色微光 + 边框高光
export default function SpotlightCard({
  children,
  className = '',
  spotlightColor = 'rgba(78,131,253,0.10)',
}: {
  children: ReactNode;
  className?: string;
  spotlightColor?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const onMove = (e: MouseEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty('--mx', `${e.clientX - rect.left}px`);
    el.style.setProperty('--my', `${e.clientY - rect.top}px`);
  };

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      className={`group/spot relative overflow-hidden ${className}`}
      style={{ ['--mx' as string]: '50%', ['--my' as string]: '50%' }}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-0 group-hover/spot:opacity-100 transition-opacity duration-300"
        style={{
          background: `radial-gradient(240px circle at var(--mx) var(--my), ${spotlightColor}, transparent 70%)`,
        }}
      />
      {children}
    </div>
  );
}
