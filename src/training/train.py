# src/training/train.py
# Treina RandomForestRegressor para prever temperatura da PRÓXIMA hora (t+1h)
# Salva: modelo (.pkl), lista de colunas usadas no fit (feature_cols.json)
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
import matplotlib.pyplot as plt

REF_PQ = Path("data/refined/weather_features.parquet")
MODEL_DIR = Path("models")
DOCS_DIR = Path("docs")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def time_split(df: pd.DataFrame, test_size: float = 0.2):
    """Split temporal: primeiras linhas = treino, últimas = teste."""
    n = len(df)
    cut = int(n * (1 - test_size))
    return df.iloc[:cut], df.iloc[cut:]


def main():
    if not REF_PQ.exists():
        raise FileNotFoundError(
            f"Arquivo de features não encontrado: {REF_PQ}. "
            "Rode: python src/processing/prepare_data.py"
        )

    df = pd.read_parquet(REF_PQ)

    # X (features) e y (alvo)
    y = df["temp_t_plus_1h"]
    X = df.drop(columns=["temp_t_plus_1h", "ts"], errors="ignore")

    # Guarda as colunas usadas no fit
    feature_cols = X.columns.tolist()

    # Split temporal
    df_xy = pd.concat([X, y], axis=1)
    train, test = time_split(df_xy, test_size=0.2)
    Xtr, ytr = train.iloc[:, :-1], train.iloc[:, -1]
    Xte, yte = test.iloc[:, :-1], test.iloc[:, -1]

    # Baseline: persistência (y_hat = temp_lag_1h)
    if "temp_lag_1h" in Xte.columns:
        y_pred_naive = Xte["temp_lag_1h"].values
        mae_n = mean_absolute_error(yte, y_pred_naive)
        rmse_n = np.sqrt(mean_squared_error(yte, y_pred_naive))
        print(f"Baseline (persistência) -> MAE={mae_n:.2f}°C | RMSE={rmse_n:.2f}°C")
    else:
        mae_n = rmse_n = np.nan
        print("Baseline indisponível (faltou coluna temp_lag_1h).")

    # Modelo
    rf = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1)
    rf.fit(Xtr, ytr)

    y_pred = rf.predict(Xte)
    mae = mean_absolute_error(yte, y_pred)
    rmse = np.sqrt(mean_squared_error(yte, y_pred))
    print(f"RandomForest -> MAE={mae:.2f}°C | RMSE={rmse:.2f}°C")

    # Gráfico comparando real vs previsões (janela final)
    last = min(120, len(yte))
    plt.figure(figsize=(9, 4))
    plt.plot(range(last), yte.values[-last:], label="Real")
    plt.plot(range(last), y_pred[-last:], label="RF")
    if not np.isnan(mae_n):
        plt.plot(range(last), y_pred_naive[-last:], label="Persistência")
    plt.legend()
    plt.title("Real vs Previsões (janela final)")
    out_img = DOCS_DIR / "forecast_compare.png"
    plt.savefig(out_img, bbox_inches="tight")
    plt.close()
    print(f"[OK] gráfico salvo em {out_img}")

    # Salva modelo + colunas
    model_path = MODEL_DIR / "model_rf_temp_next_hour.pkl"
    joblib.dump(rf, model_path)
    with open(MODEL_DIR / "feature_cols.json", "w", encoding="utf-8") as f:
        json.dump(feature_cols, f, ensure_ascii=False, indent=2)

    print(
        f"[OK] modelo salvo em {model_path}\n"
        f"[OK] {len(feature_cols)} features salvas em models/feature_cols.json"
    )


if __name__ == "__main__":
    main()
