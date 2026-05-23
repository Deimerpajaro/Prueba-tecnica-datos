import pandas as pd
from sqlalchemy import create_engine
import time

# 1. Definir parámetros de conexión
server = "localhost"
database = "Prueba"
driver = "ODBC Driver 17 for SQL Server"

connection_string = f"mssql+pyodbc://@{server}/{database}?driver={driver}"
engine = create_engine(connection_string)

# 2. URL base de la API
base_url = "https://www.datos.gov.co/resource/c36g-9fc2.json"

# 3. Descargar todos los registros usando paginación con reintentos
dfs = []
limit = 1000
offset = 0
bloque = 1
max_retries = 5
wait_seconds = 10

print("Iniciando la descarga de datos desde la API...")
start_time = time.time()

while True:
    url = f"{base_url}?$limit={limit}&$offset={offset}"
    retries = 0
    temp_df = None

    while retries < max_retries:
        try:
            temp_df = pd.read_json(url)
            break  # éxito, salir del ciclo de reintentos
        except Exception as e:
            retries += 1
            print(f"Error al leer datos desde la API (intento {retries}/{max_retries}): {e}")
            time.sleep(wait_seconds)

    if temp_df is None:
        print(f"Falla definitiva al descargar bloque {bloque} (Offset: {offset}). Se detiene la descarga.")
        break

    if temp_df.empty:
        break

    print(f"  -> Bloque {bloque}: Descargadas {len(temp_df)} filas (Offset: {offset})")
    dfs.append(temp_df)
    offset += limit
    bloque += 1

if not dfs:
    print("No se descargaron datos: la fuente está vacía o inaccesible.")
    df_crudos = pd.DataFrame()  # dataframe vacío para no romper el flujo
else:
    df_crudos = pd.concat(dfs, ignore_index=True)

print(f"\nDescarga completada (con tolerancia a fallos).")
print(f"Total filas consolidadas: {len(df_crudos)}")

# 4. Preparar estructuras
df_limpios = df_crudos.copy()
rechazos = pd.DataFrame(columns=df_crudos.columns.tolist() + ["razon_rechazo"])
log = []

# Limpieza con log (solo si hay datos)
if not df_limpios.empty:
    nulos_iniciales = df_limpios.isnull().sum().sum()
    df_limpios = df_limpios.dropna(how="all")
    df_limpios = df_limpios.fillna({"columna1": "Desconocido"})
    log.append(f"Nulos iniciales: {nulos_iniciales}, filas eliminadas: {len(df_crudos) - len(df_limpios)}")

    duplicados = df_limpios.duplicated().sum()
    df_limpios = df_limpios.drop_duplicates()
    log.append(f"Duplicados eliminados: {duplicados}")

    # ... resto de tu limpieza igual ...
else:
    log.append("No se realizaron transformaciones porque no se descargaron datos.")

# 5. Transacciones seguras
try:
    with engine.begin() as connection:
        if not df_crudos.empty:
            df_crudos.to_sql("datos_crudos", con=connection, if_exists="replace", index=False)
        if not df_limpios.empty:
            df_limpios.to_sql("datos_limpios", con=connection, if_exists="replace", index=False)
        if not rechazos.empty:
            rechazos.to_sql("rechazos", con=connection, if_exists="replace", index=False)

    print("\nCarga completada con éxito (transacción confirmada).")

except Exception as e:
    print(f"Error durante la carga: {e}")

finally:
    engine.dispose()

# 6. Reporte final
end_time = time.time()
tiempo_total = round(end_time - start_time, 2)

print("\n===== REPORTE FINAL =====")
print(f"Registros insertados en datos_crudos: {len(df_crudos)}")
print(f"Registros insertados en datos_limpios: {len(df_limpios)}")
print(f"Registros rechazados: {len(rechazos)}")
print(f"Tiempo total del proceso: {tiempo_total} segundos")
print("\nLog de transformaciones:")
for entry in log:
    print(" -", entry)

# 7. Guardar log en archivo .txt
with open("log_proceso.txt", "w", encoding="utf-8") as f:
    f.write("===== REPORTE FINAL =====\n")
    f.write(f"Registros insertados en datos_crudos: {len(df_crudos)}\n")
    f.write(f"Registros insertados en datos_limpios: {len(df_limpios)}\n")
    f.write(f"Registros rechazados: {len(rechazos)}\n")
    f.write(f"Tiempo total del proceso: {tiempo_total} segundos\n\n")
    f.write("Log de transformaciones:\n")
    for entry in log:
        f.write(" - " + entry + "\n")

print("\nEl log también se ha guardado en 'log_proceso.txt'.")

# 8. Mantener ventana activa
input("\nProceso finalizado. Presiona ENTER para cerrar la ventana...")