import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io
import re
import os
import glob
import plotly.express as px
from docx import Document
from docx.shared import Inches
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 1. CONFIGURACIÓN DE PÁGINA (¡Debe ser la primera línea ejecutada!)
# ==========================================
st.set_page_config(page_title="Supervisión Despacho - SEIN", layout="wide", initial_sidebar_state="expanded")

# Código CSS para ocultar elementos de la interfaz nativa
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .css-1jc7ptx, .e1ewe7hr3, .viewerBadge_container__1QSob,
    .styles_viewerBadge__1yB5_, .viewerBadge_link__1S137,
    .viewerBadge_text__1JaDK { display: none; }
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("⚡ Dashboard de Supervisión - Despacho Ejecutado del SEIN")
st.markdown("Supervisión del Despacho, Interconexiones y Seguridad Operativa (Datos Consolidados Locales)")

# ==========================================
# 2. CARGAR MATRIZ DE CENTRALES DEL SEIN
# ==========================================
@st.cache_data
def cargar_centrales_sein():
    try:
        df_centrales = pd.read_excel('CetralesSEIN.xlsx', sheet_name=0, header=None, usecols=[0, 1, 2, 3, 4, 6, 7, 8])
        df_centrales_limpio = df_centrales.iloc[1:].copy()
        
        df_centrales_limpio.columns = [
            'CODIGO', 'CENTRAL', 'CENTRAL_CALIFICACION', 'EMPRESA_DESPACHO', 
            'AREA_OPERATIVA', 'TIPO_INTEGRANTE', 'TIPO_GENERACION', 'REQUERIMIENTO_ESPECIAL'
        ]
        
        for col in df_centrales_limpio.columns:
            df_centrales_limpio[col] = df_centrales_limpio[col].apply(lambda x: str(x).strip() if pd.notna(x) and str(x) != 'nan' else '')
        
        df_centrales_limpio = df_centrales_limpio[df_centrales_limpio['CENTRAL'] != ''].copy()
        return df_centrales_limpio
    except Exception as e:
        st.error(f"Error cargando CetralesSEIN.xlsx: {e}")
        return pd.DataFrame()

df_matriz_centrales = cargar_centrales_sein()

if not df_matriz_centrales.empty:
    dict_recursos_maestro = dict(zip(
        df_matriz_centrales['CENTRAL'].str.strip().str.upper(), 
        df_matriz_centrales['TIPO_GENERACION'].str.strip().str.upper()
    ))
else:
    dict_recursos_maestro = {}

# ==========================================
# 3. LECTURA DEL ARCHIVO CONSOLIDADO (PARQUET)
# ==========================================
@st.cache_data(show_spinner="Cargando base de datos Parquet (ultrarrápido)...")
def cargar_consolidado_parquet(base_name, mtime):
    # Intentar leer cada archivo si existe
    def leer_parquet(sufijo):
        path = f"{base_name}_{sufijo}.parquet"
        return pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame()

    df_despacho = leer_parquet("Despacho")
    df_demanda = leer_parquet("Demanda")
    df_inter = leer_parquet("Interconexiones")
    df_cal = leer_parquet("Calificacion")
    df_cmg = leer_parquet("CMg")
    
    if not df_inter.empty and 'ENLACE' not in df_inter.columns:
        df_inter['ENLACE'] = 'CENTRO-NORTE'

    return df_despacho, df_demanda, df_inter, df_cal, df_cmg

# ==========================================
# 4. INTERFAZ DE USUARIO (BARRA LATERAL)
# ==========================================
st.sidebar.header("⚙️ Parámetros del Dashboard SEIN")

# Buscar los prefijos de los archivos Parquet
archivos_parquet = glob.glob("*_Despacho.parquet")
prefijos_bases = [f.replace("_Despacho.parquet", "") for f in archivos_parquet]

df_raw, df_inter_raw, df_seg_raw, df_dem_raw, df_cmg_raw = [pd.DataFrame()] * 5

if not prefijos_bases:
    st.sidebar.error("❌ No se detectó ninguna base de datos Parquet.")
    st.sidebar.info("Ejecuta tu script de descarga para generar los archivos .parquet")
else:
    base_seleccionada = st.sidebar.selectbox("📂 Selecciona la Base de Datos Local:", prefijos_bases)
    
    archivo_principal = f"{base_seleccionada}_Despacho.parquet"
    mtime_consolidado = os.path.getmtime(archivo_principal) if os.path.exists(archivo_principal) else 0
    
    df_des_todo, df_dem_todo, df_int_todo, df_cal_todo, df_cmg_todo = cargar_consolidado_parquet(base_seleccionada, mtime_consolidado)
    
    if not df_des_todo.empty:
        fecha_min_db = df_des_todo['FECHA_HORA'].min().date()
        fecha_max_db = df_des_todo['FECHA_HORA'].max().date()
        
        rango_fechas = st.sidebar.date_input("🗓️ Recortar Rango de Fechas:", 
                                             value=(fecha_min_db, fecha_max_db), 
                                             min_value=fecha_min_db, 
                                             max_value=fecha_max_db)
        
        if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
            f_ini = pd.to_datetime(rango_fechas[0])
            f_fin = pd.to_datetime(rango_fechas[1]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
            
            st.session_state['df_despacho'] = df_des_todo[(df_des_todo['FECHA_HORA'] >= f_ini) & (df_des_todo['FECHA_HORA'] <= f_fin)].copy()
            st.session_state['df_demanda'] = df_dem_todo[(df_dem_todo['FECHA_HORA'] >= f_ini) & (df_dem_todo['FECHA_HORA'] <= f_fin)].copy() if not df_dem_todo.empty else pd.DataFrame()
            st.session_state['df_interconexiones'] = df_int_todo[(df_int_todo['FECHA_HORA'] >= f_ini) & (df_int_todo['FECHA_HORA'] <= f_fin)].copy() if not df_int_todo.empty else pd.DataFrame()
            st.session_state['df_seguridad'] = df_cal_todo[(df_cal_todo['INICIO'] >= f_ini) & (df_cal_todo['INICIO'] <= f_fin)].copy() if not df_cal_todo.empty else pd.DataFrame()
            st.session_state['df_cmg'] = df_cmg_todo[(df_cmg_todo['FECHA_HORA'] >= f_ini) & (df_cmg_todo['FECHA_HORA'] <= f_fin)].copy() if not df_cmg_todo.empty else pd.DataFrame()
            
# ==========================================
# 5. LÓGICA DE FILTRADO Y VISUALIZACIÓN
# ==========================================
if 'df_despacho' not in st.session_state or st.session_state['df_despacho'].empty:
    st.info("💡 Selecciona un archivo consolidado y un rango de fechas en el panel lateral para visualizar los datos.")
elif df_matriz_centrales.empty:
    st.error("❌ No se pudo cargar la matriz de centrales (CetralesSEIN.xlsx). Verifica que exista en la misma ruta.")
else:
    df_raw = st.session_state['df_despacho']
    df_inter_raw = st.session_state['df_interconexiones']
    df_seg_raw = st.session_state['df_seguridad']
    df_dem_raw = st.session_state['df_demanda']
    df_cmg_raw = st.session_state['df_cmg']

    # --- Filtros Dinámicos en Cascada (Barra Lateral) ---
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filtros Operativos")
    
    opts_zona = sorted([x for x in df_matriz_centrales['AREA_OPERATIVA'].unique() if x])
    filtro_zona = st.sidebar.multiselect("📍 Área Operativa:", options=opts_zona, placeholder="Todas")
    df_f1 = df_matriz_centrales[df_matriz_centrales['AREA_OPERATIVA'].isin(filtro_zona)] if filtro_zona else df_matriz_centrales

    opts_int = sorted([x for x in df_f1['TIPO_INTEGRANTE'].unique() if x])
    defecto_int = ["COES"] if "COES" in opts_int else []
    filtro_int = st.sidebar.multiselect("⚖️ Tipo Integrante:", options=opts_int, default=defecto_int, placeholder="Todos")
    df_f2 = df_f1[df_f1['TIPO_INTEGRANTE'].isin(filtro_int)] if filtro_int else df_f1
    
    opts_req = sorted([x for x in df_f2['REQUERIMIENTO_ESPECIAL'].unique() if x])
    filtro_req = st.sidebar.multiselect("⚠️ Req. Especial:", options=opts_req, placeholder="Todos")
    df_f3 = df_f2[df_f2['REQUERIMIENTO_ESPECIAL'].isin(filtro_req)] if filtro_req else df_f2

    opts_emp = sorted([x for x in df_f3['EMPRESA_DESPACHO'].unique() if x])
    filtro_empresa = st.sidebar.multiselect("🏢 Empresa:", options=opts_emp, placeholder="Todas")
    df_f4 = df_f3[df_f3['EMPRESA_DESPACHO'].isin(filtro_empresa)] if filtro_empresa else df_f3

    opts_tipo = sorted([x for x in df_f4['TIPO_GENERACION'].unique() if x])
    filtro_tipo = st.sidebar.multiselect("⚡ Tipo de Recurso:", options=opts_tipo, placeholder="Todas")
    df_f5 = df_f4[df_f4['TIPO_GENERACION'].isin(filtro_tipo)] if filtro_tipo else df_f4

    df_f5['CENTRAL'] = df_f5['CENTRAL'].astype(str).str.strip() 
    opts_cen = sorted([x for x in df_f5['CENTRAL'].unique() if x and str(x) != "nan"])
    filtro_cen = st.sidebar.multiselect("🏭 Central:", options=opts_cen, placeholder="Todas", key="filtro_central_unico")
    df_f_final = df_f5[df_f5['CENTRAL'].isin(filtro_cen)] if filtro_cen else df_f5
    
    # --- Emparejamiento con datos operativos ---
    def limpiar_nombre_central(nombre):
        n = str(nombre).upper().strip()
        # Excepción explícita para que no borre (CS) y haga match con el Excel maestro
        if "CARHUAQUERO" in n and ("(CS)" in n or " CS " in n or "CS)" in n):
            return "CS CARHUAQUERO"
        # Limpieza estándar para el resto
        return re.sub(r'\s*\([^)]*\)$', '', n).strip()

    df_f_final = df_f_final.copy()
    df_f_final['CENTRAL_NORMALIZADA'] = df_f_final['CENTRAL'].apply(limpiar_nombre_central)

    nombres_maestro = set(df_f_final['CENTRAL_NORMALIZADA'].astype(str).str.strip().str.upper())
    nombres_calificacion_activos = [str(n).strip().upper() for n in df_f_final['CENTRAL_CALIFICACION'].unique() if pd.notna(n) and str(n).strip().upper() not in ["", "N/A", "NAN"]]

    dict_zonas = dict(zip(df_f_final['CENTRAL_NORMALIZADA'].str.upper(), df_f_final['AREA_OPERATIVA']))
    dict_tipos = dict(zip(df_f_final['CENTRAL_NORMALIZADA'].str.upper(), df_f_final['TIPO_GENERACION']))
    dict_empresas = dict(zip(df_f_final['CENTRAL_NORMALIZADA'].str.upper(), df_f_final['EMPRESA_DESPACHO']))

    df_raw['CENTRAL_BASE'] = df_raw['CENTRAL'].apply(limpiar_nombre_central)

    # Filtro estricto
    df_datos = df_raw[df_raw['CENTRAL_BASE'].isin(nombres_maestro)].copy()


    
    if df_datos.empty:
        st.warning("⚠️ No hay datos despachados para las centrales filtradas en las fechas seleccionadas.")
    else:
        st.success("✅ Datos filtrados correctamente desde el archivo local.")
        
        df_datos['ZONA'] = df_datos['CENTRAL_BASE'].map(dict_zonas).fillna("N/A")
        df_datos['TIPO_CENTRAL'] = df_datos['CENTRAL_BASE'].map(dict_tipos).fillna("N/A")
        df_datos['EMPRESA'] = df_datos['CENTRAL_BASE'].map(dict_empresas).fillna("N/A")

        colores_tecnologia = {
            "EÓLICA": "#808080", "EOLICA": "#808080",
            "HIDROELÉCTRICA": "#00BFFF", "HIDROELECTRICA": "#00BFFF",
            "SOLAR": "#FFD700",
            "DIESEL/RESIDUAL": "#FF0000",
            "GAS DE LA SELVA": "#90EE90",
            "GAS CAMISEA": "#006400",
            "GAS NORTE": "#0bb613",
            "BIOMASA": "#800080"
        }
        
        df_datos['FECHA_DIA'] = df_datos['FECHA_HORA'].dt.date
        
        # Helper Area Chart
        def crear_grafica_area(df_grafico, col_color, titulo, color_map=None):
            df_plot = df_grafico.copy().dropna(subset=[col_color])
            df_plot['DESPACHO_MW'] = pd.to_numeric(df_plot['DESPACHO_MW'], errors='coerce').fillna(0)
            df_sistema = df_plot.groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()
            max_d = df_sistema['DESPACHO_MW'].max()
            lim = max_d * 1.12 if pd.notna(max_d) and max_d > 0 else 1000
            f_min, f_max = df_plot['FECHA_HORA'].min(), df_plot['FECHA_HORA'].max()

            fig = px.area(df_plot, x="FECHA_HORA", y="DESPACHO_MW", color=col_color, title=titulo, color_discrete_map=color_map, color_discrete_sequence=px.colors.qualitative.Alphabet, template="plotly_white")
            fig.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
            fig.add_scatter(x=df_sistema['FECHA_HORA'], y=df_sistema['DESPACHO_MW'], mode='lines', line=dict(width=0, color='rgba(0,0,0,0)'), name='<b>⚡ TOTAL</b>', showlegend=False)
            
            if not df_sistema.empty:
                max_r = df_sistema.loc[df_sistema['DESPACHO_MW'].idxmax()]
                min_r = df_sistema.loc[df_sistema['DESPACHO_MW'].idxmin()]
                fig.add_scatter(x=[max_r['FECHA_HORA']], y=[max_r['DESPACHO_MW']], mode='markers+text', marker=dict(color='black', size=12, symbol='triangle-up'), text=[f"<b>Máx: {max_r['DESPACHO_MW']:,.0f} MW</b>"], textposition="top center", textfont=dict(color="blue"), showlegend=False)
                fig.add_scatter(x=[min_r['FECHA_HORA']], y=[min_r['DESPACHO_MW']], mode='markers+text', marker=dict(color='black', size=12, symbol='triangle-down'), text=[f"<b>Mín: {min_r['DESPACHO_MW']:,.0f} MW</b>"], textposition="bottom center", textfont=dict(color="blue"), showlegend=False)    
            
            fig.update_layout(hovermode="x unified", xaxis=dict(tickformat="%d/%m\n%H:%M", title="Fecha Operativa", range=[f_min, f_max]), yaxis=dict(title="Potencia (MW)", range=[0, lim]), height=550)
            return fig

        energia_total_cen = df_datos.groupby('CENTRAL')['DESPACHO_MW'].sum()
        centrales_activas = energia_total_cen[energia_total_cen > 0].index
        df_plot_cen = df_datos[df_datos['CENTRAL'].isin(centrales_activas)].copy()
        df_plot_cen['CENTRAL'] = pd.Categorical(df_plot_cen['CENTRAL'], categories=energia_total_cen[centrales_activas].sort_values(ascending=False).index, ordered=True)
        df_plot_cen = df_plot_cen.sort_values(['FECHA_HORA', 'CENTRAL'])

        # ==========================================
        # 1. DESPACHO POR TIPO DE GENERACIÓN
        # ==========================================
        st.markdown("---")
        st.header("1. 🏭 Despacho por Tipo de Generación (SEIN)")
        df_tipo = df_datos.groupby(['FECHA_HORA', 'TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
        orden = ["BIOMASA", "SOLAR", "EÓLICA", "EOLICA", "HIDROELÉCTRICA", "HIDROELECTRICA", "GAS NORTE", "GAS DE LA SELVA", "GAS CAMISEA", "DIESEL/RESIDUAL"]
        df_tipo['TIPO_CENTRAL'] = pd.Categorical(df_tipo['TIPO_CENTRAL'], categories=orden, ordered=True)
        df_tipo = df_tipo.sort_values(['FECHA_HORA', 'TIPO_CENTRAL'])
        fig_tipo = crear_grafica_area(df_tipo, 'TIPO_CENTRAL', "Curva Apilada por Tecnología", color_map=colores_tecnologia)
        st.plotly_chart(fig_tipo, use_container_width=True)

        with st.expander("Ver Datos de Despacho por Tecnología (Vista Matricial)"):
            df_tipo_pivot = df_tipo.copy()
            df_tipo_pivot['FECHA'] = df_tipo_pivot['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_tipo_pivot['HORA'] = df_tipo_pivot['FECHA_HORA'].dt.strftime('%H:%M')
            df_mat_tipo = df_tipo_pivot.pivot_table(index=['FECHA', 'HORA'], columns='TIPO_CENTRAL', values='DESPACHO_MW', aggfunc='sum').round(2).fillna(0)
            st.dataframe(df_mat_tipo, use_container_width=True)

        # ==========================================
        # 2. COSTOS MARGINALES (CMg) EN BARRAS DE REFERENCIA
        # ==========================================
        st.markdown("---")
        st.header("2. 💸 Despacho Operativo vs Costo Marginal (CMg)")
        st.info("Despacho por tecnología y flujos (Eje Izquierdo - MW) junto al Costo Marginal de la barra de referencia de Trujillo (Eje Derecho - S/./MWh). Curves de líneas resaltadas en negrita.")
        
        if df_cmg_raw.empty:
            st.info("No se encontraron datos de Costos Marginales en el archivo local.")
        else:
            df_cmg_plot = df_cmg_raw.sort_values(['FECHA_HORA', 'BARRA']).copy()
            df_cmg_plot = df_cmg_plot[df_cmg_plot['BARRA'] == 'TRUJILLO 220']
            
            df_cn_total = pd.DataFrame()
            df_l5006_total = pd.DataFrame()
            
            if not df_inter_raw.empty:
                df_cn = df_inter_raw[df_inter_raw['ENLACE'] == 'CENTRO-NORTE'].copy()
                if not df_cn.empty:
                    df_cn_total = df_cn.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
                    df_cn_total['FLUJO_NEG'] = df_cn_total['FLUJO_MW'] * -1
                
                df_l5006 = df_inter_raw[df_inter_raw['LINEA_TRANSMISION'].str.contains('L-5006', case=False, na=False)].copy()
                if not df_l5006.empty:
                    df_l5006_total = df_l5006.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
                    df_l5006_total['FLUJO_NEG'] = df_l5006_total['FLUJO_MW'] * -1
            
            colores_barra = {'TRUJILLO 220': "#0099FF"}
            fig_cmg = make_subplots(specs=[[{"secondary_y": True}]])
            
            df_tipo_cmg = df_datos.groupby(['FECHA_HORA', 'TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
            
            for tec in orden:
                df_tec = df_tipo_cmg[df_tipo_cmg['TIPO_CENTRAL'] == tec]
                if not df_tec.empty:
                    fig_cmg.add_trace(
                        go.Scatter(x=df_tec['FECHA_HORA'], y=df_tec['DESPACHO_MW'], mode='lines', line=dict(width=0), fill='tonexty', stackgroup='one', name=tec, marker_color=colores_tecnologia.get(tec, '#808080'), hovertemplate=f"<b>{tec}</b>: %{{y:,.2f}} MW"),
                        secondary_y=False
                    )
                    
            if not df_cn_total.empty:
                fig_cmg.add_trace(go.Scatter(x=df_cn_total['FECHA_HORA'], y=df_cn_total['FLUJO_NEG'], mode='lines', line=dict(width=3, dash='dash', color='#9467bd'), name='⚡ FLUJO CENTRO-NORTE', hovertemplate="<b>FLUJO CENTRO-NORTE</b>: %{y:,.2f} MW"), secondary_y=False)
                max_cn, min_cn = df_cn_total.loc[df_cn_total['FLUJO_NEG'].idxmax()], df_cn_total.loc[df_cn_total['FLUJO_NEG'].idxmin()]
                fig_cmg.add_trace(go.Scatter(x=[max_cn['FECHA_HORA']], y=[max_cn['FLUJO_NEG']], mode='markers+text', marker=dict(color='#9467bd', size=12, symbol='triangle-up'), text=[f"<b>Máx C-N: {max_cn['FLUJO_NEG']:,.0f} MW</b>"], textposition="top center", textfont=dict(color="blue"), showlegend=False, hoverinfo='skip'), secondary_y=False)
                
            if not df_l5006_total.empty:
                fig_cmg.add_trace(go.Scatter(x=df_l5006_total['FECHA_HORA'], y=df_l5006_total['FLUJO_NEG'], mode='lines', line=dict(width=3, dash='dot', color='#e377c2'), name='⚡ FLUJO L-5006', hovertemplate="<b>FLUJO L-5006</b>: %{y:,.2f} MW"), secondary_y=False)
                max_l, min_l = df_l5006_total.loc[df_l5006_total['FLUJO_NEG'].idxmax()], df_l5006_total.loc[df_l5006_total['FLUJO_NEG'].idxmin()]
                fig_cmg.add_trace(go.Scatter(x=[max_l['FECHA_HORA']], y=[max_l['FLUJO_NEG']], mode='markers+text', marker=dict(color='#e377c2', size=12, symbol='triangle-up'), text=[f"<b>Máx L-5006: {max_l['FLUJO_NEG']:,.0f} MW</b>"], textposition="top center", textfont=dict(color="blue"), showlegend=False, hoverinfo='skip'), secondary_y=False)

            def graficar_min_max_cmg_dual(fig, df_filtro, color_marcador, nombre_barra):
                if not df_filtro.empty:
                    idx_max, idx_min = df_filtro['CMG_USD'].idxmax(), df_filtro['CMG_USD'].idxmin()
                    fig.add_trace(go.Scatter(x=[df_filtro.loc[idx_max, 'FECHA_HORA']], y=[df_filtro.loc[idx_max, 'CMG_USD']], mode='markers+text', marker=dict(color=color_marcador, size=12, symbol='triangle-up'), text=[f"<b>Máx: {df_filtro.loc[idx_max, 'CMG_USD']:,.1f} S/./MWh</b>"], textposition="top center", textfont=dict(color="blue"), showlegend=False, hoverinfo='skip'), secondary_y=True)

            if not df_cmg_plot.empty:
                for barra in df_cmg_plot['BARRA'].unique():
                    df_barra = df_cmg_plot[df_cmg_plot['BARRA'] == barra]
                    fig_cmg.add_trace(go.Scatter(x=df_barra['FECHA_HORA'], y=df_barra['CMG_USD'], mode='lines', line=dict(width=3, dash='dot', color=colores_barra.get(barra, '#0099FF')), name=barra, hovertemplate=f"<b>{barra}</b>: %{{y:,.2f}} S/./MWh"), secondary_y=True)
                    graficar_min_max_cmg_dual(fig_cmg, df_barra, colores_barra.get(barra, '#0099FF'), barra)
            
            if not df_cmg_plot.empty:
                fecha_min_cmg, fecha_max_cmg = df_cmg_plot['FECHA_HORA'].min(), df_cmg_plot['FECHA_HORA'].max()
                fig_cmg.add_shape(type="line", x0=fecha_min_cmg, y0=700, x1=fecha_max_cmg, y1=700, line=dict(color="red", width=2, dash="dash"), yref="y")
                fig_cmg.add_annotation(x=fecha_max_cmg, y=700, text="<b>Límite Sup L-5006: 700 MW</b>", showarrow=False, xanchor="right", yanchor="bottom", yref="y", font=dict(color="blue"))
                fig_cmg.add_shape(type="line", x0=fecha_min_cmg, y0=600, x1=fecha_max_cmg, y1=600, line=dict(color="green", width=2, dash="dash"), yref="y")
                fig_cmg.add_annotation(x=fecha_max_cmg, y=600, text="<b>Límite Inf L-5006: 600 MW</b>", showarrow=False, xanchor="right", yanchor="bottom", yref="y", font=dict(color="blue"))

            if not df_tipo_cmg.empty:
                max_gen_total = df_tipo_cmg.groupby('FECHA_HORA')['DESPACHO_MW'].sum().max()
                max_flujo_neg = max(df_cn_total['FLUJO_NEG'].max() if not df_cn_total.empty else 0, df_l5006_total['FLUJO_NEG'].max() if not df_l5006_total.empty else 0)
                limite_y1 = max(max_gen_total, max_flujo_neg) + 400
            else:
                limite_y1 = 1400
            
            limite_y2 = (df_cmg_plot['CMG_USD'].max() * 1.15) if not df_cmg_plot.empty and df_cmg_plot['CMG_USD'].max() > 0 else 50
            
            fig_cmg.update_layout(hovermode="x unified", height=650, margin=dict(t=50, b=50, l=50, r=150), legend=dict(title="<b>Componentes SEIN</b>", orientation="v", yanchor="top", y=1, xanchor="left", x=1.05), template="plotly_white")
            fig_cmg.update_xaxes(title_text="Fecha Operativa", tickformat="%d/%m\n%H:%M")
            fig_cmg.update_yaxes(title_text="Potencia Activa (MW)", range=[0, limite_y1], secondary_y=False)
            fig_cmg.update_yaxes(title_text="Costo Marginal (S/./MWh)", range=[0, limite_y2], secondary_y=True, showgrid=False)
            
            st.plotly_chart(fig_cmg, use_container_width=True)
            
            with st.expander("Ver Datos de CMg (Vista Matricial)"):
                if not df_cmg_plot.empty:
                    df_cmg_pivot = df_cmg_plot.copy()
                    df_cmg_pivot['FECHA'] = df_cmg_pivot['FECHA_HORA'].dt.strftime('%d/%m/%Y')
                    df_cmg_pivot['HORA'] = df_cmg_pivot['FECHA_HORA'].dt.strftime('%H:%M')
                    st.dataframe(df_cmg_pivot.pivot_table(index=['FECHA', 'HORA'], columns=['BARRA'], values='CMG_USD', aggfunc='mean').round(2), use_container_width=True)

        # ==========================================
        # 3. FLUJO DE ENLACES
        # ==========================================
        st.markdown("---")
        st.header("3. 🔌 Flujo de Enlaces")
        if df_inter_raw.empty:
            st.info("No se detectaron datos de enlaces.")
        else:
            df_inter_plot = df_inter_raw.sort_values(['FECHA_HORA', 'LINEA_TRANSMISION']).copy()
            
            def marcar_min_max_flujo(fig, df_total, color_marcador):
                if not df_total.empty:
                    max_val, min_val = df_total.loc[df_total['FLUJO_MW'].abs().idxmax(), 'FLUJO_MW'], df_total.loc[df_total['FLUJO_MW'].abs().idxmin(), 'FLUJO_MW']
                    fig.add_hline(y=max_val, line_dash="dash", line_color=color_marcador, line_width=2, annotation_text=f"<b>Máx: {max_val:,.0f} MW</b>", annotation_position="top left", annotation_font=dict(color="blue"))
                    fig.add_hline(y=min_val, line_dash="dash", line_color=color_marcador, line_width=2, annotation_text=f"<b>Mín: {min_val:,.0f} MW</b>", annotation_position="bottom left", annotation_font=dict(color="blue"))
            
            df_cn = df_inter_plot[df_inter_plot['ENLACE'] == 'CENTRO-NORTE'].copy()
            if not df_cn.empty:
                fig_inter_cn = px.area(df_cn, x="FECHA_HORA", y="FLUJO_MW", color="LINEA_TRANSMISION", title="Flujo Centro-Norte (MW)", color_discrete_sequence=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'], template="plotly_white")
                df_cn_total = df_cn.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
                fig_inter_cn.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
                fig_inter_cn.add_scatter(x=df_cn_total['FECHA_HORA'], y=df_cn_total['FLUJO_MW'], mode='lines', line=dict(width=3, color='gray', dash='solid'), name='<b>⚡ TOTAL C-N</b>')
                marcar_min_max_flujo(fig_inter_cn, df_cn_total, 'black')
                fig_inter_cn.update_layout(hovermode="x unified", height=450)
                st.plotly_chart(fig_inter_cn, use_container_width=True)

            df_cs = df_inter_plot[df_inter_plot['ENLACE'] == 'CENTRO-SUR'].copy()
            if not df_cs.empty:
                fig_inter_cs = px.area(df_cs, x="FECHA_HORA", y="FLUJO_MW", color="LINEA_TRANSMISION", title="Flujo Centro-Sur (MW)", color_discrete_sequence=['#8c564b', '#e377c2', '#7f7f7f', '#bcbd22'], template="plotly_white")
                df_cs_total = df_cs.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
                fig_inter_cs.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
                fig_inter_cs.add_scatter(x=df_cs_total['FECHA_HORA'], y=df_cs_total['FLUJO_MW'], mode='lines', line=dict(width=3, color='gray', dash='solid'), name='<b>⚡ TOTAL C-S</b>')
                marcar_min_max_flujo(fig_inter_cs, df_cs_total, 'black')
                fig_inter_cs.update_layout(hovermode="x unified", height=450)
                st.plotly_chart(fig_inter_cs, use_container_width=True)

        # ==========================================
        # 4. GENERACIÓN SEIN (SIN DEMANDA)
        # ==========================================
        st.markdown("---")
        st.header("4. 📊 Generación del SEIN por Central")
        
        df_plot_cen_aux = df_plot_cen.copy().dropna(subset=['CENTRAL'])
        df_plot_cen_aux['DESPACHO_MW'] = pd.to_numeric(df_plot_cen_aux['DESPACHO_MW'], errors='coerce').fillna(0)
        
        # --- LÓGICA: AGREGAR ABREVIATURAS AL NOMBRE DE LA CENTRAL ---
        def obtener_abreviatura(tipo):
            t = str(tipo).upper()
            if "BIOMASA" in t: return "BIO"
            elif "GAS" in t: return "GAS"
            elif "DIESEL" in t or "RESIDUAL" in t: return "DIE"
            elif "HIDRO" in t: return "HID"
            elif "SOLAR" in t: return "SOL"
            elif "EOL" in t or "EÓL" in t: return "EOL"
            else: return t[:3]
            
        # Reconstruimos el nombre sumando la abreviatura
        df_plot_cen_aux['CENTRAL'] = df_plot_cen_aux.apply(
            lambda r: f"{r['CENTRAL_BASE']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})", axis=1
        )
        
        # --- SOLUCIÓN A LAS CRESTAS: Agrupar por Fecha y Nombre final para sumar duplicados ---
        df_plot_cen_aux = df_plot_cen_aux.groupby(['FECHA_HORA', 'CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
        
        # Restablecer el orden categórico correcto para la leyenda (de mayor a menor despacho)
        energia_orden_aux = df_plot_cen_aux.groupby('CENTRAL')['DESPACHO_MW'].sum().sort_values(ascending=False).index
        df_plot_cen_aux['CENTRAL'] = pd.Categorical(df_plot_cen_aux['CENTRAL'], categories=energia_orden_aux, ordered=True)
        
        # Ordenar cronológicamente y por categoría para que Plotly dibuje líneas limpias
        df_plot_cen_aux = df_plot_cen_aux.sort_values(['FECHA_HORA', 'CENTRAL'])
        # -------------------------------------------------------------------
        
        df_sistema_aux = df_plot_cen_aux.groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()
        max_demanda_real_aux = df_sistema_aux['DESPACHO_MW'].max()
        
        limite_superior_y_aux = max_demanda_real_aux * 1.05 if pd.notna(max_demanda_real_aux) and max_demanda_real_aux > 0 else 1000
        fecha_min_aux, fecha_max_aux = df_plot_cen_aux['FECHA_HORA'].min(), df_plot_cen_aux['FECHA_HORA'].max()

        fig_cen = px.area(
            df_plot_cen_aux, x="FECHA_HORA", y="DESPACHO_MW", color='CENTRAL', 
            title="Despacho de Potencia por Unidad - SEIN (MW)", labels={'CENTRAL': "Central"}, 
            color_discrete_sequence=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'],
            template="plotly_white"
        )
        
        fig_cen.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=0))
        fig_cen.add_scatter(
            x=df_sistema_aux['FECHA_HORA'], y=df_sistema_aux['DESPACHO_MW'], mode='lines',
            line=dict(width=0, color='rgba(0,0,0,0)'), name='<b>⚡ TOTAL GENERACIÓN</b>',
            hovertemplate='<b>🗓️ %{x|%d/%m/%Y %H:%M} ➡️ %{y:,.2f} MW</b>', showlegend=False
        )
        
        fig_cen.update_layout(
            hovermode="x unified",
            xaxis=dict(tickformat="%d/%m\n%H:%M", title="Fecha Operativa", range=[fecha_min_aux, fecha_max_aux]),
            yaxis=dict(title="Potencia Activa (MW)", range=[0, limite_superior_y_aux]),
            height=550, margin=dict(t=50, b=50, l=50, r=20) 
        )
        st.plotly_chart(fig_cen, use_container_width=True)

        # --- Trazabilidad y Descarga de Datos ---
        with st.expander("Ver Datos de Generación por Central (Vista Matricial)"):
            # Preparamos los datos pivoteados
            df_cen_pivot = df_plot_cen_aux.copy()
            df_cen_pivot['FECHA'] = df_cen_pivot['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_cen_pivot['HORA'] = df_cen_pivot['FECHA_HORA'].dt.strftime('%H:%M')

            # Creamos la matriz (Fechas/Horas en filas, Centrales en columnas)
            df_mat_cen = df_cen_pivot.pivot_table(
                index=['FECHA', 'HORA'],
                columns='CENTRAL',
                values='DESPACHO_MW',
                aggfunc='sum'
            ).round(2).fillna(0)

            st.markdown("**Matriz: Despacho de Potencia por Unidad (MW)**")
            st.dataframe(df_mat_cen, use_container_width=True)

            # Generamos el archivo Excel en memoria
            buffer_cen = io.BytesIO()
            with pd.ExcelWriter(buffer_cen, engine='openpyxl') as writer:
                df_mat_cen.to_excel(writer, sheet_name='Generacion_Central')

            # Botón de descarga con key única para evitar conflictos
            st.download_button(
                label="📥 Descargar Datos de Generación (Excel)",
                data=buffer_cen.getvalue(),
                file_name=f"Generacion_Central_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_descarga_generacion_cen"
            )

        # ==========================================
        # 5. POTENCIA PROMEDIO DIARIA
        # ==========================================
        st.markdown("---")
        st.header("5. 📈 Potencia Promedio Diaria (SEIN)")
        
        # --- Control de visualización (Agrupado vs Apilado) ---
        modo_visualizacion = st.radio(
            "Modo de visualización de barras:", 
            options=["Agrupado", "Apilado"], 
            horizontal=True,
            key="radio_barmode_promedio"
        )
        modo_barras = 'group' if modo_visualizacion == "Agrupado" else 'stack'
        
        # --- AÑADIR ABREVIATURAS AL NOMBRE DE LA CENTRAL ---
        def obtener_abreviatura(tipo):
            t = str(tipo).upper()
            if "BIOMASA" in t: return "BIO"
            elif "GAS" in t: return "GAS"
            elif "DIESEL" in t or "RESIDUAL" in t: return "DIE"
            elif "HIDRO" in t: return "HID"
            elif "SOLAR" in t: return "SOL"
            elif "EOL" in t or "EÓL" in t: return "EOL"
            else: return t[:3]
            
        df_prom_plot = df_plot_cen.copy()
        # Verificamos si ya tiene paréntesis para no duplicarlos
        df_prom_plot['CENTRAL'] = df_prom_plot.apply(
            lambda r: f"{r['CENTRAL']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})" if "(" not in r['CENTRAL'] else r['CENTRAL'], 
            axis=1
        )
        
        # CORRECCIÓN DE EFECTO DE BORDE: Asignar las 00:00 al día operativo correcto restando 1 minuto
        df_prom_plot['FECHA_DIA_OPERATIVO'] = (df_prom_plot['FECHA_HORA'] - pd.Timedelta(minutes=1)).dt.date
        
        # ==========================================
        # Gráfica 5.1: Promedio de todo el día (24 Horas / 48 Periodos)
        # ==========================================
        df_promedio = df_prom_plot.groupby(['FECHA_DIA_OPERATIVO', 'CENTRAL'], as_index=False)['DESPACHO_MW'].mean()
        df_promedio['FECHA_DIA_OPERATIVO'] = pd.to_datetime(df_promedio['FECHA_DIA_OPERATIVO']).dt.strftime('%d/%m/%Y')
        
        # --- ORDENAR DE MAYOR A MENOR ---
        orden_centrales_prom = df_promedio.groupby('CENTRAL')['DESPACHO_MW'].mean().sort_values(ascending=False).index
        df_promedio['CENTRAL'] = pd.Categorical(df_promedio['CENTRAL'], categories=orden_centrales_prom, ordered=True)
        df_promedio = df_promedio.sort_values(['FECHA_DIA_OPERATIVO', 'CENTRAL'])
        
        fig_prom = px.bar(
            df_promedio, x='FECHA_DIA_OPERATIVO', y='DESPACHO_MW', color='CENTRAL',
            title="Potencia Promedio Diaria Total (24 Horas) (MW)",
            barmode=modo_barras, 
            labels={'FECHA_DIA_OPERATIVO': 'Día Operativo', 'DESPACHO_MW': 'Potencia Promedio (MW)'},
            color_discrete_sequence=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'],
            template="plotly_white"
        )
        fig_prom.update_layout(xaxis=dict(type='category'), height=500)
        st.plotly_chart(fig_prom, use_container_width=True)

        # ==========================================
        # Gráfica 5.2: Promedio Operativo (Solo en periodos con inyección > 0 MW)
        # ==========================================
        df_solo_inyeccion = df_prom_plot[df_prom_plot['DESPACHO_MW'] > 0].copy()
        
        if not df_solo_inyeccion.empty:
            df_promedio_iny = df_solo_inyeccion.groupby(['FECHA_DIA_OPERATIVO', 'CENTRAL'], as_index=False)['DESPACHO_MW'].mean()
            df_promedio_iny['FECHA_DIA_OPERATIVO'] = pd.to_datetime(df_promedio_iny['FECHA_DIA_OPERATIVO']).dt.strftime('%d/%m/%Y')
            
            # --- ORDENAR DE MAYOR A MENOR ---
            orden_centrales_iny = df_promedio_iny.groupby('CENTRAL')['DESPACHO_MW'].mean().sort_values(ascending=False).index
            df_promedio_iny['CENTRAL'] = pd.Categorical(df_promedio_iny['CENTRAL'], categories=orden_centrales_iny, ordered=True)
            df_promedio_iny = df_promedio_iny.sort_values(['FECHA_DIA_OPERATIVO', 'CENTRAL'])
            
            fig_prom_iny = px.bar(
                df_promedio_iny, x='FECHA_DIA_OPERATIVO', y='DESPACHO_MW', color='CENTRAL',
                title="Potencia Promedio en Operación (MW)",
                barmode=modo_barras, 
                labels={'FECHA_DIA_OPERATIVO': 'Día Operativo', 'DESPACHO_MW': 'Promedio en Operación (MW)'},
                color_discrete_sequence=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'],
                template="plotly_white"
            )
            fig_prom_iny.update_layout(xaxis=dict(type='category'), height=500)
            st.plotly_chart(fig_prom_iny, use_container_width=True)
        else:
            st.info("No se registraron periodos con inyección de potencia mayor a 0 MW para calcular el promedio operativo.")

        # --- Trazabilidad y Descarga de Datos ---
        with st.expander("Ver Datos de Potencia Promedio (Vista Matricial)"):
            df_mat_prom = df_promedio.pivot_table(
                index='FECHA_DIA_OPERATIVO', 
                columns='CENTRAL', 
                values='DESPACHO_MW', 
                aggfunc='mean'
            ).round(2).fillna(0)
            
            st.markdown("**Matriz: Promedio Total (24 Horas) - MW**")
            st.dataframe(df_mat_prom, use_container_width=True)
            
            buffer_prom = io.BytesIO()
            with pd.ExcelWriter(buffer_prom, engine='openpyxl') as writer:
                df_mat_prom.to_excel(writer, sheet_name='Promedio_24H')
                
                if not df_solo_inyeccion.empty:
                    df_mat_prom_iny = df_promedio_iny.pivot_table(
                        index='FECHA_DIA_OPERATIVO', 
                        columns='CENTRAL', 
                        values='DESPACHO_MW', 
                        aggfunc='mean'
                    ).round(2).fillna(0)
                    df_mat_prom_iny.to_excel(writer, sheet_name='Promedio_Operativo')
            
            st.download_button(
                label="📥 Descargar Datos de Promedios (Excel)",
                data=buffer_prom.getvalue(),
                file_name=f"Potencia_Promedio_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_descarga_promedios"
            )

        # ==========================================
        # 6. CONTROL DE TIEMPOS: INACTIVIDAD Y OPERACIÓN
        # ==========================================
        st.markdown("---")
        st.header("6. ⏱️ Control de Tiempos: Inactividad y Operación (SEIN)")
        
        df_gantt = df_datos.copy()
        
        # --- LÓGICA: AGREGAR ABREVIATURAS Y AGRUPAR ---
        def obtener_abreviatura(tipo):
            t = str(tipo).upper()
            if "BIOMASA" in t: return "BIO"
            elif "GAS" in t: return "GAS"
            elif "DIESEL" in t or "RESIDUAL" in t: return "DIE"
            elif "HIDRO" in t: return "HID"
            elif "SOLAR" in t: return "SOL"
            elif "EOL" in t or "EÓL" in t: return "EOL"
            else: return t[:3]
            
        df_gantt['CENTRAL'] = df_gantt.apply(
            lambda r: f"{r['CENTRAL_BASE']} ({obtener_abreviatura(r['TIPO_CENTRAL'])})", axis=1
        )
        
        # Agrupar para consolidar unidades y evitar conteos duplicados de horas (crestas temporales)
        df_gantt = df_gantt.groupby(['FECHA_HORA', 'CENTRAL', 'TIPO_CENTRAL'], as_index=False)['DESPACHO_MW'].sum()
        df_gantt = df_gantt.sort_values(['CENTRAL', 'FECHA_HORA'])
        
        # Asignación de estados
        df_gantt['ESTADO'] = np.where(df_gantt['DESPACHO_MW'] > 0, 'OPERANDO', 'INACTIVO')
        df_gantt['CAMBIO_ESTADO'] = (df_gantt['ESTADO'] != df_gantt['ESTADO'].shift(1)) | (df_gantt['CENTRAL'] != df_gantt['CENTRAL'].shift(1))
        df_gantt['BLOQUE'] = df_gantt['CAMBIO_ESTADO'].cumsum()
        
        df_bloques = df_gantt.groupby(['CENTRAL', 'TIPO_CENTRAL', 'ESTADO', 'BLOQUE'], as_index=False).agg(
            INICIO=('FECHA_HORA', 'min'),
            FIN=('FECHA_HORA', 'max')
        )
        df_bloques['FIN'] = df_bloques['FIN'] + pd.Timedelta(minutes=30)
        
        fecha_inicio_gantt = df_datos['FECHA_HORA'].min()
        fecha_fin_gantt = df_datos['FECHA_HORA'].max() + pd.Timedelta(minutes=30)
        
        # --- GANTT 1: INACTIVIDAD (EXCLUYENDO DIÉSEL) ---
        st.markdown("#### 🚥 Cronograma de Inactividad (Tecnologías Base y Renovables)")
        st.info("Visualización de los bloques horarios donde las unidades NO inyectaron potencia (0 MW), excluyendo intencionalmente a las térmicas Diésel/Residual.")
        
        df_bloques_inactivos = df_bloques[(df_bloques['ESTADO'] == 'INACTIVO') & (df_bloques['TIPO_CENTRAL'] != 'DIESEL/RESIDUAL')].copy()
        
        if df_bloques_inactivos.empty:
            st.success("✅ No se detectaron periodos de inactividad para las unidades base/renovables seleccionadas.")
        else:
            fig_gantt_inact = px.timeline(
                df_bloques_inactivos, 
                x_start="INICIO", 
                x_end="FIN", 
                y="CENTRAL", 
                color="TIPO_CENTRAL",
                hover_data={"INICIO": "|%d/%m/%Y %H:%M", "FIN": "|%d/%m/%Y %H:%M"},
                color_discrete_map=colores_tecnologia,
                template="plotly_white"
            )
            
            fig_gantt_inact.update_yaxes(autorange="reversed")
            fig_gantt_inact.update_layout(
                xaxis=dict(tickformat="%d/%m\n%H:%M", title="Línea de Tiempo (Periodos Inactivos)", range=[fecha_inicio_gantt, fecha_fin_gantt]),
                yaxis=dict(title="Unidad Generadora", dtick=1),
                height=max(400, len(df_bloques_inactivos['CENTRAL'].unique()) * 22),
                margin=dict(t=30, b=50, l=50, r=20),
                legend=dict(title="Tecnología", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_gantt_inact, use_container_width=True)

        # --- RESUMEN ACUMULADO (BARRAS INACTIVIDAD) ---
        st.markdown("#### 📊 Resumen Acumulado de Horas por Unidad")
        
        # Usamos df_gantt en lugar de df_datos para arrastrar las abreviaturas y agrupaciones correctas
        df_tiempos = df_gantt.copy() 
        df_tiempos['INACTIVO_HR'] = (df_tiempos['DESPACHO_MW'] == 0) * 0.5
        df_tiempos['ACTIVO_HR'] = (df_tiempos['DESPACHO_MW'] > 0) * 0.5
        df_resumen_tiempos = df_tiempos.groupby(['CENTRAL', 'TIPO_CENTRAL'], as_index=False)[['INACTIVO_HR', 'ACTIVO_HR']].sum()
        
        tipos_inactividad = ['HIDROELÉCTRICA', 'HIDROELECTRICA', 'EÓLICA', 'EOLICA', 'SOLAR', 'BIOMASA', 'GAS DE LA SELVA', 'GAS CAMISEA', 'GAS NORTE']
        df_inactividad = df_resumen_tiempos[df_resumen_tiempos['TIPO_CENTRAL'].isin(tipos_inactividad)].copy()
        
        if not df_inactividad.empty:
            fig_inactividad = px.bar(
                df_inactividad, x='CENTRAL', y='INACTIVO_HR', color='TIPO_CENTRAL',
                title="Horas No Despachadas (Inactividad) por Central (Excluye Diésel)",
                labels={'CENTRAL': 'Central Generadora', 'INACTIVO_HR': 'Horas Inactivas (h)', 'TIPO_CENTRAL': 'Tipo'},
                color_discrete_map=colores_tecnologia,
                template="plotly_white"
            )
            fig_inactividad.update_layout(xaxis={'categoryorder':'total descending'}, height=450)
            st.plotly_chart(fig_inactividad, use_container_width=True)
        else:
            st.info("No hay datos de las tecnologías seleccionadas para inactividad.")

        # --- GANTT 2: ACTIVIDAD DIESEL/RESIDUAL ---
        st.markdown("---")
        st.markdown("#### 🚨 Cronograma de Operación (Diésel / Residual)")
        st.info("Visualización de los bloques donde las centrales Diesel/Residual inyectaron energía a la red.")
        
        df_bloques_diesel = df_bloques[(df_bloques['ESTADO'] == 'OPERANDO') & (df_bloques['TIPO_CENTRAL'] == 'DIESEL/RESIDUAL')].copy()
        
        if df_bloques_diesel.empty:
            st.success("✅ Las unidades Diésel/Residual seleccionadas no registraron inyección de energía en el periodo evaluado.")
        else:
            fig_gantt_diesel = px.timeline(
                df_bloques_diesel, 
                x_start="INICIO", 
                x_end="FIN", 
                y="CENTRAL", 
                color="TIPO_CENTRAL",
                hover_data={"INICIO": "|%d/%m/%Y %H:%M", "FIN": "|%d/%m/%Y %H:%M"},
                color_discrete_map=colores_tecnologia,
                template="plotly_white"
            )
            
            fig_gantt_diesel.update_yaxes(autorange="reversed")
            fig_gantt_diesel.update_layout(
                xaxis=dict(tickformat="%d/%m\n%H:%M", title="Línea de Tiempo (Periodos de Inyección)", range=[fecha_inicio_gantt, fecha_fin_gantt]),
                yaxis=dict(title="Unidad Diésel/Residual", dtick=1),
                height=max(300, len(df_bloques_diesel['CENTRAL'].unique()) * 22),
                margin=dict(t=30, b=50, l=50, r=20),
                showlegend=False 
            )
            st.plotly_chart(fig_gantt_diesel, use_container_width=True)

        # --- RESUMEN ACUMULADO (BARRAS ACTIVIDAD DIESEL) ---
        tipos_actividad = ['DIESEL/RESIDUAL']
        df_actividad = df_resumen_tiempos[df_resumen_tiempos['TIPO_CENTRAL'].isin(tipos_actividad)].copy()
        df_actividad_plot = pd.DataFrame() 
        
        if not df_actividad.empty:
            df_actividad_plot = df_actividad[df_actividad['ACTIVO_HR'] > 0]
            if not df_actividad_plot.empty:
                fig_actividad = px.bar(
                    df_actividad_plot, x='CENTRAL', y='ACTIVO_HR', color='TIPO_CENTRAL',
                    title="Horas Totales de Operación Activa (Centrales Diésel/Residual)",
                    labels={'CENTRAL': 'Central Generadora', 'ACTIVO_HR': 'Horas de Operación (h)', 'TIPO_CENTRAL': 'Tipo'},
                    color_discrete_map=colores_tecnologia,
                    template="plotly_white"
                )
                fig_actividad.update_layout(xaxis={'categoryorder':'total descending'}, height=400)
                st.plotly_chart(fig_actividad, use_container_width=True)
            else:
                st.info("No se registraron horas acumuladas de operación Diésel/Residual en la selección actual.")
        else:
            st.info("No hay centrales Diésel/Residual presentes en la selección actual.")

        with st.expander("Ver Datos de Tiempos Acumulados (Vista Matricial)"):
            st.markdown("**Matriz: Horas de Inactividad (Base y Renovables)**")
            if not df_inactividad.empty:
                df_mat_inact = df_inactividad[['CENTRAL', 'TIPO_CENTRAL', 'INACTIVO_HR']].copy()
                df_mat_inact.rename(columns={'INACTIVO_HR': 'HORAS_INACTIVAS'}, inplace=True)
                st.dataframe(df_mat_inact, use_container_width=True)
            else:
                st.info("No hay datos para mostrar en inactividad.")

            st.markdown("**Matriz: Horas de Operación (Diésel/Residual)**")
            if not df_actividad_plot.empty:
                df_mat_act = df_actividad_plot[['CENTRAL', 'TIPO_CENTRAL', 'ACTIVO_HR']].copy()
                df_mat_act.rename(columns={'ACTIVO_HR': 'HORAS_OPERACION'}, inplace=True)
                st.dataframe(df_mat_act, use_container_width=True)
            else:
                st.info("No hay datos para mostrar en operación Diésel/Residual.")

            if not df_inactividad.empty or not df_actividad_plot.empty:
                buffer_tiempos = io.BytesIO()
                with pd.ExcelWriter(buffer_tiempos, engine='openpyxl') as writer:
                    if not df_inactividad.empty:
                        df_mat_inact.to_excel(writer, sheet_name='Horas_Inactivas', index=False)
                    if not df_actividad_plot.empty:
                        df_mat_act.to_excel(writer, sheet_name='Horas_Operacion_Diesel', index=False)
                
                st.download_button(
                    label="📥 Descargar Datos de Tiempos Acumulados (Excel)",
                    data=buffer_tiempos.getvalue(),
                    file_name=f"Tiempos_Acumulados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_descarga_tiempos"
                )

        # ==========================================
        # 7. CALIFICACIÓN DE LA OPERACIÓN 
        # ==========================================
        st.markdown("---")
        st.header("7. 🛡️ Calificación de la Operación")
        
        if df_seg_raw.empty:
            st.info("No se registraron calificaciones de operación en la hoja CALIFICA_OPE_UG para el periodo consultado.")
        elif not nombres_calificacion_activos:
            st.warning("Las centrales seleccionadas no poseen mapeo de Calificación de Operación en la matriz.")
        else:
            df_bar_data = df_seg_raw.dropna(subset=['INICIO', 'FIN']).copy()
            
            if not df_bar_data.empty:
                centrales_calif_permitidas = set(nombres_calificacion_activos)
                df_bar_data['CENTRAL_LIMPIA'] = df_bar_data['CENTRAL'].astype(str).str.strip().str.upper()
                df_bar_data = df_bar_data[df_bar_data['CENTRAL_LIMPIA'].isin(centrales_calif_permitidas)].copy()
                
                if not df_bar_data.empty:
                    df_bar_data['CENTRAL_GRUPO'] = df_bar_data['CENTRAL'].astype(str) + " - " + df_bar_data['GRUPO'].astype(str)
                    df_bar_data['HORAS_OPERACION'] = (df_bar_data['FIN'] - df_bar_data['INICIO']).dt.total_seconds() / 3600.0
                    df_bar_data['HORAS_OPERACION'] = df_bar_data['HORAS_OPERACION'].clip(lower=0)

                    df_agrupado = df_bar_data.groupby(['CENTRAL_GRUPO', 'TIPO_OPERACION'], as_index=False)['HORAS_OPERACION'].sum()

                    colores_operacion = {
                        "POR SEGURIDAD": "#8B0000", "POR POTENCIA O ENERGIA": "#00BFFF",
                        "A MINIMA CARGA": "#32CD32", "POR COGENERACION": "#FF8C00",
                        "POR RSF": "#FFD700", "POR PRUEBAS": "#808080"
                    }

                    fig_bar_seg = px.bar(
                        df_agrupado, x="HORAS_OPERACION", y="CENTRAL_GRUPO", color="TIPO_OPERACION",
                        orientation='h', title="Horas Totales de Operación por Unidad y Tipo de Operación",
                        labels={"HORAS_OPERACION": "Horas Totales (h)", "CENTRAL_GRUPO": "Unidad Generadora", "TIPO_OPERACION": "Tipo de Operación"},
                        color_discrete_map=colores_operacion, template="plotly_white"
                    )

                    fig_bar_seg.update_layout(
                        yaxis=dict(title="Unidad Generadora", categoryorder="total ascending"),
                        xaxis=dict(title="Horas de Operación Totales"),
                        height=max(400, len(df_agrupado['CENTRAL_GRUPO'].unique()) * 40)
                    )
                    st.plotly_chart(fig_bar_seg, use_container_width=True)

                    with st.expander("Ver Registro Detallado de Calificación de Operaciones"):
                        df_seguridad_filtrado = df_bar_data[df_bar_data['TIPO_OPERACION'] == 'POR SEGURIDAD'].copy()
                        if not df_seguridad_filtrado.empty:
                            df_seguridad_mostrar = df_seguridad_filtrado.drop(columns=['CENTRAL_LIMPIA'], errors='ignore')
                            st.dataframe(df_seguridad_mostrar, use_container_width=True)
                        else:
                            st.info("No hay registros de operación POR SEGURIDAD en este periodo.")
                else:
                    st.warning("Las centrales filtradas no registraron operaciones calificadas en este periodo.")
            else:
                st.warning("Faltan datos válidos de INICIO o FIN para graficar las horas de operación.")

        
        # ==========================================
        # 8. EVOLUCIÓN Y COMPORTAMIENTO DE LA DEMANDA
        # ==========================================
        st.markdown("---")
        st.header("8. 🌍 Evolución y Comportamiento de la Demanda por Áreas")
        
        if df_dem_raw is None or df_dem_raw.empty:
            st.info("No se encontraron datos de demanda en el periodo descargado.")
        else:
            df_subareas = df_dem_raw[df_dem_raw['ÁREA'] != 'SEIN'].copy()
            df_sein = df_dem_raw[df_dem_raw['ÁREA'] == 'SEIN'].copy()
            
            colores_area = {"NORTE": "#FF9900", "CENTRO": "#3366CC", "SUR": "#DC3912"}
            
            fig_demanda = px.line(
                df_subareas, x="FECHA_HORA", y="DEMANDA_MW", color="ÁREA",
                title="Evolución de la Demanda por Áreas Operativas (MW)",
                color_discrete_map=colores_area,
                template="plotly_white"
            )
            
            fig_demanda.update_traces(hovertemplate="%{y:,.2f} MW", line=dict(width=2, dash='dot'))
            
            def graficar_min_max(fig, df_filtro, color_marcador, nombre_area):
                if not df_filtro.empty:
                    idx_max = df_filtro['DEMANDA_MW'].idxmax()
                    idx_min = df_filtro['DEMANDA_MW'].idxmin()
                    
                    max_row = df_filtro.loc[idx_max]
                    min_row = df_filtro.loc[idx_min]
                    
                    fig.add_scatter(
                        x=[max_row['FECHA_HORA']], y=[max_row['DEMANDA_MW']],
                        mode='markers+text', marker=dict(color=color_marcador, size=12, symbol='triangle-up'),
                        text=[f"<b>Máx: {max_row['DEMANDA_MW']:,.0f} MW</b>"], textposition="top center",
                        name=f'Máx {nombre_area}', hoverinfo='skip', showlegend=False, textfont=dict(color="blue")
                    )
                    
                    fig.add_scatter(
                        x=[min_row['FECHA_HORA']], y=[min_row['DEMANDA_MW']],
                        mode='markers+text', marker=dict(color=color_marcador, size=12, symbol='triangle-down'),
                        text=[f"<b>Mín: {min_row['DEMANDA_MW']:,.0f} MW</b>"], textposition="bottom center",
                        name=f'Mín {nombre_area}', hoverinfo='skip', showlegend=False, textfont=dict(color="blue")
                    )
                    
            for area in df_subareas['ÁREA'].unique():
                graficar_min_max(fig_demanda, df_subareas[df_subareas['ÁREA'] == area], colores_area.get(area, 'blue'), area)
            
            if not df_sein.empty:
                fig_demanda.add_scatter(
                    x=df_sein['FECHA_HORA'], y=df_sein['DEMANDA_MW'], mode='lines',
                    line=dict(width=3, color='black', dash='dash'), name='<b>⚡ DEMANDA SEIN TOTAL</b>',
                    hovertemplate='<b>🗓️ %{x|%d/%m/%Y %H:%M} ➡️ %{y:,.2f} MW</b>'
                )
                graficar_min_max(fig_demanda, df_sein, 'black', 'SEIN')
            
            fig_demanda.update_layout(
                hovermode="x unified",
                xaxis=dict(tickformat="%d/%m\n%H:%M", title="Fecha Operativa"),
                yaxis=dict(title="Demanda Activa (MW)"),
                height=550, margin=dict(t=50, b=50, l=50, r=20)
            )
            st.plotly_chart(fig_demanda, use_container_width=True)

        # ==========================================
        # 9. TRAZABILIDAD (DATA CRUDA)
        # ==========================================
        st.markdown("---")
        st.header("9. 🗄️ Trazabilidad de Potencia (Data Cruda - SEIN)")
        
        with st.expander("Ver Matriz de Despacho de Generación", expanded=False):
            df_pivot = df_plot_cen.copy()
            df_pivot['FECHA'] = df_pivot['FECHA_HORA'].dt.strftime('%d/%m/%Y')
            df_pivot['HORA'] = df_pivot['FECHA_HORA'].dt.strftime('%H:%M')
            
            jerarquia_columnas = ['ZONA', 'TIPO_CENTRAL', 'EMPRESA', 'CENTRAL']
            
            df_matricial = df_pivot.pivot_table(
                index=['FECHA', 'HORA'],
                columns=jerarquia_columnas,
                values='DESPACHO_MW',
                aggfunc='sum'
            ).round(2).fillna(0)
            
            st.dataframe(df_matricial, use_container_width=True)
            
            buffer_xls = io.BytesIO()
            with pd.ExcelWriter(buffer_xls, engine='openpyxl') as writer:
                df_matricial.to_excel(writer, sheet_name='Despacho_SEIN')
                
            st.download_button(
                label="📥 Descargar Vista Matricial (Excel)",
                data=buffer_xls.getvalue(),
                file_name=f"matriz_sein_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # ==========================================
        # 10. ANÁLISIS DE BALANCE DE POTENCIA - ÁREA NORTE
        # ==========================================
        st.markdown("---")
        st.header("10. 📉 Balance de Potencia - Área Norte")
        st.info("Evolución temporal del comportamiento eléctrico en el Norte del país: Superposición de la Demanda del Área Norte (calculada como la suma de los valores absolutos de Generación y Flujo), la Generación local total del Norte y el Flujo de Interconexión Centro-Norte.")
        
        df_dem_raw = st.session_state.get('df_demanda', pd.DataFrame())
        df_inter_raw = st.session_state.get('df_interconexiones', pd.DataFrame())
        df_gen_filtrada = df_datos.copy()
        
        if df_dem_raw.empty or df_inter_raw.empty or df_gen_filtrada.empty:
            st.info("Se requieren datos consolidados de Demanda, Enlaces y Despacho en el periodo para compilar el balance del Área Norte.")
        else:
            df_dem_norte = df_dem_raw[df_dem_raw['ÁREA'] == 'NORTE'].groupby('FECHA_HORA', as_index=False)['DEMANDA_MW'].sum()
            
            df_cn = df_inter_raw[df_inter_raw['ENLACE'] == 'CENTRO-NORTE'].copy()
            df_cn_total = df_cn.groupby('FECHA_HORA', as_index=False)['FLUJO_MW'].sum()
            df_cn_total['FLUJO_NEG'] = df_cn_total['FLUJO_MW'] * -1
            
            df_gen_norte = df_gen_filtrada[df_gen_filtrada['ZONA'] == 'NORTE'].groupby('FECHA_HORA', as_index=False)['DESPACHO_MW'].sum()
            
            df_balance = df_dem_norte.merge(df_cn_total[['FECHA_HORA', 'FLUJO_NEG']], on='FECHA_HORA', how='inner')
            df_balance = df_balance.merge(df_gen_norte, on='FECHA_HORA', how='inner')
            df_balance.columns = ['FECHA_HORA', 'DEMANDA', 'FLUJO_NEG', 'GENERACION']
            
            df_balance['DEMANDA'] = df_balance['GENERACION'].abs() + df_balance['FLUJO_NEG'].abs()
            
            fig_balance = go.Figure()
            
            fig_balance.add_trace(go.Scatter(
                x=df_balance['FECHA_HORA'], y=df_balance['DEMANDA'],
                mode='lines', line=dict(width=3, color='#FF9900'),
                name='<b>📉 DEMANDA NORTE</b>', hovertemplate="<b>Demanda Norte</b>: %{y:,.2f} MW"
            ))
            
            fig_balance.add_trace(go.Scatter(
                x=df_balance['FECHA_HORA'], y=df_balance['GENERACION'],
                mode='lines', line=dict(width=3, dash='dot', color='#1f77b4'),
                name='<b>🏭 GENERACIÓN NORTE</b>', hovertemplate="<b>Generación Norte</b>: %{y:,.2f} MW"
            ))
            
            fig_balance.add_trace(go.Scatter(
                x=df_balance['FECHA_HORA'], y=df_balance['FLUJO_NEG'],
                mode='lines', line=dict(width=3, dash='dash', color='#9467bd'),
                name='<b>🔌 -1 * FLUJO C-N</b>', hovertemplate="<b>-1 * Flujo C-N</b>: %{y:,.2f} MW"
            ))
            
            def marcar_extremos_balance(fig, x_data, y_data, color_marcador):
                if not y_data.empty:
                    idx_max = y_data.idxmax()
                    idx_min = y_data.idxmin()
                    
                    fig.add_trace(go.Scatter(
                        x=[x_data[idx_max]], y=[y_data[idx_max]],
                        mode='markers+text', marker=dict(color=color_marcador, size=10, symbol='triangle-up'),
                        text=[f"<b>Máx: {y_data[idx_max]:,.2f}</b>"], textposition="top center",
                        showlegend=False, hoverinfo='skip', textfont=dict(color="blue")
                    ))
                    fig.add_trace(go.Scatter(
                        x=[x_data[idx_min]], y=[y_data[idx_min]],
                        mode='markers+text', marker=dict(color=color_marcador, size=10, symbol='triangle-down'),
                        text=[f"<b>Mín: {y_data[idx_min]:,.2f}</b>"], textposition="bottom center",
                        showlegend=False, hoverinfo='skip', textfont=dict(color="blue")
                    ))
            
            marcar_extremos_balance(fig_balance, df_balance['FECHA_HORA'], df_balance['DEMANDA'], '#FF9900')
            marcar_extremos_balance(fig_balance, df_balance['FECHA_HORA'], df_balance['GENERACION'], '#1f77b4')
            marcar_extremos_balance(fig_balance, df_balance['FECHA_HORA'], df_balance['FLUJO_NEG'], '#9467bd')
            
            max_absoluto = max(df_balance['DEMANDA'].max(), df_balance['GENERACION'].max(), df_balance['FLUJO_NEG'].max())
            min_absoluto = min(df_balance['DEMANDA'].min(), df_balance['GENERACION'].min(), df_balance['FLUJO_NEG'].min())
            limite_y_sup = max_absoluto + 400
            limite_y_inf = min_absoluto * 1.15 if min_absoluto < 0 else 0
            
            fig_balance.update_layout(
                hovermode="x unified", height=600, margin=dict(t=50, b=50, l=50, r=150),
                legend=dict(title="<b>Variables del Área</b>", orientation="v", yanchor="top", y=1, xanchor="left", x=1.05),
                template="plotly_white",
                xaxis=dict(title_text="Fecha Operativa", tickformat="%d/%m\n%H:%M"),
                yaxis=dict(title_text="Potencia Activa (MW)", range=[limite_y_inf, limite_y_sup])
            )
            
            st.plotly_chart(fig_balance, use_container_width=True)
            
            with st.expander("Ver Datos de Balance Norte (Vista Matricial)"):
                df_mat_b = df_balance.copy()
                df_mat_b['FECHA'] = df_mat_b['FECHA_HORA'].dt.strftime('%d/%m/%Y')
                df_mat_b['HORA'] = df_mat_b['FECHA_HORA'].dt.strftime('%H:%M')
                matriz_b = df_mat_b.pivot_table(index=['FECHA', 'HORA'], values=['DEMANDA', 'GENERACION', 'FLUJO_NEG'], aggfunc='mean').round(2)
                matriz_b = matriz_b[['DEMANDA', 'GENERACION', 'FLUJO_NEG']]
                st.dataframe(matriz_b, use_container_width=True)

        # ==========================================
        # 11. EVOLUCIÓN GLOBAL DE COSTOS MARGINALES (CMg)
        # ==========================================
        st.markdown("---")
        st.header("11. 📈 Evolución Consolidada de Costos Marginales")
        st.info("Comparativa directa del Costo Marginal (USD/MWh) en las principales barras de referencia del Norte, Centro y Sur del SEIN.")
        
        df_cmg_raw = st.session_state.get('df_cmg', pd.DataFrame())
        
        if df_cmg_raw.empty:
            st.info("No se encontraron datos de Costos Marginales en el periodo descargado.")
        else:
            df_cmg_plot_11 = df_cmg_raw.sort_values(['FECHA_HORA', 'BARRA']).copy()
            
            colores_barra_11 = {
                'SANTA ROSA 220': '#d62728',  # Rojo (Centro)
                'MONTALVO 220': '#2ca02c',    # Verde (Sur)
                'TRUJILLO 220': '#ff7f0e'     # Naranja (Norte)
            }
            
            fig_cmg_11 = px.line(
                df_cmg_plot_11, x="FECHA_HORA", y="CMG_USD", color="BARRA",
                title="Costo Marginal Consolidado por Barra (USD/MWh)",
                labels={"BARRA": "Barra 220 kV", "CMG_USD": "Costo Marginal (USD/MWh)"},
                color_discrete_map=colores_barra_11, 
                template="plotly_white"
            )
            
            fig_cmg_11.update_traces(hovertemplate="<b>%{data.name}</b>: %{y:,.2f} USD/MWh", line=dict(width=3, dash='dot'))
            
            def graficar_extremos_azules(fig, df_filtro, color_marcador, nombre_barra):
                if not df_filtro.empty:
                    idx_max = df_filtro['CMG_USD'].idxmax()
                    idx_min = df_filtro['CMG_USD'].idxmin()
                    
                    fig.add_scatter(
                        x=[df_filtro.loc[idx_max, 'FECHA_HORA']], y=[df_filtro.loc[idx_max, 'CMG_USD']],
                        mode='markers+text', marker=dict(color=color_marcador, size=12, symbol='triangle-up'),
                        text=[f"<b>Máx: {df_filtro.loc[idx_max, 'CMG_USD']:,.1f}</b>"], 
                        textposition="top center", textfont=dict(color="blue"), 
                        name=f'Máx {nombre_barra}', hoverinfo='skip', showlegend=False
                    )
                    
                    fig.add_scatter(
                        x=[df_filtro.loc[idx_min, 'FECHA_HORA']], y=[df_filtro.loc[idx_min, 'CMG_USD']],
                        mode='markers+text', marker=dict(color=color_marcador, size=12, symbol='triangle-down'),
                        text=[f"<b>Mín: {df_filtro.loc[idx_min, 'CMG_USD']:,.1f}</b>"], 
                        textposition="bottom center", textfont=dict(color="blue"), 
                        name=f'Mín {nombre_barra}', hoverinfo='skip', showlegend=False
                    )

            for barra in df_cmg_plot_11['BARRA'].unique():
                df_barra_11 = df_cmg_plot_11[df_cmg_plot_11['BARRA'] == barra]
                graficar_extremos_azules(fig_cmg_11, df_barra_11, colores_barra_11.get(barra, 'black'), barra)
            
            max_val_cmg_11 = df_cmg_plot_11['CMG_USD'].max()
            limite_superior_11 = max_val_cmg_11 * 1.15 if max_val_cmg_11 > 0 else 50
            
            fig_cmg_11.update_layout(
                hovermode="x unified",
                xaxis=dict(tickformat="%d/%m\n%H:%M", title="Fecha Operativa"),
                yaxis=dict(title="Costo Marginal (USD/MWh)", range=[0, limite_superior_11]),
                height=600, margin=dict(t=50, b=50, l=50, r=150),
                legend=dict(title="<b>Barras SEIN</b>", orientation="v", yanchor="top", y=1, xanchor="left", x=1.02)
            )
            
            st.plotly_chart(fig_cmg_11, use_container_width=True)
            
            with st.expander("Ver Datos Consolidados de CMg (Vista Matricial)"):
                df_cmg_pivot_11 = df_cmg_plot_11.copy()
                df_cmg_pivot_11['FECHA'] = df_cmg_pivot_11['FECHA_HORA'].dt.strftime('%d/%m/%Y')
                df_cmg_pivot_11['HORA'] = df_cmg_pivot_11['FECHA_HORA'].dt.strftime('%H:%M')
                matriz_cmg_11 = df_cmg_pivot_11.pivot_table(index=['FECHA', 'HORA'], columns=['BARRA'], values='CMG_USD', aggfunc='mean').round(2)
                st.dataframe(matriz_cmg_11, use_container_width=True)