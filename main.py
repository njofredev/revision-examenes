import streamlit as st
import pandas as pd
from fpdf import FPDF
import os
import psycopg2
from datetime import datetime

# 1. CONFIGURACIÓN
st.set_page_config(page_title="Revisión de Exámenes", page_icon="🔍", layout="wide")

# --- CONEXIÓN HÍBRIDA (COOLIFY / STREAMLIT) ---
def conectar_db():
    # Intentamos obtener variables de entorno de Coolify
    host = os.getenv("POSTGRES_HOST")
    database = os.getenv("POSTGRES_DATABASE")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    port = os.getenv("POSTGRES_PORT")

    # Si no están en el entorno, buscamos en st.secrets
    if not host:
        try:
            if "postgres" in st.secrets:
                db_conf = st.secrets["postgres"]
                host = db_conf["host"]
                database = db_conf["database"]
                user = db_conf["user"]
                password = db_conf["password"]
                port = db_conf["port"]
        except:
            pass

    if not host:
        st.error("❌ Error: No se encontraron credenciales de base de datos.")
        return None

    try:
        return psycopg2.connect(
            host=host, 
            database=database, 
            user=user, 
            password=password, 
            port=port, 
            sslmode="require"
        )
    except Exception as e:
        st.error(f"❌ Error de conexión física a la DB: {e}")
        return None

# --- CARGAR EXCEL PARA CRUCE DE DATOS ---
@st.cache_data
def cargar_aranceles():
    if not os.path.exists("aranceles.xlsx"):
        st.error("❌ Archivo 'aranceles.xlsx' no encontrado en el servidor.")
        return None
    try:
        df = pd.read_excel("aranceles.xlsx")
        df.columns = ["Código", "Nombre", "Valor bono Fonasa", "Valor copago", "Valor particular General", "Valor particular preferencial"]
        df["Código"] = df["Código"].astype(str).str.replace(".0", "", regex=False)
        return df
    except Exception as e:
        st.error(f"❌ Error al leer Excel: {e}")
        return None

# --- INTERFAZ ---
if os.path.exists("logo.png"):
    st.image("logo.png")

st.title("Revisión de Cotizaciones Realizadas")
st.markdown("---")

# Campo de búsqueda
folio_busqueda = st.text_input("Ingrese el Folio (8 caracteres):", placeholder="Ej: A1B2C3D4").upper().strip()

if st.button("Buscar Cotización"):
    if not folio_busqueda:
        st.warning("⚠️ Por favor ingrese un folio.")
    else:
        with st.spinner("Buscando en la base de datos..."):
            conn = conectar_db()
            if conn:
                try:
                    cur = conn.cursor()
                    # 1. Buscar Maestro
                    cur.execute("SELECT * FROM cotizaciones WHERE folio = %s", (folio_busqueda,))
                    maestro = cur.fetchone()
                    
                    if maestro:
                        # 2. Buscar Detalles (Aquí estaba el error de nombre de variable)
                        cur.execute("SELECT codigo_examen FROM detalle_cotizaciones WHERE folio_cotizacion = %s", (folio_busqueda,))
                        codigos_db = [row[0] for row in cur.fetchall()]
                        
                        # 3. Cruzar con Excel
                        df_precios = cargar_aranceles()
                        if df_precios is not None:
                            df_final = df_precios[df_precios["Código"].isin(codigos_db)].copy()
                            
                            # --- MOSTRAR DATOS EN PANTALLA ---
                            st.success(f"✅ Cotización encontrada para: {maestro[2]}")
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Paciente", maestro[2])
                            c2.metric("Documento", maestro[4])
                            c3.metric("Fecha", maestro[6].strftime('%d/%m/%Y'))
                            
                            st.subheader("Detalle de Exámenes")
                            st.table(df_final.style.format("${:,.0f}", subset=["Valor bono Fonasa", "Valor copago", "Valor particular General", "Valor particular preferencial"]))
                            
                            # --- RECONSTRUIR PDF ---
                            pdf = FPDF()
                            pdf.add_page()
                            if os.path.exists("logo.png"): pdf.image("logo.png", 10, 8, h=12)
                            
                            pdf.set_font("Arial", 'B', 10); pdf.set_text_color(15, 143, 238)
                            pdf.cell(0, 5, f"FOLIO REIMPRESO: {maestro[1]}", ln=True, align='R')
                            pdf.set_text_color(0, 0, 0); pdf.ln(10)
                            pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, "Exámenes de Laboratorio", ln=True, align='C'); pdf.ln(3)

                            pdf.set_font("Arial", '', 10)
                            pdf.cell(0, 6, f"Paciente: {maestro[2]}", ln=True)
                            pdf.cell(0, 6, f"{maestro[3]}: {maestro[4]}", ln=True)
                            pdf.cell(0, 6, f"Fecha Original: {maestro[6].strftime('%d/%m/%Y %H:%M')}", ln=True); pdf.ln(6)

                            # Cabeceras Agrupadas
                            pdf.set_fill_color(15, 143, 238); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
                            pdf.cell(18, 10, "", 0, 0); pdf.cell(52, 10, "", 0, 0); pdf.cell(60, 10, "Bono Fonasa", 1, 0, 'C', True); pdf.cell(60, 10, "Arancel particular", 1, 1, 'C', True)
                            
                            pdf.set_font("Arial", 'B', 7)
                            pdf.cell(18, 10, "Código", 1, 0, 'C', True); pdf.cell(52, 10, " Nombre", 1, 0, 'L', True); pdf.cell(30, 10, "Valor Bono", 1, 0, 'C', True); pdf.cell(30, 10, "Valor a pagar(*)", 1, 0, 'C', True); pdf.cell(30, 10, "Valor general", 1, 0, 'C', True); pdf.cell(30, 10, "Valor preferencial", 1, 1, 'C', True)

                            pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 7)
                            for _, row in df_final.iterrows():
                                n_mostrar = (str(row['Nombre'])[:35] + "..") if len(str(row['Nombre'])) > 37 else str(row['Nombre'])
                                pdf.cell(18, 8, str(row['Código']), 1, 0, 'C')
                                pdf.cell(52, 8, f" {n_mostrar}", 1, 0, 'L')
                                pdf.cell(30, 8, f"${row['Valor bono Fonasa']:,.0f}", 1, 0, 'R')
                                pdf.cell(30, 8, f"${row['Valor copago']:,.0f}", 1, 0, 'R')
                                pdf.cell(30, 8, f"${row['Valor particular General']:,.0f}", 1, 0, 'R')
                                pdf.cell(30, 8, f"${row['Valor particular preferencial']:,.0f}", 1, 1, 'R')

                            # Totales desde la DB
                            pdf.set_font("Arial", 'B', 7); pdf.set_fill_color(240, 240, 240)
                            pdf.cell(70, 10, " TOTALES REIMPRESOS", 1, 0, 'L', True)
                            pdf.cell(30, 10, f"${maestro[7]:,.0f}", 1, 0, 'R', True)
                            pdf.cell(30, 10, f"${maestro[8]:,.0f}", 1, 0, 'R', True)
                            pdf.cell(30, 10, f"${maestro[9]:,.0f}", 1, 0, 'R', True)
                            pdf.cell(30, 10, f"${maestro[10]:,.0f}", 1, 1, 'R', True)

                            pdf_name = f"Reimpresion_{maestro[1]}.pdf"
                            pdf.output(pdf_name)
                            with open(pdf_name, "rb") as f:
                                st.download_button("🔵 Descargar PDF Reimpreso", data=f, file_name=pdf_name, mime="application/pdf")
                    else:
                        st.error(f"❌ El folio '{folio_busqueda}' no existe en la base de datos.")
                    
                    cur.close()
                    conn.close()
                except Exception as e:
                    st.error(f"❌ Error durante la consulta: {e}")
