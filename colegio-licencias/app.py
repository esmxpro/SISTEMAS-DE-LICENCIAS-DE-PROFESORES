from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

def crear_app():
    app = Flask(__name__)
    app.secret_key = 'secret'

    # --- Funciones auxiliares ---
    def get_db_connection():
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        return conn

    def crear_tablas():
        conn = get_db_connection()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS profesores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                carnet TEXT UNIQUE,
                contrasena TEXT,
                turno TEXT,
                especialidad TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS licencias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profesor_id INTEGER,
                fecha TEXT,
                motivo TEXT,
                estado TEXT DEFAULT 'En espera',
                fecha_inicio TEXT,
                fecha_fin TEXT,
                FOREIGN KEY (profesor_id) REFERENCES profesores(id)
            )
        ''')
        admin = conn.execute('SELECT * FROM profesores WHERE carnet = ?', ('admin',)).fetchone()
        if not admin:
            conn.execute('''
                INSERT INTO profesores (nombre, carnet, contrasena, turno, especialidad)
                VALUES (?, ?, ?, ?, ?)
            ''', ('Administrador', 'admin', generate_password_hash('admin'), 'mañana', 'Dirección'))
        conn.commit()
        conn.close()

    def migrar_tabla_licencias():
        conn = get_db_connection()
        columnas = conn.execute("PRAGMA table_info(licencias)").fetchall()
        nombres_columnas = [col['name'] for col in columnas]
        if 'fecha_inicio' not in nombres_columnas:
            conn.execute("ALTER TABLE licencias ADD COLUMN fecha_inicio TEXT")
        if 'fecha_fin' not in nombres_columnas:
            conn.execute("ALTER TABLE licencias ADD COLUMN fecha_fin TEXT")
        conn.commit()
        conn.close()

    crear_tablas()
    migrar_tabla_licencias()

    # --- Rutas ---
    @app.route('/')
    def index():
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            carnet = request.form.get('carnet')
            contrasena = request.form.get('contrasena')
            if not carnet or not contrasena:
                flash('Debe completar ambos campos', 'error')
                return redirect(url_for('login'))

            conn = get_db_connection()
            profesor = conn.execute('SELECT * FROM profesores WHERE carnet = ?', (carnet,)).fetchone()
            conn.close()

            if profesor and check_password_hash(profesor['contrasena'], contrasena):
                session.clear()
                session['user_name'] = profesor['nombre']
                if carnet == 'admin':
                    session['user_role'] = 'admin'
                    return redirect(url_for('dashboard_admin'))
                else:
                    session['user_role'] = 'profesor'
                    session['profesor_id'] = profesor['id']
                    return redirect(url_for('dashboard_profesor'))
            else:
                flash('Credenciales inválidas', 'error')
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    # --- ADMIN ---
    @app.route('/dashboard_admin')
    def dashboard_admin():
        if session.get('user_role') != 'admin':
            return redirect(url_for('login'))
        conn = get_db_connection()
        profesores = conn.execute('SELECT * FROM profesores').fetchall()
        licencias = conn.execute('''
            SELECT l.*, p.nombre FROM licencias l
            JOIN profesores p ON l.profesor_id = p.id
            ORDER BY l.fecha DESC
        ''').fetchall()
        conn.close()
        return render_template('dashboard_admin.html', profesores=profesores, licencias=licencias)

    @app.route('/register_profesor', methods=['GET', 'POST'])
    def register_profesor():
        if session.get('user_role') != 'admin':
            return redirect(url_for('login'))

        if request.method == 'POST':
            nombre = request.form.get('nombre')
            carnet = request.form.get('carnet')
            contrasena = request.form.get('contrasena')
            turno = request.form.get('turno')
            especialidad = request.form.get('especialidad')

            if not (nombre and carnet and contrasena and turno and especialidad):
                flash('Todos los campos son obligatorios', 'error')
                return redirect(url_for('register_profesor'))

            hashed_password = generate_password_hash(contrasena)
            conn = get_db_connection()
            try:
                conn.execute('''
                    INSERT INTO profesores (nombre, carnet, contrasena, turno, especialidad)
                    VALUES (?, ?, ?, ?, ?)
                ''', (nombre, carnet, hashed_password, turno, especialidad))
                conn.commit()
                flash('Profesor registrado correctamente', 'success')
            except sqlite3.IntegrityError:
                flash('El carnet ya está registrado', 'error')
            conn.close()
        return render_template('register_profesor.html')

    @app.route('/eliminar_profesor/<int:id>')
    def eliminar_profesor(id):
        if session.get('user_role') != 'admin':
            return redirect(url_for('login'))
        conn = get_db_connection()
        conn.execute('DELETE FROM profesores WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard_admin'))

    @app.route('/aceptar_licencia/<int:id>')
    def aceptar_licencia(id):
        if session.get('user_role') != 'admin':
            return redirect(url_for('login'))
        conn = get_db_connection()
        conn.execute('UPDATE licencias SET estado = "Aceptada" WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard_admin'))

    @app.route('/rechazar_licencia/<int:id>')
    def rechazar_licencia(id):
        if session.get('user_role') != 'admin':
            return redirect(url_for('login'))
        conn = get_db_connection()
        conn.execute('UPDATE licencias SET estado = "Rechazada" WHERE id = ?', (id,))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard_admin'))

    # --- PROFESOR ---
    @app.route('/dashboard_profesor')
    def dashboard_profesor():
        if session.get('user_role') != 'profesor':
            return redirect(url_for('login'))
        conn = get_db_connection()
        licencias = conn.execute(
            'SELECT * FROM licencias WHERE profesor_id = ? ORDER BY fecha DESC',
            (session['profesor_id'],)
        ).fetchall()
        conn.close()
        return render_template('dashboard_profesor.html', licencias=licencias)

    @app.route('/solicitudes', methods=['GET', 'POST'])
    def solicitudes():
        if session.get('user_role') != 'profesor':
            return redirect(url_for('login'))
        if request.method == 'POST':
            motivo = request.form.get('motivo')
            fecha_inicio = request.form.get('fecha_inicio')
            fecha_fin = request.form.get('fecha_fin')

            if not motivo or not fecha_inicio or not fecha_fin:
                flash('Todos los campos son obligatorios', 'error')
                return redirect(url_for('solicitudes'))

            # Validar fechas
            try:
                inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
                fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d")
                if inicio_dt > fin_dt:
                    flash('La fecha de inicio no puede ser posterior a la fecha de fin', 'error')
                    return redirect(url_for('solicitudes'))
                if inicio_dt < datetime.now():
                    flash('No puedes solicitar fechas pasadas', 'error')
                    return redirect(url_for('solicitudes'))
            except ValueError:
                flash('Formato de fecha inválido', 'error')
                return redirect(url_for('solicitudes'))

            fecha_solicitud = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO licencias (profesor_id, fecha, motivo, estado, fecha_inicio, fecha_fin)
                VALUES (?, ?, ?, 'En espera', ?, ?)
            ''', (session['profesor_id'], fecha_solicitud, motivo, fecha_inicio, fecha_fin))
            conn.commit()
            conn.close()
            flash('Solicitud enviada correctamente', 'success')
            return redirect(url_for('dashboard_profesor'))
        return render_template('solicitudes.html')

    return app
if __name__ == '__main__':
    app = crear_app()
    app.run(debug=True)
