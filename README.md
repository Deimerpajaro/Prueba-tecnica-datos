# Prueba-tecnica-datos
# Pipeline Automatizado de Integración de Datos de Prestadores de Salud
Este proyecto implementa un pipeline ETL robusto diseñado para integrar datos de prestadores de salud desde una API gubernamental hacia una base de datos SQL Server local

# patron de uso correcto
1. Abrir el archivo "QueryDB.sql" y ejecutar el paso 1 y 2 descrito dentro.
2. Ejecutar el archivo "Script_ETL.py" y esperar a que cargue los datos.
3. Continuacion de la base de datos (Descrito y marcado en el punto 4 del archivo SQL. QueryDB.sql), para el paso 5 se suguire un query a la vez para evitar errores en las vistas.

# Descripción General
El script automatiza la descarga de registros desde el portal de datos abiertos de Colombia, realiza una validación de esquema, limpia los datos eliminando registros nulos y realiza una carga segura mediante una tabla de staging para asegurar la integridad de la información en el destino.

# Tecnologías Utilizadas
Lenguaje: Python.
Base de datos: SQLServer.

# Librerías Principales:
pandas: Para la manipulación y limpieza de datos.
sqlalchemy y pyodbc: Para la conexión y gestión de la base de datos SQL.
Base de Datos: SQL Server (utilizando el driver ODBC Driver 17).

# Configuración del Sistema
El script está configurado para conectarse a un entorno local con los siguientes parámetros:
Servidor: localhost
Base de Datos: Prueba
Fuente de Datos: API JSON de datos.gov.co.

# Flujo del Proceso ETL
1. Extracción (Extract)
Paginación: El script descarga los datos en bloques (limit = 1000) para manejar grandes volúmenes de información de manera eficiente.
Reintentos: Implementa lógica de reintentos para manejar posibles fallos en la conexión con la API.

2. Transformación (Transform)
Validación de Esquema: Se verifica que el DataFrame contenga las 22 columnas esperadas (ej. codigoprestador, nombreprestador, municipiosede, etc.) antes de continuar.

Limpieza de Datos:
Se eliminan filas que estén completamente vacías (dropna(how="all")).
Se genera un registro de los cambios realizados en un log de transformaciones.

3. Carga (Load)
Estrategia de Staging: Los datos se cargan primero en una tabla temporal llamada staging_datos_crudos.
Carga Segura: Se utiliza un bloque de transacción (engine.begin()) para asegurar que la carga en la tabla final datos_crudos sea exitosa o se revierta en caso de error.
Actualización Condicional: El sistema compara los datos nuevos con los existentes y solo actualiza la tabla si se detectan cambios reales, evitando procesos de escritura innecesarios.

# Monitoreo y Logs
Al finalizar el proceso, el script genera un Reporte Final tanto en la consola como en un archivo de texto llamado log_proceso.txt. 

# El reporte incluye:
Total de registros leídos de la fuente.
Cantidad de registros insertados, actualizados y rechazados.
Tiempo total de ejecución del proceso.
Detalle de las transformaciones aplicadas (ej. cantidad de nulos eliminados).

# Requisitos Previos
Tener instalado el ODBC Driver 17 for SQL Server.
Contar con acceso a internet para realizar las peticiones a la URL de la API.
La base de datos "Prueba" debe estar creada en la instancia local de SQL Server.