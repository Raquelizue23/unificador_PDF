from __future__ import annotations

import argparse
import copy
import importlib
import sys
from pathlib import Path


PROPORCION_PIE_PAGINA = 0.08


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


def resolver_plantilla(carpeta: Path, plantilla: str | None, salida: Path) -> Path | None:
    if not plantilla:
        plantilla_detectada = carpeta / "plantilla.pdf"
        if plantilla_detectada.is_file() and plantilla_detectada.resolve() != salida.resolve():
            return plantilla_detectada.resolve()
        return None

    ruta_plantilla = Path(plantilla).expanduser()

    if not ruta_plantilla.is_absolute():
        ruta_plantilla = (carpeta / ruta_plantilla).resolve()
    else:
        ruta_plantilla = ruta_plantilla.resolve()

    if not ruta_plantilla.exists():
        raise FileNotFoundError(f"No existe la plantilla indicada: {ruta_plantilla}")

    if not ruta_plantilla.is_file() or ruta_plantilla.suffix.lower() != ".pdf":
        raise ValueError("La plantilla indicada debe ser un archivo PDF.")

    if ruta_plantilla == salida.resolve():
        raise ValueError("La plantilla no puede ser el mismo archivo que la salida.")

    return ruta_plantilla


def obtener_archivos_pdf(carpeta: Path, salida: Path, plantilla: Path | None) -> list[Path]:
    archivos = []
    salida_predeterminada = (carpeta / "pdf_unido.pdf").resolve()

    for archivo in sorted(carpeta.iterdir(), key=lambda item: item.name.lower()):
        if not archivo.is_file():
            continue

        if archivo.suffix.lower() != ".pdf":
            continue

        if archivo.resolve() == salida.resolve():
            continue

        if archivo.resolve() == salida_predeterminada:
            continue

        if plantilla and archivo.resolve() == plantilla.resolve():
            continue

        archivos.append(archivo)

    return archivos


def leer_paginas_pdf(pdf_reader, archivo_pdf: Path) -> list:
    lector = pdf_reader(str(archivo_pdf))

    if lector.is_encrypted:
        try:
            lector.decrypt("")
        except Exception as error:
            raise RuntimeError(
                f"No se pudo leer el PDF protegido: {archivo_pdf.name}"
            ) from error

    return list(lector.pages)


def obtener_pagina_pie(pdf_reader, ruta_plantilla: Path):
    paginas_plantilla = leer_paginas_pdf(pdf_reader, ruta_plantilla)

    if not paginas_plantilla:
        raise RuntimeError(f"La plantilla {ruta_plantilla.name} no contiene paginas.")

    return paginas_plantilla[0]


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


def unir_pdfs(
    carpeta: Path,
    salida: Path,
    plantilla: str | None,
    proporcion_pie: float = PROPORCION_PIE_PAGINA,
) -> tuple[int, int, list[str], Path | None]:
    pdf_reader, pdf_writer, transformacion_pdf = cargar_libreria_pdf()
    escritor = pdf_writer()
    errores = []
    ruta_plantilla = resolver_plantilla(carpeta, plantilla, salida)
    archivos_pdf = obtener_archivos_pdf(carpeta, salida, ruta_plantilla)
    pagina_pie = None

    if not archivos_pdf:
        raise FileNotFoundError("No se encontraron archivos PDF en la carpeta indicada.")

    archivos_procesados = 0
    paginas_consolidadas = []

    if ruta_plantilla:
        try:
            paginas_plantilla_inicio = leer_paginas_pdf(pdf_reader, ruta_plantilla)
            if not paginas_plantilla_inicio:
                raise RuntimeError(
                    f"La plantilla {ruta_plantilla.name} no contiene paginas."
                )

            paginas_plantilla_pie = leer_paginas_pdf(pdf_reader, ruta_plantilla)
            paginas_consolidadas.extend(paginas_plantilla_inicio)
            pagina_pie = paginas_plantilla_pie[0]
        except Exception as error:
            raise RuntimeError(
                f"No fue posible cargar la plantilla {ruta_plantilla.name}: {error}"
            ) from error

    for archivo_pdf in archivos_pdf:
        try:
            paginas_pdf = leer_paginas_pdf(pdf_reader, archivo_pdf)

            paginas_consolidadas.extend(paginas_pdf)
            archivos_procesados += 1
        except Exception as error:
            errores.append(f"Error al procesar {archivo_pdf.name}: {error}")

    if archivos_procesados == 0:
        raise RuntimeError("No fue posible unir ningun archivo PDF valido.")

    total_paginas = len(paginas_consolidadas)

    if pagina_pie:
        paginas_consolidadas = [
            aplicar_pie_de_pagina(pagina, pagina_pie, transformacion_pdf, proporcion_pie)
            for pagina in paginas_consolidadas
        ]

    for pagina in paginas_consolidadas:
        escritor.add_page(pagina)

    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("wb") as archivo_salida:
        escritor.write(archivo_salida)

    return archivos_procesados, total_paginas, errores, ruta_plantilla


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Une todos los archivos PDF de una carpeta en un solo documento."
    )
    parser.add_argument(
        "ruta",
        help="Ruta de la carpeta que contiene los archivos PDF.",
    )
    parser.add_argument(
        "-o",
        "--salida",
        help="Ruta del PDF resultante. Si no se indica, se crea 'pdf_unido.pdf' dentro de la carpeta.",
    )
    parser.add_argument(
        "--plantilla",
        help=(
            "Ruta del PDF de plantilla del que se tomara el pie de pagina. "
            "Si no se indica, el programa usa 'plantilla.pdf' dentro de la carpeta cuando existe."
        ),
    )
    parser.add_argument(
        "--proporcion-pie",
        type=float,
        default=PROPORCION_PIE_PAGINA,
        help=(
            "Proporcion vertical de la plantilla que se usara como pie de pagina. "
            "Por defecto es 0.14 (14%% inferior de la plantilla)."
        ),
    )
    return parser


def main() -> int:
    parser = crear_parser()
    args = parser.parse_args()

    carpeta = Path(args.ruta).expanduser().resolve()

    if not carpeta.exists():
        print("La ruta indicada no existe.", file=sys.stderr)
        return 1

    if not carpeta.is_dir():
        print("La ruta indicada no es una carpeta.", file=sys.stderr)
        return 1

    if args.salida:
        salida = Path(args.salida).expanduser().resolve()
    else:
        salida = carpeta / "pdf_unido.pdf"

    if not 0 < args.proporcion_pie <= 1:
        print("El valor de --proporcion-pie debe ser mayor que 0 y menor o igual a 1.", file=sys.stderr)
        return 1

    try:
        archivos_procesados, total_paginas, errores, ruta_plantilla = unir_pdfs(
            carpeta,
            salida,
            args.plantilla,
            args.proporcion_pie,
        )
    except Exception as error:
        print(f"No se pudo generar el PDF: {error}", file=sys.stderr)
        return 1

    print(f"PDF generado correctamente en: {salida}")
    print(f"Archivos PDF unidos: {archivos_procesados}")
    print(f"Paginas totales del consolidado: {total_paginas}")

    if ruta_plantilla:
        print(f"Plantilla agregada al inicio y pie aplicado desde: {ruta_plantilla}")
    else:
        print("Plantilla agregada al inicio y pie aplicado desde: ninguna")

    if errores:
        print("Se encontraron algunos problemas durante el proceso:")
        for error in errores:
            print(f"- {error}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
