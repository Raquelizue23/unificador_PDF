from __future__ import annotations

import copy
import importlib
import io
import tempfile
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import io
import streamlit as st

PROPORCION_PIE_PAGINA = 0.08


# ---------------------------------------------------------------------------
# Logica de union de PDFs (opera sobre bytes, sin rutas locales)
# ---------------------------------------------------------------------------

def cargar_libreria_pdf():
    for nombre_modulo in ("pypdf", "PyPDF2"):
        try:
            modulo = importlib.import_module(nombre_modulo)
            return modulo.PdfReader, modulo.PdfWriter, modulo.Transformation
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError(
        "No se encontro una libreria compatible. Instala 'pypdf' con: pip install pypdf"
    )


def leer_paginas_desde_bytes(pdf_reader, contenido: bytes, nombre: str) -> list:
    lector = pdf_reader(io.BytesIO(contenido))
    if lector.is_encrypted:
        try:
            lector.decrypt("")
        except Exception as error:
            raise RuntimeError(f"No se pudo leer el PDF protegido: {nombre}") from error
    return list(lector.pages)


def aplicar_pie_de_pagina(pagina, pagina_plantilla, transformacion_pdf, proporcion_pie: float):
    pie = copy.deepcopy(pagina_plantilla)
    ancho_fuente = float(pie.mediabox.width)
    alto_fuente = float(pie.mediabox.height)
    ancho_destino = float(pagina.mediabox.width)
    alto_destino = float(pagina.mediabox.height)

    altura_pie_fuente = alto_fuente * proporcion_pie
    altura_pie_destino = alto_destino * proporcion_pie

    if altura_pie_fuente <= 0 or altura_pie_destino <= 0:
        return pagina

    limite_inferior = float(pie.mediabox.bottom)
    limite_superior = min(limite_inferior + altura_pie_fuente, float(pie.mediabox.top))

    pie.mediabox.lower_left = (float(pie.mediabox.left), limite_inferior)
    pie.mediabox.upper_right = (float(pie.mediabox.right), limite_superior)
    pie.cropbox.lower_left = (float(pie.cropbox.left), limite_inferior)
    pie.cropbox.upper_right = (float(pie.cropbox.right), limite_superior)

    escala_x = ancho_destino / ancho_fuente
    escala_y = altura_pie_destino / altura_pie_fuente
    transformacion = transformacion_pdf().scale(sx=escala_x, sy=escala_y)
    pagina.merge_transformed_page(pie, transformacion, over=True)
    return pagina

def crear_overlay_paginacion(
    pdf_reader,
    ancho,
    alto,
    pagina_actual,
    total_paginas,
):
    buffer = io.BytesIO()

    c = canvas.Canvas(buffer, pagesize=(ancho, alto))

    texto = f"Página {pagina_actual} de {total_paginas}"

    c.setFont("Helvetica", 9)

    c.drawRightString(
        ancho - 15 * mm,
        8 * mm,
        texto
    )

    c.save()

    buffer.seek(0)

    return pdf_reader(buffer).pages[0]

def aplicar_numeracion(
    pagina,
    pdf_reader,
    pagina_actual,
    total_paginas,
):
    ancho = float(pagina.mediabox.width)
    alto = float(pagina.mediabox.height)

    overlay = crear_overlay_paginacion(
        pdf_reader,
        ancho,
        alto,
        pagina_actual,
        total_paginas,
    )

    pagina.merge_page(overlay)

    return pagina

def unir_pdfs_desde_uploads(
    archivos_subidos: list,
    plantilla_subida=None,
    proporcion_pie: float = PROPORCION_PIE_PAGINA,
) -> tuple[bytes, int, int, list[str]]:
    """
    Recibe listas de UploadedFile de Streamlit.
    Devuelve (pdf_bytes, archivos_procesados, total_paginas, errores).
    """
    pdf_reader, pdf_writer, transformacion_pdf = cargar_libreria_pdf()
    escritor = pdf_writer()
    errores: list[str] = []
    paginas_consolidadas = []
    pagina_pie = None

    # Ordenar archivos subidos por nombre (igual que la version CLI)
    archivos_ordenados = sorted(archivos_subidos, key=lambda f: f.name.lower())

    # Procesar plantilla si se subio
    if plantilla_subida:
        try:
            contenido_plantilla = plantilla_subida.read()
            paginas_plantilla = leer_paginas_desde_bytes(
                pdf_reader, contenido_plantilla, plantilla_subida.name
            )
            if not paginas_plantilla:
                raise RuntimeError(f"La plantilla {plantilla_subida.name} no contiene paginas.")
            # Leer de nuevo para el pie (los streams ya se consumieron)
            paginas_plantilla_pie = leer_paginas_desde_bytes(
                pdf_reader, contenido_plantilla, plantilla_subida.name
            )
            paginas_consolidadas.extend(paginas_plantilla)
            pagina_pie = paginas_plantilla_pie[1]
        except Exception as error:
            raise RuntimeError(f"No fue posible cargar la plantilla: {error}") from error

    # Procesar archivos PDF
    archivos_procesados = 0
    for archivo in archivos_ordenados:
        try:
            contenido = archivo.read()
            paginas = leer_paginas_desde_bytes(pdf_reader, contenido, archivo.name)
            paginas_consolidadas.extend(paginas)
            archivos_procesados += 1
        except Exception as error:
            errores.append(f"Error al procesar {archivo.name}: {error}")

    if archivos_procesados == 0:
        raise RuntimeError("No fue posible unir ningun archivo PDF valido.")

    total_paginas = len(paginas_consolidadas)

    # Aplicar pie de pagina si hay plantilla
    if pagina_pie:
        for i in range(1, len(paginas_consolidadas)):

            paginas_consolidadas[i] = aplicar_pie_de_pagina(
                paginas_consolidadas[i],
                pagina_pie,
                transformacion_pdf,
                proporcion_pie
            )

            paginas_consolidadas[i] = aplicar_numeracion(
                paginas_consolidadas[i],
                pdf_reader,
                i + 1,
                total_paginas
            )

    for pagina in paginas_consolidadas:
        escritor.add_page(pagina)

    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue(), archivos_procesados, total_paginas, errores


# ---------------------------------------------------------------------------
# Interfaz Streamlit
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Unificador de PDFs",
    page_icon="📄",
    layout="centered",
)

st.title("📄 Unificador de PDFs")
st.markdown(
    "Sube los archivos PDF que deseas unir y descarga el resultado consolidado."
)

# ---------------------------------------------------------------------------
# Carga de archivos
# ---------------------------------------------------------------------------
archivos_subidos = st.file_uploader(
    "Selecciona los archivos PDF a unir *",
    type="pdf",
    accept_multiple_files=True,
    help="Puedes seleccionar varios archivos a la vez. Se uniran en orden alfabetico por nombre.",
)

plantilla_subida = st.file_uploader(
    "Plantilla PDF (opcional)",
    type="pdf",
    accept_multiple_files=False,
    help=(
        "PDF del que se tomara el pie de pagina. Sus paginas se insertan al inicio "
        "y su franja inferior se aplica como pie en todas las paginas."
    ),
)

proporcion_pie = st.slider(
    "Proporcion del pie de pagina",
    min_value=0.01,
    max_value=1.0,
    value=PROPORCION_PIE_PAGINA,
    step=0.01,
    disabled=plantilla_subida is None,
    help="Solo aplica si subiste una plantilla. Fraccion vertical usada como pie de pagina.",
)

nombre_salida = st.text_input(
    "Nombre del archivo resultado (opcional)",
    placeholder="pdf_unido.pdf",
    help="Nombre con el que se descargara el PDF unificado. Por defecto: pdf_unido.pdf",
)

ejecutar = st.button("Unir PDFs", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Procesamiento
# ---------------------------------------------------------------------------
if ejecutar:
    if not archivos_subidos:
        st.error("Debes subir al menos un archivo PDF.")
        st.stop()

    nombre_final = nombre_salida.strip() or "pdf_unido.pdf"
    if not nombre_final.lower().endswith(".pdf"):
        nombre_final += ".pdf"

    with st.spinner("Uniendo archivos PDF..."):
        try:
            pdf_bytes, archivos_procesados, total_paginas, errores = unir_pdfs_desde_uploads(
                archivos_subidos=archivos_subidos,
                plantilla_subida=plantilla_subida,
                proporcion_pie=proporcion_pie,
            )
        except RuntimeError as e:
            st.error(f"Error durante el proceso: {e}")
            st.stop()
        except Exception as e:
            st.error(f"Error inesperado: {e}")
            st.stop()

    st.success("PDF unificado generado correctamente.")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Archivos PDF unidos", archivos_procesados)
    with col2:
        st.metric("Paginas totales", total_paginas)

    if plantilla_subida:
        st.info(f"Plantilla aplicada: `{plantilla_subida.name}`")
    else:
        st.caption("No se uso plantilla.")

    if errores:
        with st.expander("Problemas encontrados durante el proceso"):
            for error in errores:
                st.warning(error)

    st.download_button(
        label="Descargar PDF unificado",
        data=pdf_bytes,
        file_name=nombre_final,
        mime="application/pdf",
        use_container_width=True,
    )
