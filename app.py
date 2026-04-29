import os
import shutil
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = "clave_super_secreta_123"   # Cambiar en producción


# ============================================================
# CREAR USUARIO ADMINISTRADOR SI NO EXISTE
# ============================================================

if not os.path.exists('usuarios.json'):
    admin = {
        "usuarios": [
            {
                "usuario": "admin",
                "password": "admin123",
                "rol": "admin"
            }
        ]
    }
    with open('usuarios.json', 'w', encoding='utf-8') as f:
        json.dump(admin, f, ensure_ascii=False, indent=4)


# ============================================================
# UTILIDADES
# ============================================================

def cargar_eventos():
    if os.path.exists('eventos.json'):
        with open('eventos.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def guardar_eventos(eventos):
    with open('eventos.json', 'w', encoding='utf-8') as f:
        json.dump(eventos, f, ensure_ascii=False, indent=4)


def cargar_usuarios():
    with open('usuarios.json', 'r', encoding='utf-8') as f:
        return json.load(f)["usuarios"]


# ============================================================
# DECORADOR PARA PROTEGER RUTAS
# ============================================================

def login_requerido(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ============================================================
# LOGIN / LOGOUT
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']

        usuarios = cargar_usuarios()

        for u in usuarios:
            if u["usuario"] == usuario and u["password"] == password:
                session["usuario"] = usuario
                session["rol"] = u["rol"]
                return redirect(url_for("admin_dashboard"))

        return render_template("login.html", error="Usuario o contraseña incorrectos")

    return render_template("login.html")


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("login"))


# ============================================================
# RUTAS PÚBLICAS
# ============================================================

@app.route('/')
def inicio():
    return render_template('inicio.html', active_page='inicio')


@app.route('/nosotros')
def nosotros():
    return render_template('nosotros.html', active_page='nosotros')


@app.route('/contacto')
def contacto():
    return render_template('contacto.html', active_page='contacto')


@app.route('/eventos')
def eventos():
    eventos = cargar_eventos()

    # ✅ CAMBIO: guardamos el índice original junto con cada evento
    # así las fotos siempre apuntan a la carpeta correcta
    publicados = [(i, e) for i, e in enumerate(eventos) if e.get("publicado")]

    publicados.sort(
        key=lambda x: datetime.strptime(x[1]['fecha'], '%d/%m/%Y'),
        reverse=True
    )

    return render_template('eventos.html', eventos=publicados, active_page='eventos')


# ============================================================
# PANEL ADMINISTRATIVO
# ============================================================

@app.route('/admin')
@login_requerido
def admin_dashboard():
    eventos = cargar_eventos()

    total_eventos = len(eventos)
    total_fotos = sum(len(e.get("fotos", [])) for e in eventos)
    total_publicados = sum(1 for e in eventos if e.get("publicado"))
    total_pendientes = total_eventos - total_publicados

    return render_template(
        'admin/dashboard.html',
        total_eventos=total_eventos,
        total_fotos=total_fotos,
        total_publicados=total_publicados,
        total_pendientes=total_pendientes,
        eventos=eventos,
        usuario=session["usuario"],
        rol=session["rol"],
        active_page='dashboard'
    )


# ============================================================
# CREAR EVENTO
# ============================================================

@app.route('/admin/crear-evento', methods=['GET', 'POST'])
@login_requerido
def crear_evento():
    if request.method == 'POST':
        nuevo_evento = {
            "titulo": request.form['titulo'],
            "fecha": datetime.strptime(request.form['fecha'], "%Y-%m-%d").strftime("%d/%m/%Y"),
            "descripcion": request.form['descripcion'],
            "categoria": request.form['categoria'],
            "fotos": [],
            "publicado": False
        }

        eventos = cargar_eventos()
        eventos.append(nuevo_evento)
        guardar_eventos(eventos)

        id_evento = len(eventos) - 1

        # ✅ CAMBIO: flash + redirect directo a subir fotos (elimina crear_evento_exito.html)
        flash(f"Evento '{nuevo_evento['titulo']}' creado con éxito. ¡Ahora sube las fotos!")
        return redirect(url_for('subir_fotos', id_evento=id_evento))

    return render_template('admin/crear_evento.html', active_page='crear_evento')


# ============================================================
# MIS EVENTOS
# ============================================================

@app.route('/admin/mis-eventos')
@login_requerido
def mis_eventos():
    eventos = cargar_eventos()

    publicados = [e for e in eventos if e.get("publicado")]
    pendientes = [e for e in eventos if not e.get("publicado")]

    publicados.sort(key=lambda x: datetime.strptime(x['fecha'], '%d/%m/%Y'), reverse=True)
    pendientes.sort(key=lambda x: datetime.strptime(x['fecha'], '%d/%m/%Y'), reverse=True)

    eventos_ordenados = publicados + pendientes

    return render_template('admin/mis_eventos.html', eventos=eventos_ordenados, active_page='mis_eventos')


# ============================================================
# SUBIR FOTOS
# ============================================================

@app.route("/admin/subir_fotos/<int:id_evento>", methods=["GET", "POST"])
@login_requerido
def subir_fotos(id_evento):
    eventos = cargar_eventos()

    if id_evento < 0 or id_evento >= len(eventos):
        return "Evento no encontrado", 404

    evento = eventos[id_evento]

    carpeta_evento = f"static/eventos/{id_evento}"
    os.makedirs(carpeta_evento, exist_ok=True)

    if request.method == "POST":
        archivos = request.files.getlist("fotos")

        for archivo in archivos:
            if archivo.filename:
                nombre = secure_filename(archivo.filename)
                ruta = os.path.join(carpeta_evento, nombre)
                archivo.save(ruta)
                evento["fotos"].append(nombre)

        guardar_eventos(eventos)
        flash("Fotos subidas correctamente.")
        return redirect(url_for("subir_fotos", id_evento=id_evento))

    return render_template("admin/subir_fotos.html", evento=evento, id_evento=id_evento, active_page='mis_eventos')


# ============================================================
# ELIMINAR FOTO
# ============================================================

@app.route("/admin/eliminar_foto/<int:id_evento>/<nombre>")
@login_requerido
def eliminar_foto(id_evento, nombre):
    eventos = cargar_eventos()

    if id_evento < 0 or id_evento >= len(eventos):
        return "Evento no encontrado", 404

    evento = eventos[id_evento]
    ruta = f"static/eventos/{id_evento}/{nombre}"

    if os.path.exists(ruta):
        os.remove(ruta)

    if nombre in evento.get("fotos", []):
        evento["fotos"].remove(nombre)

    guardar_eventos(eventos)
    flash("Foto eliminada.")
    return redirect(url_for("subir_fotos", id_evento=id_evento))


# ============================================================
# EDITAR EVENTO
# ============================================================

@app.route('/admin/editar-evento/<int:index>', methods=['GET', 'POST'])
@login_requerido
def editar_evento(index):
    eventos = cargar_eventos()

    if index < 0 or index >= len(eventos):
        return "Evento no encontrado", 404

    evento = eventos[index]

    if request.method == 'POST':
        evento['titulo'] = request.form['titulo']
        evento['fecha'] = datetime.strptime(request.form['fecha'], "%Y-%m-%d").strftime("%d/%m/%Y")
        evento['descripcion'] = request.form['descripcion']
        evento['categoria'] = request.form['categoria']

        guardar_eventos(eventos)
        flash("Evento actualizado correctamente.")
        return redirect(url_for('mis_eventos'))

    fecha_html = datetime.strptime(evento['fecha'], "%d/%m/%Y").strftime("%Y-%m-%d")
    return render_template('admin/editar_evento.html', evento=evento, fecha_html=fecha_html, index=index, active_page='mis_eventos')


# ============================================================
# ELIMINAR EVENTO
# ============================================================

@app.route('/admin/eliminar-evento/<int:index>')
@login_requerido
def eliminar_evento(index):
    eventos = cargar_eventos()

    if index < 0 or index >= len(eventos):
        return "Evento no encontrado", 404

    carpeta = f"static/eventos/{index}"
    if os.path.exists(carpeta):
        shutil.rmtree(carpeta)

    eventos.pop(index)
    guardar_eventos(eventos)

    # ✅ CAMBIO: flash + redirect directo (elimina eliminar_evento_exito.html)
    flash("Evento eliminado correctamente.")
    return redirect(url_for('mis_eventos'))


# ============================================================
# PUBLICAR / DESPUBLICAR
# ============================================================

@app.route('/publicar_evento/<int:index>')
@login_requerido
def publicar_evento(index):
    eventos = cargar_eventos()

    if index < 0 or index >= len(eventos):
        return "Evento no encontrado", 404

    eventos[index]["publicado"] = not eventos[index].get("publicado", False)
    guardar_eventos(eventos)

    return redirect(url_for('mis_eventos'))


# ============================================================
# GALERÍA Y PERFIL — ✅ CAMBIO: ahora protegidas con login_requerido
# ============================================================

@app.route("/admin/galeria")
@login_requerido
def galeria():
    todos = cargar_eventos()
    # ✅ pasamos índice real junto con cada evento
    eventos = [(i, e) for i, e in enumerate(todos) if e.get("fotos")]
    return render_template("admin/galeria.html", eventos=eventos, active_page='galeria')


@app.route("/admin/perfil")
@login_requerido
def perfil():
    return render_template("admin/perfil.html", active_page='perfil')


# ============================================================
# EJECUCIÓN DEL SERVIDOR
# ============================================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)