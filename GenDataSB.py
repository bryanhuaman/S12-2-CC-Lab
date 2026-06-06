# ============================================================
# GenDataSB.py
# Genera registros aleatorios de metricas de servidores
# y los inserta en Supabase. Sirve para probar la app en local
# sin depender de Databricks.
#   Ejecutar:  python GenDataSB.py
# ============================================================

import os
import random
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

# Se cargan variables de entorno
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
# Se usa la service_role key para insertar sin RLS
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLE = "server_metrics"

SERVIDORES = ["SRV-CORE-01", "SRV-CORE-02", "SRV-DB-01", "SRV-WEB-01", "SRV-BCK-01"]
DISTRITOS = ["San Isidro", "Miraflores", "Surco", "La Molina", "San Borja"]


def clasificar_estado(cpu, ram, disco):
    peor = max(cpu, ram, disco)
    if peor >= 90:
        return "CRITICO"
    if peor >= 75:
        return "ADVERTENCIA"
    return "OK"


def generar_registro():
    cpu = round(random.uniform(10, 99), 1)
    ram = round(random.uniform(20, 98), 1)
    disco = round(random.uniform(30, 97), 1)
    return {
        "user_id": None,
        "email": "generador-local",
        "servidor": random.choice(SERVIDORES),
        "distrito": random.choice(DISTRITOS),
        "cpu_pct": cpu,
        "ram_pct": ram,
        "disco_pct": disco,
        "estado": clasificar_estado(cpu, ram, disco),
        "origen": "local",
        "evidencia_path": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main(n=10):
    # Se generan n registros y se insertan en lote
    registros = [generar_registro() for _ in range(n)]
    supabase.table(TABLE).insert(registros).execute()
    print(f"Se insertaron {n} registros en '{TABLE}'.")


if __name__ == "__main__":
    main(10)
