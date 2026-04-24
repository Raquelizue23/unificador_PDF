from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Importar funciones del modulo principal (sin ejecutar main())
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from create_pdf import unir_pdfs, PROPORCION_PIE_PAGINA

# ---------------------------------------------------------------------------
# Configuracion de la pagina
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Unificador de PDFs",
    page_icon="📄",
    layout="centered",
)

st.title("📄 Unificador de PDFs")
st.markdown(
    "Une todos los archivos PDF de una carpeta en un solo documento. "
    "Opcionalmente puedes indicar una carpeta de destino para el resultado."
)

# ---------------------------------------------------------------------------
# Formulario
# ---------------------------------------------------------------------------
with st.form("form_unificar"):
    ruta_origen = st.text_input(
        "Ruta de la carpeta con los archivos PDF *",
        placeholder="Ejemplo: C:\\Documentos\\PDFs",
        help="Carpeta que contiene los archivos PDF que deseas unir.",
    )

    ruta_destino = st.text_input(
        "Ruta de destino para el PDF resultado (opcional)",
        placeholder="Ejemplo: C:\\Documentos\\resultado.pdf",
        help=(
            "Ruta completa donde se guardara el PDF unificado. "
            "Si no se indica, se crea 'pdf_unido.pdf' dentro de la carpeta origen."
        ),
    )

    proporcion_pie = st.slider(
        "Proporcion del pie de pagina (si hay plantilla)",
        min_value=0.01,
        max_value=1.0,
        value=PROPORCION_PIE_PAGINA,
        step=0.01,
        help=(
            "Fraccion vertical de la plantilla que se usara como pie de pagina. "
            "Solo aplica si existe un archivo 'plantilla.pdf' en la carpeta origen."
        ),
    )

    ejecutar = st.form_submit_button("Unir PDFs", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Procesamiento
# ---------------------------------------------------------------------------
if ejecutar:
    # Validar campo obligatorio
    if not ruta_origen.strip():
        st.error("Debes indicar la ruta de la carpeta con los archivos PDF.")
        st.stop()

    carpeta = Path(ruta_origen.strip()).expanduser().resolve()

    if not carpeta.exists():
        st.error(f"La ruta indicada no existe: `{carpeta}`")
        st.stop()

    if not carpeta.is_dir():
        st.error(f"La ruta indicada no es una carpeta: `{carpeta}`")
        st.stop()

    # Resolver ruta de salida
    if ruta_destino.strip():
        salida = Path(ruta_destino.strip()).expanduser().resolve()
    else:
        salida = carpeta / "pdf_unido.pdf"

    # Ejecutar unificacion
    with st.spinner("Uniendo archivos PDF..."):
        try:
            archivos_procesados, total_paginas, errores, ruta_plantilla = unir_pdfs(
                carpeta=carpeta,
                salida=salida,
                plantilla=None,
                proporcion_pie=proporcion_pie,
            )
        except FileNotFoundError as e:
            st.error(f"No se encontraron archivos: {e}")
            st.stop()
        except RuntimeError as e:
            st.error(f"Error durante el proceso: {e}")
            st.stop()
        except Exception as e:
            st.error(f"Error inesperado: {e}")
            st.stop()

    # Resultado exitoso
    st.success("✅ PDF unificado generado correctamente.")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Archivos PDF unidos", archivos_procesados)
    with col2:
        st.metric("Paginas totales", total_paginas)

    st.info(f"Archivo guardado en: `{salida}`")

    if ruta_plantilla:
        st.info(f"Plantilla aplicada desde: `{ruta_plantilla}`")
    else:
        st.caption("No se detecto ninguna plantilla (plantilla.pdf).")

    if errores:
        with st.expander("⚠️ Problemas encontrados durante el proceso"):
            for error in errores:
                st.warning(error)

    # Ofrecer descarga del PDF generado
    try:
        with open(salida, "rb") as f:
            pdf_bytes = f.read()
        st.download_button(
            label="⬇️ Descargar PDF unificado",
            data=pdf_bytes,
            file_name=salida.name,
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception:
        st.caption("No fue posible ofrecer la descarga directa del archivo.")
