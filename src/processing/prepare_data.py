from pathlib import Path
import numpy as np
import duckdb
import pandas as pd

DB_PATH = Path("data") / "rt_weather.duckdb"
REF_DIR = Path("data") / "refined"
REF_DIR.mkdir(parents=True, exist_ok=True)

def make_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("ts").reset_index(drop=True)
    df["ts"] = pd.to_datetime(df["ts"])
    df["hour"] = df["ts"].dt.hour
    # codificação cíclica da hora (período 24h)
    df["hour_sin"] = np.sin(2*np.pi*df["hour"]/24)
    df["hour_cos"] = np.cos(2*np.pi*df["hour"]/24)

    for k in [1,2,3,4,5,6,24]:
        df[f"temp_lag_{k}h"] = df["temperature_2m"].shift(k)
    df["temp_ma_3h"] = df["temperature_2m"].rolling(3).mean()
    df["temp_ma_6h"] = df["temperature_2m"].rolling(6).mean()
    df["temp_t_plus_1h"] = df["temperature_2m"].shift(-1)

    df = df.dropna().reset_index(drop=True)

    feat_cols = [c for c in df.columns if c.startswith("temp_lag_")]
    feat_cols += ["temp_ma_3h","temp_ma_6h","relative_humidity_2m","precipitation","wind_speed_10m","hour_sin","hour_cos"]
    feat_cols = [c for c in feat_cols if c in df.columns]
    cols = ["ts"] + feat_cols + ["temp_t_plus_1h"]
    return df[cols]

def main():
    con = duckdb.connect(DB_PATH.as_posix())
    df = con.execute("SELECT * FROM raw.weather_hourly ORDER BY ts").df()
    con.close()

    if df.empty or len(df) < 30:
        print("[WARN] Poucos dados: rode /backfill e /collect na API antes.")
        return

    feat = make_features(df)
    # salva parquet
    out_pq = REF_DIR / "weather_features.parquet"
    feat.to_parquet(out_pq, index=False)
    print(f"[OK] salvo {out_pq} (linhas={len(feat)}, colunas={len(feat.columns)})")

    # (opcional) salvar no DuckDB
    con = duckdb.connect(DB_PATH.as_posix())
    con.execute("CREATE SCHEMA IF NOT EXISTS refined;")
    con.register("feat_tmp", feat)
    con.execute("DROP TABLE IF EXISTS refined.weather_features;")
    con.execute("CREATE TABLE refined.weather_features AS SELECT * FROM feat_tmp;")
    con.unregister("feat_tmp")
    con.close()
    print("[OK] tabela refined.weather_features criada")

if __name__ == "__main__":
    main()
