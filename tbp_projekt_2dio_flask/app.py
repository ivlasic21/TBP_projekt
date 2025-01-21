from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
import hashlib
import json
from datetime import datetime

app = Flask(__name__)
DATABASE_CONFIG = {
    "dbname": "tbp",
    "user": "ivan",
    "password": "ivan",
    "host": "10.24.28.192",
    "port": "5432"
}

def log_meta_data(user_id, tip, opis, vrijednost):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO meta_data (user_id, tip, opis, vrijednost)
            VALUES (%s, %s, %s, %s);
        """, (user_id, tip, opis, vrijednost))
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Greška prilikom bilježenja meta podataka: {str(e)}")



app.secret_key = 'your_secret_key'  

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        try:
            conn = psycopg2.connect(**DATABASE_CONFIG)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT u.id, up.password_hash, u.rola_id, r.naziv, p.prava
                FROM user_passwords up
                JOIN users u ON up.user_email = u.email
                JOIN roles r ON u.rola_id = r.id
                JOIN permissions p ON r.id = p.rola_id
                WHERE u.email = %s;
            """, (email,))
            result = cursor.fetchone()

            if result:
                user_id = result[0] 
                stored_password_hash = result[1]
                user_role_id = result[2]
                user_role_name = result[3]
                user_permissions = result[4]  

                hashed_input_password = hashlib.sha256(password.encode()).hexdigest()

                if stored_password_hash == hashed_input_password:
                    # Pohrana informacija u sesiju
                    session['user_email'] = email
                    session['user_role'] = user_role_name
                    session['user_permissions'] = user_permissions  

                    meta_data_value = json.dumps({
                        'ip_address': request.remote_addr,
                        'user_agent': request.user_agent.string,
                        'login_time': datetime.now().isoformat()
                    })
                    log_meta_data(user_id, 'login', 'User login details', meta_data_value)

                    print("Prijavljeni korisnik:", email)
                    print("Korisnička rola:", user_role_name)
                    print("Prava korisnika:", user_permissions)

                    cursor.close()
                    conn.close()
                    return redirect(url_for('index'))  
                else:
                    return "Pogrešna lozinka", 401
            else:
                return "Korisnik nije pronađen", 404

        except Exception as e:
            return f"Dogodila se greška: {str(e)}", 500
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('login'))


@app.route('/')
def index():
    if 'user_email' not in session:  
        return redirect(url_for('login'))  

    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        user_permissions = session.get('user_permissions', {})
        can_create = user_permissions.get('kreiranje', False)
        can_delete = user_permissions.get('brisanje', False)
        can_see = user_permissions.get('pregled', False)
        can_edit = user_permissions.get('minjanje', False)

        if not can_see:
            user_email = session.get('user_email')
            query = """
            SELECT p.id, p.naziv, p.opis, p.datum_započinjanja, p.datum_završetka, p.status, 
                   u.id AS user_id, u.ime, u.prezime
            FROM projects p
            LEFT JOIN project_users pu ON p.id = pu.project_id
            LEFT JOIN users u ON pu.user_id = u.id
            WHERE u.email = %s;
            """
            cursor.execute(query, (user_email,))
        else:
            query = """
            SELECT p.id, p.naziv, p.opis, p.datum_započinjanja, p.datum_završetka, p.status, 
                   u.id AS user_id, u.ime, u.prezime
            FROM projects p
            LEFT JOIN project_users pu ON p.id = pu.project_id
            LEFT JOIN users u ON pu.user_id = u.id;
            """
            cursor.execute(query)

        projects = cursor.fetchall()  

        # Grupiraj korisnike poprojektu
        project_dict = {}
        for project in projects:
            project_id = project[0]
            if project_id not in project_dict:
                project_dict[project_id] = {
                    'naziv': project[1],
                    'opis': project[2],
                    'datum_započinjanja': project[3],
                    'datum_završetka': project[4],
                    'status': project[5],
                    'korisnici': []
                }
            if project[6]:  #Ako postoji korisnik za projekt
                project_dict[project_id]['korisnici'].append({
                    'user_id': project[6],
                    'ime': project[7],
                    'prezime': project[8]
                })

        # Pretvori dictionary u listu
        projects_data = [
            {'id': project_id, **data} for project_id, data in project_dict.items()
        ]
        cursor.close()
        conn.close()

        return render_template('index.html', 
                       projects=projects_data,
                       can_create=can_create, 
                       can_delete=can_delete, 
                       can_edit=can_edit)

    except Exception as e:
        return f"Dogodila se greška: {str(e)}", 500




@app.route('/add_project', methods=['GET', 'POST'])
def add_project():
    user_permissions = session.get('user_permissions', {})
    can_create = user_permissions.get('kreiranje', False)

    if not can_create:
        return redirect(url_for('index'))  

    if request.method == 'POST':
        try:
            naziv = request.form['naziv']
            opis = request.form.get('opis', '')
            datum_pocetka = request.form['datum_pocetka']
            datum_zavrsetka = request.form['datum_zavrsetka']  
            status = request.form['status']
            korisnici = request.form.getlist('korisnici')  

            query = """
            INSERT INTO projects (naziv, opis, datum_započinjanja, datum_završetka, status)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """
            conn = psycopg2.connect(**DATABASE_CONFIG)
            cursor = conn.cursor()
            cursor.execute(query, (naziv, opis, datum_pocetka, datum_zavrsetka, status))
            project_id = cursor.fetchone()[0]  

            for user_id in korisnici:
                query = "INSERT INTO project_users (project_id, user_id) VALUES (%s, %s)"
                cursor.execute(query, (project_id, int(user_id)))
            conn.commit()
            cursor.close()
            conn.close()

            return redirect(url_for('index'))

        except Exception as e:
            return f"Dogodila se greška pri dodavanju projekta: {str(e)}", 500

    else:
        try:
            conn = psycopg2.connect(**DATABASE_CONFIG)
            cursor = conn.cursor()
            query = "SELECT id, ime, prezime FROM users"
            cursor.execute(query)
            korisnici = cursor.fetchall()
            print(korisnici) 
            cursor.close()
            conn.close()
            return render_template('add_project.html', korisnici=korisnici)

        except Exception as e:
            return f"Dogodila se greška pri dohvaćanju korisnika: {str(e)}", 500



@app.route('/edit_project/<int:project_id>', methods=['GET', 'POST'])
def edit_project(project_id):
    user_permissions = session.get('user_permissions', {})
    can_edit = user_permissions.get('minjanje', False)

    if not can_edit:
        return redirect(url_for('index'))  

    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        if request.method == 'POST':
            naziv = request.form['naziv']
            opis = request.form.get('opis', '')
            datum_pocetka = request.form['datum_pocetka']
            datum_završetka = request.form.get('datum_završetka', None)
            status = request.form['status']
            selected_users = request.form.getlist('users')  # Dohvati

            query = """
            UPDATE projects
            SET naziv = %s, opis = %s, datum_započinjanja = %s, datum_završetka = %s, status = %s
            WHERE id = %s
            """
            cursor.execute(query, (naziv, opis, datum_pocetka, datum_završetka, status, project_id))
            cursor.execute("DELETE FROM project_users WHERE project_id = %s", (project_id,))

            for user_id in selected_users:
                cursor.execute("INSERT INTO project_users (project_id, user_id) VALUES (%s, %s)", (project_id, user_id))

            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('index'))

        else:
            query_project = "SELECT naziv, opis, datum_započinjanja, datum_završetka, status FROM projects WHERE id = %s"
            cursor.execute(query_project, (project_id,))
            project = cursor.fetchone()

            if not project:
                return f"Projekt s ID-jem {project_id} nije pronađen.", 404

            query_users = "SELECT id, ime FROM users"
            cursor.execute(query_users)
            all_users = cursor.fetchall()

            query_project_users = "SELECT user_id FROM project_users WHERE project_id = %s"
            cursor.execute(query_project_users, (project_id,))
            project_users = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()

            return render_template('edit_project.html', project={
                'id': project_id,
                'naziv': project[0],
                'opis': project[1],
                'datum_pocetka': project[2],
                'datum_završetka': project[3],
                'status': project[4]
            }, all_users=all_users, project_users=project_users)

    except Exception as e:
        return f"Dogodila se greška: {str(e)}", 500


@app.route('/delete_project/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM project_users WHERE project_id = %s", (project_id,))

        cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('index')) 
    except Exception as e:
        return f"Dogodila se greška: {str(e)}", 500
    

if __name__ == '__main__':
    app.run(debug=True, port=5001)
