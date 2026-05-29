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
            wait = wait_seconds * (2 ** (retries - 1))
            print(f"Error al leer datos (intento {retries}/{max_retries}): {e}")
            time.sleep(wait)


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
    duplicados = df_limpios.duplicated(subset=["codigohabilitacionsede"]).sum()
    df_limpios = df_limpios.drop_duplicates(subset=["codigohabilitacionsede"])
    log.append(f"Duplicados eliminados: {duplicados}")

    # Estandarización de texto (excepto campos excluidos)
    campos_excluidos = ["t_lefonosede", "telefonoprestador", "email_prestador", "email_sede"]
    for col in df_limpios.select_dtypes(include="object").columns:
        if col not in campos_excluidos and col != "fecha_corte_reps":
            df_limpios[col] = df_limpios[col].astype(str).str.strip().str.replace(r"[^A-Za-z0-9\s]", "", regex=True)
        elif col in campos_excluidos:
            df_limpios[col] = df_limpios[col].fillna(0)

    # Estandarización de fechas en df_limpios
if "fecha_corte_reps" in df_limpios.columns:
    try:
        # Extraer la parte de fecha/hora eliminando el prefijo
        df_limpios["fecha_corte_reps"] = df_limpios["fecha_corte_reps"].str.extract(
            r'([A-Za-z]{3}\s+\d{1,2}\s+\d{4}\s+\d{1,2}:\d{2}[APM]{2})'
        )

        # Convertir a datetime usando pandas
        df_limpios["fecha_corte_reps"] = pd.to_datetime(
            df_limpios["fecha_corte_reps"], format="%b %d %Y %I:%M%p", errors="coerce"
        )

        # Convertir a string en formato SQL Server
        df_limpios["fecha_corte_reps"] = df_limpios["fecha_corte_reps"].dt.strftime("%Y-%m-%d %H:%M:%S")

        log.append("Columna 'fecha_corte_reps' estandarizada correctamente.")

    except Exception as e:
        log.append(f"Error al limpiar 'fecha_corte_reps': {e}")

# 5. Función para cargar directamente en staging
def cargar_staging(df, staging_table, connection):
    """
    Reemplaza directamente la tabla staging con los datos del DataFrame.
    """
    df.to_sql(staging_table, con=connection, if_exists="replace", index=False)
    print(f"Datos cargados directamente en '{staging_table}' ({len(df)} filas).")

    # 2. Construir MERGE dinámico
    cols = df.columns.tolist()
    col_list = ", ".join(cols)
    update_set = ", ".join([f"target.{c} = source.{c}" for c in cols])

# 6. Transacciones seguras
insertados, actualizados, rechazados = 0, 0, len(rechazos)

try:
    with engine.begin() as connection:
        # Guardar datos crudos directamente en staging
        if not df_crudos.empty:
            cargar_staging(df_crudos, "staging_datos_crudos", connection)
            insertados += len(df_crudos)

        # Guardar datos limpios directamente en staging
        if not df_limpios.empty:
            cargar_staging(df_limpios, "staging_datos_limpios", connection)
            insertados += len(df_limpios)

        # Guardar rechazos
        if not rechazos.empty:
            rechazos.to_sql("rechazos", con=connection, if_exists="replace", index=False)

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
                registros_rechazados INT,
                errores VARCHAR(MAX)
            )
        """))

        connection.execute(text("""
            INSERT INTO etl_log (fecha_inicio, fecha_fin, fuente, registros_leidos, registros_insertados, registros_rechazados, errores)
            VALUES (:fi, :ff, :fuente, :leidos, :ins, :rej, :err)
        """), {
            "fi": datetime.fromtimestamp(start_time),
            "ff": datetime.now(),
            "fuente": base_url,
            "leidos": len(df_crudos),
            "ins": insertados,
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

# 9. Revisar cambios y actualizar tablas
def actualizar_si_cambios(engine, df_crudos, df_limpios, rechazos):
    try:
        with engine.begin() as connection:
            # Revisar tabla datos_crudos
            df_existente_crudos = pd.read_sql("SELECT * FROM datos_crudos", con=connection)
            if not df_existente_crudos.equals(df_crudos):
                df_crudos.to_sql("datos_crudos", con=connection, if_exists="replace", index=False)
                print("Tabla 'datos_crudos' actualizada con nuevos cambios.")
            else:
                print("No se realizaron cambios en 'datos_crudos'.")

            # Revisar tabla datos_limpios
            df_existente_limpios = pd.read_sql("SELECT * FROM datos_limpios", con=connection)
            if not df_existente_limpios.equals(df_limpios):
                df_limpios.to_sql("datos_limpios", con=connection, if_exists="replace", index=False)
                print("Tabla 'datos_limpios' actualizada con nuevos cambios.")
            else:
                print("No se realizaron cambios en 'datos_limpios'.")

            # Revisar tabla rechazos
            df_existente_rechazos = pd.read_sql("SELECT * FROM rechazos", con=connection)
            if not df_existente_rechazos.equals(rechazos):
                rechazos.to_sql("rechazos", con=connection, if_exists="replace", index=False)
                print("Tabla 'rechazos' actualizada con nuevos cambios.")
            else:
                print("No se realizaron cambios en 'rechazos'.")

    except Exception as e:
        print(f"Error al revisar/actualizar tablas: {e}")


print("\nEl log también se ha guardado en 'log_proceso.txt'.")
input("\nProceso finalizado. Presiona ENTER para cerrar la ventana...")

