from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
import hashlib
import json  

app = Flask(__name__)

DATABASE_CONFIG = {
    "dbname": "tbp",
    "user": "ivan",
    "password": "ivan",
    "host": "10.24.28.192",
    "port": "5432"
}

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

                if isinstance(user_permissions, str):
                    user_permissions = json.loads(user_permissions)  #Pretvorba iz stringa u dict
                else:
                    user_permissions = dict(user_permissions)  #Osigurava da je dictionary

               
                hashed_input_password = hashlib.sha256(password.encode()).hexdigest()

                if stored_password_hash == hashed_input_password:
                    
                    can_create = user_permissions.get('kreiranje', False)
                    can_delete = user_permissions.get('brisanje', False)
                    can_edit = user_permissions.get('minjanje', False)
                    can_login = user_permissions.get('ekstra_stranica', False)
                    
                    print(f"User permissions: {user_permissions}")
                    print(f"Can_login: {can_login}")
                    print(f"ime; {user_role_name}")

                    if can_login:
                        #Pohrani informacije
                        session['user_email'] = email  # Pohrana emaila u sesiju
                        session['user_role'] = user_role_name  # Pohrana rola u sesiju
                        session['user_permissions'] = user_permissions  # Pohrana prava u sesiju

                        cursor.close()
                        conn.close()
                        return redirect(url_for('index'))  
                    else:
                        return "Nemate pristup ovoj stranici", 403  
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

        cursor.execute("""
            SELECT u.id, u.ime, u.prezime, u.email, u.status, u.datum_zaposlenja, r.naziv 
            FROM users u
            JOIN roles r ON u.rola_id = r.id;
        """)
        users = cursor.fetchall()  

        cursor.close()
        conn.close()

        return render_template('index.html', users=users)

    except Exception as e:
        return f"Dogodila se greška: {str(e)}", 500


@app.route('/add_user', methods=['GET'])
def add_user_form():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        cursor.execute("SELECT id, naziv FROM roles;")
        roles = cursor.fetchall()  
        cursor.close()
        conn.close()

        return render_template('add_user.html', roles=roles)

    except Exception as e:
        return f"Dogodila se greška: {str(e)}", 500


@app.route('/add_user', methods=['POST'])
def add_user():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    ime = request.form['ime']
    prezime = request.form['prezime']
    rola_id = request.form['rola_id']
    email = request.form['email']
    status = request.form['status']
    datum_zaposlenja = request.form['datum_zaposlenja']
    lozinka = request.form['lozinka']

    hashed_password = hashlib.sha256(lozinka.encode()).hexdigest()

    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (ime, prezime, rola_id, email, status, datum_zaposlenja)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (ime, prezime, rola_id ,email, status, datum_zaposlenja))
        cursor.execute("""
            INSERT INTO user_passwords (user_email, password_hash)
            VALUES (%s, %s);
        """, (email, hashed_password))
        cursor.execute("""
            UPDATE teams
            SET broj_clanova = broj_clanova + 1
            WHERE id = %s;
        """, (rola_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('index'))

    except Exception as e:
        return f"Dogodila se greška: {str(e)}", 500

        
@app.route('/edit-role/<int:user_id>', methods=['GET', 'POST'])
def edit_user_role(user_id):
    if 'user_email' not in session:
        return redirect(url_for('login'))
    conn = psycopg2.connect(**DATABASE_CONFIG)
    cur = conn.cursor()

    if request.method == 'POST':
        new_role_id = request.form['role']  # Dohvaća ID uloge
        cur.execute('UPDATE users SET rola_id = %s WHERE id = %s', (new_role_id, user_id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('index'))
    
    cur.execute('SELECT rola_id FROM users WHERE id = %s', (user_id,))
    current_role_id = cur.fetchone()[0]

    cur.execute('SELECT id, naziv FROM roles')
    all_roles = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('edit_role.html', user_id=user_id, current_role_id=current_role_id, roles=all_roles)

    
    return render_template(
        'edit_role.html', 
        user_id=user_id, 
        current_role_id=current_role_id, 
        all_roles=all_roles
    )



@app.route('/user/<string:email>')
def user_metadata(email):
    if 'user_email' not in session:
        return redirect(url_for('login'))
    conn = psycopg2.connect(**DATABASE_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
    user_id = cur.fetchone()

    if user_id is None:
        return "Korisnik nije pronađen", 404

    user_id = user_id[0] 
    cur.execute("""
        SELECT tip, opis, vrijednost
        FROM meta_data
        WHERE user_id = %s;
    """, (user_id,))
    meta_data = cur.fetchall()

    cur.close()
    conn.close()

    if not meta_data:
        return "Nema meta podataka za ovog korisnika", 404

    return render_template('user_metadata.html', email=email, meta_data=meta_data)

if __name__ == '__main__':
    app.run(debug=True)

