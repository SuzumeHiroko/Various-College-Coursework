from flask import Flask, jsonify, request, session, send_from_directory
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os
import bcrypt   
from flask_cors import CORS                    # Library for hashing passwords

load_dotenv()

app = Flask(__name__, static_folder="static")
app.secret_key = 'super_secret_key' # required for session cookies
CORS(app)

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'), #make a .env file and store your mysql connection password
    'database': 'matchtracker'
}

VALID_TABLE = {
    'game': 'game_id', 
    'tournament': 'tournament_id', 
    'matchinfo': 'matchinfo_id', 
    'team': 'team_id', 
    'player': 'player_id',
    'place': 'place_id', 
    'venue': 'venue_id', 
    'prizepool': 'prizepool_id', 
    'sponsor': 'sponsor_id',  
    'commentator': 'commentator_id',
    'organizer': 'organizer_id', 
    'manager': 'manager_id', 
    'coach': 'coach_id'
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**db_config)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# ================== USER AUTHENTICATION ==================
# For Demo: Admin Password = Admin123
# Get user record from database using username
def get_user_by_username(username: str):
        
    connection = get_db_connection()
    if connection is None:
        return None
    
    cursor = None
    try: 
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT user_id, username, password_hash, role 
            FROM UserAccount 
            WHERE username = %s
        """
        cursor.execute(query, (username,))
        user = cursor.fetchone()
        return user
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# User Registration Endpoint
# Registers a new user account (creates username, hashed password, and default role)
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json(force=True) or {}
    username = data.get('username')
    password = data.get('password')

    # Check if both username and password are included
    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400
    
    # Check if username is already taken
    if get_user_by_username(username):
        return jsonify({'error': 'username already exists'}), 400

    # Hash password using bcrypt
    password_hash = bcrypt.hashpw(
        password.encode(), 
        bcrypt.gensalt()
    ).decode()

    # Connect to database
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    
    cursor = None
    try:
        cursor = connection.cursor()
        query = """
            INSERT INTO UserAccount(username, password_hash, role)
            VALUES (%s, %s, %s)
        """
        cursor.execute(query, (username, password_hash, 'user')) # default to 'user' role
        connection.commit()

        return jsonify({
            'success': True,
            'message': 'user registered',
            'user_id': cursor.lastrowid,
            'username': username,
            'role': 'user'
        }), 201
    
    except Error as e:
        if connection:
            connection.rollback()
        return jsonify({'error':str(e)}), 500
    
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

# User Login Endpoint:
# Logs existing users in
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}      
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400

    # Look up user in database
    user = get_user_by_username(username)
    if not user:
        return jsonify({'error': 'invalid credentials'}), 401

    stored_hash = user['password_hash'] # string stored in database

    # Compare provided password to stored bcyrpt hashed password
    if not bcrypt.checkpw(password.encode(), stored_hash.encode()):
        return jsonify({'error': 'invalid credentials'}), 401
    
    # Store user info in the session so they stay logged in
    session['user_id'] = user['user_id']
    session['username'] = user['username']
    session['role'] = user['role']

    return jsonify({
        'success': True,
        'message': 'login successful',
        'user': {
            'user_id': user['user_id'],
            'username': user['username'],
            'role': user['role']
        }
    }), 200

# User Logout Endpoint:
# Logs out user
@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'logged out'}), 200

@app.get("/me")
def me():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"authenticated": False})
    return jsonify({
        "authenticated": True,
        "user": {
            "user_id": session['user_id'],
            "username": session['username'],
            "role": session['role'],
        }
    })
# =========================================================

@app.route('/getTable', methods=['POST']) 
def get_table():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try: 
        data = request.get_json(force=True)
        table_name = data.get('table_name')

        if table_name is None:
            return jsonify({'error': 'Invalid input. Check json key format'}), 400

        table_name = table_name.lower()
        if table_name not in VALID_TABLE:
            return jsonify({'error': 'Invalid table name'}), 400   

        cursor = connection.cursor(dictionary=True)
        query = f"Select * From {table_name};"
        cursor.execute(query)
        table = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(table)
    except Exception as e:  
        if connection:
            connection.rollback()  
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/getEntry', methods=['POST']) 
def get_entry():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try: 
        data = request.get_json(force=True)
        table_name = data.get('table_name')
        id = data.get('id')

        if table_name is None or id is None:
            return jsonify({'error': 'Invalid input. Check json format'}), 400
        table_name = table_name.lower()
        if table_name not in VALID_TABLE.keys():
            return jsonify({'error': 'Invalid table name'}), 400
        primary_key= VALID_TABLE[table_name];

        cursor = connection.cursor(dictionary=True)
        query = f"SELECT * FROM {table_name} WHERE {primary_key} = %s"
        cursor.execute(query, (id,))
        entry = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(entry)
    except Exception as e:  
        if connection:
            connection.rollback() 
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/deleteEntry', methods=['DELETE']) 
def delete_entry():

    # Admin Permission Check
    if session.get('role') != 'admin':
        return jsonify({'error': 'admin access required'}), 403
    
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500

    try: 
        data = request.get_json(force=True)
        table_name = data.get('table_name')
        id = data.get('id')

        if table_name is None or id is None:
            return jsonify({'error': 'Invalid input. Check json format'}), 400
        table_name = table_name.lower()
        if table_name not in VALID_TABLE.keys():
            return jsonify({'error': 'Invalid table name'}), 400
        primary_key= VALID_TABLE[table_name];

        cursor = connection.cursor(dictionary=True)
        query = f"DELETE FROM {table_name} WHERE {primary_key} = %s"
        cursor.execute(query, (id,))
        connection.commit()
        return jsonify({
            'success': True, 
            'message': 'Entry Deleted',
            'rows_affected': cursor.rowcount
        }), 201
    except Exception as e:
        if connection:
            connection.rollback()   
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/insertEntry', methods=['POST']) 
def insert_entry():

    # Admin Permission Check
    if session.get('role') != 'admin':
        return jsonify({'error': 'admin access required'}), 403
    
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None

    try: 
        data = request.get_json()
        table_name = data.get('table_name').lower()
        entry = data.get('entry')

        if table_name is None or entry is None:
            return jsonify({'error': 'Invalid input. Check json format'}), 400
        table_name = table_name.lower()
        if table_name not in VALID_TABLE.keys():
            return jsonify({'error': 'Invalid table name'}), 400

        cursor = connection.cursor(dictionary=True)
        column_names = ', '.join(entry.keys())
        placeholders = ', '.join(['%s'] * len(entry))
        query = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
        cursor.execute(query, tuple(entry.values()))
        connection.commit()
        return jsonify({
            'success': True, 
            'message': 'Entry inserted',
            'id': cursor.lastrowid
        }), 201
    except Exception as e:
        if connection:
            connection.rollback()   
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/updateEntry', methods=['PUT']) 
def update_entry():

    # Admin Permission Check
    if session.get('role') != 'admin':
        return jsonify({'error': 'admin access required'}), 403
    
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None

    try: 
        data = request.get_json()
        table_name = data.get('table_name').lower()
        id = data.get('id')
        update_colms = data.get('update_colms')

        if table_name is None or update_colms is None or id is None:
            return jsonify({'error': 'Invalid input. Check json format'}), 400
        table_name = table_name.lower()
        if table_name not in VALID_TABLE.keys():
            return jsonify({'error': 'Invalid table name'}), 400

        primary_key = VALID_TABLE[table_name]

        set_clause = ", ".join([f"{key} = %s" for key in update_colms.keys()])
        query = f"UPDATE {table_name} SET {set_clause} WHERE {primary_key} = %s"

        cursor = connection.cursor(dictionary=True)
        values = list(update_colms.values()) + [id]
        cursor.execute(query, values)
        connection.commit()

        return jsonify({
            'success': True, 
            'message': 'Entry updated',
            'rows_affected': cursor.rowcount
        }), 200 
    except Exception as e:
        if connection:
            connection.rollback()   
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/upcomingTournaments', methods=['POST']) 
def upcoming_tournaments():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try: 
        data = request.get_json(force=True)
        current_time = data.get('search')
        print(current_time)
        current_time = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S")

        if current_time is None:
            return jsonify({'error': 'Invalid input. Check json key format'}), 400

        cursor = connection.cursor(dictionary=True)
        query = """SELECT UT.tournament_name,
                          UT.tournament_schedule, 
                          UT.tournament_format, 
                          UT.game_name 
                    FROM UpcomingTournament UT
                    WHERE tournament_schedule >= %s """ 
        cursor.execute(query, (current_time,))
        entries = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(entries)
    except Exception as e:  
        if connection:
            connection.rollback()  
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/getFormat', methods=['POST']) 
def get_format():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try: 
        data = request.get_json(force=True)
        format = data.get('search')

        if format is None:
            return jsonify({'error': 'Invalid input. Check json key format: format)'}), 400

        cursor = connection.cursor(dictionary=True)
        query = """SELECT UT.tournament_name,
                          UT.tournament_schedule, 
                          UT.game_name 
                    FROM UpcomingTournament UT
                    WHERE tournament_format = %s """ 
        cursor.execute(query, (format,))
        entries = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(entries)
    except Exception as e:  
        if connection:
            connection.rollback()  
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/getPlacementPoints', methods=['POST']) 
def get_placement_points():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try: 
        data = request.get_json(force=True)
        tournament_name = data.get('search')

        if tournament_name is None:
            return jsonify({'error': 'Invalid input. Check json key format: format)'}), 400

        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT PP.team_name, 
                PP.placement_rank AS placement_rank, 
                PP.placement_points AS points, 
                PP.placement_prize_amount AS prize_amount, 
                PP.tournament_name AS tournament
            FROM PlacementPoints PP
            WHERE tournament_name = %s
            ORDER BY PP.placement_rank;
        """
        cursor.execute(query, (tournament_name,))
        entries = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(entries)
    except Exception as e:  
        if connection:
            connection.rollback()  
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/getMatchesInTournament', methods=['POST']) 
def get_matches_in_tournament():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try: 
        data = request.get_json(force=True)
        tournament_name = data.get('search')

        if tournament_name is None:
            return jsonify({'error': 'Invalid input. Check json key format: format)'}), 400

        cursor = connection.cursor(dictionary=True)
        query = """SELECT TNM.match_date_time AS schedule, 
                          TNM.match_rounds AS rounds, 
                          TNM.team1_name, 
                          TNM.team2_name,
                          TNM.winning_team_name
                FROM TournamentMatches TNM
                WHERE TNM.tournament_name = %s
                ORDER BY TNM.match_date_time;"""
        cursor.execute(query, (tournament_name,))
        entries = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(entries)
    except Exception as e:  
        if connection:
            connection.rollback()  
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/getTeamsInTournament', methods=['POST']) 
def get_teams_in_tournament():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try: 
        data = request.get_json(force=True)
        tournament_name = data.get('search')

        if tournament_name is None:
            return jsonify({'error': 'Invalid input. Check json key format', 'received_keys': list(data.keys())}), 400                                               
        cursor = connection.cursor(dictionary=True)
        query = """SELECT team_name
                   FROM TournamentTeams
                   WHERE tournament_name = %s;""" 
        cursor.execute(query, (tournament_name,))
        entries = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(entries)
    except Exception as e:  
        if connection:
            connection.rollback()  
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/getTeamWins', methods=['POST']) 
def get_team_wins():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = None 

    try: 
        data = request.get_json(force=True)
        team_name = data.get('search')

        if team_name is None:
            return jsonify({'error': 'Invalid input. Check json key format: format)'}), 400

        cursor = connection.cursor(dictionary=True)
        query = """SELECT TW.tournament_name, TW.wins
                FROM TeamWins TW 
                WHERE TW.team_name = %s
                ORDER BY TW.wins DESC"""
        cursor.execute(query, (team_name,))
        entries = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify(entries)
    except Exception as e:  
        if connection:
            connection.rollback()  
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.post("/byGame")
def by_game():
    connection = get_db_connection()
    if connection is None:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        data = request.get_json(force=True) or {}
        game_id = data.get("game_id")
        if not game_id:
            return jsonify({'error': 'Missing game_id'}), 400

        cur = connection.cursor(dictionary=True)

        # Tournaments for the game
        cur.execute("""
            SELECT t.*
            FROM Tournament t
            WHERE t.game_id = %s
        """, (game_id,))
        tournaments = cur.fetchall()

        # Teams for the game (via tournaments)
        cur.execute("""
            SELECT DISTINCT tm.*
            FROM Team tm
            JOIN TournamentTeam tt ON tt.team_id = tm.team_id
            JOIN Tournament t      ON t.tournament_id = tt.tournament_id
            WHERE t.game_id = %s
        """, (game_id,))
        teams = cur.fetchall()

        # Players for the game (direct junction)
        cur.execute("""
            SELECT p.*
            FROM Player p
            JOIN PlayerGame pg ON pg.player_id = p.player_id
            WHERE pg.game_id = %s
        """, (game_id,))
        players = cur.fetchall()

        # Organizers for the game (via tournaments)
        cur.execute("""
            SELECT DISTINCT o.*
            FROM Organizer o
            JOIN Tournament t ON t.organizer_id = o.organizer_id
            WHERE t.game_id = %s
        """, (game_id,))
        organizers = cur.fetchall()

        cur.close()
        connection.close()
        return jsonify({
            "tournaments": tournaments,
            "teams": teams,
            "players": players,
            "organizers": organizers
        })

    except Exception as e:
        if connection:
            connection.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            cur.close()
        except: pass
        try:
            connection.close()
        except: pass

if __name__ == '__main__':
    app.run(debug=True)
