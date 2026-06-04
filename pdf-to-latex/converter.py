import os
import time
import subprocess
import shutil
import google.generativeai as genai
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

load_dotenv()

# ── Configuración ─────────────────────────────────────────────
INPUT_DIR  = os.path.join(os.path.dirname(__file__), "input")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TEMPLATE   = os.path.join(os.path.dirname(__file__), "template.tex")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# ── Leer template ─────────────────────────────────────────────
def read_template() -> str:
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        return f.read()

# ── Llamada a Gemini ──────────────────────────────────────────
def pdf_to_latex(pdf_path: str) -> str:
    template = read_template()

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    prompt = f"""Eres un asistente experto en LaTeX académico.
Se te entrega un documento PDF y un template LaTeX.
Tu tarea es extraer el contenido del PDF y reformatearlo
siguiendo EXACTAMENTE la estructura del template.

REGLAS ESTRICTAS:
1. Devuelve SOLO código LaTeX válido, sin explicaciones ni bloques de markdown.
2. No incluyas ```latex ni ``` en la respuesta.
3. Respeta todos los paquetes, geometría y formato del template.
4. Completa los campos TITULO, RAMO y SIGLA con la información del PDF.
5. El campo del logo (logonegrousm) déjalo tal cual, el usuario lo agrega manualmente.
6. Distribuye el contenido en las secciones: Resultados, Análisis, Conclusión.
7. Si hay tablas, ponlas en un Anexo con \\label y referéncialas con \\hyperref.
8. Si hay tablas anchas usa table* para que ocupen ambas columnas.
9. Si hay código usa el entorno verbatim.

TEMPLATE BASE:
{template}

Genera el documento LaTeX completo con el contenido del PDF adjunto."""

    response = model.generate_content([
        {"mime_type": "application/pdf", "data": pdf_bytes},
        prompt
    ])

    return response.text.strip()

# ── Compilar con pdflatex ─────────────────────────────────────
def compile_latex(tex_path: str, output_dir: str) -> bool:
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_path],
        capture_output=True,
        text=True
    )
    # Segunda pasada para referencias cruzadas e hyperref
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_path],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

# ── Limpiar archivos auxiliares de LaTeX ─────────────────────
def clean_aux_files(base_name: str, output_dir: str):
    extensions = [".aux", ".log", ".out", ".toc"]
    for ext in extensions:
        aux = os.path.join(output_dir, base_name + ext)
        if os.path.exists(aux):
            os.remove(aux)

# ── Procesar un PDF ───────────────────────────────────────────
def process_pdf(pdf_path: str):
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    tex_path  = os.path.join(OUTPUT_DIR, base_name + ".tex")

    print(f"\n[→] Procesando: {os.path.basename(pdf_path)}")

    # 1. Generar .tex con Gemini
    print("    Llamando a Gemini...")
    try:
        latex_code = pdf_to_latex(pdf_path)
    except Exception as e:
        print(f"    [ERROR] Gemini falló: {e}")
        return

    # 2. Guardar .tex en output/
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(latex_code)
    print(f"    .tex guardado → {tex_path}")

    # 3. Copiar logo al output/ si existe junto al template
    logo_src = os.path.join(os.path.dirname(__file__), "logonegrousm.png")
    logo_dst = os.path.join(OUTPUT_DIR, "logonegrousm.png")
    if os.path.exists(logo_src) and not os.path.exists(logo_dst):
        shutil.copy(logo_src, logo_dst)

    # 4. Compilar con pdflatex
    print("    Compilando con pdflatex...")
    success = compile_latex(tex_path, OUTPUT_DIR)

    if success:
        print(f"    [✓] PDF generado → {os.path.join(OUTPUT_DIR, base_name + '.pdf')}")
    else:
        print("    [!] pdflatex terminó con advertencias — revisa el .log en output/")

    # 5. Limpiar auxiliares
    clean_aux_files(base_name, OUTPUT_DIR)

    # 6. Mover PDF fuera de input/ una vez procesado
    done_path = pdf_path.replace("input", "input") + ".done"
    os.rename(pdf_path, pdf_path + ".done")
    print(f"    Archivo original renombrado a .done (ya procesado)")

# ── Watchdog handler ──────────────────────────────────────────
class PDFHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".pdf"):
            time.sleep(1)  # espera a que termine de copiarse
            process_pdf(event.src_path)

# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("╔══════════════════════════════════════╗")
    print("║      PDF → LaTeX Converter           ║")
    print("║  Suelta un PDF en la carpeta input/  ║")
    print("║  Ctrl+C para detener                 ║")
    print("╚══════════════════════════════════════╝")
    print(f"\nMonitoreando: {INPUT_DIR}")

    observer = Observer()
    observer.schedule(PDFHandler(), INPUT_DIR, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[✓] Converter detenido.")

    observer.join()
