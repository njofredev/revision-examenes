import streamlit as st
import pandas as pd
from fpdf import FPDF
import os
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor
import pytz

# --- CONFIGURACIÓN E IDENTIDAD ---
AZUL_TABANCURA = (15, 143, 239)
st.set_page_config(page_title="Consulta Tabancura", page_icon="🏥", layout="wide")

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

@st.cache_data
def cargar_aranceles():
    if not os.path.exists("aranceles.xlsx"): return None
    try:
        df = pd.read_excel("aranceles.xlsx")
        df.columns = ["Código", "Nombre", "Bono Fonasa", "Copago", "Particular General", "Particular Preferencial"]
        df["Código"] = df["Código"].astype(str).str.replace(".0", "", regex=False).str.strip()
        return df
    except: return None

class TabancuraPDF(FPDF):
    def __init__(self, titulo_doc, subtitulo=""):
        super().__init__()
        self.titulo_doc = titulo_doc
        self.subtitulo = subtitulo

    def header(self):
        if os.path.exists("logo.png"): self.image("logo.png", 10, 8, h=12)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(30, 30, 30)
        self.cell(0, 6, "POLICLÍNICO TABANCURA", ln=True, align='R')
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, "Av. Vitacura #8620, Vitacura, Santiago", ln=True, align='R')
        self.cell(0, 4, "Teléfono: +56 2 2933 6740 | www.policlinicotabancura.cl", ln=True, align='R')
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
        self.cell(0, 10, self.clean_txt(f"Pág. {self.page_no()} | Reimpresión: {hora}"), align='C')

    def clean_txt(self, t):
        return str(t).encode('latin-1', 'replace').decode('latin-1')

    def dibujar_datos_paciente(self, nombre, rut, fecha):
        self.set_font('Helvetica', 'B', 9)
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

# --- INTERFAZ ---
st.title("🏥 Portal de Consulta y Reimpresión")
folio_busqueda = st.text_input("Ingrese Folio o ID:", placeholder="Ej: WRLP7P6C").strip()

if st.button("Consultar"):
    conn = conectar_db()
    df_aranceles = cargar_aranceles()
    if conn and df_aranceles is not None:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        es_orden = folio_busqueda.isdigit()
        
        if es_orden:
            cur.execute("SELECT * FROM ordenes_clinicas WHERE folio_orden = %s", (folio_busqueda,))
            maestro = cur.fetchone()
            if maestro:
                cur.execute("SELECT codigo_examen FROM ordenes_detalles WHERE folio_orden = %s", (folio_busqueda,))
                codigos = [r['codigo_examen'] for r in cur.fetchall()]
                df_final = df_aranceles[df_aranceles["Código"].isin(codigos)]
                
                pdf = TabancuraPDF("ORDEN DE EXÁMENES", f"FOLIO ORDEN: {maestro['folio_orden']}")
                pdf.add_page()
                pdf.dibujar_datos_paciente("Consultar en Ficha", maestro['rut_paciente'], maestro['fecha_creacion'].strftime('%d/%m/%Y'))
                
                pdf.set_font('Helvetica', 'B', 9); pdf.set_fill_color(240, 240, 240)
                pdf.cell(35, 10, " CÓDIGO", 1, 0, 'L', True)
                pdf.cell(155, 10, " PRESTACIÓN / EXAMEN SOLICITADO", 1, 1, 'L', True)
                for _, r in df_final.iterrows():
                    pdf.cell(35, 8, f" {r['Código']}", 1, 0, 'L')
                    pdf.cell(155, 8, f" {pdf.clean_txt(r['Nombre'][:80])}", 1, 1, 'L')
                
                pdf.ln(10)
                pdf.set_font('Helvetica', 'B', 9)
                pdf.cell(0, 5, "Firma y Timbre Médico", 0, 1, 'C')
                
                # Generar descarga
                out_o = pdf.output(dest='S')
                st.download_button("📥 Descargar Orden", data=bytes(out_o), file_name=f"Orden_{folio_busqueda}.pdf", mime="application/pdf")
        else:
            cur.execute("SELECT * FROM cotizaciones WHERE folio = %s", (folio_busqueda.upper(),))
            maestro = cur.fetchone()
            if maestro:
                cur.execute("SELECT codigo_examen FROM detalle_cotizaciones WHERE folio_cotizacion = %s", (folio_busqueda.upper(),))
                codigos = [r['codigo_examen'] for r in cur.fetchall()]
                df_final = df_aranceles[df_aranceles["Código"].isin(codigos)]
                
                # CORRECCIÓN DE NameError: Se eliminó el texto '' que causaba el fallo
                pdf = TabancuraPDF("PRESUPUESTO DE EXÁMENES", f"FOLIO: {maestro['folio']}")
                pdf.add_page()
                pdf.dibujar_datos_paciente(maestro['nombre_paciente'], maestro['documento_id'], maestro['fecha_cotizacion'].strftime('%d/%m/%Y'))
                
                # Encabezados con las 4 columnas de valores
                pdf.set_font('Helvetica', 'B', 7); pdf.set_fill_color(*AZUL_TABANCURA); pdf.set_text_color(255)
                pdf.cell(15, 8, "CÓDIGO", 1, 0, 'C', True)
                pdf.cell(55, 8, "EXAMEN", 1, 0, 'L', True)
                pdf.cell(30, 8, "BONO FONASA", 1, 0, 'C', True)
                pdf.cell(30, 8, "COPAGO", 1, 0, 'C', True)
                pdf.cell(30, 8, "P. GENERAL", 1, 0, 'C', True)
                pdf.cell(30, 8, "P. PREF.", 1, 1, 'C', True)
                
                pdf.set_text_color(0); pdf.set_font('Helvetica', '', 7)
                totales = {"Bono": 0, "Copago": 0, "Gral": 0, "Pref": 0}
                for _, r in df_final.iterrows():
                    pdf.cell(15, 7, r['Código'], 1, 0, 'C')
                    pdf.cell(55, 7, pdf.clean_txt(r['Nombre'][:40]), 1, 0, 'L')
                    pdf.cell(30, 7, f"${r['Bono Fonasa']:,.0f}", 1, 0, 'R')
                    pdf.cell(30, 7, f"${r['Copago']:,.0f}", 1, 0, 'R')
                    pdf.cell(30, 7, f"${r['Particular General']:,.0f}", 1, 0, 'R')
                    pdf.cell(30, 7, f"${r['Particular Preferencial']:,.0f}", 1, 1, 'R')
                    
                    totales["Bono"] += r['Bono Fonasa']
                    totales["Copago"] += r['Copago']
                    totales["Gral"] += r['Particular General']
                    totales["Pref"] += r['Particular Preferencial']
                
                # Fila de Totales corregida
                pdf.set_font('Helvetica', 'B', 7); pdf.set_fill_color(240, 240, 240)
                pdf.cell(70, 8, " TOTALES ACUMULADOS", 1, 0, 'L', True)
                pdf.cell(30, 8, f"${totales['Bono']:,.0f}", 1, 0, 'R', True)
                pdf.cell(30, 8, f"${totales['Copago']:,.0f}", 1, 0, 'R', True)
                pdf.cell(30, 8, f"${totales['Gral']:,.0f}", 1, 0, 'R', True)
                pdf.cell(30, 8, f"${totales['Pref']:,.0f}", 1, 1, 'R', True)
                
                # Generar descarga
                out_c = pdf.output(dest='S')
                st.download_button("📥 Descargar Cotización", data=bytes(out_c), file_name=f"Cotizacion_{folio_busqueda}.pdf", mime="application/pdf")
            else:
                st.error("❌ No se encontró el folio.")
        
        cur.close()
        conn.close()