"""
Analisi automatica database FootyStats.

Cartella input:  data/footystats/*.csv
Output:         output/footystats/<campionato>/<mercato>.xlsx

Esempi:
  python analyze_footystats.py
  python analyze_footystats.py --market over25
  python analyze_footystats.py --market over15 over25 btts
  python analyze_footystats.py --file sweden-superettan.csv
"""
import argparse

from core.footystats_analyzer import DATA_DIR, list_csv_files, run_analysis
from core.footystats_markets import MARKETS


def main():
    parser = argparse.ArgumentParser(description="Analisi range quote 1X2 per mercato")
    parser.add_argument(
        "--market", "-m", nargs="+", choices=list(MARKETS.keys()),
        help="Mercato/i da analizzare (default: tutti)",
    )
    parser.add_argument(
        "--file", "-f", nargs="+",
        help="Solo questi CSV (nomi file in data/footystats/)",
    )
    parser.add_argument("--list-markets", action="store_true", help="Elenco mercati disponibili")
    args = parser.parse_args()

    if args.list_markets:
        print("Mercati disponibili:\n")
        for mid, cfg in MARKETS.items():
            print(f"  {mid:12} → {cfg['label']}")
        return

    files = None
    if args.file:
        files = []
        for name in args.file:
            path = name if name.endswith(".csv") else f"{name}.csv"
            if not path.startswith("data"):
                path = f"{DATA_DIR}/{path.replace('data/footystats/', '')}"
            files.append(path)

    available = list_csv_files()
    if not available:
        print(f"Nessun file in {DATA_DIR}/")
        print("Copia i CSV FootyStats in quella cartella e rilancia.")
        return

    print(f"File trovati: {len(files or available)}")
    print(f"Mercati: {', '.join(args.market) if args.market else 'TUTTI'}\n")

    summary = run_analysis(market_ids=args.market, files=files)

    for league in summary["campionato"].unique():
        sub = summary[summary["campionato"] == league]
        print(f"=== {league} ===")
        for _, r in sub.iterrows():
            print(
                f"  {r['mercato']:<28} base {r['winrate_base']:5.1f}% | "
                f"best {r['miglior_range']} ROI {r['miglior_roi']:+.1f}% | "
                f"robusto {r['range_robusto']} WR {r['wr_robusto']}% (n={r['n_robusto']})"
            )
        print()

    print("Salvato: output/footystats/riepilogo_tutti.xlsx")


if __name__ == "__main__":
    main()
