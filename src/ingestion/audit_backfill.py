from pathlib import Path
import argparse
import duckdb
import pandas as pd

DB_PATH = Path("data/rt_weather.duckdb")

def audit(lat: float, lon: float, days: int = 30):
    con = duckdb.connect(DB_PATH.as_posix())
    try:
        # pega tudo da cidade
        df = con.execute(
            """
            SELECT ts
            FROM raw.weather_hourly
            WHERE round(latitude,4)=round(?,4) AND round(longitude,4)=round(?,4)
            ORDER BY ts
            """,
            [lat, lon],
        ).df()
    finally:
        con.close()

    if df.empty:
        print("Nenhum dado para essa cidade. Faça backfill/coleta primeiro.")
        return

    # janela: últimos N dias até a última hora coletada
    last_ts = pd.to_datetime(df["ts"].max())
    start_ts = last_ts - pd.Timedelta(days=days)

    win = df[(pd.to_datetime(df["ts"]) >= start_ts) & (pd.to_datetime(df["ts"]) <= last_ts)].copy()
    win["ts"] = pd.to_datetime(win["ts"])

    # grade horária esperada
    expected = pd.date_range(start=start_ts, end=last_ts, freq="H")
    got = pd.Series(1, index=win["ts"])
    # horas faltantes
    missing = expected.difference(got.index)

    # resumo
    hours_expected = len(expected)
    hours_got = win.shape[0]
    coverage = 100 * hours_got / hours_expected if hours_expected else 0

    print("=== AUDITORIA BACKFILL ===")
    print(f"Local: lat={lat}, lon={lon}")
    print(f"Janela (UTC): {start_ts} -> {last_ts}  ({days} dias)")
    print(f"Horas esperadas: {hours_expected}")
    print(f"Horas gravadas:  {hours_got}")
    print(f"Cobertura:       {coverage:.2f}%")
    if len(missing) == 0:
        print("OK: nenhuma hora faltando na janela.")
    else:
        print(f"Horas faltantes: {len(missing)} (mostrando até 20)")
        for t in list(missing[:20]):
            print(" -", t)

    # distribuição por dia (para diagnóstico)
    daily = (win.assign(day=win["ts"].dt.floor("D"))
                .groupby("day")["ts"].count()
                .rename("hours"))
    print("\nHoras por dia (últimos 10):")
    print(daily.tail(10))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=-23.55)
    ap.add_argument("--lon", type=float, default=-46.63)
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    audit(args.lat, args.lon, args.days)
