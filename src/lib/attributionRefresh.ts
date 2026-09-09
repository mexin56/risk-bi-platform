export interface AttributionRefreshMeta {
  serving?: boolean;
  async_refresh?: boolean;
}

export function isAttributionRefreshReady(
  generatedAt: string,
  baselineGeneratedAt: string,
  meta: AttributionRefreshMeta,
) {
  return generatedAt !== baselineGeneratedAt || (meta.serving === true && meta.async_refresh !== true);
}
