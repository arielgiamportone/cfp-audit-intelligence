import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from urllib.parse import urljoin, urlparse
import time
import re
import urllib3
import ssl

# Deshabilitar advertencias de SSL para certificados no verificados
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuración de la página
st.set_page_config(
    page_title="CFP Actas Scraper",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("🐟 Consejo Federal Pesquero - Descargador de Actas")

# Información sobre SSL
st.info("ℹ️ **Nota técnica**: Esta aplicación maneja automáticamente los problemas de certificado SSL del sitio oficial del CFP para garantizar el acceso a los documentos públicos.")

st.markdown("---")

# URL base del sitio
BASE_URL = "https://cfp.gob.ar"
ACTAS_URL = f"{BASE_URL}/actas-cfp"

# Función para obtener la lista de años disponibles
@st.cache_data(ttl=3600)  # Cache por 1 hora
def get_available_years():
    """Obtiene la lista de años disponibles desde la página principal"""
    try:
        # Configurar sesión con SSL deshabilitado para certificados expirados
        session = requests.Session()
        session.verify = False  # Deshabilitar verificación SSL
        
        response = session.get(ACTAS_URL, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar la lista de años
        year_links = soup.find_all('a', href=re.compile(r'actas-cfp\?anio=\d{4}'))
        years = []
        
        for link in year_links:
            href = link.get('href')
            if href:
                year_match = re.search(r'anio=(\d{4})', href)
                if year_match:
                    years.append(int(year_match.group(1)))
        
        # Eliminar duplicados y ordenar
        years = sorted(list(set(years)), reverse=True)
        return years
    
    except Exception as e:
        st.error(f"Error al obtener los años disponibles: {str(e)}")
        # Fallback con años conocidos
        return list(range(2025, 1997, -1))

# Función para obtener las actas de un año específico
@st.cache_data(ttl=3600)
def get_actas_for_year(year):
    """Obtiene la lista de actas para un año específico"""
    try:
        url = f"{ACTAS_URL}?anio={year}"
        
        # Configurar sesión con SSL deshabilitado para certificados expirados
        session = requests.Session()
        session.verify = False  # Deshabilitar verificación SSL
        
        response = session.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Buscar la lista de PDFs
        pdf_list = soup.find('ul', class_='ListaPdf')
        actas = []
        
        if pdf_list:
            for li in pdf_list.find_all('li'):
                link = li.find('a')
                if link and link.get('href'):
                    href = link.get('href')
                    # Construir URL completa
                    if href.startswith('/'):
                        pdf_url = BASE_URL + href
                    else:
                        pdf_url = urljoin(BASE_URL, href)
                    
                    # Extraer nombre del acta
                    acta_text = link.get_text(strip=True)
                    
                    # Verificar si tiene anexo
                    anexo_span = li.find('span', class_='ListaPdfActAnexo')
                    is_anexo = anexo_span is not None
                    
                    actas.append({
                        'nombre': acta_text,
                        'url': pdf_url,
                        'filename': os.path.basename(urlparse(href).path),
                        'is_anexo': is_anexo,
                        'year': year
                    })
        
        return actas
    
    except Exception as e:
        st.error(f"Error al obtener las actas del año {year}: {str(e)}")
        return []

# Función para descargar un archivo PDF
def download_pdf(url, filename, progress_bar=None):
    """Descarga un archivo PDF"""
    try:
        # Configurar sesión con SSL deshabilitado para certificados expirados
        session = requests.Session()
        session.verify = False  # Deshabilitar verificación SSL
        
        response = session.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        content = b""
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                content += chunk
                downloaded += len(chunk)
                if progress_bar and total_size > 0:
                    progress_bar.progress(downloaded / total_size)
        
        return content
    
    except Exception as e:
        st.error(f"Error al descargar {filename}: {str(e)}")
        return None

# Sidebar para selección de año
st.sidebar.header("🗓️ Selección de Año")

# Obtener años disponibles
with st.spinner("Cargando años disponibles..."):
    available_years = get_available_years()

if available_years:
    selected_year = st.sidebar.selectbox(
        "Selecciona un año:",
        available_years,
        index=0
    )
    
    # Botón para actualizar datos
    if st.sidebar.button("🔄 Actualizar datos"):
        st.cache_data.clear()
        st.rerun()
    
    # Obtener actas del año seleccionado
    with st.spinner(f"Cargando actas del año {selected_year}..."):
        actas = get_actas_for_year(selected_year)
    
    if actas:
        st.success(f"✅ Se encontraron {len(actas)} actas para el año {selected_year}")
        
        # Crear DataFrame para mostrar las actas
        df_actas = pd.DataFrame(actas)
        
        # Filtros adicionales
        st.sidebar.header("🔍 Filtros")
        
        # Filtro por tipo (anexo o no)
        show_anexos = st.sidebar.checkbox("Incluir anexos", value=True)
        show_main_actas = st.sidebar.checkbox("Incluir actas principales", value=True)
        
        # Aplicar filtros
        filtered_actas = []
        for acta in actas:
            if acta['is_anexo'] and show_anexos:
                filtered_actas.append(acta)
            elif not acta['is_anexo'] and show_main_actas:
                filtered_actas.append(acta)
        
        # Mostrar tabla de actas
        st.subheader(f"📋 Actas del año {selected_year}")
        
        if filtered_actas:
            # Crear tabla interactiva
            for i, acta in enumerate(filtered_actas):
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    icon = "📎" if acta['is_anexo'] else "📄"
                    st.write(f"{icon} **{acta['nombre']}**")
                    st.caption(f"Archivo: {acta['filename']}")
                
                with col2:
                    # Botón para ver URL
                    if st.button("🔗 Ver URL", key=f"url_{i}"):
                        st.info(f"URL: {acta['url']}")
                
                with col3:
                    # Botón para descargar
                    if st.button("⬇️ Descargar", key=f"download_{i}"):
                        with st.spinner(f"Descargando {acta['filename']}..."):
                            progress_bar = st.progress(0)
                            pdf_content = download_pdf(acta['url'], acta['filename'], progress_bar)
                            
                            if pdf_content:
                                st.download_button(
                                    label=f"💾 Guardar {acta['filename']}",
                                    data=pdf_content,
                                    file_name=acta['filename'],
                                    mime="application/pdf",
                                    key=f"save_{i}"
                                )
                                st.success(f"✅ {acta['filename']} listo para descargar!")
                
                st.markdown("---")
            
            # Opción para descargar todas las actas
            st.subheader("📦 Descarga masiva")
            
            if st.button("⬇️ Descargar todas las actas seleccionadas"):
                if len(filtered_actas) > 10:
                    st.warning("⚠️ Vas a descargar más de 10 archivos. Esto puede tomar tiempo.")
                    if not st.button("✅ Confirmar descarga masiva"):
                        st.stop()
                
                # Crear un ZIP con todas las actas
                import zipfile
                import io
                
                zip_buffer = io.BytesIO()
                
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    progress_text = st.empty()
                    progress_bar = st.progress(0)
                    
                    for i, acta in enumerate(filtered_actas):
                        progress_text.text(f"Descargando {acta['filename']} ({i+1}/{len(filtered_actas)})")
                        progress_bar.progress((i + 1) / len(filtered_actas))
                        
                        pdf_content = download_pdf(acta['url'], acta['filename'])
                        if pdf_content:
                            zip_file.writestr(acta['filename'], pdf_content)
                        
                        # Pequeña pausa para no sobrecargar el servidor
                        time.sleep(0.5)
                    
                    progress_text.text("✅ Descarga completada!")
                
                zip_buffer.seek(0)
                
                st.download_button(
                    label=f"💾 Descargar ZIP con {len(filtered_actas)} actas del {selected_year}",
                    data=zip_buffer.getvalue(),
                    file_name=f"actas_cfp_{selected_year}.zip",
                    mime="application/zip"
                )
        
        else:
            st.warning("No hay actas que coincidan con los filtros seleccionados.")
    
    else:
        st.error(f"No se pudieron cargar las actas para el año {selected_year}")

else:
    st.error("No se pudieron cargar los años disponibles. Verifica tu conexión a internet.")

# Información adicional
st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ Información")
st.sidebar.markdown("""
**Consejo Federal Pesquero**
- Sitio web: [cfp.gob.ar](https://cfp.gob.ar)
- Las actas son documentos públicos
- Formato: PDF
""")

st.sidebar.markdown("### 🛠️ Características")
st.sidebar.markdown("""
- ✅ Descarga individual
- ✅ Descarga masiva (ZIP)
- ✅ Filtros por tipo
- ✅ Cache inteligente
- ✅ Barra de progreso
- ✅ Manejo automático de SSL
""")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>🐟 CFP Actas Scraper | Desarrollado para facilitar el acceso a documentos públicos del Consejo Federal Pesquero</p>
</div>
""", unsafe_allow_html=True)