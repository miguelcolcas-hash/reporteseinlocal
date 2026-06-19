import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
import re
import os
import glob
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Supervisión Despacho - SEIN",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .css-1jc7ptx, .e1ewe7hr3, .viewerBadge_container__1QSob,
    .styles_viewerBadge__1yB5_, .viewerBadge_link__1S137,
    .viewerBadge_text__1JaDK { display: none; }
    /* Botón aplicar filtros destacado */
    div[data-testid="stButton"] > button[kind="primary"] {
        background-color: #1a6bc1;
        color: white;
        font-weight: 700;
        width: 100%;
        border-radius: 6px;
        padding: 0.6rem;
    }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Dashboard de Supervisión - Despacho Ejecutado del SEIN")
st.caption("Supervisión del Despacho, Interconexiones y Seguridad Operativa · Datos Consolidados Locales")

# ==========================================
# HELPERS
# ==========================================
COLORES_TECNOLOGIA = {
    "EÓLICA": "#808080", "EOLICA": "#808080",
    "HIDROELÉCTRICA": "#00BFFF", "HIDROELECTRICA": "#00BFFF",
    "SOLAR": "#FFD700",
    "DIESEL/RESIDUAL": "#FF0000",
    "GAS DE LA SELVA": "#90EE90",
    "GAS CAMISEA": "#006400",
    "GAS NORTE": "#0bb613",
    "BIOMASA": "#800080"
}

ORDEN_TECNOLOGIA = [
    "BIOMASA", "SOLAR", "EÓLICA", "EOLICA",
    "HIDROELÉCTRICA", "HIDROELECTRICA",
    "GAS NORTE", "GAS DE LA SELVA", "GAS CAMISEA", "DIESEL/RESIDUAL"
]

COLORES_SECUENCIA = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
    '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
]

def obtener_abreviatura(tipo):
    t = str(tipo).upper()
    if "BIOMASA" in t:       return "BIO"
    elif "GAS" in t:         return "GAS"
    elif "DIESEL" in t or "RESIDUAL" in t: return "DIE"
    elif "HIDRO" in t:       return "HID"
    elif "SOLAR" in t:       return "SOL"
    elif "EOL" in t or "EÓL" in t: return "EOL"
    else:                    return t[:3]

def limpiar_nombre_central(nombre):
    n = str(nombre).upper().strip()
    if "CARHUAQUERO" in n and ("(CS)" in n or " CS " in n or "CS)" in n):
        return "CS CARHUAQUERO"
    return re.sub(r'\s*\([^)]*\)$', '', n).strip()

def crear_grafica_area(df_grafico, col_color, titulo, color_map=None):
    df_plot = df_grafico.copy().dropna(subset=[col_color])
    df_plot['DESPACHO_MW'] = pd.to_numeric(df_plot['DESPACHO_MW'], errors='coerce').fillna(0)
    df_sistema = df_plot.groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()
    max_d = df_sistema['DESPACHO_MW'].max()
    lim = max_d * 1.12 if pd.notna(max_d) and max_d > 0 else 1000
    f_min, f_max = df_plot['FECHA_HORA'].min(), df_plot['FECHA_HORA'].max()

    fig = px.area(
        df_plot, x="FECHA_HORA", y="DESPACHO_MW", color=col_color,
        title=titulo, color_discrete_map=color_map,
        color_discrete_sequence=px.colors.qualitative.Alphabet,
        template="plotly_white"
    )
    fig.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
    fig.add_scatter(
        x=df_sistema['FECHA_HORA'], y=df_sistema['DESPACHO_MW'],
        mode='lines', line=dict(width=0, color='rgba(0,0,0,0)'),
        name='<b>⚡ TOTAL</b>', showlegend=False
    )
    if not df_sistema.empty:
        max_r = df_sistema.loc[df_sistema['DESPACHO_MW'].idxmax()]
        min_r = df_sistema.loc[df_sistema['DESPACHO_MW'].idxmin()]
        fig.add_scatter(
            x=[max_r['FECHA_HORA']], y=[max_r['DESPACHO_MW']],
            mode='markers+text', marker=dict(color='black', size=12, symbol='triangle-up'),
            text=[f"<b>Máx: {max_r['DESPACHO_MW']:,.0f} MW</b>"],
            textposition="top center", textfont=dict(color="blue"), showlegend=False
        )
        fig.add_scatter(
            x=[min_r['FECHA_HORA']], y=[min_r['DESPACHO_MW']],
            mode='markers+text', marker=dict(color='black', size=12, symbol='triangle-down'),
            text=[f"<b>Mín: {min_r['DESPACHO_MW']:,.0f} MW</b>"],
            textposition="bottom center", textfont=dict(color="blue"), showlegend=False
        )
    fig.update_layout(
        hovermode="x unified",
        xaxis=dict(tickformat="%d/%m\n%H:%M", title="Fecha Operativa", range=[f_min, f_max]),
        yaxis=dict(title="Potencia (MW)", range=[0, lim]),
        height=550
    )
    return fig

# ==========================================
# CARGA DE DATOS (solo lectura, sin filtros aún)
# ==========================================
@st.cache_data(show_spinner=False)
def cargar_centrales_sein():
    try:
        df = pd.read_excel('CetralesSEIN.xlsx', sheet_name=0, header=None, usecols=[0, 1, 2, 3, 4, 6, 7, 8])
        df = df.iloc[1:].copy()
        df.columns = [
            'CODIGO', 'CENTRAL', 'CENTRAL_CALIFICACION', 'EMPRESA_DESPACHO',
            'AREA_OPERATIVA', 'TIPO_INTEGRANTE', 'TIPO_GENERACION', 'REQUERIMIENTO_ESPECIAL'
        ]
        for col in df.columns:
            df[col] = df[col].apply(lambda x: str(x).strip() if pd.notna(x) and str(x) != 'nan' else '')
        return df[df['CENTRAL'] != ''].copy()
    except Exception as e:
        st.error(f"Error cargando CetralesSEIN.xlsx: {e}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def cargar_parquet(base_name, mtime):
    """Lee los parquet y devuelve los DataFrames crudos sin ningún filtro."""
    def leer(sufijo):
        path = f"{base_name}_{sufijo}.parquet"
        return pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame()

    df_des   = leer("Despacho")
    df_dem   = leer("Demanda")
    df_inter = leer("Interconexiones")
    df_cal   = leer("Calificacion")
    df_cmg   = leer("CMg")

    if not df_inter.empty and 'ENLACE' not in df_inter.columns:
        df_inter['ENLACE'] = 'CENTRO-NORTE'

    return df_des, df_dem, df_inter, df_cal, df_cmg

# ==========================================
# SIDEBAR — SELECCIÓN DE BASE Y RANGO
# ==========================================
st.sidebar.header("⚙️ Configuración")

archivos_parquet = glob.glob("*_Despacho.parquet")
prefijos_bases   = [f.replace("_Despacho.parquet", "") for f in archivos_parquet]

if not prefijos_bases:
    st.sidebar.error("❌ No se detectó ninguna base de datos Parquet.")
    st.sidebar.info("Ejecuta tu script de descarga para generar los archivos .parquet")
    st.stop()

base_seleccionada = st.sidebar.selectbox("📂 Base de Datos:", prefijos_bases)

archivo_principal = f"{base_seleccionada}_Despacho.parquet"
mtime = os.path.getmtime(archivo_principal) if os.path.exists(archivo_principal) else 0

with st.sidebar:
    with st.spinner("Leyendo índice de fechas..."):
        df_des_todo, df_dem_todo, df_int_todo, df_cal_todo, df_cmg_todo = cargar_parquet(base_seleccionada, mtime)

df_matriz = cargar_centrales_sein()
if df_matriz.empty:
    st.error("❌ No se pudo cargar CetralesSEIN.xlsx.")
    st.stop()

if df_des_todo.empty:
    st.sidebar.warning("⚠️ El archivo de despacho está vacío.")
    st.stop()

fecha_min_db = df_des_todo['FECHA_HORA'].min().date()
fecha_max_db = df_des_todo['FECHA_HORA'].max().date()

st.sidebar.markdown("---")
st.sidebar.subheader("🗓️ Rango de Fechas")
rango_fechas = st.sidebar.date_input(
    "Periodo a analizar:",
    value=(fecha_min_db, fecha_max_db),
    min_value=fecha_min_db,
    max_value=fecha_max_db
)

if not (isinstance(rango_fechas, tuple) and len(rango_fechas) == 2):
    st.info("Selecciona un rango de fechas completo para continuar.")
    st.stop()

f_ini = pd.to_datetime(rango_fechas[0])
f_fin = pd.to_datetime(rango_fechas[1]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

# ==========================================
# SIDEBAR — FILTROS OPERATIVOS (cascada)
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtros Operativos")

opts_zona = sorted([x for x in df_matriz['AREA_OPERATIVA'].unique() if x])
filtro_zona = st.sidebar.multiselect("📍 Área Operativa:", options=opts_zona, placeholder="Todas")
df_f1 = df_matriz[df_matriz['AREA_OPERATIVA'].isin(filtro_zona)] if filtro_zona else df_matriz

opts_int   = sorted([x for x in df_f1['TIPO_INTEGRANTE'].unique() if x])
defecto_int = ["COES"] if "COES" in opts_int else []
filtro_int  = st.sidebar.multiselect("⚖️ Tipo Integrante:", options=opts_int, default=defecto_int, placeholder="Todos")
df_f2 = df_f1[df_f1['TIPO_INTEGRANTE'].isin(filtro_int)] if filtro_int else df_f1

opts_req   = sorted([x for x in df_f2['REQUERIMIENTO_ESPECIAL'].unique() if x])
filtro_req = st.sidebar.multiselect("⚠️ Req. Especial:", options=opts_req, placeholder="Todos")
df_f3 = df_f2[df_f2['REQUERIMIENTO_ESPECIAL'].isin(filtro_req)] if filtro_req else df_f2

opts_emp      = sorted([x for x in df_f3['EMPRESA_DESPACHO'].unique() if x])
filtro_empresa = st.sidebar.multiselect("🏢 Empresa:", options=opts_emp, placeholder="Todas")
df_f4 = df_f3[df_f3['EMPRESA_DESPACHO'].isin(filtro_empresa)] if filtro_empresa else df_f3

opts_tipo   = sorted([x for x in df_f4['TIPO_GENERACION'].unique() if x])
filtro_tipo = st.sidebar.multiselect("⚡ Tipo de Recurso:", options=opts_tipo, placeholder="Todas")
df_f5 = df_f4[df_f4['TIPO_GENERACION'].isin(filtro_tipo)] if filtro_tipo else df_f4

df_f5 = df_f5.copy()
df_f5['CENTRAL'] = df_f5['CENTRAL'].astype(str).str.strip()
opts_cen   = sorted([x for x in df_f5['CENTRAL'].unique() if x and str(x) != "nan"])
filtro_cen = st.sidebar.multiselect("🏭 Central:", options=opts_cen, placeholder="Todas")
df_f_final = df_f5[df_f5['CENTRAL'].isin(filtro_cen)] if filtro_cen else df_f5

# ==========================================
# SIDEBAR — SELECTOR DE GRÁFICA
# ==========================================
st.sidebar.markdown("---")
st.sidebar.subheader("📊 Selección de Vista")

GRAFICAS = {
    "1 · Despacho por Tecnología":          "g1",
    "2 · Despacho vs Costo Marginal (CMg)": "g2",
    "3 · Flujo de Enlaces":                 "g3",
    "4 · Generación por Central":           "g4",
    "5 · Potencia Promedio Diaria":         "g5",
    "6 · Control de Tiempos":              "g6",
    "7 · Calificación de la Operación":    "g7",
    "8 · Demanda por Áreas":               "g8",
    "9 · Trazabilidad (Data Cruda)":       "g9",
    "10 · Balance Área Norte":             "g10",
    "11 · CMg Consolidado":                "g11",
}

grafica_seleccionada = st.sidebar.radio(
    "¿Qué quieres ver?",
    options=list(GRAFICAS.keys()),
    index=0
)

st.sidebar.markdown("---")
aplicar = st.sidebar.button("▶ Aplicar Filtros y Ver Gráfica", type="primary")

# ==========================================
# GUARDAR ESTADO CON BOTÓN
# ==========================================
if aplicar:
    st.session_state['filtros_aplicados'] = True
    st.session_state['grafica_key']       = GRAFICAS[grafica_seleccionada]
    st.session_state['grafica_nombre']    = grafica_seleccionada
    # Guardamos los DataFrames recortados para no repetir el slice en cada render
    st.session_state['df_f_final']        = df_f_final.copy()
    st.session_state['f_ini']             = f_ini
    st.session_state['f_fin']             = f_fin

# Si nunca se ha aplicado, mostrar pantalla de bienvenida
if not st.session_state.get('filtros_aplicados'):
    st.markdown("""
    <div style="text-align:center; padding: 4rem 2rem; color:#555;">
        <h2>👈 Configura los filtros y selecciona una gráfica</h2>
        <p style="font-size:1.1rem;">
            Elige el rango de fechas, aplica los filtros operativos y selecciona
            qué visualización quieres cargar. Luego pulsa <b>▶ Aplicar</b>.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ==========================================
# PREPARAR DATOS SEGÚN FILTROS GUARDADOS
# ==========================================
df_f_final_ss = st.session_state['df_f_final']
f_ini_ss      = st.session_state['f_ini']
f_fin_ss      = st.session_state['f_fin']
grafica_key   = st.session_state['grafica_key']

# Diccionarios de lookup (rápidos, sin join)
df_f_final_ss['CENTRAL_NORMALIZADA'] = df_f_final_ss['CENTRAL'].apply(limpiar_nombre_central)
nombres_maestro = set(df_f_final_ss['CENTRAL_NORMALIZADA'].str.upper())
nombres_calificacion_activos = [
    str(n).strip().upper() for n in df_f_final_ss['CENTRAL_CALIFICACION'].unique()
    if pd.notna(n) and str(n).strip().upper() not in ["", "N/A", "NAN"]
]
dict_zonas    = dict(zip(df_f_final_ss['CENTRAL_NORMALIZADA'].str.upper(), df_f_final_ss['AREA_OPERATIVA']))
dict_tipos    = dict(zip(df_f_final_ss['CENTRAL_NORMALIZADA'].str.upper(), df_f_final_ss['TIPO_GENERACION']))
dict_empresas = dict(zip(df_f_final_ss['CENTRAL_NORMALIZADA'].str.upper(), df_f_final_ss['EMPRESA_DESPACHO']))

# ---- Slice temporal ----
# IMPORTANTE: las fechas se pasan como string ISO para que Streamlit las use
# correctamente como claves de cache (los pd.Timestamp con prefijo _ son ignorados).
@st.cache_data(show_spinner=False)
def recortar_y_filtrar(base_name, mtime, f_ini_str, f_fin_str, nombres_maestro_tuple):
    f_ini_ts = pd.Timestamp(f_ini_str)
    f_fin_ts = pd.Timestamp(f_fin_str)
    nombres_set = set(nombres_maestro_tuple)

    df_des, df_dem, df_inter, df_cal, df_cmg = cargar_parquet(base_name, mtime)

    # Despacho
    mask_des = (df_des['FECHA_HORA'] >= f_ini_ts) & (df_des['FECHA_HORA'] <= f_fin_ts)
    df_des_f  = df_des[mask_des].copy()
    df_des_f['CENTRAL_BASE'] = df_des_f['CENTRAL'].apply(limpiar_nombre_central)
    df_des_f  = df_des_f[df_des_f['CENTRAL_BASE'].isin(nombres_set)]

    # Demanda
    df_dem_f = df_dem[
        (df_dem['FECHA_HORA'] >= f_ini_ts) & (df_dem['FECHA_HORA'] <= f_fin_ts)
    ].copy() if not df_dem.empty else pd.DataFrame()

    # Interconexiones
    df_int_f = df_inter[
        (df_inter['FECHA_HORA'] >= f_ini_ts) & (df_inter['FECHA_HORA'] <= f_fin_ts)
    ].copy() if not df_inter.empty else pd.DataFrame()

    # Calificación
    df_cal_f = df_cal[
        (df_cal['INICIO'] >= f_ini_ts) & (df_cal['INICIO'] <= f_fin_ts)
    ].copy() if not df_cal.empty else pd.DataFrame()

    # CMg
    df_cmg_f = df_cmg[
        (df_cmg['FECHA_HORA'] >= f_ini_ts) & (df_cmg['FECHA_HORA'] <= f_fin_ts)
    ].copy() if not df_cmg.empty else pd.DataFrame()

    return df_des_f, df_dem_f, df_int_f, df_cal_f, df_cmg_f

# Fechas como string ISO — hasheables y correctamente consideradas por el cache
f_ini_str = f_ini_ss.isoformat()
f_fin_str = f_fin_ss.isoformat()
nombres_tuple = tuple(sorted(nombres_maestro))

with st.spinner("⚡ Filtrando datos..."):
    df_datos, df_dem_raw, df_inter_raw, df_seg_raw, df_cmg_raw = recortar_y_filtrar(
        base_seleccionada, mtime, f_ini_str, f_fin_str, nombres_tuple
    )

if df_datos.empty:
    st.warning("⚠️ No hay datos despachados para las centrales filtradas en las fechas seleccionadas.")
    st.stop()

# Enrichment con diccionarios
df_datos['ZONA']         = df_datos['CENTRAL_BASE'].map(dict_zonas).fillna("N/A")
df_datos['TIPO_CENTRAL'] = df_datos['CENTRAL_BASE'].map(dict_tipos).fillna("N/A")
df_datos['EMPRESA']      = df_datos['CENTRAL_BASE'].map(dict_empresas).fillna("N/A")
df_datos['FECHA_DIA']    = df_datos['FECHA_HORA'].dt.date

# Preparar df de centrales para gráficas que lo necesitan
energia_total_cen = df_datos.groupby('CENTRAL')['DESPACHO_MW'].sum()
centrales_activas = energia_total_cen[energia_total_cen > 0].index
df_plot_cen = df_datos[df_datos['CENTRAL'].isin(centrales_activas)].copy()
df_plot_cen['CENTRAL'] = pd.Categorical(
    df_plot_cen['CENTRAL'],
    categories=energia_total_cen[centrales_activas].sort_values(ascending=False).index,
    ordered=True
)
df_plot_cen = df_plot_cen.sort_values(['FECHA_HORA', 'CENTRAL'])

# Header de la vista activa
st.success(f"✅ Mostrando: **{st.session_state['grafica_nombre']}**  |  "
           f"Periodo: {rango_fechas[0].strftime('%d/%m/%Y')} → {rango_fechas[1].strftime('%d/%m/%Y')}  |  "
           f"{len(centrales_activas)} centrales activas")

# ==========================================
# GRÁFICAS — RENDERIZADO INDIVIDUAL
# ==========================================

# ---- G1: DESPACHO POR TIPO DE GENERACIÓN ----
if grafica_key == "g1":
    st.header("1. 🏭 Despacho por Tipo de Generación (SEIN)")
    df_tipo = df_datos.groupby(['FECHA_HORA', 'TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
    df_tipo['TIPO_CENTRAL'] = pd.Categorical(df_tipo['TIPO_CENTRAL'], categories=ORDEN_TECNOLOGIA, ordered=True)
    df_tipo = df_tipo.sort_values(['FECHA_HORA', 'TIPO_CENTRAL'])
    fig = crear_grafica_area(df_tipo, 'TIPO_CENTRAL', "Curva Apilada por Tecnología", color_map=COLORES_TECNOLOGIA)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Ver Datos (Matriz)"):
        df_tipo['FECHA'] = df_tipo['FECHA_HORA'].dt.strftime('%d/%m/%Y')
        df_tipo['HORA']  = df_tipo['FECHA_HORA'].dt.strftime('%H:%M')
        mat = df_tipo.pivot_table(index=['FECHA', 'HORA'], columns='TIPO_CENTRAL', values='DESPACHO_MW', aggfunc='sum').round(2).fillna(0)
        st.dataframe(mat, use_container_width=True)

# ---- G2: DESPACHO vs CMg ----
elif grafica_key == "g2":
    st.header("2. 💸 Despacho Operativo vs Costo Marginal (CMg)")
    st.info("Despacho por tecnología y flujos (Eje Izq. - MW) vs Costo Marginal Trujillo 220 (Eje Der. - S/./MWh).")

    if df_cmg_raw.empty:
        st.info("No se encontraron datos de Costos Marginales.")
    else:
        df_cmg_plot = df_cmg_raw[df_cmg_raw['BARRA'] == 'TRUJILLO 220'].sort_values('FECHA_HORA')

        df_cn_total    = pd.DataFrame()
        df_l5006_total = pd.DataFrame()
        if not df_inter_raw.empty:
            df_cn = df_inter_raw[df_inter_raw['ENLACE'] == 'CENTRO-NORTE'].copy()
            if not df_cn.empty:
                df_cn_total = df_cn.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
                df_cn_total['FLUJO_NEG'] = df_cn_total['FLUJO_MW'] * -1
            df_l5006 = df_inter_raw[df_inter_raw['LINEA_TRANSMISION'].str.contains('L-5006', case=False, na=False)]
            if not df_l5006.empty:
                df_l5006_total = df_l5006.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
                df_l5006_total['FLUJO_NEG'] = df_l5006_total['FLUJO_MW'] * -1

        fig_cmg = make_subplots(specs=[[{"secondary_y": True}]])
        df_tipo_cmg = df_datos.groupby(['FECHA_HORA', 'TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()

        for tec in ORDEN_TECNOLOGIA:
            df_tec = df_tipo_cmg[df_tipo_cmg['TIPO_CENTRAL'] == tec]
            if not df_tec.empty:
                fig_cmg.add_trace(
                    go.Scatter(
                        x=df_tec['FECHA_HORA'], y=df_tec['DESPACHO_MW'], mode='lines',
                        line=dict(width=0), fill='tonexty', stackgroup='one', name=tec,
                        marker_color=COLORES_TECNOLOGIA.get(tec, '#808080'),
                        hovertemplate=f"<b>{tec}</b>: %{{y:,.2f}} MW"
                    ), secondary_y=False
                )

        if not df_cn_total.empty:
            fig_cmg.add_trace(go.Scatter(
                x=df_cn_total['FECHA_HORA'], y=df_cn_total['FLUJO_NEG'], mode='lines',
                line=dict(width=3, dash='dash', color='#9467bd'), name='⚡ FLUJO C-N',
                hovertemplate="<b>FLUJO C-N</b>: %{y:,.2f} MW"
            ), secondary_y=False)

        if not df_l5006_total.empty:
            fig_cmg.add_trace(go.Scatter(
                x=df_l5006_total['FECHA_HORA'], y=df_l5006_total['FLUJO_NEG'], mode='lines',
                line=dict(width=3, dash='dot', color='#e377c2'), name='⚡ FLUJO L-5006',
                hovertemplate="<b>FLUJO L-5006</b>: %{y:,.2f} MW"
            ), secondary_y=False)

        if not df_cmg_plot.empty:
            fig_cmg.add_trace(go.Scatter(
                x=df_cmg_plot['FECHA_HORA'], y=df_cmg_plot['CMG_USD'], mode='lines',
                line=dict(width=3, dash='dot', color='#0099FF'), name='TRUJILLO 220',
                hovertemplate="<b>TRUJILLO 220</b>: %{y:,.2f} S/./MWh"
            ), secondary_y=True)
            f_min_c, f_max_c = df_cmg_plot['FECHA_HORA'].min(), df_cmg_plot['FECHA_HORA'].max()
            for y_ref, label, color in [(700, "Límite Sup L-5006: 700 MW", "red"), (600, "Límite Inf L-5006: 600 MW", "green")]:
                fig_cmg.add_shape(type="line", x0=f_min_c, y0=y_ref, x1=f_max_c, y1=y_ref,
                                  line=dict(color=color, width=2, dash="dash"), yref="y")
                fig_cmg.add_annotation(x=f_max_c, y=y_ref, text=f"<b>{label}</b>",
                                       showarrow=False, xanchor="right", yanchor="bottom", yref="y",
                                       font=dict(color="blue"))

        max_gen = df_tipo_cmg.groupby('FECHA_HORA')['DESPACHO_MW'].sum().max() if not df_tipo_cmg.empty else 1400
        lim_y1  = max_gen + 400
        lim_y2  = (df_cmg_plot['CMG_USD'].max() * 1.15) if not df_cmg_plot.empty else 50

        fig_cmg.update_layout(
            hovermode="x unified", height=650,
            margin=dict(t=50, b=50, l=50, r=150),
            legend=dict(title="<b>Componentes</b>", orientation="v", yanchor="top", y=1, xanchor="left", x=1.05),
            template="plotly_white"
        )
        fig_cmg.update_xaxes(title_text="Fecha Operativa", tickformat="%d/%m\n%H:%M")
        fig_cmg.update_yaxes(title_text="Potencia Activa (MW)", range=[0, lim_y1], secondary_y=False)
        fig_cmg.update_yaxes(title_text="Costo Marginal (S/./MWh)", range=[0, lim_y2], secondary_y=True, showgrid=False)
        st.plotly_chart(fig_cmg, use_container_width=True)

        with st.expander("Ver Datos CMg (Matriz)"):
            df_cmg_plot['FECHA'] = df_cmg_plot['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_cmg_plot['HORA']  = df_cmg_plot['FECHA_HORA'].dt.strftime('%H:%M')
            mat = df_cmg_plot.pivot_table(index=['FECHA', 'HORA'], columns='BARRA', values='CMG_USD', aggfunc='mean').round(2)
            st.dataframe(mat, use_container_width=True)

# ---- G3: FLUJO DE ENLACES ----
elif grafica_key == "g3":
    st.header("3. 🔌 Flujo de Enlaces")
    if df_inter_raw.empty:
        st.info("No se detectaron datos de enlaces.")
    else:
        def marcar_min_max_flujo(fig, df_total):
            if not df_total.empty:
                mx = df_total.loc[df_total['FLUJO_MW'].abs().idxmax(), 'FLUJO_MW']
                mn = df_total.loc[df_total['FLUJO_MW'].abs().idxmin(), 'FLUJO_MW']
                for val, pos in [(mx, "top left"), (mn, "bottom left")]:
                    fig.add_hline(y=val, line_dash="dash", line_color="black", line_width=2,
                                  annotation_text=f"<b>{'Máx' if val == mx else 'Mín'}: {val:,.0f} MW</b>",
                                  annotation_position=pos, annotation_font=dict(color="blue"))

        df_inter_plot = df_inter_raw.sort_values(['FECHA_HORA', 'LINEA_TRANSMISION'])
        df_cn = df_inter_plot[df_inter_plot['ENLACE'] == 'CENTRO-NORTE']
        if not df_cn.empty:
            st.subheader("Centro-Norte")
            fig_cn = px.area(df_cn, x="FECHA_HORA", y="FLUJO_MW", color="LINEA_TRANSMISION",
                             title="Flujo Centro-Norte (MW)",
                             color_discrete_sequence=COLORES_SECUENCIA, template="plotly_white")
            df_cn_tot = df_cn.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
            fig_cn.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
            fig_cn.add_scatter(x=df_cn_tot['FECHA_HORA'], y=df_cn_tot['FLUJO_MW'],
                               mode='lines', line=dict(width=3, color='gray'), name='⚡ TOTAL C-N')
            marcar_min_max_flujo(fig_cn, df_cn_tot)
            fig_cn.update_layout(hovermode="x unified", height=450)
            st.plotly_chart(fig_cn, use_container_width=True)

        df_cs = df_inter_plot[df_inter_plot['ENLACE'] == 'CENTRO-SUR']
        if not df_cs.empty:
            st.subheader("Centro-Sur")
            fig_cs = px.area(df_cs, x="FECHA_HORA", y="FLUJO_MW", color="LINEA_TRANSMISION",
                             title="Flujo Centro-Sur (MW)",
                             color_discrete_sequence=COLORES_SECUENCIA[4:], template="plotly_white")
            df_cs_tot = df_cs.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
            fig_cs.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
            fig_cs.add_scatter(x=df_cs_tot['FECHA_HORA'], y=df_cs_tot['FLUJO_MW'],
                               mode='lines', line=dict(width=3, color='gray'), name='⚡ TOTAL C-S')
            marcar_min_max_flujo(fig_cs, df_cs_tot)
            fig_cs.update_layout(hovermode="x unified", height=450)
            st.plotly_chart(fig_cs, use_container_width=True)

# ---- G4: GENERACIÓN POR CENTRAL ----
elif grafica_key == "g4":
    st.header("4. 📊 Generación del SEIN por Central")
    df_aux = df_plot_cen.copy()
    df_aux['DESPACHO_MW'] = pd.to_numeric(df_aux['DESPACHO_MW'], errors='coerce').fillna(0)
    df_aux['CENTRAL'] = df_aux.apply(
        lambda r: f"{r['CENTRAL_BASE']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})", axis=1
    )
    df_aux = df_aux.groupby(['FECHA_HORA', 'CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
    orden_e = df_aux.groupby('CENTRAL')['DESPACHO_MW'].sum().sort_values(ascending=False).index
    df_aux['CENTRAL'] = pd.Categorical(df_aux['CENTRAL'], categories=orden_e, ordered=True)
    df_aux = df_aux.sort_values(['FECHA_HORA', 'CENTRAL'])
    df_sis  = df_aux.groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()
    lim_y   = df_sis['DESPACHO_MW'].max() * 1.05 if not df_sis.empty else 1000

    fig_cen = px.area(df_aux, x="FECHA_HORA", y="DESPACHO_MW", color='CENTRAL',
                      title="Despacho por Unidad - SEIN (MW)",
                      color_discrete_sequence=COLORES_SECUENCIA, template="plotly_white")
    fig_cen.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
    fig_cen.add_scatter(x=df_sis['FECHA_HORA'], y=df_sis['DESPACHO_MW'], mode='lines',
                        line=dict(width=0, color='rgba(0,0,0,0)'), showlegend=False,
                        name='⚡ TOTAL', hovertemplate='<b>%{x|%d/%m %H:%M} → %{y:,.2f} MW</b>')
    fig_cen.update_layout(hovermode="x unified", height=550,
                          yaxis=dict(range=[0, lim_y]),
                          xaxis=dict(tickformat="%d/%m\n%H:%M"))
    st.plotly_chart(fig_cen, use_container_width=True)

    with st.expander("Ver Datos (Matriz)"):
        df_aux['FECHA'] = df_aux['FECHA_HORA'].dt.strftime('%d/%m/%Y')
        df_aux['HORA']  = df_aux['FECHA_HORA'].dt.strftime('%H:%M')
        mat = df_aux.pivot_table(index=['FECHA', 'HORA'], columns='CENTRAL', values='DESPACHO_MW', aggfunc='sum').round(2).fillna(0)
        st.dataframe(mat, use_container_width=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as w:
            mat.to_excel(w, sheet_name='Generacion_Central')
        st.download_button("📥 Descargar Excel", buf.getvalue(),
                           f"Generacion_Central_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- G5: POTENCIA PROMEDIO DIARIA ----
elif grafica_key == "g5":
    st.header("5. 📈 Potencia Promedio Diaria (SEIN)")
    modo = st.radio("Modo de barras:", ["Agrupado", "Apilado"], horizontal=True)
    barmode = 'group' if modo == "Agrupado" else 'stack'

    df_prom = df_plot_cen.copy()
    df_prom['CENTRAL'] = df_prom.apply(
        lambda r: f"{r['CENTRAL']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})" if "(" not in r['CENTRAL'] else r['CENTRAL'], axis=1
    )
    df_prom['FECHA_DIA_OP'] = (df_prom['FECHA_HORA'] - pd.Timedelta(minutes=1)).dt.date

    df_prom24 = df_prom.groupby(['FECHA_DIA_OP', 'CENTRAL'], as_index=False)['DESPACHO_MW'].mean()
    df_prom24['FECHA_DIA_OP'] = pd.to_datetime(df_prom24['FECHA_DIA_OP']).dt.strftime('%d/%m/%Y')
    orden_p = df_prom24.groupby('CENTRAL')['DESPACHO_MW'].mean().sort_values(ascending=False).index
    df_prom24['CENTRAL'] = pd.Categorical(df_prom24['CENTRAL'], categories=orden_p, ordered=True)

    fig_p24 = px.bar(df_prom24, x='FECHA_DIA_OP', y='DESPACHO_MW', color='CENTRAL',
                     title="Potencia Promedio Total 24 h (MW)", barmode=barmode,
                     color_discrete_sequence=COLORES_SECUENCIA, template="plotly_white")
    fig_p24.update_layout(xaxis=dict(type='category'), height=500)
    st.plotly_chart(fig_p24, use_container_width=True)

    df_iny = df_prom[df_prom['DESPACHO_MW'] > 0].copy()
    if not df_iny.empty:
        df_prom_iny = df_iny.groupby(['FECHA_DIA_OP', 'CENTRAL'], as_index=False)['DESPACHO_MW'].mean()
        df_prom_iny['FECHA_DIA_OP'] = pd.to_datetime(df_prom_iny['FECHA_DIA_OP']).dt.strftime('%d/%m/%Y')
        orden_i = df_prom_iny.groupby('CENTRAL')['DESPACHO_MW'].mean().sort_values(ascending=False).index
        df_prom_iny['CENTRAL'] = pd.Categorical(df_prom_iny['CENTRAL'], categories=orden_i, ordered=True)

        fig_piny = px.bar(df_prom_iny, x='FECHA_DIA_OP', y='DESPACHO_MW', color='CENTRAL',
                          title="Potencia Promedio en Operación (MW)", barmode=barmode,
                          color_discrete_sequence=COLORES_SECUENCIA, template="plotly_white")
        fig_piny.update_layout(xaxis=dict(type='category'), height=500)
        st.plotly_chart(fig_piny, use_container_width=True)

    with st.expander("Ver Datos (Matriz)"):
        mat_p = df_prom24.pivot_table(index='FECHA_DIA_OP', columns='CENTRAL', values='DESPACHO_MW').round(2).fillna(0)
        st.dataframe(mat_p, use_container_width=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as w:
            mat_p.to_excel(w, sheet_name='Promedio_24H')
        st.download_button("📥 Descargar Excel", buf.getvalue(),
                           f"Promedios_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- G6: CONTROL DE TIEMPOS ----
elif grafica_key == "g6":
    st.header("6. ⏱️ Control de Tiempos: Inactividad y Operación")
    df_gantt = df_datos.copy()
    df_gantt['CENTRAL'] = df_gantt.apply(
        lambda r: f"{r['CENTRAL_BASE']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})", axis=1
    )
    df_gantt = df_gantt.groupby(['FECHA_HORA', 'CENTRAL', 'TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
    df_gantt = df_gantt.sort_values(['CENTRAL', 'FECHA_HORA'])
    df_gantt['ESTADO']       = np.where(df_gantt['DESPACHO_MW'] > 0, 'OPERANDO', 'INACTIVO')
    df_gantt['CAMBIO_ESTADO'] = (df_gantt['ESTADO'] != df_gantt['ESTADO'].shift(1)) | (df_gantt['CENTRAL'] != df_gantt['CENTRAL'].shift(1))
    df_gantt['BLOQUE']       = df_gantt['CAMBIO_ESTADO'].cumsum()

    df_bloques = df_gantt.groupby(['CENTRAL', 'TIPO_CENTRAL', 'ESTADO', 'BLOQUE'], as_index=False).agg(
        INICIO=('FECHA_HORA', 'min'), FIN=('FECHA_HORA', 'max')
    )
    df_bloques['FIN'] += pd.Timedelta(minutes=30)
    f_start = df_datos['FECHA_HORA'].min()
    f_end   = df_datos['FECHA_HORA'].max() + pd.Timedelta(minutes=30)

    # Inactividad
    st.subheader("🚥 Cronograma de Inactividad (Base y Renovables)")
    df_inact = df_bloques[(df_bloques['ESTADO'] == 'INACTIVO') & (df_bloques['TIPO_CENTRAL'] != 'DIESEL/RESIDUAL')]
    if df_inact.empty:
        st.success("✅ Sin periodos de inactividad detectados.")
    else:
        fig_inact = px.timeline(df_inact, x_start="INICIO", x_end="FIN", y="CENTRAL",
                                color="TIPO_CENTRAL", color_discrete_map=COLORES_TECNOLOGIA,
                                hover_data={"INICIO": "|%d/%m/%Y %H:%M", "FIN": "|%d/%m/%Y %H:%M"},
                                template="plotly_white")
        fig_inact.update_yaxes(autorange="reversed")
        fig_inact.update_layout(xaxis=dict(tickformat="%d/%m\n%H:%M", range=[f_start, f_end]),
                                height=max(400, len(df_inact['CENTRAL'].unique()) * 22))
        st.plotly_chart(fig_inact, use_container_width=True)

    # Resumen horas
    df_gantt['INACTIVO_HR'] = (df_gantt['DESPACHO_MW'] == 0) * 0.5
    df_gantt['ACTIVO_HR']   = (df_gantt['DESPACHO_MW'] > 0) * 0.5
    df_res = df_gantt.groupby(['CENTRAL', 'TIPO_CENTRAL'], as_index=False)[['INACTIVO_HR', 'ACTIVO_HR']].sum()

    tipos_base = ['HIDROELÉCTRICA', 'HIDROELECTRICA', 'EÓLICA', 'EOLICA', 'SOLAR', 'BIOMASA', 'GAS DE LA SELVA', 'GAS CAMISEA', 'GAS NORTE']
    df_inact_res = df_res[df_res['TIPO_CENTRAL'].isin(tipos_base)]
    if not df_inact_res.empty:
        fig_bars_inact = px.bar(df_inact_res, x='CENTRAL', y='INACTIVO_HR', color='TIPO_CENTRAL',
                                title="Horas No Despachadas (Excluye Diésel)",
                                color_discrete_map=COLORES_TECNOLOGIA, template="plotly_white")
        fig_bars_inact.update_layout(xaxis={'categoryorder': 'total descending'}, height=450)
        st.plotly_chart(fig_bars_inact, use_container_width=True)

    # Diesel
    st.subheader("🚨 Cronograma de Operación (Diésel / Residual)")
    df_die = df_bloques[(df_bloques['ESTADO'] == 'OPERANDO') & (df_bloques['TIPO_CENTRAL'] == 'DIESEL/RESIDUAL')]
    if df_die.empty:
        st.success("✅ Sin inyección Diésel/Residual en el periodo.")
    else:
        fig_die = px.timeline(df_die, x_start="INICIO", x_end="FIN", y="CENTRAL",
                              color="TIPO_CENTRAL", color_discrete_map=COLORES_TECNOLOGIA,
                              hover_data={"INICIO": "|%d/%m/%Y %H:%M", "FIN": "|%d/%m/%Y %H:%M"},
                              template="plotly_white")
        fig_die.update_yaxes(autorange="reversed")
        fig_die.update_layout(xaxis=dict(tickformat="%d/%m\n%H:%M", range=[f_start, f_end]),
                              height=max(300, len(df_die['CENTRAL'].unique()) * 22), showlegend=False)
        st.plotly_chart(fig_die, use_container_width=True)

    df_act_res = df_res[(df_res['TIPO_CENTRAL'] == 'DIESEL/RESIDUAL') & (df_res['ACTIVO_HR'] > 0)]
    if not df_act_res.empty:
        fig_bars_act = px.bar(df_act_res, x='CENTRAL', y='ACTIVO_HR', color='TIPO_CENTRAL',
                              title="Horas de Operación (Diésel/Residual)",
                              color_discrete_map=COLORES_TECNOLOGIA, template="plotly_white")
        fig_bars_act.update_layout(xaxis={'categoryorder': 'total descending'}, height=400)
        st.plotly_chart(fig_bars_act, use_container_width=True)

# ---- G7: CALIFICACIÓN DE LA OPERACIÓN ----
elif grafica_key == "g7":
    st.header("7. 🛡️ Calificación de la Operación")
    if df_seg_raw.empty:
        st.info("No se registraron calificaciones en el periodo.")
    elif not nombres_calificacion_activos:
        st.warning("Las centrales seleccionadas no poseen mapeo de Calificación.")
    else:
        df_bar = df_seg_raw.dropna(subset=['INICIO', 'FIN']).copy()
        df_bar['CENTRAL_LIMPIA'] = df_bar['CENTRAL'].astype(str).str.strip().str.upper()
        df_bar = df_bar[df_bar['CENTRAL_LIMPIA'].isin(set(nombres_calificacion_activos))]
        if df_bar.empty:
            st.warning("Las centrales filtradas no registraron operaciones calificadas.")
        else:
            df_bar['CENTRAL_GRUPO']  = df_bar['CENTRAL'].astype(str) + " - " + df_bar['GRUPO'].astype(str)
            df_bar['HORAS_OPERACION'] = (df_bar['FIN'] - df_bar['INICIO']).dt.total_seconds() / 3600
            df_bar['HORAS_OPERACION'] = df_bar['HORAS_OPERACION'].clip(lower=0)
            df_agr = df_bar.groupby(['CENTRAL_GRUPO', 'TIPO_OPERACION'], as_index=False)['HORAS_OPERACION'].sum()

            colores_op = {
                "POR SEGURIDAD": "#8B0000", "POR POTENCIA O ENERGIA": "#00BFFF",
                "A MINIMA CARGA": "#32CD32", "POR COGENERACION": "#FF8C00",
                "POR RSF": "#FFD700", "POR PRUEBAS": "#808080"
            }
            fig_cal = px.bar(df_agr, x="HORAS_OPERACION", y="CENTRAL_GRUPO", color="TIPO_OPERACION",
                             orientation='h', title="Horas de Operación por Unidad y Tipo",
                             color_discrete_map=colores_op, template="plotly_white")
            fig_cal.update_layout(yaxis=dict(categoryorder="total ascending"),
                                  height=max(400, len(df_agr['CENTRAL_GRUPO'].unique()) * 40))
            st.plotly_chart(fig_cal, use_container_width=True)

            with st.expander("Ver Registros de Operación POR SEGURIDAD"):
                df_seg_show = df_bar[df_bar['TIPO_OPERACION'] == 'POR SEGURIDAD'].drop(columns=['CENTRAL_LIMPIA'], errors='ignore')
                if not df_seg_show.empty:
                    st.dataframe(df_seg_show, use_container_width=True)
                else:
                    st.info("No hay registros POR SEGURIDAD en este periodo.")

# ---- G8: DEMANDA POR ÁREAS ----
elif grafica_key == "g8":
    st.header("8. 🌍 Evolución y Comportamiento de la Demanda por Áreas")
    if df_dem_raw.empty:
        st.info("No se encontraron datos de demanda.")
    else:
        df_sub  = df_dem_raw[df_dem_raw['ÁREA'] != 'SEIN']
        df_sein = df_dem_raw[df_dem_raw['ÁREA'] == 'SEIN']
        colores_area = {"NORTE": "#FF9900", "CENTRO": "#3366CC", "SUR": "#DC3912"}

        fig_dem = px.line(df_sub, x="FECHA_HORA", y="DEMANDA_MW", color="ÁREA",
                          title="Evolución de la Demanda por Áreas (MW)",
                          color_discrete_map=colores_area, template="plotly_white")
        fig_dem.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=2, dash='dot'))

        def añadir_extremos(fig, df_f, color, nombre):
            if df_f.empty: return
            im, ix = df_f['DEMANDA_MW'].idxmax(), df_f['DEMANDA_MW'].idxmin()
            for idx, sym, pos in [(im, 'triangle-up', 'top center'), (ix, 'triangle-down', 'bottom center')]:
                r = df_f.loc[idx]
                fig.add_scatter(x=[r['FECHA_HORA']], y=[r['DEMANDA_MW']], mode='markers+text',
                                marker=dict(color=color, size=12, symbol=sym),
                                text=[f"<b>{'Máx' if sym == 'triangle-up' else 'Mín'}: {r['DEMANDA_MW']:,.0f} MW</b>"],
                                textposition=pos, showlegend=False, hoverinfo='skip', textfont=dict(color="blue"))

        for area in df_sub['ÁREA'].unique():
            añadir_extremos(fig_dem, df_sub[df_sub['ÁREA'] == area], colores_area.get(area, 'blue'), area)
        if not df_sein.empty:
            fig_dem.add_scatter(x=df_sein['FECHA_HORA'], y=df_sein['DEMANDA_MW'], mode='lines',
                                line=dict(width=3, color='black', dash='dash'), name='⚡ SEIN TOTAL',
                                hovertemplate='%{x|%d/%m %H:%M} → %{y:,.2f} MW')
            añadir_extremos(fig_dem, df_sein, 'black', 'SEIN')

        fig_dem.update_layout(hovermode="x unified", height=550,
                              xaxis=dict(tickformat="%d/%m\n%H:%M"))
        st.plotly_chart(fig_dem, use_container_width=True)

# ---- G9: TRAZABILIDAD ----
elif grafica_key == "g9":
    st.header("9. 🗄️ Trazabilidad de Potencia (Data Cruda)")
    with st.expander("Ver Matriz de Despacho", expanded=True):
        df_piv = df_plot_cen.copy()
        df_piv['FECHA'] = df_piv['FECHA_HORA'].dt.strftime('%d/%m/%Y')
        df_piv['HORA']  = df_piv['FECHA_HORA'].dt.strftime('%H:%M')
        mat = df_piv.pivot_table(
            index=['FECHA', 'HORA'],
            columns=['ZONA', 'TIPO_CENTRAL', 'EMPRESA', 'CENTRAL'],
            values='DESPACHO_MW', aggfunc='sum'
        ).round(2).fillna(0)
        st.dataframe(mat, use_container_width=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as w:
            mat.to_excel(w, sheet_name='Despacho_SEIN')
        st.download_button("📥 Descargar Excel", buf.getvalue(),
                           f"matriz_sein_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- G10: BALANCE ÁREA NORTE ----
elif grafica_key == "g10":
    st.header("10. 📉 Balance de Potencia - Área Norte")
    st.info("Demanda del Norte (Generación + Flujo), Generación local Norte y Flujo Centro-Norte.")
    if df_dem_raw.empty or df_inter_raw.empty:
        st.info("Se requieren datos de Demanda e Interconexiones para este análisis.")
    else:
        df_dem_n = df_dem_raw[df_dem_raw['ÁREA'] == 'NORTE'].groupby('FECHA_HORA', as_index=False)['DEMANDA_MW'].sum()
        df_cn    = df_inter_raw[df_inter_raw['ENLACE'] == 'CENTRO-NORTE']
        df_cn_t  = df_cn.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
        df_cn_t['FLUJO_NEG'] = df_cn_t['FLUJO_MW'] * -1
        df_gen_n = df_datos[df_datos['ZONA'] == 'NORTE'].groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()

        df_bal = df_dem_n.merge(df_cn_t[['FECHA_HORA', 'FLUJO_NEG']], on='FECHA_HORA', how='inner')
        df_bal = df_bal.merge(df_gen_n, on='FECHA_HORA', how='inner')
        df_bal.columns = ['FECHA_HORA', 'DEMANDA', 'FLUJO_NEG', 'GENERACION']
        df_bal['DEMANDA'] = df_bal['GENERACION'].abs() + df_bal['FLUJO_NEG'].abs()

        fig_bal = go.Figure()
        for col, color, name in [
            ('DEMANDA', '#FF9900', '📉 DEMANDA NORTE'),
            ('GENERACION', '#1f77b4', '🏭 GENERACIÓN NORTE'),
            ('FLUJO_NEG', '#9467bd', '🔌 -1 × FLUJO C-N')
        ]:
            fig_bal.add_trace(go.Scatter(
                x=df_bal['FECHA_HORA'], y=df_bal[col], mode='lines',
                line=dict(width=3, color=color), name=f'<b>{name}</b>',
                hovertemplate=f"<b>{name}</b>: %{{y:,.2f}} MW"
            ))

        max_y = max(df_bal[c].max() for c in ['DEMANDA', 'GENERACION', 'FLUJO_NEG']) + 400
        min_y = min(df_bal[c].min() for c in ['DEMANDA', 'GENERACION', 'FLUJO_NEG'])
        min_y = min_y * 1.15 if min_y < 0 else 0

        fig_bal.update_layout(hovermode="x unified", height=600,
                              xaxis=dict(tickformat="%d/%m\n%H:%M"),
                              yaxis=dict(title="Potencia (MW)", range=[min_y, max_y]),
                              template="plotly_white", margin=dict(t=50, b=50, l=50, r=150),
                              legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02))
        st.plotly_chart(fig_bal, use_container_width=True)

        with st.expander("Ver Datos (Matriz)"):
            df_bal['FECHA'] = df_bal['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_bal['HORA']  = df_bal['FECHA_HORA'].dt.strftime('%H:%M')
            mat = df_bal.pivot_table(index=['FECHA', 'HORA'], values=['DEMANDA', 'GENERACION', 'FLUJO_NEG'], aggfunc='mean').round(2)
            st.dataframe(mat[['DEMANDA', 'GENERACION', 'FLUJO_NEG']], use_container_width=True)

# ---- G11: CMg CONSOLIDADO ----
elif grafica_key == "g11":
    st.header("11. 📈 Evolución Consolidada de Costos Marginales")
    st.info("Comparativa del CMg en las principales barras de referencia Norte, Centro y Sur del SEIN.")
    if df_cmg_raw.empty:
        st.info("No se encontraron datos de Costos Marginales.")
    else:
        df_cmg_11 = df_cmg_raw.sort_values(['FECHA_HORA', 'BARRA'])
        colores_b11 = {'SANTA ROSA 220': '#d62728', 'MONTALVO 220': '#2ca02c', 'TRUJILLO 220': '#ff7f0e'}

        fig_11 = px.line(df_cmg_11, x="FECHA_HORA", y="CMG_USD", color="BARRA",
                         title="Costo Marginal por Barra (USD/MWh)",
                         color_discrete_map=colores_b11, template="plotly_white")
        fig_11.update_traces(hovertemplate="<b>%{data.name}</b>: %{y:,.2f} USD/MWh", line=dict(width=3, dash='dot'))

        for barra in df_cmg_11['BARRA'].unique():
            df_b = df_cmg_11[df_cmg_11['BARRA'] == barra]
            color = colores_b11.get(barra, 'black')
            if df_b.empty: continue
            for fn, sym, pos in [(df_b['CMG_USD'].idxmax, 'triangle-up', 'top center'),
                                 (df_b['CMG_USD'].idxmin, 'triangle-down', 'bottom center')]:
                idx = fn()
                r   = df_b.loc[idx]
                fig_11.add_scatter(
                    x=[r['FECHA_HORA']], y=[r['CMG_USD']], mode='markers+text',
                    marker=dict(color=color, size=12, symbol=sym),
                    text=[f"<b>{'Máx' if 'up' in sym else 'Mín'}: {r['CMG_USD']:,.1f}</b>"],
                    textposition=pos, textfont=dict(color='blue'), showlegend=False, hoverinfo='skip'
                )

        lim_sup = df_cmg_11['CMG_USD'].max() * 1.15 if df_cmg_11['CMG_USD'].max() > 0 else 50
        fig_11.update_layout(hovermode="x unified", height=600,
                             xaxis=dict(tickformat="%d/%m\n%H:%M"),
                             yaxis=dict(title="CMg (USD/MWh)", range=[0, lim_sup]),
                             margin=dict(t=50, b=50, l=50, r=150),
                             legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02))
        st.plotly_chart(fig_11, use_container_width=True)

        with st.expander("Ver Datos (Matriz)"):
            df_cmg_11['FECHA'] = df_cmg_11['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_cmg_11['HORA']  = df_cmg_11['FECHA_HORA'].dt.strftime('%H:%M')
            mat = df_cmg_11.pivot_table(index=['FECHA', 'HORA'], columns='BARRA', values='CMG_USD', aggfunc='mean').round(2)
            st.dataframe(mat, use_container_width=True)