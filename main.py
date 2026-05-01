import flet as ft
import sqlite3
import google.generativeai as genai
from pypdf import PdfReader
import json
import os
import random 
import re 

DB_NAME = os.path.join(os.getcwd(), "diccionario.db")
API_KEY = ""  

model = None
if API_KEY != "PEGAR_TU_API_KEY_AQUI":
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        print(f"Error configurando IA: {e}")
        model = None

# Establece y devuelve una conexión a la base de datos SQLite.
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    return conn

# Crea la tabla 'palabras' en la base de datos si esta no existe previamente.
def crear_tabla():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS palabras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            palabra_aleman TEXT NOT NULL UNIQUE,
            traduccion_espanol TEXT NOT NULL,
            descripcion TEXT,
            genero TEXT,
            casos TEXT,
            ejemplos TEXT
        );
    """)
    conn.commit()
    conn.close()

# Inserta un nuevo registro de palabra en la base de datos.
def agregar_palabra(aleman, espanol, descripcion, genero="", casos="", ejemplos=""):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO palabras 
               (palabra_aleman, traduccion_espanol, descripcion, genero, casos, ejemplos) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (aleman, espanol, descripcion, genero, casos, ejemplos)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# Actualiza los datos de una palabra existente en la base de datos mediante su ID.
def editar_palabra(id_palabra, aleman, espanol, desc, genero, casos, ejemplos):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE palabras 
            SET palabra_aleman = ?, traduccion_espanol = ?, descripcion = ?, 
                genero = ?, casos = ?, ejemplos = ?
            WHERE id = ?
        """, (aleman, espanol, desc, genero, casos, ejemplos, id_palabra))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

# Elimina el registro de una palabra en la base de datos utilizando su ID.
def borrar_palabra(id_palabra):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM palabras WHERE id = ?", (id_palabra,))
    conn.commit()
    conn.close()

# Busca coincidencias parciales del término dado en las columnas de alemán y español.
def buscar_palabra(termino):
    conn = get_db_connection()
    cursor = conn.cursor()
    termino_busqueda = f"%{termino.lower()}%"
    cursor.execute(
        """SELECT id, palabra_aleman, traduccion_espanol, descripcion, genero, casos, ejemplos 
           FROM palabras 
           WHERE lower(palabra_aleman) LIKE ? OR lower(traduccion_espanol) LIKE ?""",
        (termino_busqueda, termino_busqueda)
    )
    resultados = cursor.fetchall()
    conn.close()
    return resultados

# Recupera y devuelve todos los registros de palabras almacenados, ordenados alfabéticamente.
def obtener_todas():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, palabra_aleman, traduccion_espanol, descripcion, genero, casos, ejemplos FROM palabras ORDER BY palabra_aleman ASC")
    resultados = cursor.fetchall()
    conn.close()
    return resultados

# Función principal que inicializa y gestiona la interfaz gráfica y eventos de la aplicación.
def main(page: ft.Page):
    page.title = "Diccionario Alemán"
    page.theme_mode = ft.ThemeMode.LIGHT 
    page.padding = 0

    # Procesa un texto de ejemplo usando la API de Gemini para extraer vocabulario estructurado en JSON.
    def extraer_de_ejemplo(texto_ejemplo):
        if model is None: return "Sin API Key", False
        if not texto_ejemplo or len(texto_ejemplo) < 5: return "Ejemplo vacío", False

        prompt = f"""
        Traducción formal.
        Analiza la frase: "{texto_ejemplo}"
        Extrae vocabulario (Sustantivos, Verbos, Adjetivos).
        FORMATO JSON OBLIGATORIO:
        [ {{ "aleman": "...", "espanol": "...", "descripcion": "...", "genero": "...", "casos": "", "ejemplos": "Aleman (Espanol)" }} ]
        """
        try:
            response = model.generate_content(prompt)
            match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if match:
                datos = json.loads(match.group(0))
                cnt = 0
                for item in datos:
                    agregar_palabra(item.get("aleman", ""), item.get("espanol", ""), item.get("descripcion", ""), item.get("genero", ""), item.get("casos", ""), item.get("ejemplos", ""))
                    cnt += 1
                msg = f"{cnt} palabras extraídas."
                return msg, True
            else: return "IA confusa.", False
        except Exception as e: return f"Error IA: {e}", False

    # Extrae texto de un archivo PDF y utiliza la API de Gemini para identificar y traducir vocabulario relevante.
    def procesar_pdf_con_ia(ruta_archivo):
        if model is None: return "ERROR: No has puesto tu API KEY.", False
        texto_completo = ""
        try:
            reader = PdfReader(ruta_archivo)
            for i in range(min(10, len(reader.pages))):
                t = reader.pages[i].extract_text()
                if t: texto_completo += t + " "
        except Exception as e: return f"Error PDF: {e}", False

        if not texto_completo: return "PDF vacío", False

        palabras_brutas = re.findall(r'\b[A-ZÄÖÜ][a-zäöüß]+\b', texto_completo)
        seleccion = list(set([p for p in palabras_brutas if len(p) > 3]))[:10]
        if not seleccion: return "Sin palabras clave.", False
        
        prompt = f"""
        Actúa como profesor de alemán. Traducción formal.
        Crea entradas para: [{", ".join(seleccion)}]
        FORMATO JSON: [ {{ "aleman": "...", "espanol": "...", "descripcion": "...", "genero": "...", "casos": "", "ejemplos": "Aleman (Espanol)" }} ]
        """
        try:
            response = model.generate_content(prompt)
            match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if match:
                datos = json.loads(match.group(0))
                cnt = 0
                for item in datos:
                    agregar_palabra(item.get("aleman", ""), item.get("espanol", ""), item.get("descripcion", ""), item.get("genero", ""), item.get("casos", ""), item.get("ejemplos", ""))
                    cnt += 1
                msg = f"Éxito. {cnt} nuevas."
                return msg, True
            else: return "Error formato IA", False
        except Exception as e: return f"Error IA: {e}", False

    txt_aleman = ft.TextField(label="Alemán", multiline=True, max_lines=2)
    txt_espanol = ft.TextField(label="Español", multiline=True, max_lines=2)
    dd_genero = ft.Dropdown(label="Género", width=150, options=[ft.dropdown.Option("Der (Masc)"), ft.dropdown.Option("Die (Fem)"), ft.dropdown.Option("Das (Neu)"), ft.dropdown.Option("Plural"), ft.dropdown.Option("Sin género")])
    txt_casos = ft.TextField(label="Casos / Plural")
    txt_ejemplos = ft.TextField(label="Ejemplos: Alemán (Español)", multiline=True)
    txt_desc = ft.TextField(label="Notas", multiline=True)

    # Valida y guarda manualmente una nueva palabra introducida en los campos de texto de la interfaz.
    def guardar_manual(e):
        if not txt_aleman.value or not txt_espanol.value: page.open(ft.SnackBar(ft.Text("Faltan datos"))); return
        g = "" if not dd_genero.value or dd_genero.value == "Sin género" else dd_genero.value
        if agregar_palabra(txt_aleman.value, txt_espanol.value, txt_desc.value, g, txt_casos.value, txt_ejemplos.value):
            page.open(ft.SnackBar(ft.Text("Guardado"), bgcolor="green"))
            txt_aleman.value=""; txt_espanol.value=""; txt_desc.value=""; txt_casos.value=""; txt_ejemplos.value=""; txt_aleman.focus(); buscar_change(None)
        else: page.open(ft.SnackBar(ft.Text("Ya existe"), bgcolor="red"))

    btn_guardar = ft.ElevatedButton("Guardar", on_click=guardar_manual, width=200)

    # Verifica la integridad del archivo de la base de datos y añade columnas faltantes si es necesario.
    def reparar_db_click(e):
        estado_msg = ""
        if not os.path.exists(DB_NAME):
            try:
                crear_tabla() 
                estado_msg = "Archivo perdido. SE HA CREADO UNA DB NUEVA."
            except Exception as ex:
                estado_msg = f"Error crítico creando DB: {ex}"
        else:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cambios = 0
                for col in ["genero", "casos", "ejemplos"]: 
                    try: 
                        cur.execute(f"ALTER TABLE palabras ADD COLUMN {col} TEXT")
                        cambios += 1
                    except: pass
                conn.commit()
                conn.close()
                if cambios > 0:
                    estado_msg = f"DB reparada ({cambios} columnas añadidas)."
                else:
                    estado_msg = "La base de datos está perfecta y conectada."
            except Exception as ex:
                estado_msg = f"Error de conexión: {ex}"
        
        page.open(ft.SnackBar(ft.Text(estado_msg), bgcolor="blue" if "reparada" in estado_msg or "perfecta" in estado_msg else "orange"))
        buscar_change(None)

    # Maneja el evento de selección de un archivo PDF, procesando su contenido y actualizando la interfaz.
    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files:
            progress_bar.visible = True; lbl_status.value = f"Analizando {e.files[0].name}..."; page.update()
            mensaje, exito = procesar_pdf_con_ia(e.files[0].path)
            progress_bar.visible = False; lbl_status.value = mensaje; lbl_status.color = "green" if exito else "red"
            if exito: buscar_change(None)
            page.update()

    file_picker = ft.FilePicker(on_result=on_file_picked); page.overlay.append(file_picker)
    progress_bar = ft.ProgressBar(width=200, color="blue", visible=False)
    lbl_status = ft.Text("...", color="grey", text_align="center")
    
    btn_importar = ft.ElevatedButton("Importar PDF", bgcolor=ft.Colors.ORANGE_100, color=ft.Colors.ORANGE_900, width=250, on_click=lambda _: file_picker.pick_files(allow_multiple=False, allowed_extensions=["pdf"]))
    btn_reparar = ft.ElevatedButton("Buscar y Reparar DB", bgcolor=ft.Colors.BLUE_GREY_100, color=ft.Colors.BLUE_GREY_900, width=250, on_click=reparar_db_click)
    switch_tema = ft.Switch(label="Modo Oscuro", on_change=lambda e: (setattr(page, 'theme_mode', ft.ThemeMode.DARK if e.control.value else ft.ThemeMode.LIGHT), page.update()))

    lista_resultados = ft.ListView(expand=True, spacing=5, padding=10)

    # Gestiona el evento de clic para borrar una palabra y actualiza la lista de resultados.
    def borrar_click(id_p, e): 
        borrar_palabra(id_p)
        buscar_change(None)
        page.open(ft.SnackBar(ft.Text("Borrado")))
    
    # Abre un cuadro de diálogo con los datos de una palabra para permitir su edición.
    def editar_dialog(id_p, datos):
        (a, e, d, g, c, ej) = datos
        ea=ft.TextField(label="Alemán", value=a); ee=ft.TextField(label="Español", value=e); eg=ft.Dropdown(label="Género", value=g, options=dd_genero.options)
        ec=ft.TextField(label="Casos", value=c); eej=ft.TextField(label="Ejemplos", value=ej, multiline=True); ed=ft.TextField(label="Notas", value=d, multiline=True)
        dlg = ft.AlertDialog(title=ft.Text("Editar"), content=ft.Column([ea,ee,eg,ec,eej,ed], height=400, scroll="auto"), 
            actions=[ft.TextButton("Guardar", on_click=lambda _: (editar_palabra(id_p, ea.value, ee.value, ed.value, eg.value, ec.value, eej.value), page.close(dlg), buscar_change(None)))])
        page.open(dlg)

    # Gestiona el evento de clic para extraer vocabulario de un ejemplo usando la IA y notifica el resultado.
    def btn_extraer_click(txt, e):
        page.open(ft.SnackBar(ft.Text("Analizando ejemplo..."), duration=2000))
        msg, ok = extraer_de_ejemplo(txt)
        page.open(ft.SnackBar(ft.Text(msg), bgcolor="green" if ok else "red"))
        if ok: buscar_change(None)

    # Filtra y actualiza la lista de resultados en la interfaz basándose en el término de búsqueda.
    def buscar_change(e):
        termino = txt_buscar.value
        lista_resultados.controls.clear()
        try:
            resultados = buscar_palabra(termino) if termino else obtener_todas()
        except Exception:
            lista_resultados.controls.append(ft.Text("Error de conexión DB. Pulsa 'Reparar DB' en Más.", color="red"))
            page.update()
            return

        if not resultados: lista_resultados.controls.append(ft.Text("Sin resultados", color="grey"))
        else:
            for row in resultados:
                id_p, aleman, espanol, desc, genero, casos, ejemplos = row
                texto_genero = genero if genero and genero not in ["N/A", "Sin género"] else "Sin género"
                
                c_txt, c_bg = (ft.Colors.ON_SURFACE, ft.Colors.TRANSPARENT)
                if "Die" in texto_genero: c_txt, c_bg = ft.Colors.PINK_200, ft.Colors.with_opacity(0.2, ft.Colors.PINK)
                elif "Der" in texto_genero: c_txt, c_bg = ft.Colors.BLUE_200, ft.Colors.with_opacity(0.2, ft.Colors.BLUE)
                elif "Das" in texto_genero: c_txt, c_bg = ft.Colors.GREEN_200, ft.Colors.with_opacity(0.2, ft.Colors.GREEN)
                
                contenido = ft.Column([
                    ft.Divider(),
                    ft.Row([ft.Column([ft.Text("GÉNERO", size=10, weight="bold"), ft.Container(content=ft.Text(texto_genero, weight="bold", color=c_txt), bgcolor=c_bg, padding=5, border_radius=5)]),
                            ft.Column([ft.Text("CASOS", size=10, weight="bold"), ft.Text(casos or "-")])], alignment="spaceBetween"),
                    ft.Text("EJEMPLOS:", size=10, weight="bold"),
                    ft.Container(content=ft.Column([ft.Text(ejemplos or "-", italic=True), ft.Row([ft.TextButton("Extraer IA", style=ft.ButtonStyle(color="amber"), on_click=lambda e, t=ejemplos: btn_extraer_click(t, e)) if ejemplos else ft.Container()], alignment="end")]), bgcolor="secondaryContainer", padding=10, border_radius=5, width=float("inf")),
                    ft.Text("NOTAS:", size=10, weight="bold"), ft.Text(desc or "-", size=12),
                    ft.Row([ft.TextButton("Editar", on_click=lambda e, i=id_p, d=row[1:]: editar_dialog(i, d)), ft.TextButton("Borrar", style=ft.ButtonStyle(color="red"), on_click=lambda e, i=id_p: borrar_click(i, e))], alignment="end")
                ], spacing=5)
                lista_resultados.controls.append(ft.Card(content=ft.ExpansionTile(title=ft.Text(aleman, weight="bold"), subtitle=ft.Text(espanol, size=14, color="grey"), controls=[ft.Container(padding=15, content=contenido)])))
        page.update()

    txt_buscar = ft.TextField(label="Buscar...", on_change=buscar_change)
    
    tab_buscar = ft.Container(padding=10, content=ft.Column([txt_buscar, lista_resultados], expand=True))
    tab_agregar = ft.Container(padding=20, content=ft.Column([ft.Text("Nueva Entrada", size=20, weight="bold"), txt_aleman, txt_espanol, ft.Row([dd_genero, txt_casos]), txt_ejemplos, txt_desc, ft.Container(height=10), btn_guardar], scroll="auto"))
    tab_mas = ft.Container(padding=20, content=ft.Column([ft.Text("Herramientas", size=20, weight="bold"), ft.Divider(), switch_tema, ft.Divider(), btn_importar, progress_bar, lbl_status, ft.Divider(), ft.Text(f"Ruta DB: {DB_NAME}", size=10, color="grey"), btn_reparar], horizontal_alignment="center", scroll="auto"))

    tabs = ft.Tabs(selected_index=0, animation_duration=300, tabs=[ft.Tab(text="Diccionario", content=tab_buscar), ft.Tab(text="Agregar", content=tab_agregar), ft.Tab(text="Más", content=tab_mas)], expand=True)
    
    crear_tabla()
    buscar_change(None)
    page.add(tabs)

ft.app(target=main)