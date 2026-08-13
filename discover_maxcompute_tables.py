from __future__ import annotations

"""Read-only, bounded discovery of likely online credit-strategy tables."""

from probe_flexi_cash_strategy import get_odps

TERMS = ("cash", "jq", "flexi", "credit", "quota", "strategy", "config", "te_")


def main() -> None:
    odps = get_odps()
    tables = odps.list_tables()
    matches: list[str] = []
    count = 0
    for table in tables:
        count += 1
        name = getattr(table, "name", str(table))
        lower = name.lower()
        if any(term in lower for term in TERMS):
            matches.append(name)
    print(f"SCANNED={count}; MATCHES={len(matches)}")
    for name in sorted(matches):
        print(name)


if __name__ == "__main__":
    main()
