import streamlit as st
import pandas as pd
from fpdf import FPDF
import os
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor

# 1. CONFIGURACIÓN
st.set_page_config(page_title="Revisión Tabancura", page_icon="🔍", layout="wide")

# --- CONEXIÓN HÍBRIDA ---
def conectar_db():
    host = os.getenv("POSTGRES_HOST")
    database = os.getenv("POSTGRES_DATABASE")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    port = os.getenv("POSTGRES_PORT")

    if not host:
        try:
            if "postgres" in st.secrets:
                db_conf = st.secrets["postgres"]
                host = db_conf["host"]
                database = db_conf["database"]
                user = db_conf["user"]
                password = db_conf["password"]
                port = db_conf["port"]
        except: pass

    if not host:
        st.error("❌ Credenciales no encontradas.")
        return None

    try:
        return psycopg2.connect(
            host=host, database=database, user=user, 
            password=password, port=port, sslmode="disable"
        )
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        return None

# --- CARGAR EXCEL ---
@st.cache_data
def cargar_aranceles():
    if not os.path.exists("aranceles.xlsx"):
        st.error("❌ 'aranceles.xlsx' no encontrado.")
        return None
    try:
        df = pd.read_excel("aranceles.xlsx")
        # Ajustamos nombres para que coincidan con la lógica de cruce
        df.columns = ["Código", "Nombre", "Bono Fonasa", "Copago", "Particular General", "Particular Preferencial"]
        df["Código"] = df["Código"].astype(str).str.replace(".0", "", regex=False).str.strip()
        return df
    except Exception as e:
        st.error(f"❌ Error Excel: {e}")
        return None

# --- CLASE PDF BASE ---
class TabancuraPDF(FPDF):
    def header(self):
        if os.path.exists("logo.png"): self.image("logo.png", 10, 8, h=12)
        self.set_font("Arial", 'B', 10)
        self.set_text_color(15, 143, 238)
        self.cell(0, 5, "POLICLÍNICO TABANCURA", ln=True, align='R')
        self.ln(10)

# --- INTERFAZ ---
if os.path.exists("logo.png"):
    st.image("logo.png", width=200)

st.title("Revisión de Cotizaciones y Órdenes Médicas")
st.info("💡 Ingrese el Folio de Cotización (Ej: A1B2C3D4) o el ID de la Orden Médica (Ej: 105).")

# Búsqueda
folio_busqueda = st.text_input("Identificador de Documento:", placeholder="Folio o ID").strip()

if st.button("Consultar Registro"):
    if not folio_busqueda:
        st.warning("⚠️ Ingrese un identificador.")
    else:
        with st.spinner("Buscando en servidor..."):
            conn = conectar_db()
            if conn:
                try:
                    # Usamos RealDictCursor para manejar nombres de columnas fácilmente
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    es_orden = folio_busqueda.isdigit()
                    
                    maestro = None
                    codigos_db = []
                    tipo_doc = ""

                    if es_orden:
                        # BUSCAR EN ORDENES CLINICAS
                        cur.execute("SELECT * FROM ordenes_clinicas WHERE folio_orden = %s", (folio_busqueda,))
                        maestro = cur.fetchone()
                        if maestro:
                            tipo_doc = "ORDEN MÉDICA"
                            cur.execute("SELECT codigo_examen FROM ordenes_detalles WHERE folio_orden = %s", (folio_busqueda,))
                            codigos_db = [row['codigo_examen'] for row in cur.fetchall()]
                    else:
                        # BUSCAR EN COTIZACIONES
                        cur.execute("SELECT * FROM cotizaciones WHERE folio = %s", (folio_busqueda.upper(),))
                        maestro = cur.fetchone()
                        if maestro:
                            tipo_doc = "COTIZACIÓN"
                            cur.execute("SELECT codigo_examen FROM detalle_cotizaciones WHERE folio_cotizacion = %s", (folio_busqueda.upper(),))
                            codigos_db = [row['codigo_examen'] for row in cur.fetchall()]

                    if maestro:
                        # Cruce con Excel
                        df_precios = cargar_aranceles()
                        df_final = df_precios[df_precios["Código"].isin(codigos_db)].copy()

                        # Mostrar datos
                        st.success(f"✅ {tipo_doc} encontrada")
                        col1, col2, col3 = st.columns(3)
                        
                        # Manejo de nombres de columna según la tabla
                        nombre_pac = maestro.get('nombre_paciente') or "N/A" # En cotizaciones
                        rut_pac = maestro.get('documento_id') or maestro.get('rut_paciente') # Ambas tablas
                        fecha = maestro.get('fecha_cotizacion') or maestro.get('fecha_creacion')
                        folio_real = maestro.get('folio') or maestro.get('folio_orden')

                        col1.metric("Paciente", nombre_pac if not es_orden else "Ver en Detalle")
                        col2.metric("RUT", rut_pac)
                        col3.metric("Fecha", fecha.strftime('%d/%m/%Y'))

                        st.subheader(f"Exámenes vinculados al Folio {folio_real}")
                        st.dataframe(df_final, use_container_width=True)

                        # --- GENERACIÓN DE PDF REIMPRESO ---
                        pdf = TabancuraPDF()
                        pdf.add_page()
                        pdf.set_font("Arial", 'B', 12)
                        pdf.cell(0, 10, f"REIMPRESIÓN DE {tipo_doc}", ln=True, align='C')
                        pdf.ln(5)
                        
                        pdf.set_font("Arial", '', 10)
                        pdf.cell(0, 7, f"Folio: {folio_real}", ln=True)
                        pdf.cell(0, 7, f"RUT Paciente: {rut_pac}", ln=True)
                        pdf.cell(0, 7, f"Fecha Emisión: {fecha.strftime('%d/%m/%Y %H:%M')}", ln=True)
                        pdf.ln(5)

                        # Tabla PDF
                        pdf.set_fill_color(15, 143, 238); pdf.set_text_color(255); pdf.set_font("Arial", 'B', 8)
                        pdf.cell(25, 8, "Código", 1, 0, 'C', True)
                        pdf.cell(100, 8, "Examen", 1, 0, 'L', True)
                        pdf.cell(30, 8, "Copago", 1, 0, 'C', True)
                        pdf.cell(35, 8, "Particular", 1, 1, 'C', True)

                        pdf.set_text_color(0); pdf.set_font("Arial", '', 8)
                        for _, row in df_final.iterrows():
                            pdf.cell(25, 7, str(row['Código']), 1, 0, 'C')
                            pdf.cell(100, 7, str(row['Nombre'])[:50], 1, 0, 'L')
                            pdf.cell(30, 7, f"${row['Copago']:,.0f}", 1, 0, 'R')
                            pdf.cell(35, 7, f"${row['Particular General']:,.0f}", 1, 1, 'R')

                        pdf_output = f"Reimpresion_{folio_real}.pdf"
                        pdf.output(pdf_output)
                        
                        with open(pdf_output, "rb") as f:
                            st.download_button(f"📥 Descargar PDF de {tipo_doc}", f, file_name=pdf_output)

                    else:
                        st.error(f"❌ El identificador '{folio_busqueda}' no existe en ninguna categoría.")

                    cur.close()
                    conn.close()
                except Exception as e:
                    st.error(f"❌ Error: {e}")