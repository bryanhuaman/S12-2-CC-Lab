# ============================================================
# app.py - App principal (Streamlit)
# Monitoreo de servidores (Help Desk)
#  - Autenticacion / registro con Supabase Auth
#  - Registro de datos estructurados + carga de evidencia (no estructurado)
#  - Area de analisis: graficos, tablas, boton de refresh y timestamp
# ============================================================

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

# ----------------------------------------------------------------
# Se cargan las variables de entorno.
# En local lee del .env; en Streamlit Cloud lee de st.secrets.
# ----------------------------------------------------------------
load_dotenv()


def get_var(name: str, default: str = "") -> str:
    # Se prioriza st.secrets (Streamlit Cloud), luego el .env local
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)


SUPABASE_URL = get_var("SUPABASE_URL")
SUPABASE_KEY = get_var("SUPABASE_KEY")          # anon key (la app)
SUPABASE_BUCKET = get_var("SUPABASE_BUCKET")

TABLE = "server_metrics"

st.set_page_config(page_title="Monitoreo de Servidores", page_icon="🖥️", layout="wide")


@st.cache_resource
def get_client():
    # Se crea un unico cliente de Supabase reutilizable
    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase = get_client()


# ----------------------------------------------------------------
# Utilidades de estado de sesion
# ----------------------------------------------------------------
def init_state():
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("last_refresh", None)
    st.session_state.setdefault("data", None)


def clasificar_estado(cpu, ram, disco):
    # Se determina el estado del servidor segun el mayor uso
    peor = max(cpu, ram, disco)
    if peor >= 90:
        return "CRITICO"
    if peor >= 75:
        return "ADVERTENCIA"
    return "OK"


# ----------------------------------------------------------------
# Pantalla de autenticacion
# ----------------------------------------------------------------
def pantalla_auth():
    st.title("🖥️ Monitoreo de Servidores")
    st.caption("Inicia sesion o crea una cuenta para continuar.")

    tab_login, tab_signup = st.tabs(["Iniciar sesion", "Registrarse"])

    with tab_login:
        email = st.text_input("Correo", key="login_email")
        pwd = st.text_input("Contraseña", type="password", key="login_pwd")
        if st.button("Entrar", type="primary"):
            try:
                res = supabase.auth.sign_in_with_password(
                    {"email": email, "password": pwd}
                )
                st.session_state["user"] = res.user
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo iniciar sesion: {e}")

    with tab_signup:
        email_s = st.text_input("Correo", key="signup_email")
        pwd_s = st.text_input("Contraseña", type="password", key="signup_pwd")
        if st.button("Crear cuenta"):
            try:
                supabase.auth.sign_up({"email": email_s, "password": pwd_s})
                st.success(
                    "Cuenta creada. Revisa tu correo si la confirmacion esta activa, "
                    "luego inicia sesion."
                )
            except Exception as e:
                st.error(f"No se pudo registrar: {e}")


# ----------------------------------------------------------------
# Carga de evidencia (dato NO estructurado) a Storage
# ----------------------------------------------------------------
# def subir_evidencia(archivo, user_id):
#     if archivo is None:
#         return None
#     ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
#     ruta = f"{user_id}/{ts}_{archivo.name}"
#     supabase.storage.from_(SUPABASE_BUCKET).upload(
#         ruta,
#         archivo.getvalue(),
#         {"content-type": archivo.type or "application/octet-stream"},
#     )
#     # Se devuelve la URL publica del archivo subido
#     return supabase.storage.from_(SUPABASE_BUCKET).get_public_url(ruta)
def subir_evidencia(archivo, user_id):
    if archivo is None:
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    ruta = f"{ts}_{archivo.name}"   # ← sin subcarpeta user_id, más simple
    try:
        supabase_service.storage.from_(SUPABASE_BUCKET).upload(
            ruta,
            archivo.getvalue(),
            {"content-type": archivo.type or "application/octet-stream"},
        )
        return supabase_service.storage.from_(SUPABASE_BUCKET).get_public_url(ruta)
    except Exception as e:
        st.error(f"Error subiendo evidencia: {e}")
        return None


# ----------------------------------------------------------------
# Formulario de registro manual de una lectura
# ----------------------------------------------------------------
def seccion_registro(user):
    st.subheader("➕ Registrar lectura manual")
    c1, c2, c3 = st.columns(3)
    with c1:
        servidor = st.text_input("Servidor", value="SRV-CORE-01")
        distrito = st.text_input("Distrito / Datacenter", value="San Isidro")
    with c2:
        cpu = st.slider("CPU (%)", 0, 100, 40)
        ram = st.slider("RAM (%)", 0, 100, 55)
    with c3:
        disco = st.slider("Disco (%)", 0, 100, 60)
        evidencia = st.file_uploader(
            "Evidencia (captura/log)", type=["png", "jpg", "jpeg", "txt", "log"]
        )

    estado = clasificar_estado(cpu, ram, disco)
    st.info(f"Estado calculado: **{estado}**")

    if st.button("Guardar lectura", type="primary"):
        try:
            url_evidencia = subir_evidencia(evidencia, user.id)
            registro = {
                "user_id": user.id,
                "email": user.email,
                "servidor": servidor,
                "distrito": distrito,
                "cpu_pct": float(cpu),
                "ram_pct": float(ram),
                "disco_pct": float(disco),
                "estado": estado,
                "origen": "app",
                "evidencia_path": url_evidencia,
            }
            supabase.table(TABLE).insert(registro).execute()
            st.success("Lectura registrada correctamente.")
        except Exception as e:
            st.error(f"Error al guardar: {e}")


# ----------------------------------------------------------------
# Lectura de datos para el area de analisis
# ----------------------------------------------------------------
def cargar_datos():
    res = (
        supabase.table(TABLE)
        .select("*")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    )
    df = pd.DataFrame(res.data)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df


# ----------------------------------------------------------------
# Area de analisis: graficos, tablas, refresh y timestamp
# ----------------------------------------------------------------
def seccion_analisis():
    st.subheader("📊 Area de analisis")

    col_btn, col_ts = st.columns([1, 3])
    with col_btn:
        if st.button("🔄 Actualizar datos", type="primary"):
            st.session_state["data"] = cargar_datos()
            st.session_state["last_refresh"] = datetime.now()

    # Se cargan datos la primera vez automaticamente
    if st.session_state["data"] is None:
        st.session_state["data"] = cargar_datos()
        st.session_state["last_refresh"] = datetime.now()

    with col_ts:
        ts = st.session_state["last_refresh"]
        ts_txt = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "—"
        st.markdown(f"🕒 **Ultima actualizacion:** `{ts_txt}`")

    df = st.session_state["data"]
    if df is None or df.empty:
        st.warning("Aun no hay datos. Registra una lectura o espera al job de Databricks.")
        return

    # ---- KPIs ----
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Lecturas totales", len(df))
    k2.metric("Servidores únicos", df["servidor"].nunique())
    k3.metric("CPU promedio", f"{df['cpu_pct'].mean():.1f}%")
    k4.metric("Críticos", int((df["estado"] == "CRITICO").sum()))

    # ---- Grafico 1: CPU / RAM / Disco en el tiempo ----
    st.markdown("**Uso de recursos en el tiempo**")
    df_t = df.sort_values("created_at")
    fig_line = px.line(
        df_t,
        x="created_at",
        y=["cpu_pct", "ram_pct", "disco_pct"],
        labels={"value": "% uso", "created_at": "Tiempo", "variable": "Recurso"},
    )
    st.plotly_chart(fig_line, use_container_width=True)

    g1, g2 = st.columns(2)
    # ---- Grafico 2: CPU promedio por servidor ----
    with g1:
        st.markdown("**CPU promedio por servidor**")
        prom = df.groupby("servidor")["cpu_pct"].mean().reset_index()
        fig_bar = px.bar(prom, x="servidor", y="cpu_pct", labels={"cpu_pct": "CPU %"})
        st.plotly_chart(fig_bar, use_container_width=True)

    # ---- Grafico 3: distribucion de estados ----
    with g2:
        st.markdown("**Distribucion por estado**")
        conteo = df["estado"].value_counts().reset_index()
        conteo.columns = ["estado", "cantidad"]
        fig_pie = px.pie(conteo, names="estado", values="cantidad", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

    # ---- Tabla: ultimas lecturas ----
    st.markdown("**Ultimas lecturas**")
    cols = ["created_at", "servidor", "distrito", "cpu_pct", "ram_pct",
            "disco_pct", "estado", "origen"]
    st.dataframe(df[cols].head(50), use_container_width=True)


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------
def main():
    init_state()

    if not st.session_state["user"]:
        pantalla_auth()
        return

    user = st.session_state["user"]
    with st.sidebar:
        st.write(f"👤 {user.email}")
        if st.button("Cerrar sesion"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            st.session_state["user"] = None
            st.rerun()

    st.title("🖥️ Monitoreo de Servidores")
    seccion_registro(user)
    st.divider()
    seccion_analisis()


if __name__ == "__main__":
    main()
