from pathlib import Path
import duckdb, joblib, pandas as pd
from src.processing.prepare_data import make_features

DB_PATH = Path("data") / "rt_weather.duckdb"
MODEL_PATH = Path("models") / "model_rf_temp_next_hour.pkl"

def main():
    con = duckdb.connect(DB_PATH.as_posix())
    df = con.execute("SELECT * FROM raw.weather_hourly ORDER BY ts").df()
    con.close()
    if df.empty or len(df) < 12:
        print("[WARN] dados insuficientes, rode a API /backfill e /collect.")
        return
    feat = make_features(df)
    # última linha contém features para prever a próxima hora do último ponto observado
    x = feat.drop(columns=["temp_t_plus_1h","ts"]).iloc[[-1]]
    model = joblib.load(MODEL_PATH)
    pred = model.predict(x)[0]
    print(f"Previsão para a PRÓXIMA hora: {pred:.2f} °C")

if __name__ == "__main__":
    main()
