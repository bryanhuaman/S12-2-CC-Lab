import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.express as px
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

# Cargar variables de entorno
load_dotenv()
SUPABASE_URL    = os.getenv('SUPABASE_URL')
SUPABASE_KEY    = os.getenv('SUPABASE_KEY')
SUPABASE_BUCKET = os.getenv('SUPABASE_BUCKET', 'EVIDENCIA')

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error('Define SUPABASE_URL y SUPABASE_KEY en tu .env antes de ejecutar la app')
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title='Monitoreo de Servidores', page_icon='🖥️', layout='wide')

TABLE = 'server_metrics'

# ----------------------------------------------------------------
# Funciones auxiliares
# ----------------------------------------------------------------
def clasificar_estado(cpu, ram, disco):
    peor = max(cpu, ram, disco)
    if peor >= 90:
        return 'CRITICO'
    elif peor >= 75:
        return 'ADVERTENCIA'
    else:
        return 'OK'

def subir_evidencia(archivo, user_id):
    if archivo is None:
        return None
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    filename = f"{user_id}_{ts}_{archivo.name}"
    try:
        file_bytes = archivo.getvalue()
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            filename, file_bytes,
            {'content-type': archivo.type or 'application/octet-stream'}
        )
        return supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
    except Exception as e:
        st.error(f'Error subiendo evidencia al storage: {e}')
        return None

# ----------------------------------------------------------------
# Menu principal
# ----------------------------------------------------------------
st.title('🖥️ Monitoreo de Servidores')

menu = st.sidebar.selectbox('Menu', ['Entrar / Registrar', 'Registro', 'Analisis'])

# ----------------------------------------------------------------
# Autenticacion
# ----------------------------------------------------------------
if menu == 'Entrar / Registrar':
    st.header('Autenticacion')
    action = st.radio('Accion', ['Entrar', 'Registrar'])
    email    = st.text_input('Email')
    password = st.text_input('Contrasena', type='password')

    if action == 'Registrar':
        if st.button('Crear cuenta'):
            if not email or not password:
                st.warning('Ingresa email y contrasena')
            else:
                try:
                    supabase.auth.sign_up({'email': email, 'password': password})
                    st.success('Cuenta creada. Revisa tu correo para confirmar (si esta habilitado).')
                except Exception as e:
                    st.error(f'Error al registrar: {e}')
    else:
        if st.button('Entrar'):
            if not email or not password:
                st.warning('Ingresa email y contrasena')
            else:
                try:
                    res = supabase.auth.sign_in_with_password({'email': email, 'password': password})
                    st.session_state['user'] = res.user
                    st.success('Autenticado correctamente')
                except Exception as e:
                    st.error(f'Error al autenticar: {e}')

    if st.button('Cerrar sesion'):
        try:
            supabase.auth.sign_out()
        except:
            pass
        st.session_state.pop('user', None)
        st.success('Sesion cerrada')

# ----------------------------------------------------------------
# Registro manual de lectura
# ----------------------------------------------------------------
if menu == 'Registro':
    user = st.session_state.get('user')
    if not user:
        st.info('Por favor entra a tu cuenta en el menu "Entrar / Registrar"')
    else:
        st.write('Conectado como:', user.email)
        with st.form('form_registro'):
            st.subheader('Registrar lectura de servidor')
            c1, c2, c3 = st.columns(3)
            with c1:
                servidor = st.text_input('Servidor', value='SRV-CORE-01')
                distrito = st.text_input('Distrito / Datacenter', value='San Isidro')
            with c2:
                cpu   = st.slider('CPU (%)',   0, 100, 40)
                ram   = st.slider('RAM (%)',   0, 100, 55)
            with c3:
                disco     = st.slider('Disco (%)', 0, 100, 60)
                evidencia = st.file_uploader(
                    'Evidencia (captura/log)',
                    type=['png', 'jpg', 'jpeg', 'txt', 'log']
                )
            submitted = st.form_submit_button('Guardar lectura')

        if submitted:
            estado = clasificar_estado(cpu, ram, disco)
            st.info(f'Estado calculado: **{estado}**')
            try:
                url_evidencia = subir_evidencia(evidencia, user.id)
                record = {
                    'user_id':        str(user.id),
                    'email':          user.email,
                    'servidor':       servidor,
                    'distrito':       distrito,
                    'cpu_pct':        float(cpu),
                    'ram_pct':        float(ram),
                    'disco_pct':      float(disco),
                    'estado':         estado,
                    'origen':         'app',
                    'evidencia_path': url_evidencia,
                    'created_at':     datetime.now(timezone.utc).isoformat()
                }
                supabase.table(TABLE).insert(record).execute()
                st.success('Lectura guardada en Supabase')
            except Exception as e:
                st.error(f'Error al guardar: {e}')

        st.markdown('---')
        st.subheader('Tus ultimas lecturas')
        try:
            resp = supabase.table(TABLE).select('*').eq('email', user.email) \
                .order('created_at', desc=True).limit(5).execute()
            rows = resp.data
            if rows:
                for r in rows:
                    st.write(
                        f"{r.get('created_at')} | {r.get('servidor')} | "
                        f"CPU: {r.get('cpu_pct')}% RAM: {r.get('ram_pct')}% "
                        f"Disco: {r.get('disco_pct')}% | Estado: {r.get('estado')}"
                    )
            else:
                st.info('No hay registros todavia')
        except Exception as e:
            st.error(f'No se pudieron recuperar registros: {e}')

# ----------------------------------------------------------------
# Area de analisis
# ----------------------------------------------------------------
if menu == 'Analisis':
    st.header('📊 Area de Analisis')

    col_btn, col_ts = st.columns([1, 3])
    with col_btn:
        if st.button('🔄 Actualizar datos', type='primary'):
            st.session_state['data']         = None
            st.session_state['last_refresh'] = None

    # Cargar datos
    if st.session_state.get('data') is None:
        try:
            res = supabase.table(TABLE).select('*') \
                .order('created_at', desc=True).limit(500).execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                df['created_at'] = pd.to_datetime(df['created_at'], utc=True)
            st.session_state['data']         = df
            st.session_state['last_refresh'] = datetime.now()
        except Exception as e:
            st.error(f'Error cargando datos: {e}')
            st.stop()

    with col_ts:
        ts = st.session_state.get('last_refresh')
        ts_txt = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else '—'
        st.markdown(f'🕒 **Ultima actualizacion:** `{ts_txt}`')

    df = st.session_state.get('data')
    if df is None or df.empty:
        st.warning('Aun no hay datos. Registra una lectura o espera al job de Databricks.')
        st.stop()

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric('Lecturas totales',  len(df))
    k2.metric('Servidores unicos', df['servidor'].nunique())
    k3.metric('CPU promedio',      f"{df['cpu_pct'].mean():.1f}%")
    k4.metric('Criticos',          int((df['estado'] == 'CRITICO').sum()))

    # Grafico 1: linea de recursos en el tiempo
    st.markdown('**Uso de recursos en el tiempo**')
    df_t = df.sort_values('created_at')
    fig_line = px.line(
        df_t, x='created_at', y=['cpu_pct', 'ram_pct', 'disco_pct'],
        labels={'value': '% uso', 'created_at': 'Tiempo', 'variable': 'Recurso'}
    )
    st.plotly_chart(fig_line, use_container_width=True)

    g1, g2 = st.columns(2)
    # Grafico 2: CPU promedio por servidor
    with g1:
        st.markdown('**CPU promedio por servidor**')
        prom = df.groupby('servidor')['cpu_pct'].mean().reset_index()
        fig_bar = px.bar(prom, x='servidor', y='cpu_pct', labels={'cpu_pct': 'CPU %'})
        st.plotly_chart(fig_bar, use_container_width=True)

    # Grafico 3: distribucion de estados
    with g2:
        st.markdown('**Distribucion por estado**')
        conteo = df['estado'].value_counts().reset_index()
        conteo.columns = ['estado', 'cantidad']
        fig_pie = px.pie(conteo, names='estado', values='cantidad', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Tabla de ultimas lecturas
    st.markdown('**Ultimas lecturas**')
    cols = ['created_at', 'servidor', 'distrito', 'cpu_pct',
            'ram_pct', 'disco_pct', 'estado', 'origen']
    st.dataframe(df[cols].head(50), use_container_width=True)
