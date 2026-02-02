import streamlit as st
import pandas as pd
from fpdf import FPDF
import os
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor
import pytz

# 1. CONFIGURACIÓN E IDENTIDAD INSTITUCIONAL
AZUL_TABANCURA = (15, 143, 239) # #0F8FEF
VERDE_TABANCURA = (35, 181, 116) # #23B574

st.set_page_config(page_title="Consulta Tabancura", page_icon="🏥", layout="wide")

# --- CONEXIÓN A BASE DE DATOS ---
def conectar_db():
    try:
        return psycopg2.connect(
            host=os.getenv("POSTGRES_HOST"),
            database=os.getenv("POSTGRES_DATABASE"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            sslmode="disable"
        )
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        return None

# --- CARGAR ARANCELES PARA RECONSTRUCCIÓN ---
@st.cache_data
def cargar_aranceles():
    if not os.path.exists("aranceles.xlsx"): return None
    try:
        df = pd.read_excel("aranceles.xlsx")
        df.columns = ["Código", "Nombre", "Bono Fonasa", "Copago", "Particular General", "Particular Preferencial"]
        df["Código"] = df["Código"].astype(str).str.replace(".0", "", regex=False).str.strip()
        return df
    except: return None

# --- CLASE PDF UNIFICADA (Mismo diseño que sistemas emisores) ---
class TabancuraPDF(FPDF):
    def __init__(self, titulo_doc, subtitulo=""):
        super().__init__()
        self.titulo_doc = titulo_doc
        self.subtitulo = subtitulo

    def header(self):
        # Logo y Datos de Contacto 
        if os.path.exists("logo.png"): self.image("logo.png", 10, 8, h=12)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(30, 30, 30)
        self.cell(0, 6, "POLICLÍNICO TABANCURA", ln=True, align='R')
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, "Av. Vitacura #8620, Vitacura, Santiago", ln=True, align='R')
        self.cell(0, 4, "Teléfono: +56 2 2933 6740 | www.policlinicotabancura.cl", ln=True, align='R')
        
        # Título del Documento [cite: 14, 16]
        self.ln(10)
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(*AZUL_TABANCURA)
        self.cell(0, 10, self.clean_txt(self.titulo_doc.upper()), ln=True, align='C')
        if self.subtitulo:
            self.set_font('Helvetica', 'B', 10)
            self.cell(0, 5, self.clean_txt(self.subtitulo), ln=True, align='C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(170)
        hora = datetime.now(pytz.timezone('America/Santiago')).strftime('%d/%m/%Y %H:%M')
        self.cell(0, 10, self.clean_txt(f"Pág. {self.page_no()} | Reimpresión: {hora} | Validar en portal web"), align='C')

    def clean_txt(self, t):
        return str(t).encode('latin-1', 'replace').decode('latin-1')

    def dibujar_datos_paciente(self, nombre, rut, fecha):
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(50, 50, 50)
        self.cell(20, 6, "Paciente:", 0, 0)
        self.set_font('Helvetica', '', 9)
        self.cell(100, 6, self.clean_txt(nombre), 0, 0)
        self.set_font('Helvetica', 'B', 9)
        self.cell(15, 6, "RUT:", 0, 0)
        self.set_font('Helvetica', '', 9)
        self.cell(0, 6, rut, 0, 1)
        self.set_font('Helvetica', 'B', 9)
        self.cell(20, 6, "Fecha:", 0, 0)
        self.set_font('Helvetica', '', 9)
        self.cell(0, 6, fecha, 0, 1)
        self.ln(5)

# --- INTERFAZ DE USUARIO ---
st.title("🏥 Portal de Consulta y Reimpresión")
st.markdown("---")

folio_busqueda = st.text_input("Ingrese Folio de Cotización o ID de Orden:", placeholder="Ej: WRLP7P6C o 105").strip()

if st.button("Consultar y Previsualizar"):
    if not folio_busqueda:
        st.warning("⚠️ Ingrese un identificador.")
    else:
        conn = conectar_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            es_orden = folio_busqueda.isdigit()
            
            # 1. BÚSQUEDA DE DATOS
            if es_orden:
                cur.execute("SELECT * FROM ordenes_clinicas WHERE folio_orden = %s", (folio_busqueda,))
                maestro = cur.fetchone()
                if maestro:
                    cur.execute("SELECT codigo_examen, nombre_examen FROM ordenes_detalles WHERE folio_orden = %s", (folio_busqueda,))
                    detalles = cur.fetchall()
                    titulo = "ORDEN DE EXÁMENES"
                    subtitulo = f"FOLIO ORDEN: {maestro['folio_orden']}"
                    # Formateo para PDF
                    nombre_pac = "Consultar en Ficha" 
                    rut_pac = maestro['rut_paciente']
                    fecha_doc = maestro['fecha_creacion'].strftime('%d/%m/%Y')
            else:
                cur.execute("SELECT * FROM cotizaciones WHERE folio = %s", (folio_busqueda.upper(),))
                maestro = cur.fetchone()
                if maestro:
                    cur.execute("SELECT codigo_examen, nombre_examen, valor_copago FROM detalle_cotizaciones WHERE folio_cotizacion = %s", (folio_busqueda.upper(),))
                    detalles = cur.fetchall()
                    titulo = "PRESUPUESTO DE EXÁMENES"
                    subtitulo = f"FOLIO COTIZACIÓN: {maestro['folio']}"
                    nombre_pac = maestro['nombre_paciente']
                    rut_pac = maestro['documento_id']
                    fecha_doc = maestro['fecha_cotizacion'].strftime('%d/%m/%Y')

            # 2. GENERACIÓN DE PDF SI EXISTE REGISTRO
            if maestro:
                st.success(f"✅ Registro encontrado: {titulo}")
                
                pdf = TabancuraPDF(titulo, subtitulo)
                pdf.add_page()
                pdf.dibujar_datos_paciente(nombre_pac, rut_pac, fecha_doc)

                # Diseño de Tabla según tipo de documento [cite: 11, 24]
                if es_orden:
                    pdf.set_font('Helvetica', 'B', 9); pdf.set_fill_color(240, 240, 240)
                    pdf.cell(35, 10, " CÓDIGO", 1, 0, 'L', True)
                    pdf.cell(155, 10, " PRESTACIÓN / EXAMEN SOLICITADO", 1, 1, 'L', True)
                    pdf.set_font('Helvetica', '', 9)
                    for d in detalles:
                        pdf.cell(35, 8, f" {d['codigo_examen']}", 1, 0, 'L')
                        pdf.cell(155, 8, f" {pdf.clean_txt(d['nombre_examen'][:80])}", 1, 1, 'L')
                    # Firma Médica [cite: 12]
                    pdf.ln(15); pdf.set_draw_color(180, 180, 180)
                    pdf.line(70, pdf.get_y(), 140, pdf.get_y())
                    pdf.set_font('Helvetica', 'B', 9); pdf.cell(0, 5, "Firma y Timbre Médico", 0, 1, 'C')
                else:
                    # Formato Cotización con Precios [cite: 24]
                    pdf.set_font('Helvetica', 'B', 8); pdf.set_fill_color(*AZUL_TABANCURA); pdf.set_text_color(255)
                    pdf.cell(25, 10, "CÓDIGO", 1, 0, 'C', True)
                    pdf.cell(105, 10, "EXAMEN", 1, 0, 'L', True)
                    pdf.cell(30, 10, "COPAGO", 1, 0, 'C', True)
                    pdf.cell(30, 10, "PARTICULAR", 1, 1, 'C', True)
                    pdf.set_text_color(0); pdf.set_font('Helvetica', '', 8)
                    for d in detalles:
                        pdf.cell(25, 8, f" {d['codigo_examen']}", 1, 0, 'C')
                        pdf.cell(105, 8, f" {pdf.clean_txt(d['nombre_examen'][:55])}", 1, 0, 'L')
                        pdf.cell(30, 8, f"${d.get('valor_copago', 0):,.0f}", 1, 0, 'R')
                        pdf.cell(30, 8, "Consultar", 1, 1, 'R')

                # Descarga
                pdf_bytes = pdf.output(dest='S')
                st.download_button(
                    label=f"📥 Descargar {titulo} PDF",
                    data=bytes(pdf_bytes) if isinstance(pdf_bytes, (bytes, bytearray)) else pdf_bytes.encode('latin-1'),
                    file_name=f"Reimpresion_{folio_busqueda}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            else:
                st.error("❌ No se encontró ningún documento con ese folio.")
            
            cur.close()
            conn.close()