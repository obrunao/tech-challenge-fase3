from pathlib import Path
import duckdb

DB = Path("data/rt_weather.duckdb")

con = duckdb.connect(DB.as_posix())

print("\n-- Tabelas --")
print(con.sql("SELECT table_schema, table_name FROM information_schema.tables ORDER BY 1,2").df())

print("\n-- Esquema raw.weather_hourly --")
print(con.sql("DESCRIBE raw.weather_hourly").df())

print("\n-- Estatísticas --")
print(con.sql("SELECT COUNT(*) AS n, MIN(ts) AS first, MAX(ts) AS last FROM raw.weather_hourly").df())

print("\n-- Amostra (últimas 10) --")
print(con.sql("SELECT * FROM raw.weather_hourly ORDER BY ts DESC LIMIT 10").df())

con.close()
