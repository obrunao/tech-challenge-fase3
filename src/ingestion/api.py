# src/ingestion/api.py
# API para coletar clima horário (Open-Meteo) e gravar em DuckDB.
# - /collect: últimas horas (forecast) -> filtra FUTURO, salva ts em UTC
# - /backfill: histórico por intervalo (start_date/end_date) ou por 'days'
# - Dedup por (ts, latitude, longitude)
# - Lat/Lon normalizados (4 casas) para consistência

from pathlib import Path
from datetime import date, timedelta
from typing import Optional

import duckdb
import pandas as pd
import requests
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
DB_PATH = Path("data") / "rt_weather.duckdb"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",  # alternativamente pode vir 'relativehumidity_2m'
    "precipitation",
    "wind_speed_10m",        # alternativamente pode vir 'windspeed_10m'
]

# ---------------------------------------------------------------------
# DuckDB: criar tabela se não existir
# ---------------------------------------------------------------------
def ensure_table() -> None:
    con = duckdb.connect(DB_PATH.as_posix())
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS raw.weather_hourly (
            ts TIMESTAMP,
            latitude DOUBLE,
            longitude DOUBLE,
            temperature_2m DOUBLE,
            relative_humidity_2m DOUBLE,
            precipitation DOUBLE,
            wind_speed_10m DOUBLE
        );
        """
    )
    con.close()

ensure_table()

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def norm_latlon(lat: float, lon: float, nd: int = 4):
    """Arredonda lat/lon para nd casas (evita 'quase duplicatas')."""
    return round(lat, nd), round(lon, nd)

def to_df_hourly(payload: dict, lat: float, lon: float) -> pd.DataFrame:
    """
    Converte o JSON da Open-Meteo em DataFrame horário.
    - 'time' vem no fuso indicado em 'timezone' (quando usamos timezone=auto)
    - localiza no fuso, CORTA FUTURO e converte 'ts' para UTC (naive) antes de gravar
    """
    hourly = payload.get("hourly", {})
    tz_name = payload.get("timezone", "UTC")  # ex.: "America/Sao_Paulo"

    # Normaliza chaves que mudam entre endpoints antigos/novos
    rh = hourly.get("relative_humidity_2m", hourly.get("relativehumidity_2m", []))
    ws = hourly.get("wind_speed_10m", hourly.get("windspeed_10m", []))

    df = pd.DataFrame(
        {
            "ts": hourly.get("time", []),
            "latitude": lat,
            "longitude": lon,
            "temperature_2m": hourly.get("temperature_2m", []),
            "relative_humidity_2m": rh,
            "precipitation": hourly.get("precipitation", []),
            "wind_speed_10m": ws,
        }
    )
    if df.empty:
        return df

    # 1) timestamps no fuso local retornado pela API
    df["ts"] = pd.to_datetime(df["ts"])
    df["ts"] = df["ts"].dt.tz_localize(tz_name, ambiguous="infer")

    # 2) remove FUTURO (compara no mesmo fuso)
    now_local = pd.Timestamp.now(tz_name).floor("H")
    df = df[df["ts"] <= now_local]

    # 3) converte para UTC e remove tz (naive) para armazenar
    df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)

    # remove linhas sem temperatura
    df = df.dropna(subset=["temperature_2m"]).reset_index(drop=True)
    return df

def append_duckdb(df: pd.DataFrame) -> int:
    """Insere no DuckDB apenas linhas novas (dedupe por ts, latitude, longitude)."""
    if df.empty:
        return 0
    con = duckdb.connect(DB_PATH.as_posix())
    con.register("df_tmp", df)

    # Compatível com todas as versões: usa NOT EXISTS no lugar de ANTI JOIN
    con.execute(
        """
        CREATE TEMP TABLE new_rows AS
        SELECT t.*
        FROM df_tmp AS t
        WHERE NOT EXISTS (
            SELECT 1
            FROM raw.weather_hourly AS r
            WHERE r.ts = t.ts
              AND r.latitude = t.latitude
              AND r.longitude = t.longitude
        );
        """
    )
    inserted = con.execute("SELECT COUNT(*) FROM new_rows").fetchone()[0]
    con.execute("INSERT INTO raw.weather_hourly SELECT * FROM new_rows;")
    con.execute("DROP TABLE new_rows;")
    con.unregister("df_tmp")
    con.close()
    return inserted

# ---------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------
app = FastAPI(
    title="Tech Challenge Fase 3 – Weather API",
    description="Coleta de clima horário (Open-Meteo) + persistência em DuckDB",
    version="1.2.0",
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/collect")
def collect(
    latitude: float = Query(-23.55, description="Latitude (padrão: São Paulo)"),
    longitude: float = Query(-46.63, description="Longitude (padrão: São Paulo)"),
    past_hours: int = Query(6, ge=1, le=48, description="Quantas horas anteriores trazer"),
):
    """
    Coleta as ÚLTIMAS horas (passadas) a partir do forecast e grava no DuckDB.
    Mesmo usando forecast_hours=0, filtramos novamente no código para garantir que nada futuro entre.
    """
    try:
        latitude, longitude = norm_latlon(latitude, longitude)
        hourly_list = ",".join(HOURLY_VARS)
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            f"&hourly={hourly_list}"
            f"&past_hours={past_hours}&forecast_hours=0"
            "&timezone=auto"
        )
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        payload = r.json()
        df = to_df_hourly(payload, latitude, longitude)
        n = append_duckdb(df)

        tz_used = payload.get("timezone", "UTC")
        first_ts = df["ts"].min().isoformat() if not df.empty else None
        last_ts = df["ts"].max().isoformat() if not df.empty else None

        return {
            "inserted_rows": int(n),
            "rows_returned": int(len(df)),
            "lat": latitude,
            "lon": longitude,
            "timezone": tz_used,
            "first_ts_utc": first_ts,
            "last_ts_utc": last_ts,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/backfill")
def backfill(
    latitude: float = Query(-23.55),
    longitude: float = Query(-46.63),
    days: int = Query(30, ge=1, le=180, description="Dias de histórico caso não informe intervalo"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Baixa histórico horário (archive) e grava no DuckDB.
    - Se 'start_date' e 'end_date' forem passados, usa esse intervalo explicitamente (inclusivo).
    - Caso contrário, usa 'days' retroativos a partir de hoje.
    """
    try:
        latitude, longitude = norm_latlon(latitude, longitude)

        if start_date and end_date:
            s, e = start_date, end_date
        else:
            e = date.today().isoformat()
            s = (date.today() - timedelta(days=days)).isoformat()

        hourly_list = ",".join(HOURLY_VARS)
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={latitude}&longitude={longitude}"
            f"&hourly={hourly_list}"
            f"&start_date={s}&end_date={e}"
            "&timezone=auto"
        )
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        payload = r.json()
        df = to_df_hourly(payload, latitude, longitude)
        n = append_duckdb(df)

        tz_used = payload.get("timezone", "UTC")
        first_ts = df["ts"].min().isoformat() if not df.empty else None
        last_ts = df["ts"].max().isoformat() if not df.empty else None

        return {
            "inserted_rows": int(n),
            "rows_returned": int(len(df)),
            "lat": latitude,
            "lon": longitude,
            "timezone": tz_used,
            "first_ts_utc": first_ts,
            "last_ts_utc": last_ts,
            "range_used": {"start_date": s, "end_date": e},
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
