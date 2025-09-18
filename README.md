# 1) vá para a pasta do projeto (ajuste se estiver noutro lugar)
cd C:\Users\Bruno\Desktop\tech-challenge-fase3-rt-weather

# 2) garanta que o remoto está correto (troque se precisar)
git remote remove origin 2>$null
git remote add origin https://github.com/obrunao/tech-challenge-fase3.git
git branch -M main

# 3) crie/sobrescreva o README.md com o conteúdo completo
$readme = @'
# Tech Challenge – Fase 3 (FIAP)
## Previsão de Temperatura em Tempo *Quase* Real (Open-Meteo + FastAPI + DuckDB + Streamlit)

Projeto completo para coletar dados horários de clima, armazenar em **DuckDB**, treinar um modelo de **Machine Learning** (Random Forest) e disponibilizar um **dashboard** (Streamlit) com previsão da **próxima hora** para a cidade selecionada.

---

## 🔗 Sumário
- [Visão geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Pré-requisitos](#pré-requisitos)
- [Setup rápido](#setup-rápido)
- [Como rodar](#como-rodar)
  - [1) Subir a API (FastAPI)](#1-subir-a-api-fastapi)
  - [2) Trazer dados (Backfill / Collect)](#2-trazer-dados-backfill--collect)
  - [3) Preparar features](#3-preparar-features)
  - [4) Treinar o modelo](#4-treinar-o-modelo)
  - [5) Rodar o app (Streamlit)](#5-rodar-o-app-streamlit)
- [Endpoints da API](#endpoints-da-api)
- [Esquema do banco (DuckDB)](#esquema-do-banco-duckdb)
- [Geração de features & modelo](#geração-de-features--modelo)
- [Dashboard / App](#dashboard--app)
- [Auditoria & utilitários (opcional)](#auditoria--utilitários-opcional)
- [Resolução de problemas](#resolução-de-problemas)
- [Critérios do Tech Challenge](#critérios-do-tech-challenge)
- [Licença](#licença)

---

## Visão geral
- **Coleta**: via **FastAPI** usando **Open-Meteo** (previsão + arquivo histórico).
- **Armazenamento**: **DuckDB** em `data/rt_weather.duckdb` (tabela `raw.weather_hourly`).
- **Processamento**: `src/processing/prepare_data.py` gera *features* (refined/Parquet).
- **Modelagem**: `src/training/train.py` treina **RandomForestRegressor** e salva:
  - `models/model_rf_temp_next_hour.pkl`
  - `models/feature_cols.json` (ordem das colunas do treino).
- **Aplicação**: `src/app/app.py` (Streamlit) para:
  - selecionar cidade/coords;
  - coletar/backfill pela API;
  - limpar **apenas** dados brutos (por cidade ou todos);
  - visualizar séries (hora local) e **prever a próxima hora**;
  - exportar CSV do recorte visto.

---

## Arquitetura
Open-Meteo (forecast/archive)
│
▼
FastAPI (/collect, /backfill) ───► DuckDB (raw.weather_hourly)
│ │
│ └──► data/refined/weather_features.parquet
│ ▲
│ │ (prepare_data.py)
│ RandomForest (train.py)
│ │
└──────────────► Streamlit (app.py) ◄────────┘
• seleção de cidade
• coleta/backfill/limpeza
• gráfico + previsão (+1h)

yaml
Copiar código

---

## Estrutura do repositório
.
├── data/
│ ├── raw/ # (não versionado)
│ ├── refined/ # features .parquet (gerado)
│ └── rt_weather.duckdb # banco DuckDB (gerado)
├── docs/ # imagens/prints
├── models/ # modelos/artefatos (gerados)
├── src/
│ ├── ingestion/
│ │ └── api.py # FastAPI (coleta/backfill)
│ ├── processing/
│ │ └── prepare_data.py # gera features a partir do DuckDB
│ ├── training/
│ │ └── train.py # treina RandomForest e salva .pkl
│ └── app/
│ └── app.py # dashboard Streamlit
├── requirements.txt
└── README.md

yaml
Copiar código
> `data/rt_weather.duckdb`, `models/*.pkl` etc. não são versionados (veja `.gitignore`).

---

## Pré-requisitos
- Python 3.10+
- Pip
- Git

---

## Setup rápido
Windows (PowerShell):
```powershell
git clone https://github.com/obrunao/tech-challenge-fase3.git
cd tech-challenge-fase3

python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt
# (se faltar) 
pip install fastapi uvicorn
Linux/macOS (bash):

bash
Copiar código
git clone https://github.com/obrunao/tech-challenge-fase3.git
cd tech-challenge-fase3

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
# (se faltar) 
pip install fastapi uvicorn
Como rodar
1) Subir a API (FastAPI)
powershell
Copiar código
python -m uvicorn src.ingestion.api:app --reload --port 8000
Teste:

powershell
Copiar código
Invoke-WebRequest http://127.0.0.1:8000/health | Select-Object -ExpandProperty Content
# -> {"status":"ok"}
2) Trazer dados (Backfill / Collect)
Em outro terminal (API ativa):

Backfill 30 dias (São Paulo)

powershell
Copiar código
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/backfill?latitude=-23.55&longitude=-46.63&days=30"
Backfill por intervalo (um dia específico)

powershell
Copiar código
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/backfill?latitude=-23.55&longitude=-46.63&start_date=2025-09-16&end_date=2025-09-16"
Coletar últimas 6h (forecast)

powershell
Copiar código
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/collect?latitude=-23.55&longitude=-46.63&past_hours=6"
A API grava em raw.weather_hourly e deduplica por (ts, latitude, longitude).
Timestamps são salvos em UTC, o app converte para hora local.

3) Preparar features
powershell
Copiar código
python src/processing/prepare_data.py
Gera data/refined/weather_features.parquet.

4) Treinar o modelo
powershell
Copiar código
python src/training/train.py
Salva:

models/model_rf_temp_next_hour.pkl

models/feature_cols.json

5) Rodar o app (Streamlit)
powershell
Copiar código
streamlit run src/app/app.py
No app você pode:

selecionar cidade ou digitar coordenadas;

Coletar (últimas 6h) e Backfill (30 dias);

ver hora local, último registro e Δ horas;

limpar dados brutos (cidade ou todos) sem tocar no modelo;

ver gráfico no fuso da cidade e a previsão da próxima hora;

abrir a tabela com lat/lon e baixar CSV do recorte.

Endpoints da API
Base: http://127.0.0.1:8000

GET /health → {"status":"ok"}

GET /collect?latitude={lat}&longitude={lon}&past_hours={1..48}
Coleta horas passadas recentes (forecast), filtra futuro, grava no DuckDB.

POST /backfill?latitude={lat}&longitude={lon}&days={1..180}
Histórico dos últimos N dias (arquivo).

POST /backfill?latitude={lat}&longitude={lon}&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
Backfill de intervalo explícito.

Resposta típica

json
Copiar código
{
  "inserted_rows": 144,
  "rows_returned": 144,
  "lat": -23.55,
  "lon": -46.63,
  "timezone": "America/Sao_Paulo",
  "first_ts_utc": "2025-09-15T00:00:00",
  "last_ts_utc":  "2025-09-16T23:00:00",
  "range_used": {"start_date":"2025-09-15","end_date":"2025-09-16"}
}
Esquema do banco (DuckDB)
Tabela raw.weather_hourly:

coluna	tipo	descrição
ts	TIMESTAMP	hora UTC (naive, sem timezone)
latitude	DOUBLE	lat normalizada (4 casas)
longitude	DOUBLE	lon normalizada (4 casas)
temperature_2m	DOUBLE	temperatura (°C)
relative_humidity_2m	DOUBLE	umidade relativa (%)
precipitation	DOUBLE	precipitação (mm)
wind_speed_10m	DOUBLE	velocidade do vento (km/h)

Geração de features & modelo
src/processing/prepare_data.py (make_features):

temp_lag_1h, temp_lag_24h;

cíclicas: hour_sin, hour_cos;

médias móveis simples (janelas curtas).

src/training/train.py:

split temporal train/test;

RandomForestRegressor (baseline x naïve last-hour);

Métricas: MAE / RMSE (console);

Salva modelo + feature_cols.json (ordem das colunas).

Dashboard / App
src/app/app.py:

seleção cidade/coords + detecção do timezone;

Coletar/Backfill (via API) e limpar dados brutos (cidade/todos);

gráfico no fuso local, previsão da próxima hora;

tabela com ts_local, latitude, longitude, temperature_2m e download CSV.

Auditoria & utilitários (opcional)
src/ingestion/audit_backfill.py: cobertura (horas esperadas x gravadas).

src/ingestion/fill_gaps.py: preenche lacunas (últimos 30 dias).

Resolução de problemas
Conexão recusada ao coletar/backfill: API não está rodando.
python -m uvicorn src.ingestion.api:app --reload --port 8000

Porta ocupada: use --port 8001 e ajuste API_BASE no app (env var).

Linhas no futuro: o app filtra; para limpar no banco, use o botão de sanitização (se habilitado) ou um DELETE por ts > now() (UTC).

Dia corrente < 24h: normal; o dia ainda não fechou.

Critérios do Tech Challenge
✔️ Problema: série temporal (regressão) – prever temperatura da próxima hora.
✔️ Coleta: APIs (Open-Meteo), histórico + quase tempo real.
✔️ Armazenamento: DuckDB (estruturado).
✔️ Análise: gráficos/tabela por cidade, hora local, Δh.
✔️ Processamento: feature engineering (lags, cíclicos…).
✔️ Modelagem: comparação com baseline, métricas e modelo salvo.
✔️ Deploy: Streamlit (app) + FastAPI (coleta).
✔️ Documentação: README com guia de execução.
