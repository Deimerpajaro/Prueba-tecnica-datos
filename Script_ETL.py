import pandas as pd
from sqlalchemy import create_engine, text
import time
from datetime import datetime

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
            break
        except Exception as e:
            retries += 1
            print(f"Error al leer datos desde la API (intento {retries}/{max_retries}): {e}")
            time.sleep(wait_seconds)

    if temp_df is None:
        raise Exception(f"Falla definitiva al descargar bloque {bloque} (Offset: {offset}).")

    if temp_df.empty:
        break

    print(f"  -> Bloque {bloque}: Descargadas {len(temp_df)} filas (Offset: {offset})")
    dfs.append(temp_df)
    offset += limit
    bloque += 1

if not dfs:
    raise Exception("No se descargaron datos: la fuente está vacía o inaccesible.")
else:
    df_crudos = pd.concat(dfs, ignore_index=True)

# Validación de columnas reales
expected_columns = [
    "codigoprestador","nombreprestador","codigohabilitacionsede","nombresede","tipoid","numeroidentificacion",
    "naturalezajuridica","ese","municipio_prestador","departamentoprestadordesc","municipioprestadordesc",
    "direccionprestador","email_prestador","telefonoprestador","municipiosede","departamentodededesc",
    "municipiosededesc","direcci_nsede","email_sede","t_lefonosede","claseprestador","fecha_corte_reps"
]

missing_cols = [c for c in expected_columns if c not in df_crudos.columns]
if missing_cols:
    raise Exception(f"Formato inesperado: faltan columnas {missing_cols}")

print(f"\nDescarga completada. Total filas consolidadas: {len(df_crudos)}")

# 4. Preparar estructuras
df_limpios = df_crudos.copy()
rechazos = pd.DataFrame(columns=df_crudos.columns.tolist() + ["razon_rechazo"])
log = []

# Limpieza y estandarización
if not df_limpios.empty:
    # Nulos
    nulos_iniciales = df_limpios.isnull().sum().sum()
    df_limpios = df_limpios.dropna(how="all")
    log.append(f"Nulos iniciales: {nulos_iniciales}, filas eliminadas: {len(df_crudos) - len(df_limpios)}")

    # Duplicados
    duplicados = df_limpios.duplicated().sum()
    df_limpios = df_limpios.drop_duplicates()
    log.append(f"Duplicados eliminados: {duplicados}")

    # Estandarización de texto (excepto campos excluidos)
    campos_excluidos = ["t_lefonosede", "telefonoprestador", "email_prestador", "email_sede"]
    for col in df_limpios.select_dtypes(include="object").columns:
        if col not in campos_excluidos and col != "fecha_corte_reps":
            df_limpios[col] = df_limpios[col].astype(str).str.strip().str.replace(r"[^A-Za-z0-9\s]", "", regex=True)
        elif col in campos_excluidos:
            df_limpios[col] = df_limpios[col].fillna(0)

    # Estandarización de fechas
    if "fecha_corte_reps" in df_limpios.columns:
        df_limpios["fecha_corte_reps"] = pd.to_datetime(df_limpios["fecha_corte_reps"], errors="coerce")
        invalid_dates = df_limpios[df_limpios["fecha_corte_reps"].isnull()]
        if not invalid_dates.empty:
            invalid_dates["razon_rechazo"] = "Fecha inválida"
            rechazos = pd.concat([rechazos, invalid_dates])
            df_limpios = df_limpios.dropna(subset=["fecha_corte_reps"])
        log.append(f"Fechas inválidas rechazadas: {len(invalid_dates)}")

else:
    log.append("No se realizaron transformaciones porque no se descargaron datos.")

# 5. Carga incremental con upsert
def upsert_table(df, table_name, connection):
    # Cargar chunk en tabla temporal
    temp_table = f"#{table_name}_temp"
    df.to_sql(temp_table, con=connection, if_exists="replace", index=False)

    # Construir MERGE dinámico
    cols = df.columns.tolist()
    col_list = ", ".join(cols)
    update_set = ", ".join([f"target.{c} = source.{c}" for c in cols])

    merge_sql = f"""
        MERGE {table_name} AS target
        USING {temp_table} AS source
        ON target.codigoprestador = source.codigoprestador
        WHEN MATCHED THEN UPDATE SET {update_set}
        WHEN NOT MATCHED THEN INSERT ({col_list})
        VALUES ({", ".join([f"source.{c}" for c in cols])});
    """
    connection.execute(text(merge_sql))

# 6. Transacciones seguras
insertados, actualizados, rechazados = 0, 0, len(rechazos)

try:
    with engine.begin() as connection:
        if not df_crudos.empty:
            upsert_table(df_crudos, "datos_crudos", connection)
            insertados += len(df_crudos)
        if not df_limpios.empty:
            upsert_table(df_limpios, "datos_limpios", connection)
            insertados += len(df_limpios)
        if not rechazos.empty:
            rechazos.to_sql("rechazos", con=connection, if_exists="append", index=False)

        # Tabla de control de cargas
        connection.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='etl_log' AND xtype='U')
            CREATE TABLE etl_log (
                id INT IDENTITY(1,1) PRIMARY KEY,
                fecha_inicio DATETIME,
                fecha_fin DATETIME,
                fuente VARCHAR(255),
                registros_leidos INT,
                registros_insertados INT,
                registros_actualizados INT,
                registros_rechazados INT,
                errores VARCHAR(MAX)
            )
        """))

        connection.execute(text("""
            INSERT INTO etl_log (fecha_inicio, fecha_fin, fuente, registros_leidos, registros_insertados, registros_actualizados, registros_rechazados, errores)
            VALUES (:fi, :ff, :fuente, :leidos, :ins, :upd, :rej, :err)
        """), {
            "fi": datetime.fromtimestamp(start_time),
            "ff": datetime.now(),
            "fuente": base_url,
            "leidos": len(df_crudos),
            "ins": insertados,
            "upd": actualizados,
            "rej": rechazados,
            "err": "; ".join(log)
        })

    print("\nCarga completada con éxito (transacción confirmada).")

except Exception as e:
    print(f"Error durante la carga: {e}")
    raise

finally:
    engine.dispose()

# 7. Reporte final
end_time = time.time()
tiempo_total = round(end_time - start_time, 2)

print("\n===== REPORTE FINAL =====")
print(f"Registros leídos: {len(df_crudos)}")
print(f"Registros insertados: {insertados}")
print(f"Registros actualizados: {actualizados}")
print(f"Registros rechazados: {rechazados}")
print(f"Tiempo total del proceso: {tiempo_total} segundos")
print("\nLog de transformaciones:")
for entry in log:
    print(" -", entry)

# 8. Guardar log en archivo .txt
with open("log_proceso.txt", "w", encoding="utf-8") as f:
    f.write("===== REPORTE FINAL =====\n")
    f.write(f"Registros leídos: {len(df_crudos)}\n")
    f.write(f"Registros insertados: {insertados}\n")
    f.write(f"Registros actualizados: {actualizados}\n")
    f.write(f"Registros rechazados: {rechazados}\n")
    f.write(f"Tiempo total del proceso: {tiempo_total} segundos\n\n")
    f.write("Log de transformaciones:\n")
    for entry in log:
        f.write(" - " + entry + "\n")

print("\nEl log también se ha guardado en 'log_proceso.txt'.")
input("\nProceso finalizado. Presiona ENTER para cerrar la ventana...")