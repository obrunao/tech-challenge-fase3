import duckdb

lat, lon = -23.55, -46.63
con = duckdb.connect("data/rt_weather.duckdb")
df = con.execute(
    """
    SELECT date_trunc('day', ts) AS day, COUNT(*) AS hours
    FROM raw.weather_hourly
    WHERE round(latitude,4)=round(?,4) AND round(longitude,4)=round(?,4)
    GROUP BY 1 ORDER BY 1
    """,
    [lat, lon]
).df()
con.close()
print(df)
