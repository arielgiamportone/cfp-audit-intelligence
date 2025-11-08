# 🐟 CFP Actas Scraper

Una aplicación web desarrollada con Streamlit para facilitar la descarga de actas públicas del Consejo Federal Pesquero (CFP) de Argentina.

## 🚀 Características

- **Interfaz intuitiva**: Selección fácil de años y actas
- **Descarga individual**: Descarga actas específicas en formato PDF
- **Descarga masiva**: Descarga todas las actas de un año en un archivo ZIP
- **Filtros inteligentes**: Separa actas principales de anexos
- **Cache optimizado**: Mejora el rendimiento evitando consultas repetidas
- **Barra de progreso**: Seguimiento visual del progreso de descarga
- **Responsive**: Funciona en dispositivos móviles y desktop

## 📋 Requisitos

- Python 3.8 o superior
- Conexión a internet para acceder al sitio del CFP

## 🛠️ Instalación

1. **Clona o descarga los archivos del proyecto**

2. **Instala las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Ejecuta la aplicación:**
   ```bash
   streamlit run cfp_scraper.py
   ```

4. **Abre tu navegador** en la dirección que muestra Streamlit (generalmente `http://localhost:8501`)

## 📖 Uso

### Selección de Año
1. En la barra lateral izquierda, selecciona el año de interés
2. La aplicación cargará automáticamente todas las actas disponibles para ese año

### Filtros
- **Incluir anexos**: Muestra/oculta documentos anexos
- **Incluir actas principales**: Muestra/oculta actas principales

### Descarga Individual
1. Busca el acta que necesitas en la lista
2. Haz clic en "⬇️ Descargar" junto al acta deseada
3. Espera a que se complete la descarga
4. Haz clic en "💾 Guardar" para descargar el archivo

### Descarga Masiva
1. Configura los filtros según tus necesidades
2. Haz clic en "⬇️ Descargar todas las actas seleccionadas"
3. Confirma la descarga si hay más de 10 archivos
4. Espera a que se genere el archivo ZIP
5. Descarga el archivo ZIP con todas las actas

## 🔧 Funcionalidades Técnicas

### Web Scraping
- Utiliza `requests` y `BeautifulSoup` para extraer datos del sitio oficial del CFP
- Maneja errores de conexión y timeouts
- Respeta la estructura del sitio web oficial

### Cache Inteligente
- Cache de 1 hora para listas de años y actas
- Botón de actualización manual para forzar la recarga de datos
- Mejora significativamente el rendimiento

### Gestión de Archivos
- Descarga streaming para archivos grandes
- Compresión ZIP para descargas masivas
- Nombres de archivo preservados del sitio original

## 🌐 Fuente de Datos

Los datos se obtienen directamente del sitio oficial del Consejo Federal Pesquero:
- **URL base**: https://cfp.gob.ar
- **Sección de actas**: https://cfp.gob.ar/actas-cfp
- **Años disponibles**: 1998 - 2025 (según disponibilidad)

## ⚠️ Consideraciones

- **Uso responsable**: La aplicación incluye pausas entre descargas para no sobrecargar el servidor
- **Documentos públicos**: Todas las actas son documentos de acceso público
- **Conexión requerida**: Necesitas conexión a internet para acceder a los datos
- **Límites de descarga**: Para descargas masivas de más de 10 archivos, se solicita confirmación

## 🐛 Solución de Problemas

### Error de conexión
- Verifica tu conexión a internet
- Comprueba que el sitio del CFP esté disponible
- Usa el botón "🔄 Actualizar datos" para reintentar

### Descarga lenta
- Las descargas dependen de la velocidad de tu conexión
- El servidor del CFP puede tener limitaciones de velocidad
- Para archivos grandes, ten paciencia

### Archivo no encontrado
- Algunos enlaces pueden estar rotos en el sitio original
- Intenta acceder directamente al sitio del CFP para verificar

## 📝 Estructura del Proyecto

```
CFP_Actas/
├── cfp_scraper.py          # Aplicación principal de Streamlit
├── requirements.txt        # Dependencias de Python
├── README.md              # Este archivo
├── cfpweb_actas1.html     # Archivo de ejemplo (página principal)
├── cfp_actas_2024.html    # Archivo de ejemplo (actas 2024)
└── cfp_actas_1998.html    # Archivo de ejemplo (actas 1998)
```

## 🤝 Contribuciones

Si encuentras errores o tienes sugerencias de mejora:
1. Reporta el problema describiendo los pasos para reproducirlo
2. Incluye capturas de pantalla si es relevante
3. Menciona tu sistema operativo y versión de Python

## 📄 Licencia

Este proyecto es de uso libre para fines educativos y de investigación. Los documentos descargados son propiedad del Consejo Federal Pesquero de Argentina.

---

**Desarrollado para facilitar el acceso a documentos públicos del sector pesquero argentino** 🇦🇷