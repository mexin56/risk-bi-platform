export type AttributionTab = 'credit' | 'fund';

export function normalizeAttributionTab(value: string | null): AttributionTab {
  return value === 'fund' ? 'fund' : 'credit';
}

export function normalizePageParam(page: string | null): 'overview' | 'attribution' | string {
  if (page === 'fundMonitor') return 'attribution';
  return page || 'overview';
}

export function defaultAttributionTab(canCredit: boolean, canFund: boolean): AttributionTab | null {
  if (canCredit) return 'credit';
  if (canFund) return 'fund';
  return null;
}

export function buildAttributionUrl(currentUrl: string, tab: AttributionTab): string {
  const url = new URL(currentUrl);
  url.searchParams.set('page', 'attribution');
  url.searchParams.set('tab', tab);
  return url.toString();
}
