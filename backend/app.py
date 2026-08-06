from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify, send_from_directory
import sqlite3
import hashlib
import bcrypt
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'task_manager_secret_key_12345'

UPLOAD_FOLDER = '/data/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'xlsx', 'pptx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def verify_password(password, stored_hash):
    if stored_hash.startswith('$2'):
        try:
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
        except ValueError:
            return False
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash

def get_db():
    conn = sqlite3.connect('/data/task_manager.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    # Request logs
    conn.execute('''
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            method TEXT,
            path TEXT,
            ip TEXT,
            status TEXT,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        conn.execute('ALTER TABLE request_logs ADD COLUMN username TEXT')
    except sqlite3.OperationalError:
        pass
    # Users
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Boards
    conn.execute('''
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            owner_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
    ''')
    # Board Lists
    conn.execute('''
        CREATE TABLE IF NOT EXISTS board_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER,
            name TEXT NOT NULL,
            position INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (board_id) REFERENCES boards (id)
        )
    ''')
    # Tasks
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER,
            list_id INTEGER,
            user_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            position INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (board_id) REFERENCES boards (id),
            FOREIGN KEY (list_id) REFERENCES board_lists (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    # Checklists
    conn.execute('''
        CREATE TABLE IF NOT EXISTS checklists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            item TEXT NOT NULL,
            checked INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    ''')
    # Labels
    conn.execute('''
        CREATE TABLE IF NOT EXISTS labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Task-Labels mapping
    conn.execute('''
        CREATE TABLE IF NOT EXISTS task_labels (
            task_id INTEGER,
            label_id INTEGER,
            FOREIGN KEY (task_id) REFERENCES tasks (id),
            FOREIGN KEY (label_id) REFERENCES labels (id)
        )
    ''')
    # Attachments
    conn.execute('''
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            uploaded_by INTEGER,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    ''')
    
    # Default labels
    default_labels = [
        ('Urgent', '#ea4335'),
        ('High Priority', '#fbbc04'),
        ('Medium Priority', '#1a73e8'),
        ('Low Priority', '#34a853'),
        ('Feature', '#9c27b0'),
        ('Bug', '#ff6d00')
    ]
    for name, color in default_labels:
        exists = conn.execute('SELECT * FROM labels WHERE name = ?', (name,)).fetchone()
        if not exists:
            conn.execute('INSERT INTO labels (name, color) VALUES (?, ?)', (name, color))
    
    # Default admin
    admin = conn.execute('SELECT * FROM users WHERE username = ?', ('admin',)).fetchone()
    if not admin:
        hashed = hashlib.sha256('admin123'.encode()).hexdigest()
        conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                     ('admin', hashed, 'admin'))
    conn.commit()
    conn.close()

init_db()

@app.before_request
def log_request():
    if request.path == '/api/requests':
        return
    try:
        username = None
        if request.method in ('POST', 'PUT', 'PATCH'):
            if request.form:
                u = request.form.get('username')
                if u:
                    username = u.strip()
            if not username and request.is_json:
                data = request.get_json(silent=True) or {}
                u = data.get('username')
                if u:
                    username = str(u).strip()
        if not username:
            username = session.get('username')
        conn = sqlite3.connect('/data/task_manager.db')
        conn.execute('INSERT INTO request_logs (method, path, ip, status, username) VALUES (?, ?, ?, ?, ?)',
                     (request.method, request.path, request.remote_addr, 'pending', username))
        conn.commit()
        conn.close()
    except Exception:
        pass

@app.route('/api/requests', methods=['GET'])
def api_requests():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    logs = conn.execute('SELECT * FROM request_logs ORDER BY id DESC LIMIT 50').fetchall()
    conn.close()
    return jsonify([dict(l) for l in logs])

# ============ ROUTES ============

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('boards_page'))

@app.route('/boards')
def boards_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    boards = conn.execute('SELECT * FROM boards WHERE owner_id = ? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    conn.close()
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>My Boards</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Poppins', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 1200px; margin: auto; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; color: white; }
            .header h1 { font-size: 32px; font-weight: 700; }
            .user-info { background: rgba(255,255,255,0.2); padding: 10px 20px; border-radius: 30px; backdrop-filter: blur(10px); }
            .btn-logout { background: rgba(255,255,255,0.2); color: white; padding: 10px 20px; border-radius: 30px; text-decoration: none; margin-left: 15px; transition: 0.3s; }
            .btn-logout:hover { background: rgba(255,255,255,0.4); }
            .boards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 25px; }
            .board-card { background: white; padding: 25px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); transition: all 0.3s ease; text-decoration: none; color: #333; display: block; position: relative; overflow: hidden; }
            .board-card::before { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 4px; background: linear-gradient(90deg, #667eea, #764ba2); }
            .board-card:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(0,0,0,0.15); }
            .board-card h3 { margin: 0 0 10px 0; color: #333; font-size: 20px; font-weight: 600; }
            .board-card p { color: #666; font-size: 14px; }
            .add-board-btn { background: rgba(255,255,255,0.15); border: 2px dashed rgba(255,255,255,0.5); padding: 25px; border-radius: 16px; text-align: center; cursor: pointer; transition: 0.3s; color: white; backdrop-filter: blur(10px); }
            .add-board-btn:hover { background: rgba(255,255,255,0.25); border-color: white; transform: translateY(-5px); }
            .add-board-btn h3 { margin: 0; font-weight: 500; }
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); backdrop-filter: blur(5px); justify-content: center; align-items: center; z-index: 1000; }
            .modal-content { background: white; padding: 40px; border-radius: 20px; width: 450px; max-width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); animation: slideUp 0.3s ease; }
            @keyframes slideUp { from { transform: translateY(50px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
            .modal-content h2 { color: #333; margin-bottom: 20px; font-weight: 600; }
            .modal-content input { width: 100%; padding: 14px; margin: 12px 0; border: 2px solid #eee; border-radius: 12px; font-size: 15px; transition: 0.3s; }
            .modal-content input:focus { border-color: #667eea; outline: none; box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1); }
            .modal-content button { padding: 14px 30px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; border-radius: 12px; cursor: pointer; font-size: 16px; font-weight: 600; transition: 0.3s; width: 100%; margin-top: 10px; }
            .modal-content button:hover { transform: scale(1.02); box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4); }
            .modal-close { position: absolute; top: 15px; right: 20px; font-size: 24px; cursor: pointer; color: #999; transition: 0.3s; }
            .modal-close:hover { color: #333; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📋 My Boards</h1>
                <div>
                    <span class="user-info">👤 {{ user['username'] }}</span>
                    <a href="/logout" class="btn-logout">Logout</a>
                </div>
            </div>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <div class="boards-grid">
                {% for board in boards %}
                <a href="/board/{{ board['id'] }}" class="board-card">
                    <h3>{{ board['name'] }}</h3>
                    <p>{{ board['description'] or 'No description' }}</p>
                </a>
                {% endfor %}
                <div class="add-board-btn" onclick="openAddBoardModal()">
                    <h3>+ New Board</h3>
                </div>
            </div>
        </div>
        <div class="modal" id="addBoardModal">
            <div class="modal-content">
                <h2>Create New Board</h2>
                <input type="text" id="boardName" placeholder="Board name (e.g. Office Tasks)" required>
                <input type="text" id="boardDesc" placeholder="Description (optional)">
                <button onclick="createBoard()">Create</button>
                <button onclick="closeAddBoardModal()" style="background:#ea4335;">Cancel</button>
            </div>
        </div>
        <script>
        function openAddBoardModal() { document.getElementById('addBoardModal').style.display = 'flex'; }
        function closeAddBoardModal() { document.getElementById('addBoardModal').style.display = 'none'; }
        function createBoard() {
            const name = document.getElementById('boardName').value.trim();
            if(!name) { alert('Please enter a board name!'); return; }
            fetch('/api/create_board', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: name, description: document.getElementById('boardDesc').value.trim()})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        </script>
    </body>
    </html>
    ''', user=user, boards=boards)

@app.route('/api/create_board', methods=['POST'])
def create_board():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name: return jsonify({'error': 'Board name required'}), 400
    conn = get_db()
    owner = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    owner_id = session['user_id']
    if owner and owner['role'] == 'admin' and data.get('owner_id'):
        owner_id = int(data['owner_id'])
    conn.execute('INSERT INTO boards (name, description, owner_id) VALUES (?, ?, ?)', (name, data.get('description'), owner_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'owner_id': owner_id})

@app.route('/api/boards', methods=['GET'])
def api_boards():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    boards = conn.execute('SELECT * FROM boards ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(b) for b in boards])

@app.route('/api/boards/<int:board_id>', methods=['GET'])
def api_board_detail(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    board = conn.execute('SELECT * FROM boards WHERE id = ? AND owner_id = ?', (board_id, session['user_id'])).fetchone()
    if not board: return jsonify({'error': 'Board not found'}), 404
    lists = conn.execute('SELECT * FROM board_lists WHERE board_id = ? ORDER BY position', (board_id,)).fetchall()
    tasks = conn.execute('SELECT * FROM tasks WHERE board_id = ? ORDER BY position', (board_id,)).fetchall()
    conn.close()
    return jsonify({'board': dict(board), 'lists': [dict(l) for l in lists], 'tasks': [dict(t) for t in tasks]})

@app.route('/board/<int:board_id>')
def board_view(board_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    board = conn.execute('SELECT * FROM boards WHERE id = ? AND owner_id = ?', (board_id, session['user_id'])).fetchone()
    if not board: return redirect(url_for('boards_page'))
    lists = conn.execute('SELECT * FROM board_lists WHERE board_id = ? ORDER BY position', (board_id,)).fetchall()
    tasks = conn.execute('''
        SELECT tasks.*, users.username as users_username 
        FROM tasks 
        JOIN users ON tasks.user_id = users.id 
        WHERE tasks.board_id = ? 
        ORDER BY tasks.position
    ''', (board_id,)).fetchall()
    checklists = {}
    labels_by_task = {}
    all_labels = conn.execute('SELECT * FROM labels').fetchall()
    attachments_by_task = {}
    for task in tasks:
        cl = conn.execute('SELECT * FROM checklists WHERE task_id = ?', (task['id'],)).fetchall()
        checklists[task['id']] = cl
        labels = conn.execute('''
            SELECT labels.* FROM labels 
            JOIN task_labels ON labels.id = task_labels.label_id 
            WHERE task_labels.task_id = ?
        ''', (task['id'],)).fetchall()
        labels_by_task[task['id']] = labels
        atts = conn.execute('SELECT * FROM attachments WHERE task_id = ? ORDER BY uploaded_at DESC', (task['id'],)).fetchall()
        attachments_by_task[task['id']] = atts
    conn.close()
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ board['name'] }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Poppins', sans-serif; background: #f0f2f5; min-height: 100vh; padding: 20px; }
            .container { max-width: 100%; margin: auto; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; padding: 0 10px; }
            .header h1 { font-size: 28px; font-weight: 700; color: #333; display: flex; align-items: center; gap: 10px; }
            .btn-back { padding: 10px 20px; background: white; color: #333; text-decoration: none; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); transition: 0.3s; font-weight: 500; }
            .btn-back:hover { box-shadow: 0 5px 15px rgba(0,0,0,0.1); transform: translateY(-2px); }
            .board { display: flex; gap: 20px; overflow-x: auto; padding: 10px 0 30px 0; min-height: 400px; }
            .list-column { background: #ebecf0; border-radius: 16px; padding: 15px; min-width: 300px; max-width: 300px; display: flex; flex-direction: column; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
            .list-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 0 5px; }
            .list-header h3 { margin: 0; font-size: 16px; font-weight: 600; color: #172b4d; }
            .list-header .task-count { background: rgba(9,30,66,0.08); padding: 2px 12px; border-radius: 20px; font-size: 12px; color: #5e6c84; }
            .task-card { background: white; padding: 14px 16px; border-radius: 12px; box-shadow: 0 1px 3px rgba(9,30,66,0.15); margin-bottom: 10px; cursor: grab; transition: all 0.2s ease; border: 1px solid transparent; }
            .task-card:hover { box-shadow: 0 4px 12px rgba(9,30,66,0.2); transform: translateY(-2px); border-color: #667eea; }
            .task-card .card-title { font-weight: 600; font-size: 15px; color: #172b4d; margin-bottom: 4px; }
            .task-card .card-desc { font-size: 13px; color: #5e6c84; margin-bottom: 6px; }
            .task-card.dragging { opacity: 0.5; transform: scale(0.95); }
            .add-card-btn { width: 100%; padding: 10px; background: transparent; border: none; border-radius: 8px; margin-top: 8px; cursor: pointer; color: #5e6c84; font-size: 14px; transition: 0.2s; font-weight: 500; }
            .add-card-btn:hover { background: rgba(9,30,66,0.08); color: #172b4d; }
            .add-list-btn { min-width: 300px; max-width: 300px; background: rgba(255,255,255,0.5); border: 2px dashed #a0aabf; border-radius: 16px; padding: 20px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.3s; }
            .add-list-btn:hover { background: rgba(255,255,255,0.8); border-color: #667eea; }
            .add-list-btn h3 { color: #5e6c84; margin: 0; font-weight: 500; }
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); backdrop-filter: blur(5px); justify-content: center; align-items: center; z-index: 1000; }
            .modal-content { background: white; padding: 35px; border-radius: 20px; width: 500px; max-width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.2); position: relative; animation: slideUp 0.3s ease; }
            @keyframes slideUp { from { transform: translateY(50px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
            .modal-content h2 { font-size: 24px; font-weight: 600; color: #333; margin-bottom: 20px; }
            .modal-content input, .modal-content textarea, .modal-content select { width: 100%; padding: 12px 16px; margin: 8px 0; border: 2px solid #eee; border-radius: 12px; font-size: 15px; transition: 0.3s; font-family: 'Poppins', sans-serif; }
            .modal-content input:focus, .modal-content textarea:focus { border-color: #667eea; outline: none; box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1); }
            .modal-content textarea { resize: vertical; min-height: 80px; }
            .modal-content button { padding: 12px 30px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; border-radius: 12px; cursor: pointer; font-size: 16px; font-weight: 600; transition: 0.3s; width: 100%; margin-top: 10px; }
            .modal-content button:hover { transform: scale(1.02); box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3); }
            .modal-close { position: absolute; top: 15px; right: 20px; font-size: 24px; cursor: pointer; color: #999; transition: 0.3s; }
            .modal-close:hover { color: #333; transform: rotate(90deg); }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📋 {{ board['name'] }}</h1>
                <a href="/boards" class="btn-back">← Back to Boards</a>
            </div>
            <div class="board">
                {% for lst in lists %}
                <div class="list-column" data-list-id="{{ lst['id'] }}">
                    <div class="list-header">
                        <h3>{{ lst['name'] }}</h3>
                        <span class="task-count">{{ tasks|selectattr('list_id', 'equalto', lst['id'])|list|length }}</span>
                    </div>
                    <div>
                        {% for task in tasks if task['list_id'] == lst['id'] %}
                        <div class="task-card" draggable="true" data-task-id="{{ task['id'] }}" data-list-id="{{ task['list_id'] }}">
                            <div class="card-title">{{ task['title'] }}</div>
                            {% if task['description'] %}<div class="card-desc">{{ task['description'][:60] }}{% if task['description']|length > 60 %}...{% endif %}</div>{% endif %}
                            
                            <!-- Labels -->
                            <div class="labels-container" style="display:flex;gap:4px;flex-wrap:wrap;margin:6px 0;">
                                {% for label in labels_by_task[task['id']] %}
                                <span style="background:{{ label['color'] }};padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;color:white;">{{ label['name'] }}</span>
                                {% endfor %}
                            </div>

                            <!-- Checklists -->
                            <div class="checklist" style="margin:8px 0;padding:8px;background:#f8f9fa;border-radius:8px;">
                                <div style="font-size:13px;font-weight:600;color:#5f6368;margin-bottom:4px;">📝 Sub-tasks:</div>
                                {% for item in checklists[task['id']] %}
                                <div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:14px;">
                                    <input type="checkbox" {% if item['checked'] %}checked{% endif %} onchange="toggleChecklist({{ item['id'] }}, this.checked)">
                                    <span style="{% if item['checked'] %}text-decoration:line-through;color:#999;{% endif %}">{{ item['item'] }}</span>
                                </div>
                                {% endfor %}
                                <div style="display:flex;gap:6px;margin-top:6px;">
                                    <input type="text" id="newChecklist_{{ task['id'] }}" placeholder="Add sub-task..." style="flex:1;padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:13px;">
                                    <button onclick="addChecklist({{ task['id'] }})" style="padding:6px 12px;background:#1a73e8;color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Add</button>
                                </div>
                            </div>

                            <!-- Attachments -->
                            <div class="attachments-container" style="margin:8px 0;padding:8px;background:#f8f9fa;border-radius:8px;">
                                <div style="font-size:13px;font-weight:600;color:#5f6368;margin-bottom:4px;">📎 Attachments:</div>
                                {% for att in attachments_by_task[task['id']] %}
                                <div style="display:flex;align-items:center;gap:8px;padding:2px 0;font-size:13px;">
                                    <a href="/download/{{ att['id'] }}" target="_blank">{{ att['filename'] }}</a>
                                    <span style="color:#ea4335;cursor:pointer;font-size:12px;" onclick="deleteAttachment({{ att['id'] }})">🗑️</span>
                                </div>
                                {% endfor %}
                                <div style="display:flex;gap:6px;margin-top:6px;">
                                    <form action="/upload/{{ task['id'] }}" method="POST" enctype="multipart/form-data" style="display:flex;gap:6px;flex:1;flex-wrap:wrap;">
                                        <input type="file" name="file" style="flex:1;padding:4px;font-size:13px;border:1px solid #ddd;border-radius:6px;">
                                        <button type="submit" style="padding:4px 12px;background:#1a73e8;color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Upload</button>
                                    </form>
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    <button class="add-card-btn" onclick="openAddCard({{ lst['id'] }})">+ Add a card</button>
                </div>
                {% endfor %}
                <div class="add-list-btn" onclick="openAddList({{ board['id'] }})">
                    <h3 style="color:#5e6c84;">+ Add a list</h3>
                </div>
            </div>
        </div>
        <div class="modal" id="addListModal">
            <div class="modal-content">
                <h2>Add New List</h2>
                <input type="text" id="addListName" placeholder="List name (e.g. To Do)">
                <button onclick="submitAddList({{ board['id'] }})">Add</button>
                <button onclick="closeModal('addListModal')" style="background:#ea4335;">Cancel</button>
            </div>
        </div>
        <div class="modal" id="addCardModal">
            <div class="modal-content">
                <h2>Add New Card</h2>
                <input type="hidden" id="addCardListId">
                <input type="text" id="addCardTitle" placeholder="Card title">
                <textarea id="addCardDesc" placeholder="Description (optional)"></textarea>
                <button onclick="submitAddCard()">Add</button>
                <button onclick="closeModal('addCardModal')" style="background:#ea4335;">Cancel</button>
            </div>
        </div>
        <script>
        let addCardListId = null;

        function openModal(id) { document.getElementById(id).style.display = 'flex'; }
        function closeModal(id) { document.getElementById(id).style.display = 'none'; }
        
        function openAddList(boardId) { document.getElementById('addListName').value = ''; openModal('addListModal'); }
        
        function openAddCard(listId) {
            addCardListId = listId;
            document.getElementById('addCardListId').value = listId;
            document.getElementById('addCardTitle').value = '';
            document.getElementById('addCardDesc').value = '';
            openModal('addCardModal');
        }
        
        function submitAddList(boardId) {
            const name = document.getElementById('addListName').value.trim();
            if(!name) { alert('Please enter a list name!'); return; }
            fetch('/api/add_list', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({board_id: boardId, name: name})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        
        function submitAddCard() {
            const listId = document.getElementById('addCardListId').value;
            const title = document.getElementById('addCardTitle').value.trim();
            if(!title) { alert('Please enter a card title!'); return; }
            fetch('/api/add_card', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    list_id: listId,
                    title: title,
                    description: document.getElementById('addCardDesc').value.trim()
                })
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        
        // Drag & Drop
        let draggedCardId = null;
        document.addEventListener('dragstart', function(e) {
            if(e.target.classList.contains('task-card')) {
                draggedCardId = e.target.dataset.taskId;
                e.target.style.opacity = '0.5';
            }
        });
        document.addEventListener('dragend', function(e) {
            if(e.target.classList.contains('task-card')) e.target.style.opacity = '1';
        });
        document.addEventListener('dragover', function(e) { e.preventDefault(); });
        document.addEventListener('drop', function(e) {
            e.preventDefault();
            const dropZone = e.target.closest('.list-column');
            if(dropZone && draggedCardId) {
                const newListId = dropZone.dataset.listId;
                fetch('/api/move_task', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({task_id: draggedCardId, list_id: newListId})
                }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
            }
        });

        // Checklist functions
        function addChecklist(taskId) {
            const input = document.getElementById('newChecklist_' + taskId);
            const item = input.value.trim();
            if(!item) return;
            fetch('/api/add_checklist', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, item: item})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }
        function toggleChecklist(itemId, checked) {
            fetch('/api/toggle_checklist', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({item_id: itemId, checked: checked})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }

        // Label functions
        function addLabel(taskId) {
            const select = document.getElementById('labelSelect_' + taskId);
            const labelId = select.value;
            if(!labelId) return;
            fetch('/api/add_label', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, label_id: labelId})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }
        function removeLabel(taskId, labelId) {
            fetch('/api/remove_label', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, label_id: labelId})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }

        // Attachment functions
        function deleteAttachment(attId) {
            if(!confirm('Delete this attachment?')) return;
            fetch('/api/delete_attachment/' + attId, { method: 'DELETE' })
            .then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }
        </script>
    </body>
    </html>
    ''', board=board, lists=lists, tasks=tasks, checklists=checklists, labels_by_task=labels_by_task, all_labels=all_labels, attachments_by_task=attachments_by_task)

# ============ API ROUTES ============

@app.route('/api/add_list', methods=['POST'])
def add_list():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    board_id = data.get('board_id')
    name = data.get('name', '').strip()
    if not board_id or not name: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    pos = conn.execute('SELECT MAX(position) as max FROM board_lists WHERE board_id = ?', (board_id,)).fetchone()['max'] or 0
    conn.execute('INSERT INTO board_lists (board_id, name, position) VALUES (?, ?, ?)', (board_id, name, pos + 1))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/add_card', methods=['POST'])
def add_card():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    list_id = data.get('list_id')
    title = data.get('title', '').strip()
    if not list_id or not title: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    board = conn.execute('SELECT board_id FROM board_lists WHERE id = ?', (list_id,)).fetchone()
    if not board: return jsonify({'error': 'List not found'}), 404
    pos = conn.execute('SELECT MAX(position) as max FROM tasks WHERE list_id = ?', (list_id,)).fetchone()['max'] or 0
    cursor = conn.execute('INSERT INTO tasks (board_id, list_id, user_id, title, description, position) VALUES (?, ?, ?, ?, ?, ?)', 
                 (board['board_id'], list_id, session['user_id'], title, data.get('description'), pos + 1))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/move_task', methods=['POST'])
def move_task():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    new_list_id = data.get('list_id')
    if not task_id or not new_list_id: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    board = conn.execute('SELECT board_id FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not board: return jsonify({'error': 'Task not found'}), 404
    pos = conn.execute('SELECT MAX(position) as max FROM tasks WHERE list_id = ?', (new_list_id,)).fetchone()['max'] or 0
    conn.execute('UPDATE tasks SET list_id = ?, position = ? WHERE id = ?', (new_list_id, pos + 1, task_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ============ EDIT API ============
@app.route('/api/edit_board', methods=['POST'])
def edit_board():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    board_id = data.get('board_id')
    name = data.get('name', '').strip()
    if not board_id or not name: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    board = conn.execute('SELECT * FROM boards WHERE id = ? AND owner_id = ?', (board_id, session['user_id'])).fetchone()
    if not board: return jsonify({'error': 'Board not found'}), 404
    conn.execute('UPDATE boards SET name = ?, description = ? WHERE id = ?', (name, data.get('description', board['description']), board_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/delete_board/<int:board_id>', methods=['DELETE'])
def delete_board(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    board = conn.execute('SELECT * FROM boards WHERE id = ? AND owner_id = ?', (board_id, session['user_id'])).fetchone()
    if not board: return jsonify({'error': 'Board not found'}), 404
    tasks = conn.execute('SELECT id FROM tasks WHERE board_id = ?', (board_id,)).fetchall()
    for task in tasks:
        conn.execute('DELETE FROM task_labels WHERE task_id = ?', (task['id'],))
        conn.execute('DELETE FROM checklists WHERE task_id = ?', (task['id'],))
        conn.execute('DELETE FROM attachments WHERE task_id = ?', (task['id'],))
    conn.execute('DELETE FROM tasks WHERE board_id = ?', (board_id,))
    conn.execute('DELETE FROM board_lists WHERE board_id = ?', (board_id,))
    conn.execute('DELETE FROM boards WHERE id = ?', (board_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/delete_list/<int:list_id>', methods=['DELETE'])
def delete_list(list_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    lst = conn.execute('SELECT * FROM board_lists WHERE id = ?', (list_id,)).fetchone()
    if not lst: return jsonify({'error': 'List not found'}), 404
    board = conn.execute('SELECT * FROM boards WHERE id = ? AND owner_id = ?', (lst['board_id'], session['user_id'])).fetchone()
    if not board: return jsonify({'error': 'Board not found'}), 404
    tasks = conn.execute('SELECT id FROM tasks WHERE list_id = ?', (list_id,)).fetchall()
    for task in tasks:
        conn.execute('DELETE FROM task_labels WHERE task_id = ?', (task['id'],))
        conn.execute('DELETE FROM checklists WHERE task_id = ?', (task['id'],))
        conn.execute('DELETE FROM attachments WHERE task_id = ?', (task['id'],))
    conn.execute('DELETE FROM tasks WHERE list_id = ?', (list_id,))
    conn.execute('DELETE FROM board_lists WHERE id = ?', (list_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/edit_task', methods=['POST'])
def edit_task():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    title = data.get('title', '').strip()
    if not task_id or not title: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not task: return jsonify({'error': 'Task not found'}), 404
    board = conn.execute('SELECT * FROM boards WHERE id = ? AND owner_id = ?', (task['board_id'], session['user_id'])).fetchone()
    if not board: return jsonify({'error': 'Board not found'}), 404
    conn.execute('UPDATE tasks SET title = ?, description = ? WHERE id = ?', (title, data.get('description', task['description']), task_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/delete_task/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not task: return jsonify({'error': 'Task not found'}), 404
    board = conn.execute('SELECT * FROM boards WHERE id = ? AND owner_id = ?', (task['board_id'], session['user_id'])).fetchone()
    if not board: return jsonify({'error': 'Board not found'}), 404
    conn.execute('DELETE FROM task_labels WHERE task_id = ?', (task_id,))
    conn.execute('DELETE FROM checklists WHERE task_id = ?', (task_id,))
    conn.execute('DELETE FROM attachments WHERE task_id = ?', (task_id,))
    conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ============ CHECKLIST API ============
@app.route('/api/add_checklist', methods=['POST'])
def add_checklist():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    item = data.get('item', '').strip()
    if not task_id or not item: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    conn.execute('INSERT INTO checklists (task_id, item) VALUES (?, ?)', (task_id, item))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/toggle_checklist', methods=['POST'])
def toggle_checklist():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    item_id = data.get('item_id')
    checked = data.get('checked') == 'true'
    if not item_id: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    conn.execute('UPDATE checklists SET checked = ? WHERE id = ?', (1 if checked else 0, item_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ============ LABEL API ============
@app.route('/api/add_label', methods=['POST'])
def add_label():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    label_id = data.get('label_id')
    if not task_id or not label_id: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    conn.execute('INSERT INTO task_labels (task_id, label_id) VALUES (?, ?)', (task_id, label_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/remove_label', methods=['POST'])
def remove_label():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    label_id = data.get('label_id')
    if not task_id or not label_id: return jsonify({'error': 'Invalid data'}), 400
    conn = get_db()
    conn.execute('DELETE FROM task_labels WHERE task_id = ? AND label_id = ?', (task_id, label_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ============ ATTACHMENT API ============
@app.route('/upload/<int:task_id>', methods=['POST'])
def upload_file(task_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    if 'file' not in request.files: return jsonify({'error': 'No file selected'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename): return jsonify({'error': 'File type not allowed'}), 400
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    conn = get_db()
    conn.execute('INSERT INTO attachments (task_id, filename, filepath, uploaded_by) VALUES (?, ?, ?, ?)', 
                 (task_id, file.filename, filepath, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/download/<int:att_id>')
def download_file(att_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    att = conn.execute('SELECT * FROM attachments WHERE id = ?', (att_id,)).fetchone()
    conn.close()
    if not att: return jsonify({'error': 'Attachment not found'}), 404
    return send_from_directory(app.config['UPLOAD_FOLDER'], att['filepath'].split('/')[-1])

@app.route('/api/delete_attachment/<int:att_id>', methods=['DELETE'])
def delete_attachment(att_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    att = conn.execute('SELECT * FROM attachments WHERE id = ?', (att_id,)).fetchone()
    if not att: return jsonify({'error': 'Attachment not found'}), 404
    os.remove(att['filepath'])
    conn.execute('DELETE FROM attachments WHERE id = ?', (att_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ============ AUTH ROUTES ============

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('boards_page'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and verify_password(password, user['password']):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('boards_page'))
        flash('Invalid username or password!', 'error')
    return render_template_string(LOGIN_PAGE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session: return redirect(url_for('boards_page'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        if not username or not password: flash('Please fill all fields!', 'error')
        elif password != confirm: flash('Passwords do not match!', 'error')
        elif len(password) < 4: flash('Password must be at least 4 characters!', 'error')
        else:
            conn = get_db()
            existing = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if existing: flash('Username already taken!', 'error')
            else:
                conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashlib.sha256(password.encode()).hexdigest()))
                conn.commit()
                flash('Account created! Please login.', 'success')
            conn.close()
            return redirect(url_for('login'))
    return render_template_string(REGISTER_PAGE)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

LOGIN_PAGE = '''
<!DOCTYPE html>
<html><head><title>Login</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:'Poppins',sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.login-box{background:white;padding:40px;border-radius:20px;box-shadow:0 10px 30px rgba(0,0,0,0.1);max-width:400px;width:90%}h1{color:#1a73e8;text-align:center}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:8px}button{width:100%;padding:12px;background:#1a73e8;color:white;border:none;border-radius:8px;cursor:pointer}.links{text-align:center;margin-top:20px}.flash{padding:12px;border-radius:8px;margin-bottom:15px}.flash-success{background:#e6f4ea;color:#137333}.flash-error{background:#fce8e6;color:#c5221f}</style></head>
<body><div class="login-box"><h1>📋 Task Manager</h1><p style="text-align:center;color:#5f6368;">Login to manage your boards</p>
{% with messages = get_flashed_messages(with_categories=true) %}{% for category, message in messages %}<div class="flash flash-{{ category }}">{{ message }}</div>{% endfor %}{% endwith %}
<form method="POST"><input type="text" name="username" placeholder="Username" required><input type="password" name="password" placeholder="Password" required><button type="submit">🔑 Login</button></form>
<div class="links">Don't have an account? <a href="/register" style="color:#1a73e8;text-decoration:none;">Register here</a></div></div></body></html>
'''

REGISTER_PAGE = '''
<!DOCTYPE html>
<html><head><title>Register</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:'Poppins',sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.register-box{background:white;padding:40px;border-radius:20px;box-shadow:0 10px 30px rgba(0,0,0,0.1);max-width:400px;width:90%}h1{color:#1a73e8;text-align:center}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:8px}button{width:100%;padding:12px;background:#1a73e8;color:white;border:none;border-radius:8px;cursor:pointer}.links{text-align:center;margin-top:20px}.flash{padding:12px;border-radius:8px;margin-bottom:15px}.flash-success{background:#e6f4ea;color:#137333}.flash-error{background:#fce8e6;color:#c5221f}</style></head>
<body><div class="register-box"><h1>📋 Task Manager</h1><p style="text-align:center;color:#5f6368;">Create a new account</p>
{% with messages = get_flashed_messages(with_categories=true) %}{% for category, message in messages %}<div class="flash flash-{{ category }}">{{ message }}</div>{% endfor %}{% endwith %}
<form method="POST"><input type="text" name="username" placeholder="Choose a username" required><input type="password" name="password" placeholder="Password (min 4 chars)" required><input type="password" name="confirm_password" placeholder="Confirm password" required><button type="submit">✅ Register</button></form>
<div class="links">Already have an account? <a href="/login" style="color:#1a73e8;text-decoration:none;">Login here</a></div></div></body></html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)