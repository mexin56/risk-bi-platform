export class LatestRequestGuard {
  private latest = 0;

  begin() {
    this.latest += 1;
    return this.latest;
  }

  isCurrent(requestId: number) {
    return requestId === this.latest;
  }
}
