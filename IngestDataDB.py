# Databricks notebook source
# MAGIC %md
# MAGIC # Job de Databricks - Generador de metricas -> Supabase
# MAGIC Este notebook GENERA metricas aleatorias de servidores y las INSERTA
# MAGIC en la tabla `server_metrics` de Supabase (la BD de la app).
# MAGIC Se programa como Job con frecuencia de 1 minuto.

# COMMAND ----------

# Se instalan dependencias en el cluster/serverless
%pip install supabase python-dotenv

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import os
import random
from datetime import datetime, timezone

from supabase import create_client

# COMMAND ----------

# ------------------------------------------------------------
# Variables de entorno.
# En Databricks NO uses .env: define estos valores como
# parametros del Job (widgets) o en variables de entorno del cluster.
# ------------------------------------------------------------
try:
    dbutils.widgets.text("SUPABASE_URL", "")
    dbutils.widgets.text("SUPABASE_SERVICE_KEY", "")
    SUPABASE_URL = dbutils.widgets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    SUPABASE_KEY = dbutils.widgets.get("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
except Exception:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
TABLE = "server_metrics"

# COMMAND ----------

SERVIDORES = ["SRV-CORE-01", "SRV-CORE-02", "SRV-DB-01", "SRV-WEB-01", "SRV-BCK-01"]
DISTRITOS = ["San Isidro", "Miraflores", "Surco", "La Molina", "San Borja"]


def clasificar_estado(cpu, ram, disco):
    # Se determina el estado segun el mayor uso
    peor = max(cpu, ram, disco)
    if peor >= 90:
        return "CRITICO"
    if peor >= 75:
        return "ADVERTENCIA"
    return "OK"


def generar_registro():
    # Se genera una lectura aleatoria de un servidor
    cpu = round(random.uniform(10, 99), 1)
    ram = round(random.uniform(20, 98), 1)
    disco = round(random.uniform(30, 97), 1)
    return {
        "user_id": None,
        "email": "databricks-job",
        "servidor": random.choice(SERVIDORES),
        "distrito": random.choice(DISTRITOS),
        "cpu_pct": cpu,
        "ram_pct": ram,
        "disco_pct": disco,
        "estado": clasificar_estado(cpu, ram, disco),
        "origen": "databricks",
        "evidencia_path": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

# COMMAND ----------

def main():
    # Se generan varios registros por corrida y se insertan en Supabase
    n = random.randint(3, 6)
    registros = [generar_registro() for _ in range(n)]
    supabase.table(TABLE).insert(registros).execute()
    print(f"Se insertaron {n} registros en Supabase ({TABLE}) "
          f"el {datetime.now(timezone.utc).isoformat()}")


main()
