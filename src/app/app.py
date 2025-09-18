# src/app/app.py
# App Streamlit: histórico + previsão da PRÓXIMA hora (t+1h)
# - Seleção de cidade ou coordenadas
# - Hora local do lugar + último registro local + Δh
# - Limpeza SOMENTE dos dados brutos (raw.weather_hourly): por cidade ou geral
# - Coleta via API (collect/backfill)
# - Gráfico no fuso da cidade
# - Alinha features com as do treino (feature_cols.json) antes de prever

# --- garantir que a raiz do projeto esteja no sys.path (para importar src/*) ---
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# -----------------------------------------------------------------------------

import json
import requests
import duckdb
import joblib
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from src.processing.prepare_data import make_features  # MESMAS features do treino

# ---------------------------
# Caminhos e configs
# ---------------------------
DB_PATH = ROOT / "data" / "rt_weather.duckdb"
MODEL_PATH = ROOT / "models" / "model_rf_temp_next_hour.pkl"
FEATURES_PATH = ROOT / "models" / "feature_cols.json"
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="RT Weather – Next Hour Temp", layout="centered")
st.title("🌦️ Previsão de Temperatura (Próxima Hora)")

# ---------------------------
# Utilitários
# ---------------------------
def get_timezone_for(lat: float, lon: float) -> str:
    """
    Descobre o fuso da localidade consultando diretamente a Open-Meteo
    (não insere nada no DB).
    """
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("timezone", "UTC")
    except Exception:
        return "UTC"

def get_last_ts_utc() -> pd.Timestamp | None:
    """Lê o MAX(ts) da tabela raw.weather_hourly (UTC / naive)."""
    if not DB_PATH.exists():
        return None
    con = duckdb.connect(DB_PATH.as_posix())
    try:
        # tabela pode não existir ainda
        return con.execute("SELECT MAX(ts) FROM raw.weather_hourly").fetchone()[0]
    except Exception:
        return None
    finally:
        con.close()

def delete_raw_city(lat: float, lon: float) -> int:
    """
    Remove SOMENTE as linhas da cidade atual (lat/lon) da tabela raw.weather_hourly.
    Usa arredondamento a 4 casas para evitar problemas de float.
    Retorna o nº de linhas removidas.
    """
    if not DB_PATH.exists():
        return 0
    con = duckdb.connect(DB_PATH.as_posix())
    try:
        n = con.execute(
            """
            SELECT COUNT(*) FROM raw.weather_hourly
            WHERE round(latitude,4)=round(?,4) AND round(longitude,4)=round(?,4)
            """,
            [lat, lon],
        ).fetchone()[0]
        con.execute(
            """
            DELETE FROM raw.weather_hourly
            WHERE round(latitude,4)=round(?,4) AND round(longitude,4)=round(?,4)
            """,
            [lat, lon],
        )
        return int(n)
    except Exception:
        return 0
    finally:
        con.close()

def delete_raw_all() -> int:
    """
    Remove TODAS as linhas da tabela raw.weather_hourly (não mexe em refined/modelos).
    Retorna o nº de linhas removidas.
    """
    if not DB_PATH.exists():
        return 0
    con = duckdb.connect(DB_PATH.as_posix())
    try:
        n = con.execute("SELECT COUNT(*) FROM raw.weather_hourly").fetchone()[0]
        con.execute("DELETE FROM raw.weather_hourly")
        return int(n)
    except Exception:
        return 0
    finally:
        con.close()

# ---------------------------
# Seleção do local
# ---------------------------
st.subheader("Local")

CITIES = {
    "São Paulo, BR": (-23.55, -46.63),
    "Rio de Janeiro, BR": (-22.9000, -43.2000),
    "Belo Horizonte, BR": (-19.9167, -43.9345),
    "Curitiba, BR": (-25.4284, -49.2733),
    "Porto Alegre, BR": (-30.0331, -51.2300),
    "Lisboa, PT": (38.7223, -9.1393),
    "Porto, PT": (41.1579, -8.6291),
    "Madrid, ES": (40.4168, -3.7038),
    "Londres, UK": (51.5074, -0.1278),
    "Berlim, DE": (52.5244, 13.4105),
    "Nova York, US": (40.7128, -74.0060),
    "Tóquio, JP": (35.6762, 139.6503),
    "Sydney, AU": (-33.8688, 151.2093),
}

modo = st.radio(
    "Como escolher o lugar?",
    ["Lista de cidades", "Coordenadas manuais"],
    horizontal=True,
)

if modo == "Lista de cidades":
    cidade = st.selectbox("Cidade", list(CITIES.keys()), index=0)
    lat, lon = CITIES[cidade]
    st.caption(f"Lat/Lon selecionados: {lat:.4f}, {lon:.4f}")
else:
    col1, col2 = st.columns(2)
    lat = col1.number_input("Latitude", value=-23.55, step=0.01, format="%.4f")
    lon = col2.number_input("Longitude", value=-46.63, step=0.01, format="%.4f")

# ---------------------------
# Barra lateral: Coleta + Relógio local + Limpeza de dados brutos
# ---------------------------
with st.sidebar:
    st.header("Coleta (API FastAPI)")
    if st.button("🔄 Coletar agora (últimas 6h)"):
        try:
            r = requests.get(
                f"{API_BASE}/collect",
                params={"latitude": lat, "longitude": lon, "past_hours": 6},
                timeout=20,
            )
            st.success(r.json())
        except Exception as e:
            st.error(str(e))
    if st.button("📦 Backfill (últimos 30 dias)"):
        try:
            r = requests.post(
                f"{API_BASE}/backfill",
                params={"latitude": lat, "longitude": lon, "days": 30},
                timeout=60,
            )
            st.success(r.json())
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("🕒 Hora local & status")
    tz = get_timezone_for(lat, lon)
    now_local = pd.Timestamp.now(tz).floor("H")
    last_utc = get_last_ts_utc()
    if last_utc is not None:
        last_local = pd.Timestamp(last_utc, tz="UTC").tz_convert(tz)
        delta_h = (now_local - last_local) / pd.Timedelta(hours=1)
        st.write(f"**Timezone:** {tz}")
        st.write(f"**Agora (local):** {now_local}")
        st.write(f"**Último registro (local):** {last_local}")
    else:
        st.info(f"Timezone: {tz}\n\nSem registros ainda — faça o backfill/coleta.")

    st.divider()
    st.subheader("🧹 Limpar DADOS BRUTOS (raw)")
    st.caption("Remove apenas linhas da tabela raw.weather_hourly. Não mexe em features/modelos.")

    col_a, col_b = st.columns(2)
    with col_a:
        confirm_city = st.checkbox("Confirmo (cidade atual)")
        if st.button("Apagar dados brutos\n(desta cidade)", disabled=not confirm_city):
            n = delete_raw_city(lat, lon)
            st.success(f"Removidas {n} linhas desta cidade.")
            st.experimental_rerun()
    with col_b:
        confirm_all = st.checkbox("Confirmo (todos os locais)")
        if st.button("Apagar dados brutos\n(todos os locais)", disabled=not confirm_all):
            n = delete_raw_all()
            st.success(f"Removidas {n} linhas de todos os locais.")
            st.experimental_rerun()

# ---------------------------
# Carregar dados do DuckDB
# ---------------------------
if not DB_PATH.exists():
    st.warning("Banco DuckDB não encontrado. Rode a API /backfill ou /collect primeiro.")
    st.stop()

con = duckdb.connect(DB_PATH.as_posix())
df = con.execute("SELECT * FROM raw.weather_hourly ORDER BY ts").df()
con.close()

if df.empty:
    st.warning("Sem dados ainda. Use os botões na barra lateral para coletar.")
    st.stop()

df_local = df.copy()
df_local["ts_local"] = (
    pd.to_datetime(df_local["ts"]).dt.tz_localize("UTC").dt.tz_convert(tz)
)
st.write(f"Fuso da cidade: **{tz}**")
st.line_chart(df_local.set_index("ts_local")["temperature_2m"].tail(48))


# ---------------------------
# Carregar modelo e lista de features do treino
# ---------------------------
if not MODEL_PATH.exists() or not FEATURES_PATH.exists():
    st.error(
        "Modelo/feature_cols não encontrados. Rode o treino primeiro "
        "(prepare_data.py e training/train.py)."
    )
    st.stop()

model = joblib.load(MODEL_PATH)
with open(FEATURES_PATH, "r", encoding="utf-8") as f:
    feature_cols = json.load(f)

# ---------------------------
# Gerar features atuais e ALINHAR ao conjunto do treino
# ---------------------------
feat = make_features(df)
if len(feat) == 0:
    st.warning("Ainda não há features suficientes (rode mais coletas ou o backfill).")
    st.stop()

X = feat.drop(columns=["temp_t_plus_1h", "ts"], errors="ignore")

# adiciona colunas faltantes com zero
for c in feature_cols:
    if c not in X.columns:
        X[c] = 0
# mantém exatamente as colunas do treino e na mesma ordem (remove extras)
X = X[feature_cols]

# ---------------------------
# Previsão da próxima hora
# ---------------------------
x_last = X.iloc[[-1]]
y_hat = model.predict(x_last)[0]

st.subheader("🔮 Previsão (próxima hora)")
st.metric("Temperatura prevista", f"{y_hat:.2f} °C")

# gráfico com ponto previsto (+1h) em hora local
fig, ax = plt.subplots()
hist = df_local.set_index("ts_local")["temperature_2m"].tail(24)
hist.plot(ax=ax)
ax.scatter([hist.index[-1] + pd.Timedelta(hours=1)], [y_hat], marker="x")
ax.set_title("Últimas 24h (local) + ponto previsto (+1h)")
st.pyplot(fig)

with st.expander("🔎 Ver dados (tabela)"):
    st.caption(f"Fuso da cidade: **{tz}**")

    # label dinâmico do slider
    if "n_hours" not in st.session_state:
        st.session_state.n_hours = 168
    st.markdown(f"Mostrar últimas **{st.session_state.n_hours}** horas")
    st.session_state.n_hours = st.slider(
        label="", min_value=24, max_value=1000, value=st.session_state.n_hours, step=24,
        label_visibility="collapsed",
    )
    n = st.session_state.n_hours

    # inclui lat/lon na tabela (arredondadas) + ordena colunas
    df_view = (
        df_local
        .assign(
            latitude=lambda d: d["latitude"].round(4),
            longitude=lambda d: d["longitude"].round(4),
        )
        [["ts_local", "latitude", "longitude", "temperature_2m"]]
        .tail(n)
    )

    st.dataframe(
        df_view,
        use_container_width=True,
        height=350,
        # (opcional) formatação de colunas:
        # column_config={
        #     "latitude": st.column_config.NumberColumn(format="%.4f"),
        #     "longitude": st.column_config.NumberColumn(format="%.4f"),
        # }
    )

    st.write("Total de linhas no banco:", len(df))

    # download do recorte mostrado (inclui lat/lon e N horas)
    csv = df_view.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Baixar CSV (recorte mostrado)",
        data=csv,
        file_name=f"weather_last_{n}_hours_{lat:.4f}_{lon:.4f}.csv",
        mime="text/csv",
    )
