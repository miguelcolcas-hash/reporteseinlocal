import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import calendar
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
header    {visibility: hidden;}
footer    {visibility: hidden;}
.css-1jc7ptx, .e1ewe7hr3, .viewerBadge_container__1QSob,
.styles_viewerBadge__1yB5_, .viewerBadge_link__1S137,
.viewerBadge_text__1JaDK { display: none; }


/* ── BANNER de vista activa ── */
.view-banner {
    background: #f0f5ff;
    border-left: 4px solid #1a6bc1;
    border-radius: 6px;
    padding: 10px 16px;
    margin-bottom: 16px;
    font-size: 0.85rem;
    color: #1e3a6e;
    font-weight: 600;
}

/* ── SIDEBAR header ── */
section[data-testid="stSidebar"] {
    background: #f8faff;
    border-right: 1px solid #dde4f0;
}

/* Botón Aplicar */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #1a6bc1 0%, #0f4a96 100%);
    color: white;
    font-weight: 700;
    width: 100%;
    border: none;
    border-radius: 8px;
    padding: 0.65rem;
    font-size: 0.92rem;
    box-shadow: 0 3px 10px rgba(26,107,193,0.35);
    transition: opacity 0.2s;
}
div[data-testid="stButton"] > button[kind="primary"]:hover { opacity: 0.88; }

/* Separadores sidebar */
.sidebar-section {
    background: #eef2fb;
    border-radius: 6px;
    padding: 4px 10px;
    margin: 10px 0 6px;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #1a6bc1;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────
# HELPERS GLOBALES
# ──────────────────────────────────────────
MESES_ES = {
    1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
    7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"
}
MESES_CORTO = {
    1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
    7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"
}

COLORES_TECNOLOGIA = {
    "EÓLICA":"#808080","EOLICA":"#808080",
    "HIDROELÉCTRICA":"#00BFFF","HIDROELECTRICA":"#00BFFF",
    "SOLAR":"#FFD700","DIESEL/RESIDUAL":"#FF0000",
    "GAS DE LA SELVA":"#90EE90","GAS CAMISEA":"#006400",
    "GAS NORTE":"#0bb613","BIOMASA":"#800080"
}
ORDEN_TECNOLOGIA = [
    "BIOMASA","SOLAR","EÓLICA","EOLICA",
    "HIDROELÉCTRICA","HIDROELECTRICA",
    "GAS NORTE","GAS DE LA SELVA","GAS CAMISEA","DIESEL/RESIDUAL"
]
COLORES_SECUENCIA = [
    '#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd',
    '#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf'
]

def obtener_abreviatura(tipo):
    t = str(tipo).upper()
    if "BIOMASA" in t:                       return "BIO"
    elif "GAS" in t:                         return "GAS"
    elif "DIESEL" in t or "RESIDUAL" in t:   return "DIE"
    elif "HIDRO" in t:                       return "HID"
    elif "SOLAR" in t:                       return "SOL"
    elif "EOL" in t or "EÓL" in t:          return "EOL"
    else:                                    return t[:3]

def limpiar_nombre_central(nombre):
    n = str(nombre).upper().strip()
    if "CARHUAQUERO" in n and ("(CS)" in n or " CS " in n or "CS)" in n):
        return "CS CARHUAQUERO"
    return re.sub(r'\s*\([^)]*\)$', '', n).strip()

def tickformat_inteligente(f_ini, f_fin):
    """Devuelve el tickformat y dtick adecuado según el rango."""
    dias = (f_fin - f_ini).days
    if dias <= 3:
        return "%d/%m\n%H:%M", None
    elif dias <= 60:
        return "%d/%m/%Y", None
    elif dias <= 400:
        return "%b %Y", None          # Ene 2024
    else:
        return "%b\n%Y", "M2"         # cada 2 meses

def agregar_lineas_anio(fig, f_ini, f_fin, secondary_y=False):
    """Añade líneas verticales donde cambia el año y una etiqueta."""
    anio_ini = f_ini.year
    anio_fin = f_fin.year
    for anio in range(anio_ini + 1, anio_fin + 1):
        corte = pd.Timestamp(f"{anio}-01-01")
        if f_ini < corte < f_fin:
            fig.add_vline(
                x=corte.timestamp() * 1000,
                line=dict(color="#1a6bc1", width=1.5, dash="dot"),
                annotation_text=f"<b>{anio}</b>",
                annotation_position="top left",
                annotation_font=dict(color="#1a6bc1", size=11)
            )

def crear_grafica_area(df_grafico, col_color, titulo, color_map=None, f_ini=None, f_fin=None):
    df_plot = df_grafico.copy().dropna(subset=[col_color])
    df_plot['DESPACHO_MW'] = pd.to_numeric(df_plot['DESPACHO_MW'], errors='coerce').fillna(0)
    df_sistema = df_plot.groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()
    max_d = df_sistema['DESPACHO_MW'].max()
    lim   = max_d * 1.12 if pd.notna(max_d) and max_d > 0 else 1000
    fm, fx = df_plot['FECHA_HORA'].min(), df_plot['FECHA_HORA'].max()
    tfmt, dtick = tickformat_inteligente(fm, fx)

    fig = px.area(
        df_plot, x="FECHA_HORA", y="DESPACHO_MW", color=col_color,
        title=titulo, color_discrete_map=color_map,
        color_discrete_sequence=px.colors.qualitative.Alphabet,
        template="plotly_white"
    )
    fig.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
    fig.add_scatter(x=df_sistema['FECHA_HORA'], y=df_sistema['DESPACHO_MW'],
                    mode='lines', line=dict(width=0, color='rgba(0,0,0,0)'),
                    name='<b>⚡ TOTAL</b>', showlegend=False)
    if not df_sistema.empty:
        max_r = df_sistema.loc[df_sistema['DESPACHO_MW'].idxmax()]
        min_r = df_sistema.loc[df_sistema['DESPACHO_MW'].idxmin()]
        for r, sym, pos in [(max_r,'triangle-up','top center'),(min_r,'triangle-down','bottom center')]:
            fig.add_scatter(x=[r['FECHA_HORA']], y=[r['DESPACHO_MW']], mode='markers+text',
                            marker=dict(color='black', size=12, symbol=sym),
                            text=[f"<b>{'Máx' if 'up' in sym else 'Mín'}: {r['DESPACHO_MW']:,.0f} MW</b>"],
                            textposition=pos, textfont=dict(color='blue'), showlegend=False)

    xaxis_cfg = dict(tickformat=tfmt, title="Fecha Operativa", range=[fm, fx])
    if dtick: xaxis_cfg['dtick'] = dtick
    fig.update_layout(hovermode="x unified", xaxis=xaxis_cfg,
                      yaxis=dict(title="Potencia (MW)", range=[0, lim]), height=550)
    if f_ini and f_fin:
        agregar_lineas_anio(fig, f_ini, f_fin)
    return fig



# ──────────────────────────────────────────
# CARGA DE DATOS
# ──────────────────────────────────────────
@st.cache_data(show_spinner=False)
def cargar_centrales_sein():
    try:
        df = pd.read_excel('CetralesSEIN.xlsx', sheet_name=0, header=None, usecols=[0,1,2,3,4,6,7,8])
        df = df.iloc[1:].copy()
        df.columns = ['CODIGO','CENTRAL','CENTRAL_CALIFICACION','EMPRESA_DESPACHO',
                      'AREA_OPERATIVA','TIPO_INTEGRANTE','TIPO_GENERACION','REQUERIMIENTO_ESPECIAL']
        for col in df.columns:
            df[col] = df[col].apply(lambda x: str(x).strip() if pd.notna(x) and str(x) != 'nan' else '')
        return df[df['CENTRAL'] != ''].copy()
    except Exception as e:
        st.error(f"Error cargando CetralesSEIN.xlsx: {e}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def cargar_parquet(base_name, mtime):
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

@st.cache_data(show_spinner=False)
def recortar_y_filtrar(base_name, mtime, f_ini_str, f_fin_str, nombres_maestro_tuple):
    f_ini_ts = pd.Timestamp(f_ini_str)
    f_fin_ts = pd.Timestamp(f_fin_str)
    nombres_set = set(nombres_maestro_tuple)
    df_des, df_dem, df_inter, df_cal, df_cmg = cargar_parquet(base_name, mtime)

    mask_des = (df_des['FECHA_HORA'] >= f_ini_ts) & (df_des['FECHA_HORA'] <= f_fin_ts)
    df_des_f = df_des[mask_des].copy()
    df_des_f['CENTRAL_BASE'] = df_des_f['CENTRAL'].apply(limpiar_nombre_central)
    df_des_f = df_des_f[df_des_f['CENTRAL_BASE'].isin(nombres_set)]

    def slice_df(df, col='FECHA_HORA'):
        if df.empty: return pd.DataFrame()
        return df[(df[col] >= f_ini_ts) & (df[col] <= f_fin_ts)].copy()

    df_dem_f  = slice_df(df_dem)
    df_int_f  = slice_df(df_inter)
    df_cal_f  = slice_df(df_cal, col='INICIO')
    df_cmg_f  = slice_df(df_cmg)
    return df_des_f, df_dem_f, df_int_f, df_cal_f, df_cmg_f

# ──────────────────────────────────────────
# SIDEBAR — BASE DE DATOS
# ──────────────────────────────────────────
st.markdown('<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">'
            '<span style="font-size:1.6rem">⚡</span>'
            '<div><h2 style="margin:0;font-size:1.25rem;">Dashboard de Supervisión</h2>'
            '<p style="margin:0;font-size:0.78rem;opacity:0.8;">Despacho Ejecutado del SEIN</p></div>'
            '</div>', unsafe_allow_html=True)
st.markdown('<hr style="margin:8px 0 16px;border:none;border-top:2px solid #e0e6ef">', unsafe_allow_html=True)

st.sidebar.markdown('<div class="sidebar-section">⚙ Base de Datos</div>', unsafe_allow_html=True)
archivos_parquet = glob.glob("*_Despacho.parquet")
prefijos_bases   = [f.replace("_Despacho.parquet","") for f in archivos_parquet]

if not prefijos_bases:
    st.sidebar.error("❌ No se detectó ninguna base de datos Parquet.")
    st.stop()

base_seleccionada = st.sidebar.selectbox("📂 Base de Datos:", prefijos_bases, label_visibility="collapsed")
archivo_principal = f"{base_seleccionada}_Despacho.parquet"
mtime = os.path.getmtime(archivo_principal) if os.path.exists(archivo_principal) else 0

with st.sidebar:
    with st.spinner("Leyendo índice..."):
        df_des_todo, df_dem_todo, df_int_todo, df_cal_todo, df_cmg_todo = cargar_parquet(base_seleccionada, mtime)

df_matriz = cargar_centrales_sein()
if df_matriz.empty:
    st.error("❌ No se pudo cargar CetralesSEIN.xlsx.")
    st.stop()
if df_des_todo.empty:
    st.sidebar.warning("⚠️ Archivo de despacho vacío.")
    st.stop()

fecha_min_db = df_des_todo['FECHA_HORA'].min().date()
fecha_max_db = df_des_todo['FECHA_HORA'].max().date()
anios_disp   = sorted(df_des_todo['FECHA_HORA'].dt.year.unique().tolist())

# ──────────────────────────────────────────
# SIDEBAR — SELECTOR TEMPORAL (Año + Mes)
# ──────────────────────────────────────────
st.sidebar.markdown('<div class="sidebar-section">🗓 Rango de Fechas</div>', unsafe_allow_html=True)

modo_fecha = st.sidebar.radio(
    "Modo de selección:",
    ["Por Año/Mes", "Rango exacto (días)"],
    horizontal=True
)

if modo_fecha == "Por Año/Mes":
    col_a, col_b = st.sidebar.columns(2)
    with col_a:
        anio_ini_sel = st.selectbox("Año inicio", anios_disp, index=0)
    with col_b:
        anio_fin_sel = st.selectbox("Año fin", anios_disp, index=len(anios_disp)-1)

    meses_ini_disp = [m for m in range(1,13)
                      if date(anio_ini_sel, m, 1) >= date(fecha_min_db.year, fecha_min_db.month, 1)]
    meses_fin_disp = [m for m in range(1,13)
                      if date(anio_fin_sel, m, 1) <= date(fecha_max_db.year, fecha_max_db.month, 1)]

    col_c, col_d = st.sidebar.columns(2)
    with col_c:
        mes_ini_idx = meses_ini_disp.index(fecha_min_db.month) if (
            anio_ini_sel == fecha_min_db.year and fecha_min_db.month in meses_ini_disp) else 0
        mes_ini_sel = st.selectbox("Mes inicio",
                                   meses_ini_disp,
                                   index=mes_ini_idx,
                                   format_func=lambda m: MESES_CORTO[m])
    with col_d:
        mes_fin_idx = len(meses_fin_disp)-1
        mes_fin_sel = st.selectbox("Mes fin",
                                   meses_fin_disp,
                                   index=mes_fin_idx,
                                   format_func=lambda m: MESES_CORTO[m])

    f_ini = pd.Timestamp(date(anio_ini_sel, mes_ini_sel, 1))
    ultimo_dia = calendar.monthrange(anio_fin_sel, mes_fin_sel)[1]
    f_fin = pd.Timestamp(date(anio_fin_sel, mes_fin_sel, ultimo_dia)) + pd.Timedelta(hours=23, minutes=59, seconds=59)

    label_periodo = (f"{MESES_CORTO[mes_ini_sel]} {anio_ini_sel} → "
                     f"{MESES_CORTO[mes_fin_sel]} {anio_fin_sel}")
else:
    rango_fechas = st.sidebar.date_input(
        "Periodo exacto:",
        value=(fecha_min_db, fecha_max_db),
        min_value=fecha_min_db,
        max_value=fecha_max_db
    )
    if not (isinstance(rango_fechas, tuple) and len(rango_fechas) == 2):
        st.info("Selecciona un rango de fechas completo.")
        st.stop()
    f_ini = pd.Timestamp(rango_fechas[0])
    f_fin = pd.Timestamp(rango_fechas[1]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    label_periodo = f"{rango_fechas[0].strftime('%d/%m/%Y')} → {rango_fechas[1].strftime('%d/%m/%Y')}"

# Validar coherencia
# Validar coherencia y límite máximo de 4 meses
if f_ini > f_fin:
    st.sidebar.error("⚠️ El inicio es posterior al fin. Ajusta la selección.")
    st.stop()

# Validar que el rango no exceda los 4 meses (aprox. 124 días máximos)
if (f_fin - f_ini).days > 124:
    st.sidebar.error("⏱️ El rango de fechas supera los 4 meses permitidos. Por favor, selecciona un periodo más corto.")
    st.stop()
# ──────────────────────────────────────────
# SIDEBAR — FILTROS OPERATIVOS
# ──────────────────────────────────────────
st.sidebar.markdown('<div class="sidebar-section">🔍 Filtros Operativos</div>', unsafe_allow_html=True)

opts_zona  = sorted([x for x in df_matriz['AREA_OPERATIVA'].unique() if x])
filtro_zona = st.sidebar.multiselect("📍 Área Operativa:", options=opts_zona, placeholder="Todas")
df_f1 = df_matriz[df_matriz['AREA_OPERATIVA'].isin(filtro_zona)] if filtro_zona else df_matriz

opts_int    = sorted([x for x in df_f1['TIPO_INTEGRANTE'].unique() if x])
defecto_int = ["COES"] if "COES" in opts_int else []
filtro_int  = st.sidebar.multiselect("⚖️ Tipo Integrante:", options=opts_int, default=defecto_int, placeholder="Todos")
df_f2 = df_f1[df_f1['TIPO_INTEGRANTE'].isin(filtro_int)] if filtro_int else df_f1

opts_req   = sorted([x for x in df_f2['REQUERIMIENTO_ESPECIAL'].unique() if x])
filtro_req = st.sidebar.multiselect("⚠️ Req. Especial:", options=opts_req, placeholder="Todos")
df_f3 = df_f2[df_f2['REQUERIMIENTO_ESPECIAL'].isin(filtro_req)] if filtro_req else df_f2

opts_emp      = sorted([x for x in df_f3['EMPRESA_DESPACHO'].unique() if x])
filtro_empresa = st.sidebar.multiselect("🏢 Empresa:", options=opts_emp, placeholder="Todas")
df_f4 = df_f3[df_f3['EMPRESA_DESPACHO'].isin(filtro_empresa)] if filtro_empresa else df_f3

opts_tipo  = sorted([x for x in df_f4['TIPO_GENERACION'].unique() if x])
filtro_tipo = st.sidebar.multiselect("⚡ Tipo de Recurso:", options=opts_tipo, placeholder="Todas")
df_f5 = df_f4[df_f4['TIPO_GENERACION'].isin(filtro_tipo)] if filtro_tipo else df_f4

df_f5 = df_f5.copy()
df_f5['CENTRAL'] = df_f5['CENTRAL'].astype(str).str.strip()
opts_cen   = sorted([x for x in df_f5['CENTRAL'].unique() if x and str(x) != "nan"])
filtro_cen = st.sidebar.multiselect("🏭 Central:", options=opts_cen, placeholder="Todas")
df_f_final = df_f5[df_f5['CENTRAL'].isin(filtro_cen)] if filtro_cen else df_f5

# ──────────────────────────────────────────
# SIDEBAR — SELECTOR DE GRÁFICA
# ──────────────────────────────────────────
st.sidebar.markdown('<div class="sidebar-section">📊 Vista</div>', unsafe_allow_html=True)

GRAFICAS = {
    "1 · Despacho por Tecnología":           "g1",
    "2 · Despacho vs CMg":                   "g2",
    "3 · Flujo de Enlaces":                  "g3",
    "4 · Generación por Central":            "g4",
    "5 · Potencia Promedio Diaria":          "g5",
    "6 · Control de Tiempos":               "g6",
    "7 · Calificación de la Operación":     "g7",
    "8 · Demanda por Áreas":                "g8",
    "9 · Trazabilidad (Data Cruda)":        "g9",
    "10 · Balance Área Norte":              "g10",
    "11 · CMg Consolidado":                 "g11",
}

grafica_seleccionada = st.sidebar.radio(
    "¿Qué quieres ver?",
    options=list(GRAFICAS.keys()),
    index=0,
    label_visibility="collapsed"
)

st.sidebar.markdown("---")
aplicar = st.sidebar.button("▶ Aplicar Filtros y Ver Gráfica", type="primary")

# ──────────────────────────────────────────
# GUARDAR ESTADO
# ──────────────────────────────────────────
if aplicar:
    st.session_state['filtros_aplicados'] = True
    st.session_state['grafica_key']       = GRAFICAS[grafica_seleccionada]
    st.session_state['grafica_nombre']    = grafica_seleccionada
    st.session_state['df_f_final']        = df_f_final.copy()
    st.session_state['f_ini']             = f_ini
    st.session_state['f_fin']             = f_fin
    st.session_state['label_periodo']     = label_periodo

if not st.session_state.get('filtros_aplicados'):
    st.markdown("""
    <div style="text-align:center;padding:5rem 2rem;color:#6b7a99;background:#f8faff;
                border-radius:12px;border:2px dashed #d0d9ee;margin-top:2rem">
        <div style="font-size:3rem;margin-bottom:1rem">📊</div>
        <h2 style="color:#0f172a;margin-bottom:0.5rem">Configura y aplica los filtros</h2>
        <p style="font-size:1rem;max-width:480px;margin:0 auto">
            Selecciona el <b>rango de fechas</b> por año/mes, aplica los filtros operativos,
            elige la <b>visualización</b> que necesitas y pulsa <b>▶ Aplicar</b>.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ──────────────────────────────────────────
# PREPARAR DATOS
# ──────────────────────────────────────────
df_f_final_ss   = st.session_state['df_f_final']
f_ini_ss        = st.session_state['f_ini']
f_fin_ss        = st.session_state['f_fin']
grafica_key     = st.session_state['grafica_key']
label_periodo_ss= st.session_state.get('label_periodo', '')

df_f_final_ss['CENTRAL_NORMALIZADA'] = df_f_final_ss['CENTRAL'].apply(limpiar_nombre_central)
nombres_maestro = set(df_f_final_ss['CENTRAL_NORMALIZADA'].str.upper())
nombres_calificacion_activos = [
    str(n).strip().upper() for n in df_f_final_ss['CENTRAL_CALIFICACION'].unique()
    if pd.notna(n) and str(n).strip().upper() not in ["","N/A","NAN"]
]
dict_zonas    = dict(zip(df_f_final_ss['CENTRAL_NORMALIZADA'].str.upper(), df_f_final_ss['AREA_OPERATIVA']))
dict_tipos    = dict(zip(df_f_final_ss['CENTRAL_NORMALIZADA'].str.upper(), df_f_final_ss['TIPO_GENERACION']))
dict_empresas = dict(zip(df_f_final_ss['CENTRAL_NORMALIZADA'].str.upper(), df_f_final_ss['EMPRESA_DESPACHO']))

f_ini_str     = f_ini_ss.isoformat()
f_fin_str     = f_fin_ss.isoformat()
nombres_tuple = tuple(sorted(nombres_maestro))

with st.spinner("⚡ Filtrando datos..."):
    df_datos, df_dem_raw, df_inter_raw, df_seg_raw, df_cmg_raw = recortar_y_filtrar(
        base_seleccionada, mtime, f_ini_str, f_fin_str, nombres_tuple
    )

if df_datos.empty:
    st.warning("⚠️ No hay datos despachados para las centrales filtradas en las fechas seleccionadas.")
    st.stop()

df_datos['ZONA']         = df_datos['CENTRAL_BASE'].map(dict_zonas).fillna("N/A")
df_datos['TIPO_CENTRAL'] = df_datos['CENTRAL_BASE'].map(dict_tipos).fillna("N/A")
df_datos['EMPRESA']      = df_datos['CENTRAL_BASE'].map(dict_empresas).fillna("N/A")
df_datos['FECHA_DIA']    = df_datos['FECHA_HORA'].dt.date

energia_total_cen = df_datos.groupby('CENTRAL')['DESPACHO_MW'].sum()
centrales_activas = energia_total_cen[energia_total_cen > 0].index
df_plot_cen = df_datos[df_datos['CENTRAL'].isin(centrales_activas)].copy()
df_plot_cen['CENTRAL'] = pd.Categorical(
    df_plot_cen['CENTRAL'],
    categories=energia_total_cen[centrales_activas].sort_values(ascending=False).index,
    ordered=True
)
df_plot_cen = df_plot_cen.sort_values(['FECHA_HORA','CENTRAL'])


# ──────────────────────────────────────────
# HELPER: tickformat para ejes de gráficas
# ──────────────────────────────────────────
def xaxis_layout(f_ini, f_fin, extra=None):
    tfmt, dtick = tickformat_inteligente(f_ini, f_fin)
    cfg = dict(tickformat=tfmt, title="Fecha Operativa", range=[f_ini, f_fin])
    if dtick: cfg['dtick'] = dtick
    if extra: cfg.update(extra)
    return cfg

# ══════════════════════════════════════════
# GRÁFICAS
# ══════════════════════════════════════════

# ── G1 ──────────────────────────────────
if grafica_key == "g1":
    st.header("1. 🏭 Despacho por Tipo de Generación (SEIN)")
    df_tipo = df_datos.groupby(['FECHA_HORA','TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
    df_tipo['TIPO_CENTRAL'] = pd.Categorical(df_tipo['TIPO_CENTRAL'], categories=ORDEN_TECNOLOGIA, ordered=True)
    df_tipo = df_tipo.sort_values(['FECHA_HORA','TIPO_CENTRAL'])
    fig = crear_grafica_area(df_tipo, 'TIPO_CENTRAL', "Curva Apilada por Tecnología",
                             color_map=COLORES_TECNOLOGIA, f_ini=f_ini_ss, f_fin=f_fin_ss)
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Ver Datos (Matriz)"):
        df_tipo['FECHA'] = df_tipo['FECHA_HORA'].dt.strftime('%d/%m/%Y')
        df_tipo['HORA']  = df_tipo['FECHA_HORA'].dt.strftime('%H:%M')
        mat = df_tipo.pivot_table(index=['FECHA','HORA'], columns='TIPO_CENTRAL', values='DESPACHO_MW', aggfunc='sum').round(2).fillna(0)
        st.dataframe(mat, use_container_width=True)

# ── G2 ──────────────────────────────────
elif grafica_key == "g2":
    st.header("2. 💸 Despacho Operativo vs Costo Marginal (CMg)")
    st.info("Despacho por tecnología y flujos (Eje Izq. - MW) vs CMg Trujillo 220 (Eje Der. - S/./MWh).")
    if df_cmg_raw.empty:
        st.info("No se encontraron datos de Costos Marginales.")
    else:
        df_cmg_plot = df_cmg_raw[df_cmg_raw['BARRA'] == 'TRUJILLO 220'].sort_values('FECHA_HORA')
        df_cn_total = df_l5006_total = pd.DataFrame()
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
        df_tipo_cmg = df_datos.groupby(['FECHA_HORA','TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
        for tec in ORDEN_TECNOLOGIA:
            df_tec = df_tipo_cmg[df_tipo_cmg['TIPO_CENTRAL'] == tec]
            if not df_tec.empty:
                fig_cmg.add_trace(go.Scatter(
                    x=df_tec['FECHA_HORA'], y=df_tec['DESPACHO_MW'], mode='lines',
                    line=dict(width=0), fill='tonexty', stackgroup='one', name=tec,
                    marker_color=COLORES_TECNOLOGIA.get(tec,'#808080'),
                    hovertemplate=f"<b>{tec}</b>: %{{y:,.2f}} MW"
                ), secondary_y=False)
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
            for y_ref, label, color in [(700,"Límite Sup L-5006: 700 MW","red"),(600,"Límite Inf L-5006: 600 MW","green")]:
                fig_cmg.add_shape(type="line", x0=f_min_c, y0=y_ref, x1=f_max_c, y1=y_ref,
                                  line=dict(color=color, width=2, dash="dash"), yref="y")
                fig_cmg.add_annotation(x=f_max_c, y=y_ref, text=f"<b>{label}</b>",
                                       showarrow=False, xanchor="right", yanchor="bottom", yref="y",
                                       font=dict(color="blue"))

        max_gen = df_tipo_cmg.groupby('FECHA_HORA')['DESPACHO_MW'].sum().max() if not df_tipo_cmg.empty else 1400
        lim_y1  = max_gen + 400
        lim_y2  = (df_cmg_plot['CMG_USD'].max() * 1.15) if not df_cmg_plot.empty else 50
        tfmt, dtick = tickformat_inteligente(f_ini_ss, f_fin_ss)
        xax = dict(title_text="Fecha Operativa", tickformat=tfmt)
        if dtick: xax['dtick'] = dtick
        fig_cmg.update_layout(hovermode="x unified", height=650,
                              margin=dict(t=50,b=50,l=50,r=150),
                              legend=dict(title="<b>Componentes</b>",orientation="v",yanchor="top",y=1,xanchor="left",x=1.05),
                              template="plotly_white")
        fig_cmg.update_xaxes(**xax)
        fig_cmg.update_yaxes(title_text="Potencia Activa (MW)", range=[0,lim_y1], secondary_y=False)
        fig_cmg.update_yaxes(title_text="Costo Marginal (S/./MWh)", range=[0,lim_y2], secondary_y=True, showgrid=False)
        agregar_lineas_anio(fig_cmg, f_ini_ss, f_fin_ss)
        st.plotly_chart(fig_cmg, use_container_width=True)
        with st.expander("Ver Datos CMg (Matriz)"):
            df_cmg_plot['FECHA'] = df_cmg_plot['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_cmg_plot['HORA']  = df_cmg_plot['FECHA_HORA'].dt.strftime('%H:%M')
            st.dataframe(df_cmg_plot.pivot_table(index=['FECHA','HORA'], columns='BARRA', values='CMG_USD', aggfunc='mean').round(2), use_container_width=True)

# ── G3 ──────────────────────────────────
elif grafica_key == "g3":
    st.header("3. 🔌 Flujo de Enlaces")
    if df_inter_raw.empty:
        st.info("No se detectaron datos de enlaces.")
    else:
        def marcar_min_max_flujo(fig, df_total):
            if df_total.empty: return
            mx = df_total.loc[df_total['FLUJO_MW'].abs().idxmax(), 'FLUJO_MW']
            mn = df_total.loc[df_total['FLUJO_MW'].abs().idxmin(), 'FLUJO_MW']
            for val, pos in [(mx,"top left"),(mn,"bottom left")]:
                fig.add_hline(y=val, line_dash="dash", line_color="black", line_width=2,
                              annotation_text=f"<b>{'Máx' if val==mx else 'Mín'}: {val:,.0f} MW</b>",
                              annotation_position=pos, annotation_font=dict(color="blue"))

        df_inter_plot = df_inter_raw.sort_values(['FECHA_HORA','LINEA_TRANSMISION'])
        tfmt, dtick = tickformat_inteligente(f_ini_ss, f_fin_ss)

        for enlace, subtitulo in [('CENTRO-NORTE','Centro-Norte'),('CENTRO-SUR','Centro-Sur')]:
            df_e = df_inter_plot[df_inter_plot['ENLACE'] == enlace]
            if df_e.empty: continue
            st.subheader(subtitulo)
            fig_e = px.area(df_e, x="FECHA_HORA", y="FLUJO_MW", color="LINEA_TRANSMISION",
                            title=f"Flujo {subtitulo} (MW)",
                            color_discrete_sequence=COLORES_SECUENCIA, template="plotly_white")
            df_e_tot = df_e.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
            fig_e.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
            fig_e.add_scatter(x=df_e_tot['FECHA_HORA'], y=df_e_tot['FLUJO_MW'],
                              mode='lines', line=dict(width=3, color='gray'), name=f'⚡ TOTAL {subtitulo[:2].upper()}-{"N" if "NORTE" in enlace else "S"}')
            marcar_min_max_flujo(fig_e, df_e_tot)
            xax_cfg = dict(tickformat=tfmt, title="Fecha Operativa")
            if dtick: xax_cfg['dtick'] = dtick
            fig_e.update_layout(hovermode="x unified", height=450, xaxis=xax_cfg)
            agregar_lineas_anio(fig_e, f_ini_ss, f_fin_ss)
            st.plotly_chart(fig_e, use_container_width=True)

# ── G4 ──────────────────────────────────
elif grafica_key == "g4":
    st.header("4. 📊 Generación del SEIN por Central")
    df_aux = df_plot_cen.copy()
    df_aux['DESPACHO_MW'] = pd.to_numeric(df_aux['DESPACHO_MW'], errors='coerce').fillna(0)
    df_aux['CENTRAL'] = df_aux.apply(
        lambda r: f"{r['CENTRAL_BASE']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})", axis=1)
    df_aux = df_aux.groupby(['FECHA_HORA','CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
    orden_e = df_aux.groupby('CENTRAL')['DESPACHO_MW'].sum().sort_values(ascending=False).index
    df_aux['CENTRAL'] = pd.Categorical(df_aux['CENTRAL'], categories=orden_e, ordered=True)
    df_aux  = df_aux.sort_values(['FECHA_HORA','CENTRAL'])
    df_sis  = df_aux.groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()
    lim_y   = df_sis['DESPACHO_MW'].max() * 1.05 if not df_sis.empty else 1000
    tfmt, dtick = tickformat_inteligente(f_ini_ss, f_fin_ss)
    fig_cen = px.area(df_aux, x="FECHA_HORA", y="DESPACHO_MW", color='CENTRAL',
                      title="Despacho por Unidad - SEIN (MW)",
                      color_discrete_sequence=COLORES_SECUENCIA, template="plotly_white")
    fig_cen.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
    fig_cen.add_scatter(x=df_sis['FECHA_HORA'], y=df_sis['DESPACHO_MW'], mode='lines',
                        line=dict(width=0, color='rgba(0,0,0,0)'), showlegend=False,
                        name='⚡ TOTAL', hovertemplate='<b>%{x|%d/%m/%Y} → %{y:,.2f} MW</b>')
    xax_cfg = dict(tickformat=tfmt, title="Fecha Operativa")
    if dtick: xax_cfg['dtick'] = dtick
    fig_cen.update_layout(hovermode="x unified", height=550,
                          yaxis=dict(range=[0,lim_y]), xaxis=xax_cfg)
    agregar_lineas_anio(fig_cen, f_ini_ss, f_fin_ss)
    st.plotly_chart(fig_cen, use_container_width=True)
    with st.expander("Ver Datos (Matriz)"):
        df_aux['FECHA'] = df_aux['FECHA_HORA'].dt.strftime('%d/%m/%Y')
        df_aux['HORA']  = df_aux['FECHA_HORA'].dt.strftime('%H:%M')
        mat = df_aux.pivot_table(index=['FECHA','HORA'], columns='CENTRAL', values='DESPACHO_MW', aggfunc='sum').round(2).fillna(0)
        st.dataframe(mat, use_container_width=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as w: mat.to_excel(w, sheet_name='Generacion_Central')
        st.download_button("📥 Descargar Excel", buf.getvalue(),
                           f"Generacion_Central_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── G5 ──────────────────────────────────
elif grafica_key == "g5":
    st.header("5. 📈 Potencia Promedio Diaria (SEIN)")
    modo = st.radio("Modo de barras:", ["Agrupado","Apilado"], horizontal=True)
    barmode = 'group' if modo == "Agrupado" else 'stack'
    df_prom = df_plot_cen.copy()
    df_prom['CENTRAL'] = df_prom.apply(
        lambda r: f"{r['CENTRAL']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})" if "(" not in r['CENTRAL'] else r['CENTRAL'], axis=1)
    df_prom['FECHA_DIA_OP'] = (df_prom['FECHA_HORA'] - pd.Timedelta(minutes=1)).dt.date

    # Etiqueta de día que incluye año (dd/mm/YYYY)
    df_prom24 = df_prom.groupby(['FECHA_DIA_OP','CENTRAL'], as_index=False)['DESPACHO_MW'].mean()
    df_prom24['FECHA_LABEL'] = pd.to_datetime(df_prom24['FECHA_DIA_OP']).dt.strftime('%d/%m/%Y')
    orden_p = df_prom24.groupby('CENTRAL')['DESPACHO_MW'].mean().sort_values(ascending=False).index
    df_prom24['CENTRAL'] = pd.Categorical(df_prom24['CENTRAL'], categories=orden_p, ordered=True)

    fig_p24 = px.bar(df_prom24, x='FECHA_LABEL', y='DESPACHO_MW', color='CENTRAL',
                     title="Potencia Promedio Total 24 h (MW)", barmode=barmode,
                     color_discrete_sequence=COLORES_SECUENCIA, template="plotly_white")
    fig_p24.update_layout(xaxis=dict(type='category', title="Día Operativo"), height=500)
    st.plotly_chart(fig_p24, use_container_width=True)

    df_iny = df_prom[df_prom['DESPACHO_MW'] > 0].copy()
    if not df_iny.empty:
        df_prom_iny = df_iny.groupby(['FECHA_DIA_OP','CENTRAL'], as_index=False)['DESPACHO_MW'].mean()
        df_prom_iny['FECHA_LABEL'] = pd.to_datetime(df_prom_iny['FECHA_DIA_OP']).dt.strftime('%d/%m/%Y')
        orden_i = df_prom_iny.groupby('CENTRAL')['DESPACHO_MW'].mean().sort_values(ascending=False).index
        df_prom_iny['CENTRAL'] = pd.Categorical(df_prom_iny['CENTRAL'], categories=orden_i, ordered=True)
        fig_piny = px.bar(df_prom_iny, x='FECHA_LABEL', y='DESPACHO_MW', color='CENTRAL',
                          title="Potencia Promedio en Operación (MW)", barmode=barmode,
                          color_discrete_sequence=COLORES_SECUENCIA, template="plotly_white")
        fig_piny.update_layout(xaxis=dict(type='category', title="Día Operativo"), height=500)
        st.plotly_chart(fig_piny, use_container_width=True)

    with st.expander("Ver Datos (Matriz)"):
        mat_p = df_prom24.pivot_table(index='FECHA_LABEL', columns='CENTRAL', values='DESPACHO_MW').round(2).fillna(0)
        st.dataframe(mat_p, use_container_width=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as w: mat_p.to_excel(w, sheet_name='Promedio_24H')
        st.download_button("📥 Descargar Excel", buf.getvalue(),
                           f"Promedios_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── G6 ──────────────────────────────────
elif grafica_key == "g6":
    st.header("6. ⏱️ Control de Tiempos: Inactividad y Operación")
    df_gantt = df_datos.copy()
    df_gantt['CENTRAL'] = df_gantt.apply(
        lambda r: f"{r['CENTRAL_BASE']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})", axis=1)
    df_gantt = df_gantt.groupby(['FECHA_HORA','CENTRAL','TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
    df_gantt = df_gantt.sort_values(['CENTRAL','FECHA_HORA'])
    df_gantt['ESTADO']        = np.where(df_gantt['DESPACHO_MW'] > 0, 'OPERANDO', 'INACTIVO')
    df_gantt['CAMBIO_ESTADO'] = (df_gantt['ESTADO'] != df_gantt['ESTADO'].shift(1)) | (df_gantt['CENTRAL'] != df_gantt['CENTRAL'].shift(1))
    df_gantt['BLOQUE']        = df_gantt['CAMBIO_ESTADO'].cumsum()
    df_bloques = df_gantt.groupby(['CENTRAL','TIPO_CENTRAL','ESTADO','BLOQUE'], as_index=False).agg(
        INICIO=('FECHA_HORA','min'), FIN=('FECHA_HORA','max'))
    df_bloques['FIN'] += pd.Timedelta(minutes=30)
    f_start, f_end = df_datos['FECHA_HORA'].min(), df_datos['FECHA_HORA'].max() + pd.Timedelta(minutes=30)
    tfmt, dtick = tickformat_inteligente(f_ini_ss, f_fin_ss)
    xax_gantt = dict(tickformat=tfmt, title="Línea de Tiempo")
    if dtick: xax_gantt['dtick'] = dtick

    st.subheader("🚥 Cronograma de Inactividad (Base y Renovables)")
    df_inact = df_bloques[(df_bloques['ESTADO'] == 'INACTIVO') & (df_bloques['TIPO_CENTRAL'] != 'DIESEL/RESIDUAL')]
    if df_inact.empty:
        st.success("✅ Sin periodos de inactividad detectados.")
    else:
        fig_inact = px.timeline(df_inact, x_start="INICIO", x_end="FIN", y="CENTRAL",
                                color="TIPO_CENTRAL", color_discrete_map=COLORES_TECNOLOGIA,
                                hover_data={"INICIO":"|%d/%m/%Y %H:%M","FIN":"|%d/%m/%Y %H:%M"},
                                template="plotly_white")
        fig_inact.update_yaxes(autorange="reversed")
        fig_inact.update_layout(xaxis=dict(**xax_gantt, range=[f_start, f_end]),
                                height=max(400, len(df_inact['CENTRAL'].unique()) * 22))
        agregar_lineas_anio(fig_inact, f_ini_ss, f_fin_ss)
        st.plotly_chart(fig_inact, use_container_width=True)

    df_gantt['INACTIVO_HR'] = (df_gantt['DESPACHO_MW'] == 0) * 0.5
    df_gantt['ACTIVO_HR']   = (df_gantt['DESPACHO_MW'] > 0) * 0.5
    df_res = df_gantt.groupby(['CENTRAL','TIPO_CENTRAL'], as_index=False)[['INACTIVO_HR','ACTIVO_HR']].sum()
    tipos_base = ['HIDROELÉCTRICA','HIDROELECTRICA','EÓLICA','EOLICA','SOLAR','BIOMASA',
                  'GAS DE LA SELVA','GAS CAMISEA','GAS NORTE']
    df_inact_res = df_res[df_res['TIPO_CENTRAL'].isin(tipos_base)]
    if not df_inact_res.empty:
        fig_bars = px.bar(df_inact_res, x='CENTRAL', y='INACTIVO_HR', color='TIPO_CENTRAL',
                          title="Horas No Despachadas (Excluye Diésel)",
                          color_discrete_map=COLORES_TECNOLOGIA, template="plotly_white")
        fig_bars.update_layout(xaxis={'categoryorder':'total descending'}, height=450)
        st.plotly_chart(fig_bars, use_container_width=True)

    st.subheader("🚨 Cronograma de Operación (Diésel / Residual)")
    df_die = df_bloques[(df_bloques['ESTADO'] == 'OPERANDO') & (df_bloques['TIPO_CENTRAL'] == 'DIESEL/RESIDUAL')]
    if df_die.empty:
        st.success("✅ Sin inyección Diésel/Residual.")
    else:
        fig_die = px.timeline(df_die, x_start="INICIO", x_end="FIN", y="CENTRAL",
                              color="TIPO_CENTRAL", color_discrete_map=COLORES_TECNOLOGIA,
                              hover_data={"INICIO":"|%d/%m/%Y %H:%M","FIN":"|%d/%m/%Y %H:%M"},
                              template="plotly_white")
        fig_die.update_yaxes(autorange="reversed")
        fig_die.update_layout(xaxis=dict(**xax_gantt, range=[f_start, f_end]),
                              height=max(300, len(df_die['CENTRAL'].unique()) * 22), showlegend=False)
        agregar_lineas_anio(fig_die, f_ini_ss, f_fin_ss)
        st.plotly_chart(fig_die, use_container_width=True)

    df_act_res = df_res[(df_res['TIPO_CENTRAL'] == 'DIESEL/RESIDUAL') & (df_res['ACTIVO_HR'] > 0)]
    if not df_act_res.empty:
        fig_bars_act = px.bar(df_act_res, x='CENTRAL', y='ACTIVO_HR', color='TIPO_CENTRAL',
                              title="Horas de Operación (Diésel/Residual)",
                              color_discrete_map=COLORES_TECNOLOGIA, template="plotly_white")
        fig_bars_act.update_layout(xaxis={'categoryorder':'total descending'}, height=400)
        st.plotly_chart(fig_bars_act, use_container_width=True)

# ── G7 ──────────────────────────────────
elif grafica_key == "g7":
    st.header("7. 🛡️ Calificación de la Operación")
    if df_seg_raw.empty:
        st.info("No se registraron calificaciones en el periodo.")
    elif not nombres_calificacion_activos:
        st.warning("Las centrales seleccionadas no poseen mapeo de Calificación.")
    else:
        df_bar = df_seg_raw.dropna(subset=['INICIO','FIN']).copy()
        df_bar['CENTRAL_LIMPIA'] = df_bar['CENTRAL'].astype(str).str.strip().str.upper()
        df_bar = df_bar[df_bar['CENTRAL_LIMPIA'].isin(set(nombres_calificacion_activos))]
        if df_bar.empty:
            st.warning("Las centrales filtradas no registraron operaciones calificadas.")
        else:
            df_bar['CENTRAL_GRUPO']   = df_bar['CENTRAL'].astype(str) + " - " + df_bar['GRUPO'].astype(str)
            df_bar['HORAS_OPERACION'] = (df_bar['FIN'] - df_bar['INICIO']).dt.total_seconds() / 3600
            df_bar['HORAS_OPERACION'] = df_bar['HORAS_OPERACION'].clip(lower=0)
            df_agr = df_bar.groupby(['CENTRAL_GRUPO','TIPO_OPERACION'], as_index=False)['HORAS_OPERACION'].sum()
            colores_op = {"POR SEGURIDAD":"#8B0000","POR POTENCIA O ENERGIA":"#00BFFF",
                          "A MINIMA CARGA":"#32CD32","POR COGENERACION":"#FF8C00",
                          "POR RSF":"#FFD700","POR PRUEBAS":"#808080"}
            fig_cal = px.bar(df_agr, x="HORAS_OPERACION", y="CENTRAL_GRUPO", color="TIPO_OPERACION",
                             orientation='h', title="Horas de Operación por Unidad y Tipo",
                             color_discrete_map=colores_op, template="plotly_white")
            fig_cal.update_layout(yaxis=dict(categoryorder="total ascending"),
                                  height=max(400, len(df_agr['CENTRAL_GRUPO'].unique()) * 40))
            st.plotly_chart(fig_cal, use_container_width=True)
            with st.expander("Ver Registros POR SEGURIDAD"):
                df_seg_show = df_bar[df_bar['TIPO_OPERACION'] == 'POR SEGURIDAD'].drop(columns=['CENTRAL_LIMPIA'], errors='ignore')
                st.dataframe(df_seg_show, use_container_width=True) if not df_seg_show.empty else st.info("Sin registros POR SEGURIDAD.")

# ── G8 ──────────────────────────────────
elif grafica_key == "g8":
    st.header("8. 🌍 Evolución y Comportamiento de la Demanda por Áreas")
    if df_dem_raw.empty:
        st.info("No se encontraron datos de demanda.")
    else:
        df_sub  = df_dem_raw[df_dem_raw['ÁREA'] != 'SEIN']
        df_sein = df_dem_raw[df_dem_raw['ÁREA'] == 'SEIN']
        colores_area = {"NORTE":"#FF9900","CENTRO":"#3366CC","SUR":"#DC3912"}
        tfmt, dtick = tickformat_inteligente(f_ini_ss, f_fin_ss)

        fig_dem = px.line(df_sub, x="FECHA_HORA", y="DEMANDA_MW", color="ÁREA",
                          title="Evolución de la Demanda por Áreas (MW)",
                          color_discrete_map=colores_area, template="plotly_white")
        fig_dem.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=2, dash='dot'))

        def añadir_extremos(fig, df_f, color, nombre):
            if df_f.empty: return
            im = df_f['DEMANDA_MW'].idxmax(); ix = df_f['DEMANDA_MW'].idxmin()
            for idx, sym, pos in [(im,'triangle-up','top center'),(ix,'triangle-down','bottom center')]:
                r = df_f.loc[idx]
                fig.add_scatter(x=[r['FECHA_HORA']], y=[r['DEMANDA_MW']], mode='markers+text',
                                marker=dict(color=color, size=12, symbol=sym),
                                text=[f"<b>{'Máx' if 'up' in sym else 'Mín'}: {r['DEMANDA_MW']:,.0f} MW</b>"],
                                textposition=pos, showlegend=False, hoverinfo='skip', textfont=dict(color="blue"))

        for area in df_sub['ÁREA'].unique():
            añadir_extremos(fig_dem, df_sub[df_sub['ÁREA'] == area], colores_area.get(area,'blue'), area)
        if not df_sein.empty:
            fig_dem.add_scatter(x=df_sein['FECHA_HORA'], y=df_sein['DEMANDA_MW'], mode='lines',
                                line=dict(width=3, color='black', dash='dash'), name='⚡ SEIN TOTAL',
                                hovertemplate='%{x|%d/%m/%Y} → %{y:,.2f} MW')
            añadir_extremos(fig_dem, df_sein, 'black', 'SEIN')

        xax_cfg = dict(tickformat=tfmt, title="Fecha Operativa")
        if dtick: xax_cfg['dtick'] = dtick
        fig_dem.update_layout(hovermode="x unified", height=550, xaxis=xax_cfg)
        agregar_lineas_anio(fig_dem, f_ini_ss, f_fin_ss)
        st.plotly_chart(fig_dem, use_container_width=True)

# ── G9 ──────────────────────────────────
elif grafica_key == "g9":
    st.header("9. 🗄️ Trazabilidad de Potencia (Data Cruda)")
    with st.expander("Ver Matriz de Despacho", expanded=True):
        df_piv = df_plot_cen.copy()
        df_piv['FECHA'] = df_piv['FECHA_HORA'].dt.strftime('%d/%m/%Y')
        df_piv['HORA']  = df_piv['FECHA_HORA'].dt.strftime('%H:%M')
        mat = df_piv.pivot_table(index=['FECHA','HORA'],
                                  columns=['ZONA','TIPO_CENTRAL','EMPRESA','CENTRAL'],
                                  values='DESPACHO_MW', aggfunc='sum').round(2).fillna(0)
        st.dataframe(mat, use_container_width=True)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as w: mat.to_excel(w, sheet_name='Despacho_SEIN')
        st.download_button("📥 Descargar Excel", buf.getvalue(),
                           f"matriz_sein_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── G10 ─────────────────────────────────
elif grafica_key == "g10":
    st.header("10. 📉 Balance de Potencia - Área Norte")
    st.info("Demanda Norte (Generación + Flujo absoluto), Generación local Norte y Flujo Centro-Norte.")
    if df_dem_raw.empty or df_inter_raw.empty:
        st.info("Se requieren datos de Demanda e Interconexiones.")
    else:
        df_dem_n = df_dem_raw[df_dem_raw['ÁREA'] == 'NORTE'].groupby('FECHA_HORA', as_index=False)['DEMANDA_MW'].sum()
        df_cn    = df_inter_raw[df_inter_raw['ENLACE'] == 'CENTRO-NORTE']
        df_cn_t  = df_cn.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
        df_cn_t['FLUJO_NEG'] = df_cn_t['FLUJO_MW'] * -1
        df_gen_n = df_datos[df_datos['ZONA'] == 'NORTE'].groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()
        df_bal = df_dem_n.merge(df_cn_t[['FECHA_HORA','FLUJO_NEG']], on='FECHA_HORA', how='inner')
        df_bal = df_bal.merge(df_gen_n, on='FECHA_HORA', how='inner')
        df_bal.columns = ['FECHA_HORA','DEMANDA','FLUJO_NEG','GENERACION']
        df_bal['DEMANDA'] = df_bal['GENERACION'].abs() + df_bal['FLUJO_NEG'].abs()

        fig_bal = go.Figure()
        for col, color, name in [('DEMANDA','#FF9900','📉 DEMANDA NORTE'),
                                  ('GENERACION','#1f77b4','🏭 GENERACIÓN NORTE'),
                                  ('FLUJO_NEG','#9467bd','🔌 -1 × FLUJO C-N')]:
            fig_bal.add_trace(go.Scatter(x=df_bal['FECHA_HORA'], y=df_bal[col], mode='lines',
                                         line=dict(width=3, color=color), name=f'<b>{name}</b>',
                                         hovertemplate=f"<b>{name}</b>: %{{y:,.2f}} MW"))

        max_y = max(df_bal[c].max() for c in ['DEMANDA','GENERACION','FLUJO_NEG']) + 400
        min_y = min(df_bal[c].min() for c in ['DEMANDA','GENERACION','FLUJO_NEG'])
        min_y = min_y * 1.15 if min_y < 0 else 0
        tfmt, dtick = tickformat_inteligente(f_ini_ss, f_fin_ss)
        xax_cfg = dict(title_text="Fecha Operativa", tickformat=tfmt)
        if dtick: xax_cfg['dtick'] = dtick
        fig_bal.update_layout(hovermode="x unified", height=600,
                              xaxis=xax_cfg, yaxis=dict(title="Potencia (MW)", range=[min_y, max_y]),
                              template="plotly_white", margin=dict(t=50,b=50,l=50,r=150),
                              legend=dict(orientation="v",yanchor="top",y=1,xanchor="left",x=1.02))
        agregar_lineas_anio(fig_bal, f_ini_ss, f_fin_ss)
        st.plotly_chart(fig_bal, use_container_width=True)
        with st.expander("Ver Datos (Matriz)"):
            df_bal['FECHA'] = df_bal['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_bal['HORA']  = df_bal['FECHA_HORA'].dt.strftime('%H:%M')
            mat = df_bal.pivot_table(index=['FECHA','HORA'], values=['DEMANDA','GENERACION','FLUJO_NEG'], aggfunc='mean').round(2)
            st.dataframe(mat[['DEMANDA','GENERACION','FLUJO_NEG']], use_container_width=True)

# ── G11 ─────────────────────────────────
elif grafica_key == "g11":
    st.header("11. 📈 Evolución Consolidada de Costos Marginales")
    st.info("Comparativa del CMg en barras de referencia Norte, Centro y Sur del SEIN.")
    if df_cmg_raw.empty:
        st.info("No se encontraron datos de Costos Marginales.")
    else:
        df_cmg_11   = df_cmg_raw.sort_values(['FECHA_HORA','BARRA'])
        colores_b11 = {'SANTA ROSA 220':'#d62728','MONTALVO 220':'#2ca02c','TRUJILLO 220':'#ff7f0e'}
        tfmt, dtick = tickformat_inteligente(f_ini_ss, f_fin_ss)
        fig_11 = px.line(df_cmg_11, x="FECHA_HORA", y="CMG_USD", color="BARRA",
                         title="Costo Marginal por Barra (USD/MWh)",
                         color_discrete_map=colores_b11, template="plotly_white")
        fig_11.update_traces(hovertemplate="<b>%{data.name}</b>: %{y:,.2f} USD/MWh", line=dict(width=3, dash='dot'))
        for barra in df_cmg_11['BARRA'].unique():
            df_b = df_cmg_11[df_cmg_11['BARRA'] == barra]
            color = colores_b11.get(barra, 'black')
            if df_b.empty: continue
            for fn, sym, pos in [(df_b['CMG_USD'].idxmax,'triangle-up','top center'),
                                 (df_b['CMG_USD'].idxmin,'triangle-down','bottom center')]:
                idx = fn(); r = df_b.loc[idx]
                fig_11.add_scatter(x=[r['FECHA_HORA']], y=[r['CMG_USD']], mode='markers+text',
                                   marker=dict(color=color, size=12, symbol=sym),
                                   text=[f"<b>{'Máx' if 'up' in sym else 'Mín'}: {r['CMG_USD']:,.1f}</b>"],
                                   textposition=pos, textfont=dict(color='blue'), showlegend=False, hoverinfo='skip')
        lim_sup = df_cmg_11['CMG_USD'].max() * 1.15 if df_cmg_11['CMG_USD'].max() > 0 else 50
        xax_cfg = dict(tickformat=tfmt, title="Fecha Operativa")
        if dtick: xax_cfg['dtick'] = dtick
        fig_11.update_layout(hovermode="x unified", height=600, xaxis=xax_cfg,
                             yaxis=dict(title="CMg (USD/MWh)", range=[0, lim_sup]),
                             margin=dict(t=50,b=50,l=50,r=150),
                             legend=dict(orientation="v",yanchor="top",y=1,xanchor="left",x=1.02))
        agregar_lineas_anio(fig_11, f_ini_ss, f_fin_ss)
        st.plotly_chart(fig_11, use_container_width=True)
        with st.expander("Ver Datos (Matriz)"):
            df_cmg_11['FECHA'] = df_cmg_11['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_cmg_11['HORA']  = df_cmg_11['FECHA_HORA'].dt.strftime('%H:%M')
            mat = df_cmg_11.pivot_table(index=['FECHA','HORA'], columns='BARRA', values='CMG_USD', aggfunc='mean').round(2)
            st.dataframe(mat, use_container_width=True)