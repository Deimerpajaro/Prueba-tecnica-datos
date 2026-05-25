-- Paso 1: crea la base de datos
-- Creacion de la Base de datos
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'Prueba')
BEGIN
    CREATE DATABASE Prueba;
END
GO

-- Se selecciona la Base de datos a usar
USE Prueba;

-- Paso 2: ejecuta Script_ETL.py antes de proceder

DROP TABLE datos_crudos
DROP TABLE datos_limpios

-- Paso 3: una vez ejecutado el Script_ETL.py podemos continuar con los siguientes pasos en donde se realizara la limpieza y modificaciones necesarias para la correcta estructura de la base de datos
-- Creamos ta tabla del DataLake()
CREATE TABLE datos_crudos (
    codigoprestador VARCHAR(50),
	nombreprestador VARCHAR(100),
    codigohabilitacionsede VARCHAR(50),
    nombresede VARCHAR(255),
	tipoid VARCHAR(10),
	numeroidentificacion BIGINT,
    naturalezajuridica VARCHAR(100),
    ese VARCHAR(10),
    municipio_prestador VARCHAR(10),
    departamentoprestadordesc VARCHAR(100),
    municipioprestadordesc VARCHAR(100),
    direccionprestador VARCHAR(255),
    email_prestador VARCHAR(150),
    telefonoprestador VARCHAR(100),
    municipiosede VARCHAR(10),
    departamentodededesc VARCHAR(100),
    municipiosededesc VARCHAR(100),
    direcci_nsede VARCHAR(255),
    email_sede VARCHAR(255),
    t_lefonosede VARCHAR(100),
    claseprestador VARCHAR(100),
    fecha_corte_reps VARCHAR(100)
);

-- Creamos ta tabla del DataLake()
CREATE TABLE datos_limpios (
    codigoprestador VARCHAR(50),
	nombreprestador VARCHAR(100),
    codigohabilitacionsede VARCHAR(50),
    nombresede VARCHAR(255),
	tipoid VARCHAR(10),
	numeroidentificacion BIGINT,
    naturalezajuridica VARCHAR(100),
    ese VARCHAR(10),
    municipio_prestador VARCHAR(10),
    departamentoprestadordesc VARCHAR(100),
    municipioprestadordesc VARCHAR(100),
    direccionprestador VARCHAR(255),
    email_prestador VARCHAR(150),
    telefonoprestador VARCHAR(100),
    municipiosede VARCHAR(10),
    departamentodededesc VARCHAR(100),
    municipiosededesc VARCHAR(100),
    direcci_nsede VARCHAR(255),
    email_sede VARCHAR(255),
    t_lefonosede VARCHAR(100),
    claseprestador VARCHAR(100),
    fecha_corte_reps VARCHAR(100)
);


-- Se borra la tabla en caso de que exista para crear la tabla madre de Registro Especial de Prestadores y Sedes de Servicios de Salud (Prestadores), que sera la tabla de uso para los analistas
DROP TABLE IF EXISTS [dbo].[Prestadores]
SELECT DISTINCT [codigoprestador] AS [CodigoPrestador]
      ,[nombreprestador] AS [NombrePrestador]
      ,[tipoid] AS [TipoIdentificacion]
      ,[numeroidentificacion] AS [NumeroIdentificacion]
INTO [dbo].[Prestadores]
FROM [Prueba].[dbo].[datos_limpios];
GO

-- Se borra la tabla en caso de que exista para crear la tabla Hija de Registro Especial de Prestadores y Sedes de Servicios de Salud (SedePrestadores), que sera la tabla de uso para los analistas
DROP TABLE IF EXISTS [dbo].[SedePrestadores]
SELECT [codigoprestador] AS [CodigoPrestador]
	  ,[codigohabilitacionsede] AS [CodigoHabilitacionSede]
      ,[nombresede] AS [NombreSede]
      ,[naturalezajuridica] AS [NaturalezaJuridica]
      ,[ese] AS [ESE]
      ,[municipio_prestador] AS [MunicipioPrestador]
      ,[departamentoprestadordesc] AS [DepartamentoPrestadorDescripcion]
      ,[municipioprestadordesc] AS [MunicipioPrestadorDescripcion]
      ,[direccionprestador] AS [DireccionPrestador]
      ,[email_prestador] AS [EmailPrestador]
      ,[telefonoprestador] AS [TelefonoPrestador]
      ,[municipiosede] AS [MunicipioSede]
      ,[departamentodededesc] AS [DepartamentoSedeDescripcion]
      ,[municipiosededesc] AS [MunicipioSedeDescripcion]
      ,[direcci_nsede] AS [DireccionSede]
      ,[email_sede] AS [EmailSede]
      ,[t_lefonosede] AS [TelefonoSede]
      ,[claseprestador] AS [ClasePrestadorDescripcion]
      ,[fecha_corte_reps] AS [FechaCorte]
INTO [dbo].[SedePrestadores]
FROM [Prueba].[dbo].[datos_limpios];
GO

-- SE modifica la columna para asegurarse de que no acepte valores nulos
ALTER TABLE [dbo].[Prestadores]
ALTER COLUMN CodigoPrestador VARCHAR(50) NOT NULL; 
GO
-- Se asigna la Llave Primaria 
ALTER TABLE [dbo].[Prestadores]
ADD CONSTRAINT PK_CodigoPrestador 
PRIMARY KEY (CodigoPrestador);
GO

-- SE modifica la columna para asegurarse de que no acepte valores nulos
ALTER TABLE [dbo].[SedePrestadores]
ALTER COLUMN CodigoPrestador VARCHAR(50) NOT NULL; 
GO
-- Se asigna la Llave Foranea 
ALTER TABLE [dbo].[SedePrestadores]
ADD CONSTRAINT FK_SedePrestadores_Prestadores
FOREIGN KEY (CodigoPrestador)
REFERENCES [dbo].[Prestadores] (CodigoPrestador);
GO

--Vistas
--Creacion de la vista del Directorio de Sedes por Región
CREATE VIEW vista_directorio_geografico AS
SELECT 
    SP.DepartamentoPrestadorDescripcion,
    SP.MunicipioSede, 
    P.CodigoPrestador,
    P.NombrePrestador,
    SP.CodigoHabilitacionSede,
    SP.NombreSede,
    SP.ClasePrestadorDescripcion,
    SP.ESE
FROM dbo.Prestadores P
INNER JOIN dbo.SedePrestadores SP 
ON P.CodigoPrestador = SP.CodigoPrestador;

--Creacion de la vista de Caracterización de Prestadores e Instituciones Públicas (ESE)
CREATE VIEW vista_caracterizacion_juridica AS
SELECT 
    SP.CodigoPrestador,
    P.NombrePrestador,
    P.TipoIdentificacion,
    P.NumeroIdentificacion,
    SP.NaturalezaJuridica,
    SP.ClasePrestadorDescripcion,
    SP.ESE,
    REPLACE(REPLACE(ese, 'SI', 'Pública (ESE)'), 'NO', 'Privada/Otro') AS tipo_gestion
FROM dbo.Prestadores P
INNER JOIN dbo.SedePrestadores SP 
ON P.CodigoPrestador = SP.CodigoPrestador;


--Creacion de la vista de la Densidad de Infraestructura de Salud (Métrica de Control)
CREATE VIEW vista_cantidad_sedes AS
SELECT 
    DepartamentoPrestadorDescripcion,
    MunicipioSede,
    ClasePrestadorDescripcion,
    COUNT(DISTINCT CodigoPrestador) AS total_prestadores_unicos,
    COUNT(DISTINCT CodigoHabilitacionSede) AS total_sedes_habilitadas
FROM dbo.SedePrestadores
GROUP BY DepartamentoPrestadorDescripcion, municipiosede, ClasePrestadorDescripcion;

--