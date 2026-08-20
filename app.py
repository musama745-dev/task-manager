from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from supabase import create_client, Client
import hashlib
import os
import threading
import requests
from datetime import date, datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', '') or 'task_manager_secret_key_12345'

# ============ SUPABASE SETUP ============
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# n8n webhook URL for email notifications (login + board limit, set in Vercel Dashboard)
N8N_LOGIN_WEBHOOK = os.environ.get('N8N_LOGIN_WEBHOOK', '')

# ============ GOOGLE SETUP ============
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')

# ============ POSTHOG SETUP ============
POSTHOG_API_KEY = os.environ.get('POSTHOG_API_KEY', '01a00fa2-edf3-0000-8c6f-c5854ca38dcb')
POSTHOG_HOST = os.environ.get('POSTHOG_HOST', 'https://us.posthog.com')

try:
    from posthog import Posthog
    posthog_client = Posthog(project_api_key=POSTHOG_API_KEY, host=POSTHOG_HOST)
    _posthog_available = True
except Exception as e:
    print(f"posthog init warning: {e}")
    posthog_client = None
    _posthog_available = False

def track_event(distinct_id, event, properties=None):
    """Safely track a PostHog event (non-blocking)."""
    if not _posthog_available:
        return
    try:
        props = dict(properties or {})
        props.setdefault('$ip', request.remote_addr or '')
        threading.Thread(
            target=posthog_client.capture,
            args=(str(distinct_id), event),
            kwargs={'properties': props},
            daemon=True
        ).start()
    except Exception as e:
        print(f"posthog track warning: {e}")

def _notify_webhook(payload):
    """Fire-and-forget webhook to n8n (background thread)."""
    if not N8N_LOGIN_WEBHOOK:
        return
    try:
        requests.post(N8N_LOGIN_WEBHOOK, json=payload, timeout=5)
    except Exception as e:
        print(f"n8n notify warning: {e}")

def notify_login(username, email, ip):
    """Email notification when a user logs in."""
    pass  # Webhook removed for logins


def notify_board_limit(username, email, count):
    """Email notification when a user crosses the board limit."""
    _notify_webhook({
        'type': 'board_limit',
        'username': username,
        'email': email or '',
        'count': count,
        'limit': 50,
        'time': datetime.now().isoformat()
    })

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'xlsx', 'pptx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    """Seed default labels and admin user if they don't exist."""
    if not supabase:
        return
    try:
        # Default labels
        existing = supabase.table('labels').select('name').execute().data
        existing_names = [l['name'] for l in existing]
        default_labels = [
            ('Urgent', '#ea4335'),
            ('High Priority', '#fbbc04'),
            ('Medium Priority', '#1a73e8'),
            ('Low Priority', '#34a853'),
            ('Feature', '#9c27b0'),
            ('Bug', '#ff6d00')
        ]
        for name, color in default_labels:
            if name not in existing_names:
                supabase.table('labels').insert({'name': name, 'color': color}).execute()
        # Default admin
        admin = supabase.table('users').select('*').eq('username', 'admin').execute().data
        if not admin:
            hashed = hashlib.sha256('admin123'.encode()).hexdigest()
            supabase.table('users').insert({'username': 'admin', 'password': hashed, 'role': 'admin'}).execute()
    except Exception as e:
        print(f"init_db warning: {e}")

init_db()

# ============ ROUTES ============

@app.route('/')
def home():
    if not supabase:
        return '''<h1>⚙️ Setup Required</h1>
        <p>Please set <code>SUPABASE_URL</code> and <code>SUPABASE_KEY</code> environment variables in Vercel Dashboard.</p>
        <p>Then run the <code>init_supabase.sql</code> script in Supabase SQL Editor.</p>''', 503
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('boards_page'))

@app.route('/boards')
def boards_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_data = supabase.table('users').select('*').eq('id', session['user_id']).execute().data
    if not user_data:
        session.clear()
        return redirect(url_for('login'))
    user = user_data[0]
    boards = supabase.table('boards').select('*').eq('owner_id', session['user_id']).order('created_at', desc=True).execute().data
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>My Boards</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root { --bg-grad-start: #667eea; --bg-grad-end: #764ba2; --card-bg: white; --text: #333; --text-secondary: #666; --border: #eee; }
            [data-theme="dark"] { --bg-grad-start: #1a1a2e; --bg-grad-end: #16213e; --card-bg: #16213e; --text: #e0e0e0; --text-secondary: #a0a0b0; --border: #333; }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Poppins', sans-serif; background: linear-gradient(135deg, var(--bg-grad-start) 0%, var(--bg-grad-end) 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 1200px; margin: auto; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; color: white; }
            .header h1 { font-size: 32px; font-weight: 700; }
            .user-info { background: rgba(255,255,255,0.2); padding: 10px 20px; border-radius: 30px; backdrop-filter: blur(10px); }
            .btn-logout { background: rgba(255,255,255,0.2); color: white; padding: 10px 20px; border-radius: 30px; text-decoration: none; margin-left: 15px; transition: 0.3s; }
            .btn-logout:hover { background: rgba(255,255,255,0.4); }
            .boards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 25px; }
            .board-card { background: var(--card-bg); padding: 25px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); transition: all 0.3s ease; text-decoration: none; color: var(--text); display: block; position: relative; overflow: hidden; }
            .board-card::before { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 4px; background: linear-gradient(90deg, #667eea, #764ba2); }
            .board-card:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(0,0,0,0.15); }
            .board-card h3 { margin: 0 0 10px 0; color: var(--text); font-size: 20px; font-weight: 600; }
            .board-card p { color: var(--text-secondary); font-size: 14px; }
            .board-card .board-actions { display: flex; gap: 8px; margin-top: 14px; }
            .card-btn { padding: 6px 14px; background: #f1f3f4; color: #333; border: none; border-radius: 8px; cursor: pointer; font-size: 12px; font-weight: 600; transition: 0.2s; font-family: 'Poppins', sans-serif; }
            .card-btn:hover { background: #e8eaed; }
            .card-btn.del { background: #fee2e2; color: #991b2b; }
            .card-btn.del:hover { background: #fecaca; }
            .flash { padding: 12px 20px; border-radius: 10px; margin-bottom: 20px; font-weight: 500; }
            .flash-success { background: #dcfce7; color: #166534; }
            .flash-error { background: #fee2e2; color: #991b2b; }
            .add-board-btn { background: rgba(255,255,255,0.15); border: 2px dashed rgba(255,255,255,0.5); padding: 25px; border-radius: 16px; text-align: center; cursor: pointer; transition: 0.3s; color: white; backdrop-filter: blur(10px); }
            .add-board-btn:hover { background: rgba(255,255,255,0.25); border-color: white; transform: translateY(-5px); }
            .add-board-btn h3 { margin: 0; font-weight: 500; }
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); backdrop-filter: blur(5px); justify-content: center; align-items: center; z-index: 1000; }
            .modal-content { background: var(--card-bg); padding: 40px; border-radius: 20px; width: 450px; max-width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.3); animation: slideUp 0.3s ease; }
            @keyframes slideUp { from { transform: translateY(50px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
            .modal-content h2 { color: #333; margin-bottom: 20px; font-weight: 600; }
            .modal-content input { width: 100%; padding: 14px; margin: 12px 0; border: 2px solid var(--border); border-radius: 12px; font-size: 15px; transition: 0.3s; background: var(--bg); color: var(--text); }
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
                    <button class="btn-logout" onclick="toggleDark()" id="darkBtn" style="border-radius:30px;border:none;cursor:pointer;font-size:16px;">🌙</button>
                    <span class="user-info">👤 {{ user['username'] }}</span>
                    {% if user['role'] == 'admin' %}
                    <a href="/login-log" class="btn-logout">📊 Login Activity</a>
                    {% endif %}
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
                    <div class="board-actions">
                        <button class="card-btn" onclick="event.preventDefault();event.stopPropagation();editBoard({{ board['id'] }}, '{{ board['name'] }}')">✏️ Edit</button>
                        <button class="card-btn del" onclick="event.preventDefault();event.stopPropagation();deleteBoard({{ board['id'] }})">🗑️ Delete</button>
                    </div>
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
        function editBoard(boardId, currentName) {
            const name = prompt('Board name:', currentName);
            if(!name || !name.trim()) return;
            const desc = prompt('Description:', '');
            fetch('/api/edit_board', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({board_id: boardId, name: name.trim(), description: desc})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function deleteBoard(boardId) {
            if(!confirm('Delete this board and all its lists/tasks?')) return;
            fetch('/api/delete_board/' + boardId, { method: 'DELETE' })
            .then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
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
    supabase.table('boards').insert({
        'name': name,
        'description': data.get('description'),
        'owner_id': session['user_id']
    }).execute()
    track_event(session['user_id'], 'board_created', {
        'board_name': name,
        'board_id': session['user_id']
    })

    # Board limit alert: email when a user reaches 50 boards
    try:
        bcount = len(supabase.table('boards').select('id').eq('owner_id', session['user_id']).execute().data)
        if bcount == 50:
            uinfo = supabase.table('users').select('username', 'email').eq('id', session['user_id']).execute().data
            uname = uinfo[0]['username'] if uinfo else session.get('username', 'user')
            uemail = uinfo[0].get('email') if uinfo else ''
            threading.Thread(target=notify_board_limit, args=(uname, uemail, bcount), daemon=True).start()
    except Exception as e:
        print(f"board limit check warning: {e}")

    return jsonify({'success': True})

@app.route('/board/<int:board_id>')
def board_view(board_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    board_data = supabase.table('boards').select('*').eq('id', board_id).eq('owner_id', session['user_id']).execute().data
    if not board_data: return redirect(url_for('boards_page'))
    board = board_data[0]
    lists = supabase.table('board_lists').select('*').eq('board_id', board_id).order('position').execute().data
    # Get tasks with user info
    tasks_raw = []
    try:
        tasks_raw = supabase.table('tasks').select('*, users(username)').eq('board_id', board_id).order('position').execute().data
    except:
        tasks_raw = supabase.table('tasks').select('*').eq('board_id', board_id).order('position').execute().data
    tasks = []
    for t in tasks_raw:
        user_info = t.pop('users', None) if isinstance(t.get('users'), dict) else None
        t['users_username'] = user_info['username'] if user_info else ''
        tasks.append(t)
    # Batch fetch checklists, labels, attachments
    task_ids = [t['id'] for t in tasks]
    checklists = {tid: [] for tid in task_ids}
    labels_by_task = {tid: [] for tid in task_ids}
    attachments_by_task = {tid: [] for tid in task_ids}
    if task_ids:
        try:
            all_cl = supabase.table('checklists').select('*').in_('task_id', task_ids).execute().data
            for cl in all_cl:
                checklists[cl['task_id']].append(cl)
        except:
            pass
        try:
            all_tl = supabase.table('task_labels').select('task_id, labels(*)').in_('task_id', task_ids).execute().data
            for tl in all_tl:
                label_info = tl.get('labels')
                if label_info:
                    labels_by_task[tl['task_id']].append(label_info)
        except:
            pass
        try:
            all_att = supabase.table('attachments').select('*').in_('task_id', task_ids).order('uploaded_at', desc=True).execute().data
            for att in all_att:
                attachments_by_task[att['task_id']].append(att)
        except:
            pass
    # Fetch comments for all tasks
    comments_by_task = {tid: [] for tid in task_ids}
    if task_ids:
        try:
            all_cm = supabase.table('comments').select('*').in_('task_id', task_ids).order('created_at').execute().data
            for cm in all_cm:
                cm['username'] = ''
                try:
                    u = supabase.table('users').select('username').eq('id', cm['user_id']).execute().data
                    if u: cm['username'] = u[0]['username']
                except:
                    pass
                comments_by_task[cm['task_id']].append(cm)
        except:
            pass
    all_labels = []
    try:
        all_labels = supabase.table('labels').select('*').execute().data
    except:
        pass
    all_users = []
    try:
        all_users = supabase.table('users').select('id, username').execute().data
    except:
        pass
    # Fetch dependencies
    deps_by_task = {tid: [] for tid in task_ids}
    if task_ids:
        try:
            all_deps = supabase.table('task_dependencies').select('*, tasks!task_dependencies_blocked_by_id_fkey(title)').execute().data
            for d in all_deps:
                bt = d.pop('tasks', None)
                if d.get('task_id') in deps_by_task:
                    deps_by_task[d['task_id']].append({'id': d['id'], 'blocked_by_id': d['blocked_by_id'], 'blocked_by_title': bt['title'] if bt else ''})
        except:
            pass
    # Activity log
    activity_logs = []
    try:
        activity_logs = supabase.table('activity_log').select('*, users(username)').eq('board_id', board_id).order('created_at', desc=True).limit(30).execute().data
        for al in activity_logs:
            u = al.pop('users', None)
            al['username'] = u['username'] if u else 'system'
    except:
        pass
    # Board shares
    board_shares = []
    try:
        board_shares = supabase.table('board_shares').select('*, users(username)').eq('board_id', board_id).execute().data
        for bs in board_shares:
            u = bs.pop('users', None)
            bs['username'] = u['username'] if u else ''
    except:
        pass
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ board['name'] }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root { --bg: #f0f2f5; --card-bg: white; --text: #333; --text-secondary: #5e6c84; --list-bg: #ebecf0; --border: #eee; --modal-bg: white; }
            [data-theme="dark"] { --bg: #1a1a2e; --card-bg: #16213e; --text: #e0e0e0; --text-secondary: #a0a0b0; --list-bg: #0f3460; --border: #333; --modal-bg: #16213e; }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Poppins', sans-serif; background: var(--bg); min-height: 100vh; padding: 20px; color: var(--text); }
            .container { max-width: 100%; margin: auto; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 0 10px; flex-wrap: wrap; gap: 10px; }
            .header h1 { font-size: 28px; font-weight: 700; color: var(--text); display: flex; align-items: center; gap: 10px; }
            .btn-back { padding: 10px 20px; background: var(--card-bg); color: var(--text); text-decoration: none; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); transition: 0.3s; font-weight: 500; }
            .btn-back:hover { box-shadow: 0 5px 15px rgba(0,0,0,0.1); transform: translateY(-2px); }
            .filter-bar { display: flex; gap: 10px; margin-bottom: 20px; padding: 12px 16px; background: var(--card-bg); border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); flex-wrap: wrap; align-items: center; }
            .filter-bar input, .filter-bar select { padding: 8px 12px; border: 2px solid var(--border); border-radius: 8px; font-size: 13px; font-family: 'Poppins', sans-serif; background: var(--bg); color: var(--text); }
            .filter-bar input { flex: 1; min-width: 180px; }
            .filter-bar select { min-width: 130px; }
            .filter-bar .filter-label { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
            .filter-clear { padding: 6px 14px; background: #ea4335; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 12px; font-weight: 600; font-family: 'Poppins', sans-serif; }
            .board { display: flex; gap: 20px; overflow-x: auto; padding: 10px 0 30px 0; min-height: 400px; }
            .list-column { background: var(--list-bg); border-radius: 16px; padding: 15px; min-width: 300px; max-width: 300px; display: flex; flex-direction: column; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
            .list-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 0 5px; }
            .list-header h3 { margin: 0; font-size: 16px; font-weight: 600; color: var(--text); }
            .list-header .task-count { background: rgba(9,30,66,0.08); padding: 2px 12px; border-radius: 20px; font-size: 12px; color: var(--text-secondary); }
            .task-card { background: var(--card-bg); padding: 14px 16px; border-radius: 12px; box-shadow: 0 1px 3px rgba(9,30,66,0.15); margin-bottom: 10px; cursor: grab; transition: all 0.2s ease; border: 1px solid transparent; }
            .task-card:hover { box-shadow: 0 4px 12px rgba(9,30,66,0.2); transform: translateY(-2px); border-color: #667eea; }
            .task-card .card-title { font-weight: 600; font-size: 15px; color: var(--text); margin-bottom: 4px; }
            .task-card .card-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
            .task-card.dragging { opacity: 0.5; transform: scale(0.95); }
            .add-card-btn { width: 100%; padding: 10px; background: transparent; border: none; border-radius: 8px; margin-top: 8px; cursor: pointer; color: var(--text-secondary); font-size: 14px; transition: 0.2s; font-weight: 500; }
            .add-card-btn:hover { background: rgba(9,30,66,0.08); color: var(--text); }
            .add-list-btn { min-width: 300px; max-width: 300px; background: rgba(255,255,255,0.5); border: 2px dashed #a0aabf; border-radius: 16px; padding: 20px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.3s; }
            .add-list-btn:hover { background: rgba(255,255,255,0.8); border-color: #667eea; }
            .add-list-btn h3 { color: var(--text-secondary); margin: 0; font-weight: 500; }
            .header-actions { display: flex; gap: 10px; align-items: center; }
            .btn-sm { padding: 8px 16px; background: var(--card-bg); color: var(--text); border: none; border-radius: 12px; cursor: pointer; font-size: 13px; font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,0.05); transition: 0.3s; font-family: 'Poppins', sans-serif; }
            .btn-sm:hover { box-shadow: 0 5px 15px rgba(0,0,0,0.1); transform: translateY(-2px); }
            .btn-sm.btn-danger { background: #ea4335; color: white; }
            .del-list { background: transparent; border: none; color: var(--text-secondary); font-size: 16px; cursor: pointer; padding: 4px 8px; border-radius: 6px; transition: 0.2s; }
            .del-list:hover { background: rgba(234,67,53,0.1); color: #ea4335; }
            .task-header { display: flex; align-items: flex-start; gap: 8px; }
            .completion-checkbox { width: 18px; height: 18px; accent-color: #34a853; cursor: pointer; margin-top: 2px; flex-shrink: 0; }
            .task-card.completed { opacity: 0.6; }
            .task-card.completed .card-title { text-decoration: line-through; color: #999; }
            .task-meta { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
            .priority-badge { display: inline-block; padding: 2px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; border: none; font-family: 'Poppins', sans-serif; }
            .priority-badge.low { background: #dbeafe; color: #1e40af; }
            .priority-badge.medium { background: #f3e5f5; color: #6b21a8; }
            .priority-badge.high { background: #fee2e2; color: #991b2b; }
            .due-date { display: inline-block; padding: 2px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; cursor: pointer; border: none; font-family: 'Poppins', sans-serif; }
            .due-date.overdue { background: #fee2e2; color: #991b2b; }
            .due-date.on-time { background: #dcfce7; color: #166534; }
            .task-actions { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
            .mini-btn { padding: 4px 10px; background: var(--border); color: var(--text); border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: 0.2s; font-family: 'Poppins', sans-serif; }
            .mini-btn:hover { background: #e8eaed; }
            .mini-btn.del { background: #fee2e2; color: #991b2b; }
            .mini-btn.del:hover { background: #fecaca; }
            .assignee-badge { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; background: #e8eaf6; color: #283593; cursor: pointer; border: none; font-family: 'Poppins', sans-serif; }
            .comments-section { margin: 8px 0; padding: 8px; background: var(--bg); border-radius: 8px; }
            .comment-item { display: flex; justify-content: space-between; align-items: flex-start; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
            .comment-item:last-child { border-bottom: none; }
            .comment-user { font-weight: 600; color: #667eea; margin-right: 6px; }
            .comment-body { color: var(--text); flex: 1; }
            .comment-time { font-size: 11px; color: var(--text-secondary); margin-left: 8px; white-space: nowrap; }
            .comment-del { color: #ea4335; cursor: pointer; font-size: 11px; margin-left: 4px; }
            .comment-input-row { display: flex; gap: 6px; margin-top: 6px; }
            .comment-input-row input { flex: 1; padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; background: var(--card-bg); color: var(--text); }
            .comment-input-row button { padding: 6px 12px; background: #667eea; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600; }
            .label-manager-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
            .label-manager-row .label-dot { width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }
            .flash { padding: 12px 20px; border-radius: 10px; margin-bottom: 20px; font-weight: 500; }
            .flash-success { background: #dcfce7; color: #166534; }
            .flash-error { background: #fee2e2; color: #991b2b; }
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); backdrop-filter: blur(5px); justify-content: center; align-items: center; z-index: 1000; }
            .modal-content { background: var(--modal-bg); padding: 35px; border-radius: 20px; width: 500px; max-width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.2); position: relative; animation: slideUp 0.3s ease; }
            @keyframes slideUp { from { transform: translateY(50px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
            .modal-content h2 { font-size: 24px; font-weight: 600; color: var(--text); margin-bottom: 20px; }
            .modal-content input, .modal-content textarea, .modal-content select { width: 100%; padding: 12px 16px; margin: 8px 0; border: 2px solid var(--border); border-radius: 12px; font-size: 15px; transition: 0.3s; font-family: 'Poppins', sans-serif; background: var(--bg); color: var(--text); }
            .modal-content input:focus, .modal-content textarea:focus { border-color: #667eea; outline: none; box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1); }
            .modal-content textarea { resize: vertical; min-height: 80px; }
            .modal-content button { padding: 12px 30px; background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; border-radius: 12px; cursor: pointer; font-size: 16px; font-weight: 600; transition: 0.3s; width: 100%; margin-top: 10px; }
            .modal-content button:hover { transform: scale(1.02); box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3); }
            .modal-close { position: absolute; top: 15px; right: 20px; font-size: 24px; cursor: pointer; color: #999; transition: 0.3s; }
            .modal-close:hover { color: var(--text); transform: rotate(90deg); }
            .dark-toggle { background: var(--card-bg); border: 2px solid var(--border); color: var(--text); padding: 8px 14px; border-radius: 12px; cursor: pointer; font-size: 18px; transition: 0.3s; }
            .dark-toggle:hover { transform: scale(1.1); }
            .bulk-bar { display:none; position:fixed; bottom:20px; left:50%; transform:translateX(-50%); background:var(--card-bg); padding:12px 24px; border-radius:16px; box-shadow:0 10px 40px rgba(0,0,0,0.2); z-index:900; gap:10px; align-items:center; }
            .bulk-bar.active { display:flex; }
            .bulk-bar button { padding:8px 16px; border:none; border-radius:10px; cursor:pointer; font-weight:600; font-family:'Poppins',sans-serif; font-size:13px; }
            .bulk-bar .bulk-move { background:#667eea; color:white; }
            .bulk-bar .bulk-complete { background:#34a853; color:white; }
            .bulk-bar .bulk-delete { background:#ea4335; color:white; }
            .bulk-bar .bulk-cancel { background:var(--border); color:var(--text); }
            .undo-toast { display:none; position:fixed; bottom:80px; left:50%; transform:translateX(-50%); background:#333; color:white; padding:12px 24px; border-radius:12px; z-index:999; font-size:14px; align-items:center; gap:10px; }
            .undo-toast.show { display:flex; }
            .undo-toast button { background:#667eea; color:white; border:none; padding:6px 14px; border-radius:8px; cursor:pointer; font-weight:600; font-family:'Poppins',sans-serif; }
            .timer-btn { display:inline-flex; align-items:center; gap:4px; padding:2px 10px; border-radius:12px; font-size:11px; font-weight:600; border:none; cursor:pointer; font-family:'Poppins',sans-serif; }
            .timer-btn.start { background:#dcfce7; color:#166534; }
            .timer-btn.stop { background:#fee2e2; color:#991b2b; }
            .timer-info { font-size:11px; color:var(--text-secondary); margin-top:4px; }
            .recurring-btn { display:inline-block; padding:2px 10px; border-radius:6px; font-size:11px; font-weight:600; cursor:pointer; border:none; font-family:'Poppins',sans-serif; background:#e8eaf6; color:#283593; }
            .recurring-btn.active { background:#667eea; color:white; }
            .reminder-btn { padding:2px 8px; border-radius:6px; font-size:11px; cursor:pointer; border:none; background:var(--border); color:var(--text); font-family:'Poppins',sans-serif; }
            .dependency-tag { display:inline-block; padding:2px 8px; border-radius:6px; font-size:10px; font-weight:600; background:#fff3e0; color:#e65100; margin:2px 0; }
            .bulk-checkbox { width:16px; height:16px; accent-color:#667eea; cursor:pointer; margin-right:6px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📋 {{ board['name'] }}</h1>
                <div class="header-actions">
                    <button class="dark-toggle" onclick="toggleDark()" title="Toggle dark mode" id="darkBtn">🌙</button>
                    <a href="/calendar/{{ board['id'] }}" class="btn-sm" style="text-decoration:none;">📅 Calendar</a>
                    <a href="/gantt/{{ board['id'] }}" class="btn-sm" style="text-decoration:none;">📊 Gantt</a>
                    <button class="btn-sm" onclick="openTemplateModal()">📋 Templates</button>
                    <button class="btn-sm" onclick="openThemePicker()">🎨 Theme</button>
                    <button class="btn-sm" onclick="openActivityLog()">📜 Activity</button>
                    <button class="btn-sm" onclick="openShareBoard()">👥 Share</button>
                    <button class="btn-sm" onclick="window.location='/api/export_board/{{ board['id'] }}'">📥 Export CSV</button>
                    <button class="btn-sm" onclick="openLabelManager()">🏷️ Labels</button>
                    <button class="btn-sm" onclick="editBoard()">✏️ Edit</button>
                    <button class="btn-sm btn-danger" onclick="deleteBoard()">🗑️ Delete</button>
                    <a href="/boards" class="btn-back">← Back</a>
                </div>
            </div>
            <div class="filter-bar">
                <span class="filter-label">🔍 Filter:</span>
                <input type="text" id="searchInput" placeholder="Search tasks..." oninput="filterTasks()">
                <select id="filterPriority" onchange="filterTasks()">
                    <option value="">All Priorities</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                </select>
                <select id="filterLabel" onchange="filterTasks()">
                    <option value="">All Labels</option>
                    {% for label in all_labels %}
                    <option value="{{ label['name'] }}">{{ label['name'] }}</option>
                    {% endfor %}
                </select>
                <select id="filterAssignee" onchange="filterTasks()">
                    <option value="">All Assignees</option>
                    {% for u in all_users %}
                    <option value="{{ u['id'] }}">{{ u['username'] }}</option>
                    {% endfor %}
                </select>
                <button class="filter-clear" onclick="clearFilters()">Clear</button>
            </div>
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <div class="board">
                {% for lst in lists %}
                <div class="list-column" data-list-id="{{ lst['id'] }}">
                    <div class="list-header">
                        <h3>{{ lst['name'] }}</h3>
                        <span style="display:flex;align-items:center;gap:8px;">
                            <span class="task-count">{{ tasks|selectattr('list_id', 'equalto', lst['id'])|list|length }}</span>
                            <button class="del-list" onclick="deleteList({{ lst['id'] }})" title="Delete list">✕</button>
                        </span>
                    </div>
                    <div>
                        {% for task in tasks if task['list_id'] == lst['id'] %}
                        <div class="task-card{% if task['status'] == 'completed' %} completed{% endif %}" draggable="true" data-task-id="{{ task['id'] }}" data-list-id="{{ task['list_id'] }}" data-title="{{ task['title']|lower }}" data-priority="{{ task['priority'] or 'medium' }}" data-labels="{{ labels_by_task[task['id']]|map(attribute='name')|join(',')|lower }}" data-assignee="{{ task.get('assignee_id') or '' }}">
                            <div class="task-header">
                                <input type="checkbox" class="bulk-checkbox" data-task-id="{{ task['id'] }}" onchange="updateBulkBar()" title="Select for bulk action">
                                <input type="checkbox" class="completion-checkbox" {% if task['status'] == 'completed' %}checked{% endif %} onchange="toggleComplete({{ task['id'] }}, this.checked)" title="Mark complete">
                                <div style="flex:1;">
                                    <div class="card-title">{{ task['title'] }}</div>
                                    {% if task['description'] %}<div class="card-desc">{{ task['description'][:60] }}{% if task['description']|length > 60 %}...{% endif %}</div>{% endif %}
                                </div>
                            </div>
                            <div class="task-meta">
                                {% set pri = task['priority'] or 'medium' %}
                                <button class="priority-badge {{ pri }}" onclick="setPriority({{ task['id'] }}, '{{ pri }}')" title="Change priority">{{ pri|title }}</button>
                                {% if task['due_date'] %}
                                {% set due_date = task['due_date'] %}
                                {% set due_date_obj = due_date.split('T')[0] if 'T' in due_date else due_date[:10] %}
                                {% set cls = 'overdue' if due_date_obj < today else 'on-time' %}
                                <button class="due-date {{ cls }}" onclick="setDueDate({{ task['id'] }}, '{{ task['due_date'] or '' }}')" title="Set due date">📅 {{ due_date_obj }}</button>
                                {% else %}
                                <button class="due-date on-time" onclick="setDueDate({{ task['id'] }}, '')" title="Set due date">📅 Set due date</button>
                                {% endif %}
                                {% set rec = task.get('recurring') or '' %}
                                <button class="recurring-btn{% if rec %} active{% endif %}" onclick="setRecurring({{ task['id'] }}, '{{ rec }}')" title="Set recurring">🔄 {{ rec or 'One-time' }}</button>
                                <button class="timer-btn start" onclick="startTimer({{ task['id'] }})" title="Start timer">▶ Timer</button>
                                <button class="reminder-btn" onclick="setReminder({{ task['id'] }})" title="Set reminder">🔔</button>
                            </div>
                            <!-- Labels -->
                            <div class="labels-container" style="display:flex;gap:4px;flex-wrap:wrap;margin:6px 0;">
                                {% for label in labels_by_task[task['id']] %}
                                <span style="background:{{ label['color'] }};padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;color:white;">{{ label['name'] }}</span>
                                {% endfor %}
                            </div>
                            <!-- Dependencies -->
                            {% if deps_by_task[task['id']] %}
                            <div style="margin:4px 0;">
                                {% for dep in deps_by_task[task['id']] %}
                                <span class="dependency-tag">🔒 Blocked by: {{ dep['blocked_by_title'] }}</span>
                                {% endfor %}
                            </div>
                            {% endif %}

                            <!-- Assignee -->
                            <div style="margin:6px 0;">
                                <select class="assignee-badge" onchange="assignTask({{ task['id'] }}, this.value)" title="Assign to">
                                    <option value=""{% if not task.get('assignee_id') %} selected{% endif %}>👤 Unassigned</option>
                                    {% for u in all_users %}
                                    <option value="{{ u['id'] }}"{% if task.get('assignee_id') == u['id'] %} selected{% endif %}>👤 {{ u['username'] }}</option>
                                    {% endfor %}
                                </select>
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
                                    </form><a href="/google/login" style="display:block;width:100%;padding:12px;background:#fff;color:#333;border:1px solid #ddd;border-radius:8px;text-align:center;text-decoration:none;margin-top:10px;box-sizing:border-box;">?? Continue with Google</a>
                                </div>
                            </div>
                            <div class="task-actions">
                                <button class="mini-btn" onclick="editTask({{ task['id'] }})">✏️ Edit</button>
                                <button class="mini-btn" onclick="setDueDate({{ task['id'] }}, '{{ task['due_date'] or '' }}')">📅 Due</button>
                                <button class="mini-btn del" onclick="deleteTask({{ task['id'] }})">🗑️ Delete</button>
                            </div>

                            <!-- Comments -->
                            <div class="comments-section">
                                <div style="font-size:13px;font-weight:600;color:#5f6368;margin-bottom:4px;">💬 Comments ({{ comments_by_task[task['id']]|length }}):</div>
                                {% for cm in comments_by_task[task['id']] %}
                                <div class="comment-item">
                                    <span class="comment-user">{{ cm['username'] }}</span>
                                    <span class="comment-body">{{ cm['body'] }}</span>
                                    <span class="comment-time">{{ cm['created_at'][:16].replace('T',' ') if cm['created_at'] else '' }}</span>
                                    <span class="comment-del" onclick="deleteComment({{ cm['id'] }})">✕</span>
                                </div>
                                {% endfor %}
                                <div class="comment-input-row" style="position:relative;">
                                    <input type="text" id="newComment_{{ task['id'] }}" placeholder="Write a comment... (@ to mention)" oninput="checkMention(this)" onkeypress="if(event.key==='Enter')addComment({{ task['id'] }})">
                                    <button onclick="addComment({{ task['id'] }})">Send</button>
                                    <div class="mention-dropdown" id="mention_{{ task['id'] }}" style="display:none;position:absolute;bottom:100%;left:0;background:var(--card-bg);border:1px solid var(--border);border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.15);z-index:10;max-height:120px;overflow-y:auto;min-width:150px;"></div>
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
        <div class="modal" id="labelManagerModal">
            <div class="modal-content">
                <h2>🏷️ Label Manager</h2>
                <div style="margin-bottom:15px;">
                    <div style="font-size:13px;font-weight:600;color:#5f6368;margin-bottom:6px;">New label:</div>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <input type="text" id="newLabelName" placeholder="Label name" style="flex:1;">
                        <input type="color" id="newLabelColor" value="#1a73e8" style="width:50px;padding:2px;margin:0;">
                        <button onclick="createLabel()" style="width:auto;padding:10px 16px;margin:0;">Create</button>
                    </div>
                </div>
                <div style="max-height:300px;overflow-y:auto;">
                    {% for label in all_labels %}
                    <div class="label-manager-row">
                        <span class="label-dot" style="background:{{ label['color'] }};"></span>
                        <span style="flex:1;font-size:14px;">{{ label['name'] }}</span>
                        <button class="mini-btn" onclick="editLabelPrompt({{ label['id'] }}, '{{ label['name'] }}', '{{ label['color'] }}')">Edit</button>
                        <button class="mini-btn del" onclick="deleteLabel({{ label['id'] }})">Delete</button>
                    </div>
                    {% endfor %}
                </div>
                <button onclick="closeModal('labelManagerModal')" style="background:#ea4335;">Close</button>
            </div>
        </div>
        <div class="modal" id="activityLogModal">
            <div class="modal-content" style="width:600px;max-height:80vh;overflow-y:auto;">
                <h2>📜 Activity Log</h2>
                <div id="activityLogContent">
                    {% for al in activity_logs %}
                    <div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px;">
                        <span style="color:#667eea;font-weight:600;min-width:90px;">{{ al['username'] }}</span>
                        <span style="flex:1;">{{ al['action'] }}</span>
                        <span style="color:var(--text-secondary);font-size:11px;">{{ al.get('details','') }}</span>
                        <span style="color:var(--text-secondary);font-size:11px;min-width:100px;text-align:right;">{{ al['created_at'][:16].replace('T',' ') if al['created_at'] else '' }}</span>
                    </div>
                    {% endfor %}
                    {% if not activity_logs %}
                    <p style="color:var(--text-secondary);text-align:center;padding:20px;">No activity yet.</p>
                    {% endif %}
                </div>
                <button onclick="closeModal('activityLogModal')" style="background:#ea4335;">Close</button>
            </div>
        </div>
        <div class="modal" id="shareBoardModal">
            <div class="modal-content">
                <h2>👥 Share Board</h2>
                <div style="margin-bottom:15px;">
                    <div style="display:flex;gap:8px;align-items:center;">
                        <select id="shareUserSelect" style="flex:1;padding:12px;border:2px solid var(--border);border-radius:12px;font-family:'Poppins',sans-serif;background:var(--bg);color:var(--text);">
                            {% for u in all_users %}
                            <option value="{{ u['id'] }}">{{ u['username'] }}</option>
                            {% endfor %}
                        </select>
                        <button onclick="shareBoard()" style="padding:12px 20px;margin:0;width:auto;">Share</button>
                    </div>
                </div>
                <div style="margin-bottom:15px;">
                    <div style="font-size:14px;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Shared with:</div>
                    {% for bs in board_shares %}
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);">
                        <span style="font-size:14px;">👤 {{ bs['username'] }}</span>
                        <button class="mini-btn del" onclick="unshareBoard({{ bs['user_id'] }})">Remove</button>
                    </div>
                    {% endfor %}
                    {% if not board_shares %}
                    <p style="color:var(--text-secondary);font-size:13px;">Not shared with anyone yet.</p>
                    {% endif %}
                </div>
                <button onclick="closeModal('shareBoardModal')" style="background:#ea4335;">Close</button>
            </div>
        </div>
        <div class="modal" id="quickAddModal">
            <div class="modal-content" style="width:400px;">
                <h2>⚡ Quick Add Task</h2>
                <input type="text" id="quickAddTitle" placeholder="Task title" onkeypress="if(event.key==='Enter')submitQuickAdd()">
                <select id="quickAddList" style="width:100%;padding:12px 16px;margin:8px 0;border:2px solid var(--border);border-radius:12px;font-family:'Poppins',sans-serif;background:var(--bg);color:var(--text);">
                    {% for lst in lists %}
                    <option value="{{ lst['id'] }}">{{ lst['name'] }}</option>
                    {% endfor %}
                </select>
                <button onclick="submitQuickAdd()">Add Task</button>
                <button onclick="closeModal('quickAddModal')" style="background:#ea4335;">Cancel</button>
            </div>
        </div>
        <div id="keyboardHelp" style="display:none;position:fixed;bottom:20px;right:20px;background:var(--card-bg);padding:20px;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,0.2);z-index:999;max-width:300px;">
            <h3 style="margin-bottom:10px;font-size:16px;color:var(--text);">⌨️ Keyboard Shortcuts</h3>
            <div style="font-size:13px;color:var(--text-secondary);line-height:2;">
                <b>/</b> - Quick add task<br>
                <b>l</b> - Add new list<br>
                <b>L</b> - Open label manager<br>
                <b>s</b> - Focus search<br>
                <b>d</b> - Toggle dark mode<br>
                <b>?</b> - Show/hide shortcuts<br>
                <b>Esc</b> - Close modal
            </div>
        </div>
        <div class="bulk-bar" id="bulkBar">
            <span id="bulkCount" style="font-weight:600;font-size:13px;color:var(--text);">0 selected</span>
            <select id="bulkMoveTarget" style="padding:6px 10px;border:1px solid var(--border);border-radius:8px;font-size:12px;font-family:'Poppins',sans-serif;background:var(--bg);color:var(--text);">
                {% for lst in lists %}
                <option value="{{ lst['id'] }}">{{ lst['name'] }}</option>
                {% endfor %}
            </select>
            <button class="bulk-move" onclick="bulkMove()">📦 Move</button>
            <button class="bulk-complete" onclick="bulkComplete()">✅ Complete</button>
            <button class="bulk-delete" onclick="bulkDelete()">🗑️ Delete</button>
            <button class="bulk-cancel" onclick="clearBulk()">✕ Cancel</button>
        </div>
        <div class="undo-toast" id="undoToast">
            <span id="undoMsg">Action done</span>
            <button onclick="doUndo()">Undo</button>
        </div>
        <div class="modal" id="templateModal">
            <div class="modal-content" style="width:550px;">
                <span class="modal-close" onclick="closeModal('templateModal')">&times;</span>
                <h2>📋 Task Templates</h2>
                <div style="margin-bottom:15px;">
                    <div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">Create new template:</div>
                    <input type="text" id="tmplName" placeholder="Template name" style="margin-bottom:6px;">
                    <div id="tmplTaskList"></div>
                    <button onclick="addTmplTask()" style="width:auto;padding:8px 16px;margin:6px 0;font-size:13px;">+ Add task to template</button>
                    <button onclick="saveTemplate()" style="margin-top:6px;">Save Template</button>
                </div>
                <div style="border-top:1px solid var(--border);padding-top:12px;">
                    <div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Existing templates:</div>
                    <div id="tmplList"></div>
                </div>
                <button onclick="closeModal('templateModal')" style="background:#ea4335;">Close</button>
            </div>
        </div>
        <div class="modal" id="themePickerModal">
            <div class="modal-content" style="width:400px;">
                <span class="modal-close" onclick="closeModal('themePickerModal')">&times;</span>
                <h2>🎨 Board Theme</h2>
                <div style="margin:15px 0;">
                    <div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">Background Color:</div>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <div onclick="setTheme('#f0f2f5','')" style="width:40px;height:40px;border-radius:10px;background:#f0f2f5;border:3px solid var(--border);cursor:pointer;" title="Default"></div>
                        <div onclick="setTheme('#e8f5e9','')" style="width:40px;height:40px;border-radius:10px;background:#e8f5e9;border:3px solid var(--border);cursor:pointer;" title="Green"></div>
                        <div onclick="setTheme('#e3f2fd','')" style="width:40px;height:40px;border-radius:10px;background:#e3f2fd;border:3px solid var(--border);cursor:pointer;" title="Blue"></div>
                        <div onclick="setTheme('#fce4ec','')" style="width:40px;height:40px;border-radius:10px;background:#fce4ec;border:3px solid var(--border);cursor:pointer;" title="Pink"></div>
                        <div onclick="setTheme('#fff3e0','')" style="width:40px;height:40px;border-radius:10px;background:#fff3e0;border:3px solid var(--border);cursor:pointer;" title="Orange"></div>
                        <div onclick="setTheme('#f3e5f5','')" style="width:40px;height:40px;border-radius:10px;background:#f3e5f5;border:3px solid var(--border);cursor:pointer;" title="Purple"></div>
                    </div>
                    <div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin:12px 0 8px;">Custom color:</div>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <input type="color" id="customThemeColor" value="#f0f2f5" style="width:50px;padding:2px;margin:0;">
                        <button onclick="setTheme(document.getElementById('customThemeColor').value,'')" style="width:auto;padding:8px 16px;margin:0;font-size:13px;">Apply</button>
                    </div>
                </div>
                <button onclick="closeModal('themePickerModal')" style="background:#ea4335;">Close</button>
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

        // Label Manager functions
        function openLabelManager() {
            document.getElementById('newLabelName').value = '';
            document.getElementById('newLabelColor').value = '#1a73e8';
            openModal('labelManagerModal');
        }
        function createLabel() {
            const name = document.getElementById('newLabelName').value.trim();
            const color = document.getElementById('newLabelColor').value;
            if(!name) { alert('Please enter a label name!'); return; }
            fetch('/api/create_label', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: name, color: color})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function editLabelPrompt(labelId, currentName, currentColor) {
            const name = prompt('Label name:', currentName);
            if(!name || !name.trim()) return;
            const color = prompt('Label color (e.g. #1a73e8):', currentColor);
            fetch('/api/edit_label', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({label_id: labelId, name: name.trim(), color: color || currentColor})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function deleteLabel(labelId) {
            if(!confirm('Delete this label? It will be removed from all tasks.')) return;
            fetch('/api/delete_label/' + labelId, { method: 'DELETE' })
            .then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }

        // Board functions
        function editBoard() {
            const name = prompt('Board name:', document.querySelector('.header h1').textContent.replace('📋','').trim());
            if(!name || !name.trim()) return;
            const desc = prompt('Description:', '');
            fetch('/api/edit_board', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({board_id: {{ board['id'] }}, name: name.trim(), description: desc})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function deleteBoard() {
            if(!confirm('Delete this board and all its lists/tasks?')) return;
            fetch('/api/delete_board/{{ board['id'] }}', { method: 'DELETE' })
            .then(res => res.json()).then(data => { if(data.success) window.location = '/boards'; else alert('Error: ' + data.error); });
        }

        // List functions
        function deleteList(listId) {
            if(!confirm('Delete this list and all its tasks?')) return;
            fetch('/api/delete_list/' + listId, { method: 'DELETE' })
            .then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }

        // Task functions
        function editTask(taskId) {
            const card = document.querySelector('.task-card[data-task-id="'+taskId+'"]');
            const title = prompt('Task title:', card ? card.querySelector('.card-title').textContent.trim() : '');
            if(!title || !title.trim()) return;
            const desc = prompt('Description:');
            fetch('/api/edit_task', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, title: title.trim(), description: desc})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function setDueDate(taskId, currentDue) {
            const today = new Date().toISOString().split('T')[0];
            const due = prompt('Enter due date (YYYY-MM-DD), or leave empty to clear:', currentDue || today);
            if(due === null) return;
            if(!due.trim()) {
                fetch('/api/set_due_date', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({task_id: taskId, due_date: null})
                }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
                return;
            }
            fetch('/api/set_due_date', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, due_date: due.trim()})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function deleteTask(taskId) {
            if(!confirm('Delete this task?')) return;
            fetch('/api/delete_task/' + taskId, { method: 'DELETE' })
            .then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function toggleComplete(taskId, completed) {
            fetch('/api/toggle_complete/' + taskId, { method: 'POST' })
            .then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function setPriority(taskId, currentPriority) {
            const priorities = ['low', 'medium', 'high'];
            const currentIndex = priorities.indexOf(currentPriority);
            const nextIndex = (currentIndex + 1) % 3;
            const nextPriority = priorities[nextIndex];
            fetch('/api/set_priority', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, priority: nextPriority})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }

        // Comment functions
        function addComment(taskId) {
            const input = document.getElementById('newComment_' + taskId);
            const body = input.value.trim();
            if(!body) return;
            fetch('/api/add_comment', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, body: body})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }
        function deleteComment(commentId) {
            if(!confirm('Delete this comment?')) return;
            fetch('/api/delete_comment/' + commentId, { method: 'DELETE' })
            .then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }

        // Assignee function
        function assignTask(taskId, assigneeId) {
            fetch('/api/assign_task', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, assignee_id: assigneeId || null})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }

        // Search & Filter
        function filterTasks() {
            const query = document.getElementById('searchInput').value.toLowerCase();
            const priority = document.getElementById('filterPriority').value;
            const label = document.getElementById('filterLabel').value.toLowerCase();
            const assignee = document.getElementById('filterAssignee').value;
            document.querySelectorAll('.task-card').forEach(card => {
                const title = card.dataset.title || '';
                const pri = card.dataset.priority || '';
                const labels = card.dataset.labels || '';
                const ass = card.dataset.assignee || '';
                let show = true;
                if(query && !title.includes(query)) show = false;
                if(priority && pri !== priority) show = false;
                if(label && !labels.includes(label)) show = false;
                if(assignee && ass !== assignee) show = false;
                card.style.display = show ? '' : 'none';
            });
        }
        function clearFilters() {
            document.getElementById('searchInput').value = '';
            document.getElementById('filterPriority').value = '';
            document.getElementById('filterLabel').value = '';
            document.getElementById('filterAssignee').value = '';
            filterTasks();
        }

        // Dark Mode
        function toggleDark() {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
            localStorage.setItem('theme', isDark ? 'light' : 'dark');
            document.getElementById('darkBtn').textContent = isDark ? '🌙' : '☀️';
        }
        (function() {
            const saved = localStorage.getItem('theme');
            if(saved === 'dark') {
                document.documentElement.setAttribute('data-theme', 'dark');
                document.getElementById('darkBtn').textContent = '☀️';
            }
        })();

        // Activity Log
        function openActivityLog() { openModal('activityLogModal'); }

        // Board Sharing
        function openShareBoard() { openModal('shareBoardModal'); }
        function shareBoard() {
            const userId = document.getElementById('shareUserSelect').value;
            fetch('/api/share_board', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({board_id: {{ board['id'] }}, user_id: parseInt(userId)})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }
        function unshareBoard(userId) {
            fetch('/api/unshare_board', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({board_id: {{ board['id'] }}, user_id: userId})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }

        // Recurring Tasks
        function setRecurring(taskId, current) {
            const options = ['', 'daily', 'weekly', 'monthly', 'yearly'];
            const idx = options.indexOf(current || '');
            const next = options[(idx + 1) % options.length];
            fetch('/api/set_recurring', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_id: taskId, recurring: next || null})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); });
        }

        // Quick Add
        function openQuickAdd() { openModal('quickAddModal'); document.getElementById('quickAddTitle').focus(); }
        function submitQuickAdd() {
            const title = document.getElementById('quickAddTitle').value.trim();
            const listId = document.getElementById('quickAddList').value;
            if(!title) { alert('Enter a task title!'); return; }
            fetch('/api/add_card', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({list_id: listId, title: title})
            }).then(res => res.json()).then(data => { if(data.success) location.reload(); else alert('Error: ' + data.error); });
        }

        // Keyboard Shortcuts
        document.addEventListener('keydown', function(e) {
            if(e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
            switch(e.key) {
                case '/': e.preventDefault(); openQuickAdd(); break;
                case 'l': e.preventDefault(); openAddList({{ board['id'] }}); break;
                case 'L': e.preventDefault(); openLabelManager(); break;
                case 's': e.preventDefault(); document.getElementById('searchInput').focus(); break;
                case 'd': e.preventDefault(); toggleDark(); break;
                case '?': e.preventDefault(); document.getElementById('keyboardHelp').style.display = document.getElementById('keyboardHelp').style.display === 'none' ? 'block' : 'none'; break;
                case 'Escape':
                    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
                    document.getElementById('keyboardHelp').style.display = 'none';
                    break;
            }
        });

        // Time Tracking
        function startTimer(taskId) {
            fetch('/api/start_timer', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task_id:taskId}) })
            .then(r=>r.json()).then(d=>{ if(d.success) location.reload(); else alert('Error: '+d.error); });
        }

        // Bulk Actions
        function getSelectedIds() {
            const ids = [];
            document.querySelectorAll('.bulk-checkbox:checked').forEach(cb => ids.push(parseInt(cb.dataset.taskId)));
            return ids;
        }
        function updateBulkBar() {
            const ids = getSelectedIds();
            const bar = document.getElementById('bulkBar');
            if(ids.length > 0) {
                bar.classList.add('active');
                document.getElementById('bulkCount').textContent = ids.length + ' selected';
            } else {
                bar.classList.remove('active');
            }
        }
        function clearBulk() {
            document.querySelectorAll('.bulk-checkbox').forEach(cb => cb.checked = false);
            document.getElementById('bulkBar').classList.remove('active');
        }
        function bulkMove() {
            const ids = getSelectedIds();
            const listId = document.getElementById('bulkMoveTarget').value;
            if(!ids.length) return;
            fetch('/api/bulk_move', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task_ids:ids, list_id:parseInt(listId)}) })
            .then(r=>r.json()).then(d=>{ if(d.success){ showUndo('Moved '+d.moved+' tasks'); location.reload(); } else alert('Error: '+d.error); });
        }
        function bulkComplete() {
            const ids = getSelectedIds();
            if(!ids.length) return;
            fetch('/api/bulk_complete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task_ids:ids, status:'completed'}) })
            .then(r=>r.json()).then(d=>{ if(d.success){ showUndo('Completed '+d.updated+' tasks'); location.reload(); } else alert('Error: '+d.error); });
        }
        function bulkDelete() {
            const ids = getSelectedIds();
            if(!ids.length || !confirm('Delete '+ids.length+' tasks?')) return;
            fetch('/api/bulk_delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task_ids:ids}) })
            .then(r=>r.json()).then(d=>{ if(d.success){ showUndo('Deleted '+d.deleted+' tasks'); location.reload(); } else alert('Error: '+d.error); });
        }

        // Undo
        let undoTimer = null;
        function showUndo(msg) {
            document.getElementById('undoMsg').textContent = msg;
            document.getElementById('undoToast').classList.add('show');
            if(undoTimer) clearTimeout(undoTimer);
            undoTimer = setTimeout(() => document.getElementById('undoToast').classList.remove('show'), 5000);
        }
        function doUndo() {
            fetch('/api/undo', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({}) })
            .then(r=>r.json()).then(d=>{ if(d.success){ showUndo('Undid: '+d.action); location.reload(); } else alert('Nothing to undo'); });
            document.getElementById('undoToast').classList.remove('show');
        }

        // Templates
        let tmplTasks = [];
        function openTemplateModal() {
            document.getElementById('tmplName').value = '';
            tmplTasks = [];
            document.getElementById('tmplTaskList').innerHTML = '';
            loadTemplates();
            openModal('templateModal');
        }
        function addTmplTask() {
            tmplTasks.push({title:'', description:'', priority:'medium'});
            renderTmplTasks();
        }
        function renderTmplTasks() {
            let html = '';
            tmplTasks.forEach((t,i) => {
                html += '<div style="display:flex;gap:6px;margin:4px 0;align-items:center;">';
                html += '<input type="text" value="'+t.title+'" placeholder="Task title" onchange="tmplTasks['+i+'].title=this.value" style="flex:1;padding:6px;border:1px solid var(--border);border-radius:6px;font-size:13px;font-family:Poppins,sans-serif;background:var(--bg);color:var(--text);">';
                html += '<select onchange="tmplTasks['+i+'].priority=this.value" style="padding:6px;border:1px solid var(--border);border-radius:6px;font-size:12px;font-family:Poppins,sans-serif;background:var(--bg);color:var(--text);">';
                ['low','medium','high'].forEach(p => html += '<option value="'+p+'"'+(t.priority===p?' selected':'')+'>'+p+'</option>');
                html += '</select>';
                html += '<button onclick="tmplTasks.splice('+i+',1);renderTmplTasks()" style="padding:4px 8px;background:#ea4335;color:white;border:none;border-radius:6px;cursor:pointer;font-size:12px;">✕</button>';
                html += '</div>';
            });
            document.getElementById('tmplTaskList').innerHTML = html;
        }
        function saveTemplate() {
            const name = document.getElementById('tmplName').value.trim();
            if(!name) { alert('Enter template name!'); return; }
            const validTasks = tmplTasks.filter(t => t.title.trim());
            if(!validTasks.length) { alert('Add at least one task!'); return; }
            fetch('/api/create_template', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name, board_id:{{ board['id'] }}, tasks:validTasks}) })
            .then(r=>r.json()).then(d=>{ if(d.success){ alert('Template saved!'); loadTemplates(); } else alert('Error: '+d.error); });
        }
        function loadTemplates() {
            fetch('/api/templates/{{ board['id'] }}').then(r=>r.json()).then(data => {
                let html = '';
                if(!data.length) html = '<p style="color:var(--text-secondary);font-size:13px;">No templates yet.</p>';
                data.forEach(t => {
                    const count = Array.isArray(t.tasks_json) ? t.tasks_json.length : 0;
                    html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);">';
                    html += '<span style="font-size:14px;font-weight:500;">'+t.name+' <span style="color:var(--text-secondary);font-size:12px;">('+count+' tasks)</span></span>';
                    html += '<div style="display:flex;gap:6px;">';
                    html += '<button class="mini-btn" onclick="useTmpl('+t.id+')" style="background:#667eea;color:white;">Use</button>';
                    html += '<button class="mini-btn del" onclick="delTmpl('+t.id+')">Delete</button>';
                    html += '</div></div>';
                });
                document.getElementById('tmplList').innerHTML = html;
            });
        }
        function useTmpl(tmplId) {
            const listId = prompt('Enter list ID to add tasks to (or check the board):');
            if(!listId) return;
            fetch('/api/use_template', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({template_id:tmplId, list_id:parseInt(listId)}) })
            .then(r=>r.json()).then(d=>{ if(d.success){ alert('Added '+d.count+' tasks!'); location.reload(); } else alert('Error: '+d.error); });
        }
        function delTmpl(tmplId) {
            if(!confirm('Delete this template?')) return;
            fetch('/api/delete_template/'+tmplId, {method:'DELETE'}).then(r=>r.json()).then(d=>{ if(d.success) loadTemplates(); });
        }

        // Theme Picker
        function openThemePicker() { openModal('themePickerModal'); }
        function setTheme(color, bg) {
            fetch('/api/update_theme', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({board_id:{{ board['id'] }}, theme_color:color, theme_bg:bg||null}) })
            .then(r=>r.json()).then(d=>{ if(d.success){ document.body.style.background = color; closeModal('themePickerModal'); } });
        }

        // Reminder
        function setReminder(taskId) {
            const dt = prompt('Remind at (YYYY-MM-DD HH:MM):', '');
            if(!dt) return;
            const msg = prompt('Reminder message:', '') || '';
            fetch('/api/set_reminder', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task_id:taskId, remind_at:dt, message:msg}) })
            .then(r=>r.json()).then(d=>{ if(d.success) alert('Reminder set!'); else alert('Error: '+d.error); });
        }

        // Real-time polling (every 30s)
        setInterval(() => { if(!document.hidden) location.reload(); }, 30000);

        // @Mentions
        const allUsers = [{% for u in all_users %}{id:{{ u['id'] }},name:'{{ u['username'] }}'}{% if not loop.last %},{% endif %}{% endfor %}];
        function checkMention(input) {
            const val = input.value;
            const atIdx = val.lastIndexOf('@');
            const ddId = 'mention_' + input.id.split('_')[1];
            const dd = document.getElementById(ddId);
            if(!dd) return;
            if(atIdx === -1 || atIdx !== val.length - 1) { dd.style.display = 'none'; return; }
            const query = val.slice(atIdx + 1).toLowerCase();
            const matches = allUsers.filter(u => u.name.toLowerCase().includes(query));
            if(!matches.length) { dd.style.display = 'none'; return; }
            dd.innerHTML = matches.map(u => '<div style="padding:6px 10px;cursor:pointer;font-size:13px;" onmousedown="insertMention('+input.id.split('_')[1]+',\''+u.name+'\')">@'+u.name+'</div>').join('');
            dd.style.display = 'block';
        }
        function insertMention(taskId, username) {
            const input = document.getElementById('newComment_' + taskId);
            const atIdx = input.value.lastIndexOf('@');
            input.value = input.value.slice(0, atIdx) + '@' + username + ' ';
            document.getElementById('mention_' + taskId).style.display = 'none';
            input.focus();
        }
        </script>
    </body>
    </html>
    ''', board=board, lists=lists, tasks=tasks, checklists=checklists, labels_by_task=labels_by_task, all_labels=all_labels, attachments_by_task=attachments_by_task, comments_by_task=comments_by_task, all_users=all_users, activity_logs=activity_logs, board_shares=board_shares, today=date.today().isoformat(), deps_by_task=deps_by_task)

# ============ ACTIVITY LOG HELPER ============
def log_activity(board_id, action, details=''):
    try:
        supabase.table('activity_log').insert({
            'board_id': board_id,
            'user_id': session.get('user_id'),
            'action': action,
            'details': details
        }).execute()
    except Exception as e:
        print(f"activity log warning: {e}")

# ============ EXPORT CSV ============
@app.route('/api/export_board/<int:board_id>')
def export_board(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    if not is_owner_or_admin(board_id): return jsonify({'error': 'Permission denied'}), 403
    import csv, io
    tasks = supabase.table('tasks').select('*, board_lists(name)').eq('board_id', board_id).order('position').execute().data
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Title', 'Description', 'List', 'Priority', 'Status', 'Due Date', 'Assignee ID', 'Created At'])
    for t in tasks:
        list_info = t.pop('board_lists', None)
        writer.writerow([
            t['id'], t['title'], t.get('description', ''),
            list_info['name'] if list_info else '',
            t.get('priority', ''), t.get('status', ''),
            t.get('due_date', ''), t.get('assignee_id', ''),
            t.get('created_at', '')
        ])
    track_event(session['user_id'], 'board_exported', {'board_id': board_id})
    from flask import Response
    return Response(
        '\ufeff' + output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=board_{board_id}_export.csv'}
    )

# ============ BOARD SHARING API ============
@app.route('/api/share_board', methods=['POST'])
def share_board():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    board_id = data.get('board_id')
    target_user_id = data.get('user_id')
    if not board_id or not target_user_id: return jsonify({'error': 'Invalid data'}), 400
    if not is_owner_or_admin(board_id): return jsonify({'error': 'Permission denied'}), 403
    try:
        supabase.table('board_shares').insert({'board_id': board_id, 'user_id': target_user_id}).execute()
    except:
        pass
    track_event(session['user_id'], 'board_shared', {'board_id': board_id, 'shared_with': target_user_id})
    return jsonify({'success': True})

@app.route('/api/unshare_board', methods=['POST'])
def unshare_board():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    board_id = data.get('board_id')
    target_user_id = data.get('user_id')
    if not board_id or not target_user_id: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('board_shares').delete().eq('board_id', board_id).eq('user_id', target_user_id).execute()
    return jsonify({'success': True})

@app.route('/api/board_shares/<int:board_id>')
def get_board_shares(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    shares = supabase.table('board_shares').select('*, users(username)').eq('board_id', board_id).execute().data
    result = []
    for s in shares:
        u = s.pop('users', None)
        result.append({'id': s['id'], 'user_id': s['user_id'], 'username': u['username'] if u else ''})
    return jsonify(result)

# ============ ACTIVITY LOG API ============
@app.route('/api/activity_log/<int:board_id>')
def get_activity_log(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    logs = supabase.table('activity_log').select('*, users(username)').eq('board_id', board_id).order('created_at', desc=True).limit(50).execute().data
    result = []
    for l in logs:
        u = l.pop('users', None)
        result.append({'id': l['id'], 'action': l['action'], 'details': l.get('details', ''), 'username': u['username'] if u else '', 'created_at': l.get('created_at', '')})
    return jsonify(result)

# ============ RECURRING TASKS API ============
@app.route('/api/set_recurring', methods=['POST'])
def set_recurring():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    recurring = data.get('recurring')
    if not task_id: return jsonify({'error': 'Invalid data'}), 400
    if not _task_owner_ok(task_id): return jsonify({'error': 'Permission denied'}), 403
    if recurring and recurring not in ('daily', 'weekly', 'monthly', 'yearly'):
        return jsonify({'error': 'Invalid recurring type'}), 400
    supabase.table('tasks').update({'recurring': recurring or None}).eq('id', task_id).execute()
    track_event(session['user_id'], 'task_recurring_set', {'task_id': task_id, 'recurring': recurring})
    return jsonify({'success': True})

@app.route('/api/check_recurring')
def check_recurring():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    user = supabase.table('users').select('role').eq('id', session['user_id']).execute().data
    if not user or user[0].get('role') != 'admin': return jsonify({'error': 'Admin only'}), 403
    from datetime import timedelta
    now = datetime.now()
    recurring = supabase.table('tasks').select('*').not_.is_('recurring', 'null').execute().data
    created = 0
    for t in recurring:
        next_run = t.get('next_run')
        if next_run and next_run > now.isoformat():
            continue
        task_date = t.get('created_at', '')
        original = supabase.table('tasks').select('*').eq('id', t['id']).execute().data
        if not original: continue
        orig = original[0]
        new_next = None
        if t['recurring'] == 'daily':
            new_next = (now + timedelta(days=1)).isoformat()
        elif t['recurring'] == 'weekly':
            new_next = (now + timedelta(weeks=1)).isoformat()
        elif t['recurring'] == 'monthly':
            new_next = (now + timedelta(days=30)).isoformat()
        elif t['recurring'] == 'yearly':
            new_next = (now + timedelta(days=365)).isoformat()
        supabase.table('tasks').insert({
            'board_id': orig['board_id'],
            'list_id': orig['list_id'],
            'user_id': session['user_id'],
            'title': orig['title'],
            'description': orig.get('description'),
            'priority': orig.get('priority', 'medium'),
            'due_date': new_next[:10] if new_next else None,
            'recurring': t['recurring'],
            'next_run': new_next
        }).execute()
        supabase.table('tasks').update({'next_run': new_next}).eq('id', t['id']).execute()
        created += 1
    return jsonify({'success': True, 'created': created})

# ============ API ROUTES ============

@app.route('/api/add_list', methods=['POST'])
def add_list():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    board_id = data.get('board_id')
    name = data.get('name', '').strip()
    if not board_id or not name: return jsonify({'error': 'Invalid data'}), 400
    result = supabase.table('board_lists').select('position').eq('board_id', board_id).order('position', desc=True).limit(1).execute().data
    max_pos = result[0]['position'] if result else 0
    supabase.table('board_lists').insert({
        'board_id': board_id,
        'name': name,
        'position': max_pos + 1
    }).execute()
    track_event(session['user_id'], 'list_created', {
        'list_name': name,
        'board_id': board_id
    })
    log_activity(board_id, 'list_created', name)
    return jsonify({'success': True})

@app.route('/api/add_card', methods=['POST'])
def add_card():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    list_id = data.get('list_id')
    title = data.get('title', '').strip()
    if not list_id or not title: return jsonify({'error': 'Invalid data'}), 400
    board_data = supabase.table('board_lists').select('board_id').eq('id', list_id).execute().data
    if not board_data: return jsonify({'error': 'List not found'}), 404
    result = supabase.table('tasks').select('position').eq('list_id', list_id).order('position', desc=True).limit(1).execute().data
    max_pos = result[0]['position'] if result else 0
    supabase.table('tasks').insert({
        'board_id': board_data[0]['board_id'],
        'list_id': list_id,
        'user_id': session['user_id'],
        'title': title,
        'description': data.get('description'),
        'position': max_pos + 1
    }).execute()
    track_event(session['user_id'], 'task_created', {
        'title': title,
        'list_id': list_id,
        'board_id': board_data[0]['board_id']
    })
    log_activity(board_data[0]['board_id'], 'task_created', title)
    return jsonify({'success': True})

@app.route('/api/move_task', methods=['POST'])
def move_task():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    new_list_id = data.get('list_id')
    if not task_id or not new_list_id: return jsonify({'error': 'Invalid data'}), 400
    task_data = supabase.table('tasks').select('board_id').eq('id', task_id).execute().data
    if not task_data: return jsonify({'error': 'Task not found'}), 404
    result = supabase.table('tasks').select('position').eq('list_id', new_list_id).order('position', desc=True).limit(1).execute().data
    max_pos = result[0]['position'] if result else 0
    supabase.table('tasks').update({
        'list_id': new_list_id,
        'position': max_pos + 1
    }).eq('id', task_id).execute()
    return jsonify({'success': True})

# ============ CHECKLIST API ============
@app.route('/api/add_checklist', methods=['POST'])
def add_checklist():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    item = data.get('item', '').strip()
    if not task_id or not item: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('checklists').insert({'task_id': task_id, 'item': item}).execute()
    return jsonify({'success': True})

@app.route('/api/toggle_checklist', methods=['POST'])
def toggle_checklist():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    item_id = data.get('item_id')
    checked = bool(data.get('checked'))
    if not item_id: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('checklists').update({'checked': checked}).eq('id', item_id).execute()
    return jsonify({'success': True})

# ============ LABEL API ============
@app.route('/api/add_label', methods=['POST'])
def add_label():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    label_id = data.get('label_id')
    if not task_id or not label_id: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('task_labels').insert({'task_id': task_id, 'label_id': label_id}).execute()
    return jsonify({'success': True})

@app.route('/api/remove_label', methods=['POST'])
def remove_label():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    label_id = data.get('label_id')
    if not task_id or not label_id: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('task_labels').delete().eq('task_id', task_id).eq('label_id', label_id).execute()
    return jsonify({'success': True})

# ============ ATTACHMENT API (Supabase Storage) ============
@app.route('/upload/<int:task_id>', methods=['POST'])
def upload_file(task_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    # Find board for redirect
    task_data = supabase.table('tasks').select('board_id').eq('id', task_id).execute().data
    redirect_url = url_for('board_view', board_id=task_data[0]['board_id']) if task_data else url_for('boards_page')
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(redirect_url)
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(redirect_url)
    if not allowed_file(file.filename):
        flash('File type not allowed', 'error')
        return redirect(redirect_url)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    storage_path = f"{session['user_id']}/{timestamp}_{file.filename}"
    file_bytes = file.read()
    try:
        supabase.storage.from_('attachments').upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": file.content_type or 'application/octet-stream'}
        )
        supabase.table('attachments').insert({
            'task_id': task_id,
            'filename': file.filename,
            'filepath': storage_path,
            'uploaded_by': session['user_id']
        }).execute()
        flash('File uploaded!', 'success')
    except Exception as e:
        flash(f'Upload error: {str(e)}', 'error')
    return redirect(redirect_url)

@app.route('/download/<int:att_id>')
def download_file(att_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    att_data = supabase.table('attachments').select('*').eq('id', att_id).execute().data
    if not att_data: return jsonify({'error': 'Attachment not found'}), 404
    att = att_data[0]
    public_url = supabase.storage.from_('attachments').get_public_url(att['filepath'])
    return redirect(public_url)

@app.route('/api/delete_attachment/<int:att_id>', methods=['DELETE'])
def delete_attachment(att_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    att_data = supabase.table('attachments').select('*').eq('id', att_id).execute().data
    if not att_data: return jsonify({'error': 'Attachment not found'}), 404
    att = att_data[0]
    try:
        supabase.storage.from_('attachments').remove([att['filepath']])
    except:
        pass
    supabase.table('attachments').delete().eq('id', att_id).execute()
    return jsonify({'success': True})

# ============ COMMENT API ============
@app.route('/api/add_comment', methods=['POST'])
def add_comment():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    body = (data.get('body') or '').strip()
    if not task_id or not body: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('comments').insert({
        'task_id': task_id,
        'user_id': session['user_id'],
        'body': body
    }).execute()
    track_event(session['user_id'], 'comment_added', {'task_id': task_id})
    return jsonify({'success': True})

@app.route('/api/delete_comment/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    supabase.table('comments').delete().eq('id', comment_id).execute()
    return jsonify({'success': True})

# ============ ASSIGNEE API ============
@app.route('/api/assign_task', methods=['POST'])
def assign_task():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    assignee_id = data.get('assignee_id')
    if not task_id: return jsonify({'error': 'Invalid data'}), 400
    if not _task_owner_ok(task_id): return jsonify({'error': 'Permission denied'}), 403
    supabase.table('tasks').update({'assignee_id': assignee_id}).eq('id', task_id).execute()
    track_event(session['user_id'], 'task_assigned', {'task_id': task_id, 'assignee_id': assignee_id})
    return jsonify({'success': True})

# ============ TIME TRACKING API ============
@app.route('/api/start_timer', methods=['POST'])
def start_timer():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    if not task_id: return jsonify({'error': 'Invalid data'}), 400
    from datetime import timezone
    supabase.table('time_entries').insert({
        'task_id': task_id,
        'user_id': session['user_id'],
        'start_time': datetime.now(timezone.utc).isoformat()
    }).execute()
    return jsonify({'success': True})

@app.route('/api/stop_timer', methods=['POST'])
def stop_timer():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    entry_id = data.get('entry_id')
    if not entry_id: return jsonify({'error': 'Invalid data'}), 400
    from datetime import timezone
    entry = supabase.table('time_entries').select('*').eq('id', entry_id).execute().data
    if not entry: return jsonify({'error': 'Entry not found'}), 404
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(entry[0]['start_time'].replace('Z', '+00:00'))
    duration = int((now - start).total_seconds())
    supabase.table('time_entries').update({
        'end_time': now.isoformat(),
        'duration_seconds': duration
    }).eq('id', entry_id).execute()
    return jsonify({'success': True, 'duration': duration})

@app.route('/api/time_entries/<int:task_id>')
def get_time_entries(task_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    entries = supabase.table('time_entries').select('*').eq('task_id', task_id).order('created_at', desc=True).execute().data
    return jsonify(entries)

@app.route('/api/timer_status/<int:task_id>')
def timer_status(task_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    entries = supabase.table('time_entries').select('*').eq('task_id', task_id).is_('end_time', 'null').execute().data
    running = entries[0] if entries else None
    all_entries = supabase.table('time_entries').select('duration_seconds').eq('task_id', task_id).execute().data
    total = sum(e.get('duration_seconds', 0) for e in all_entries)
    return jsonify({'running': running, 'total_seconds': total})

# ============ TASK DEPENDENCIES API ============
@app.route('/api/add_dependency', methods=['POST'])
def add_dependency():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    blocked_by_id = data.get('blocked_by_id')
    if not task_id or not blocked_by_id or task_id == blocked_by_id:
        return jsonify({'error': 'Invalid data'}), 400
    supabase.table('task_dependencies').insert({
        'task_id': task_id,
        'blocked_by_id': blocked_by_id
    }).execute()
    return jsonify({'success': True})

@app.route('/api/remove_dependency', methods=['POST'])
def remove_dependency():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    dep_id = data.get('dep_id')
    if not dep_id: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('task_dependencies').delete().eq('id', dep_id).execute()
    return jsonify({'success': True})

@app.route('/api/dependencies/<int:board_id>')
def get_dependencies(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    deps = supabase.table('task_dependencies').select('*, tasks!task_dependencies_blocked_by_id_fkey(title)').execute().data
    result = []
    for d in deps:
        bt = d.pop('tasks', None)
        result.append({'id': d['id'], 'task_id': d['task_id'], 'blocked_by_id': d['blocked_by_id'], 'blocked_by_title': bt['title'] if bt else ''})
    return jsonify(result)

# ============ TASK TEMPLATES API ============
@app.route('/api/create_template', methods=['POST'])
def create_template():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    name = (data.get('name') or '').strip()
    board_id = data.get('board_id')
    tasks = data.get('tasks', [])
    if not name or not board_id: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('task_templates').insert({
        'name': name,
        'board_id': board_id,
        'tasks_json': tasks
    }).execute()
    return jsonify({'success': True})

@app.route('/api/templates/<int:board_id>')
def get_templates(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    templates = supabase.table('task_templates').select('*').eq('board_id', board_id).execute().data
    return jsonify(templates)

@app.route('/api/use_template', methods=['POST'])
def use_template():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    template_id = data.get('template_id')
    list_id = data.get('list_id')
    if not template_id or not list_id: return jsonify({'error': 'Invalid data'}), 400
    tmpl = supabase.table('task_templates').select('*').eq('id', template_id).execute().data
    if not tmpl: return jsonify({'error': 'Template not found'}), 404
    tasks_json = tmpl[0]['tasks_json']
    board_data = supabase.table('board_lists').select('board_id').eq('id', list_id).execute().data
    if not board_data: return jsonify({'error': 'List not found'}), 404
    board_id = board_data[0]['board_id']
    for t in tasks_json:
        supabase.table('tasks').insert({
            'board_id': board_id,
            'list_id': list_id,
            'user_id': session['user_id'],
            'title': t.get('title', 'Untitled'),
            'description': t.get('description', ''),
            'priority': t.get('priority', 'medium')
        }).execute()
    return jsonify({'success': True, 'count': len(tasks_json)})

@app.route('/api/delete_template/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    supabase.table('task_templates').delete().eq('id', template_id).execute()
    return jsonify({'success': True})

# ============ BOARD ROLES API ============
@app.route('/api/set_board_role', methods=['POST'])
def set_board_role():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    board_id = data.get('board_id')
    target_user_id = data.get('user_id')
    role = data.get('role', 'editor')
    if not board_id or not target_user_id: return jsonify({'error': 'Invalid data'}), 400
    if role not in ('viewer', 'editor', 'admin'): return jsonify({'error': 'Invalid role'}), 400
    if not is_owner_or_admin(board_id): return jsonify({'error': 'Permission denied'}), 403
    try:
        supabase.table('board_roles').upsert({
            'board_id': board_id,
            'user_id': target_user_id,
            'role': role
        }).execute()
    except:
        supabase.table('board_roles').update({'role': role}).eq('board_id', board_id).eq('user_id', target_user_id).execute()
    return jsonify({'success': True})

@app.route('/api/board_roles/<int:board_id>')
def get_board_roles(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    roles = supabase.table('board_roles').select('*, users(username)').eq('board_id', board_id).execute().data
    result = []
    for r in roles:
        u = r.pop('users', None)
        result.append({'id': r['id'], 'user_id': r['user_id'], 'username': u['username'] if u else '', 'role': r['role']})
    return jsonify(result)

# ============ UNDO API ============
@app.route('/api/log_undo', methods=['POST'])
def log_undo():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    action_type = data.get('action_type')
    action_data = data.get('action_data', {})
    if not action_type: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('undo_log').insert({
        'user_id': session['user_id'],
        'action_type': action_type,
        'action_data': action_data
    }).execute()
    return jsonify({'success': True})

@app.route('/api/undo', methods=['POST'])
def undo_last():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    log = supabase.table('undo_log').select('*').eq('user_id', session['user_id']).order('created_at', desc=True).limit(1).execute().data
    if not log: return jsonify({'error': 'Nothing to undo'}), 400
    entry = log[0]
    action_type = entry['action_type']
    action_data = entry['action_data']
    if action_type == 'task_deleted':
        supabase.table('tasks').insert(action_data).execute()
    elif action_type == 'task_moved':
        supabase.table('tasks').update({'list_id': action_data.get('old_list_id')}).eq('id', action_data.get('task_id')).execute()
    supabase.table('undo_log').delete().eq('id', entry['id']).execute()
    return jsonify({'success': True, 'action': action_type})

# ============ BULK ACTIONS API ============
@app.route('/api/bulk_move', methods=['POST'])
def bulk_move():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_ids = data.get('task_ids', [])
    new_list_id = data.get('list_id')
    if not task_ids or not new_list_id: return jsonify({'error': 'Invalid data'}), 400
    for tid in task_ids:
        result = supabase.table('tasks').select('position').eq('list_id', new_list_id).order('position', desc=True).limit(1).execute().data
        max_pos = result[0]['position'] if result else 0
        supabase.table('tasks').update({'list_id': new_list_id, 'position': max_pos + 1}).eq('id', tid).execute()
    return jsonify({'success': True, 'moved': len(task_ids)})

@app.route('/api/bulk_delete', methods=['POST'])
def bulk_delete():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_ids = data.get('task_ids', [])
    if not task_ids: return jsonify({'error': 'Invalid data'}), 400
    for tid in task_ids:
        supabase.table('tasks').delete().eq('id', tid).execute()
    return jsonify({'success': True, 'deleted': len(task_ids)})

@app.route('/api/bulk_complete', methods=['POST'])
def bulk_complete():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_ids = data.get('task_ids', [])
    status = data.get('status', 'completed')
    if not task_ids: return jsonify({'error': 'Invalid data'}), 400
    for tid in task_ids:
        supabase.table('tasks').update({'status': status}).eq('id', tid).execute()
    return jsonify({'success': True, 'updated': len(task_ids)})

# ============ BOARD THEME API ============
@app.route('/api/update_theme', methods=['POST'])
def update_theme():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    board_id = data.get('board_id')
    theme_color = data.get('theme_color')
    theme_bg = data.get('theme_bg')
    if not board_id: return jsonify({'error': 'Invalid data'}), 400
    updates = {}
    if theme_color is not None: updates['theme_color'] = theme_color
    if theme_bg is not None: updates['theme_bg'] = theme_bg
    if updates:
        supabase.table('boards').update(updates).eq('id', board_id).execute()
    return jsonify({'success': True})

# ============ CALENDAR/GANTT DATA API ============
@app.route('/api/calendar_data/<int:board_id>')
def calendar_data(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    tasks = supabase.table('tasks').select('id, title, due_date, priority, status, assignee_id, list_id, board_lists(name)').eq('board_id', board_id).not_.is_('due_date', 'null').execute().data
    result = []
    for t in tasks:
        li = t.pop('board_lists', None)
        result.append({
            'id': t['id'], 'title': t['title'], 'due_date': t['due_date'],
            'priority': t.get('priority', 'medium'), 'status': t.get('status', 'pending'),
            'list': li['name'] if li else ''
        })
    return jsonify(result)

# ============ REMINDERS API ============
@app.route('/api/set_reminder', methods=['POST'])
def set_reminder():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    remind_at = data.get('remind_at')
    message = data.get('message', '')
    if not task_id or not remind_at: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('reminders').insert({
        'task_id': task_id,
        'remind_at': remind_at,
        'message': message
    }).execute()
    return jsonify({'success': True})

# ============ BOARD / LIST / TASK MANAGEMENT API ============

def is_owner_or_admin(board_id, user_id=None):
    """Check if user owns the board or is admin."""
    user_id = user_id or session['user_id']
    board = supabase.table('boards').select('*').eq('id', board_id).execute().data
    if not board:
        return False
    board = board[0]
    if board.get('owner_id') == user_id:
        return True
    user = supabase.table('users').select('role').eq('id', user_id).execute().data
    if user and user[0].get('role') == 'admin':
        return True
    return False

def _task_owner_ok(task_id):
    """Return True if current user owns the task's board (or is admin)."""
    task = supabase.table('tasks').select('board_id').eq('id', task_id).execute().data
    if not task:
        return False
    return is_owner_or_admin(task[0]['board_id'])

@app.route('/api/boards', methods=['GET'])
def api_boards():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    boards = supabase.table('boards').select('*').eq('owner_id', session['user_id']).order('created_at', desc=True).execute().data
    return jsonify(boards)

@app.route('/api/boards/<int:board_id>', methods=['GET'])
def api_board_detail(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    board = supabase.table('boards').select('*').eq('id', board_id).eq('owner_id', session['user_id']).execute().data
    if not board: return jsonify({'error': 'Board not found'}), 404
    lists = supabase.table('board_lists').select('*').eq('board_id', board_id).order('position').execute().data
    tasks = supabase.table('tasks').select('*').eq('board_id', board_id).order('position').execute().data
    return jsonify({'board': board[0], 'lists': lists, 'tasks': tasks})

@app.route('/api/edit_board', methods=['POST'])
def edit_board():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    board_id = data.get('board_id')
    name = (data.get('name') or '').strip()
    if not board_id or not name: return jsonify({'error': 'Invalid data'}), 400
    if not is_owner_or_admin(board_id): return jsonify({'error': 'Permission denied'}), 403
    supabase.table('boards').update({'name': name, 'description': data.get('description')}).eq('id', board_id).execute()
    return jsonify({'success': True})

@app.route('/api/delete_board/<int:board_id>', methods=['DELETE'])
def delete_board(board_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    if not is_owner_or_admin(board_id): return jsonify({'error': 'Permission denied'}), 403
    supabase.table('boards').delete().eq('id', board_id).execute()
    return jsonify({'success': True})

@app.route('/api/delete_list/<int:list_id>', methods=['DELETE'])
def delete_list(list_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    lst = supabase.table('board_lists').select('board_id').eq('id', list_id).execute().data
    if not lst: return jsonify({'error': 'List not found'}), 404
    if not is_owner_or_admin(lst[0]['board_id']): return jsonify({'error': 'Permission denied'}), 403
    supabase.table('board_lists').delete().eq('id', list_id).execute()
    return jsonify({'success': True})

@app.route('/api/edit_task', methods=['POST'])
def edit_task():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    title = (data.get('title') or '').strip()
    if not task_id or not title: return jsonify({'error': 'Invalid data'}), 400
    if not _task_owner_ok(task_id): return jsonify({'error': 'Permission denied'}), 403
    supabase.table('tasks').update({'title': title, 'description': data.get('description')}).eq('id', task_id).execute()
    return jsonify({'success': True})

@app.route('/api/delete_task/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    if not _task_owner_ok(task_id): return jsonify({'error': 'Permission denied'}), 403
    task_info = supabase.table('tasks').select('board_id, title').eq('id', task_id).execute().data
    board_id = task_info[0]['board_id'] if task_info else None
    task_title = task_info[0].get('title', '') if task_info else ''
    supabase.table('tasks').delete().eq('id', task_id).execute()
    track_event(session['user_id'], 'task_deleted', {
        'task_id': task_id
    })
    if board_id:
        log_activity(board_id, 'task_deleted', task_title)
    return jsonify({'success': True})

@app.route('/api/set_due_date', methods=['POST'])
def set_due_date():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    if not task_id: return jsonify({'error': 'Invalid data'}), 400
    if not _task_owner_ok(task_id): return jsonify({'error': 'Permission denied'}), 403
    due_date = data.get('due_date')
    supabase.table('tasks').update({'due_date': due_date}).eq('id', task_id).execute()
    track_event(session['user_id'], 'task_due_date_set', {
        'task_id': task_id,
        'due_date': due_date
    })
    return jsonify({'success': True, 'due_date': due_date})

@app.route('/api/toggle_complete/<int:task_id>', methods=['POST'])
def toggle_complete(task_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    task = supabase.table('tasks').select('status').eq('id', task_id).execute().data
    if not task: return jsonify({'error': 'Task not found'}), 404
    if not _task_owner_ok(task_id): return jsonify({'error': 'Permission denied'}), 403
    new_status = 'completed' if task[0].get('status') != 'completed' else 'pending'
    supabase.table('tasks').update({'status': new_status}).eq('id', task_id).execute()
    track_event(session['user_id'], 'task_toggled', {
        'task_id': task_id,
        'new_status': new_status
    })
    task_info = supabase.table('tasks').select('board_id, title').eq('id', task_id).execute().data
    if task_info:
        log_activity(task_info[0]['board_id'], 'task_completed' if new_status == 'completed' else 'task_uncompleted', task_info[0].get('title', ''))
    return jsonify({'success': True, 'status': new_status})

@app.route('/api/set_priority', methods=['POST'])
def set_priority():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    task_id = data.get('task_id')
    priority = data.get('priority')
    if not task_id or priority not in ('low', 'medium', 'high'):
        return jsonify({'error': 'Invalid data'}), 400
    if not _task_owner_ok(task_id): return jsonify({'error': 'Permission denied'}), 403
    supabase.table('tasks').update({'priority': priority}).eq('id', task_id).execute()
    return jsonify({'success': True, 'priority': priority})

@app.route('/api/create_label', methods=['POST'])
def create_label():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    name = (data.get('name') or '').strip()
    color = (data.get('color') or '#1a73e8').strip()
    if not name: return jsonify({'error': 'Label name required'}), 400
    supabase.table('labels').insert({'name': name, 'color': color}).execute()
    return jsonify({'success': True})

@app.route('/api/edit_label', methods=['POST'])
def edit_label():
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    data = request.get_json()
    label_id = data.get('label_id')
    name = (data.get('name') or '').strip()
    if not label_id or not name: return jsonify({'error': 'Invalid data'}), 400
    supabase.table('labels').update({'name': name, 'color': (data.get('color') or '#1a73e8')}).eq('id', label_id).execute()
    return jsonify({'success': True})

@app.route('/api/delete_label/<int:label_id>', methods=['DELETE'])
def delete_label(label_id):
    if 'user_id' not in session: return jsonify({'error': 'Not logged in'}), 401
    supabase.table('labels').delete().eq('id', label_id).execute()
    return jsonify({'success': True})

@app.route('/calendar/<int:board_id>')
def calendar_view(board_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    board_data = supabase.table('boards').select('*').eq('id', board_id).eq('owner_id', session['user_id']).execute().data
    if not board_data: return redirect(url_for('boards_page'))
    board = board_data[0]
    tasks_raw = supabase.table('tasks').select('*').eq('board_id', board_id).execute().data
    tasks_json = []
    for t in tasks_raw:
        dd = t.get('due_date')
        if dd:
            dd_short = dd[:10] if len(dd) >= 10 else dd
            tasks_json.append({'id': t['id'], 'title': t['title'], 'due_date': dd_short, 'priority': t.get('priority', 'medium'), 'status': t.get('status', 'pending')})
    return render_template_string('''<!DOCTYPE html><html><head><title>Calendar - {{ board['name'] }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg: #f0f2f5; --card-bg: white; --text: #333; --text-secondary: #5e6c84; --border: #eee; }
        [data-theme="dark"] { --bg: #1a1a2e; --card-bg: #16213e; --text: #e0e0e0; --text-secondary: #a0a0b0; --border: #333; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Poppins',sans-serif; background:var(--bg); color:var(--text); padding:20px; }
        .cal-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; flex-wrap:wrap; gap:10px; }
        .cal-header h1 { font-size:24px; }
        .cal-nav { display:flex; gap:10px; align-items:center; }
        .cal-nav button { padding:8px 16px; background:var(--card-bg); color:var(--text); border:2px solid var(--border); border-radius:10px; cursor:pointer; font-weight:600; font-family:'Poppins',sans-serif; }
        .cal-nav span { font-size:18px; font-weight:600; min-width:180px; text-align:center; }
        .cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:4px; }
        .cal-day-header { padding:8px; text-align:center; font-weight:600; font-size:13px; color:var(--text-secondary); }
        .cal-day { min-height:100px; background:var(--card-bg); border-radius:10px; padding:8px; border:1px solid var(--border); }
        .cal-day.today { border-color:#667eea; border-width:2px; }
        .cal-day.other-month { opacity:0.4; }
        .cal-day-num { font-weight:600; font-size:13px; margin-bottom:4px; color:var(--text); }
        .cal-task { padding:3px 8px; border-radius:6px; font-size:11px; font-weight:500; margin-bottom:2px; color:white; cursor:pointer; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .cal-task.low { background:#34a853; }
        .cal-task.medium { background:#667eea; }
        .cal-task.high { background:#ea4335; }
        .btn-back { padding:8px 16px; background:var(--card-bg); color:var(--text); text-decoration:none; border-radius:10px; border:2px solid var(--border); font-weight:600; font-family:'Poppins',sans-serif; }
        .dark-toggle { background:var(--card-bg); border:2px solid var(--border); color:var(--text); padding:8px 14px; border-radius:10px; cursor:pointer; font-size:16px; }
    </style></head><body>
    <div class="cal-header">
        <h1>📅 {{ board['name'] }} - Calendar</h1>
        <div class="cal-nav">
            <button onclick="changeMonth(-1)">◀</button>
            <span id="calTitle"></span>
            <button onclick="changeMonth(1)">▶</button>
            <button class="dark-toggle" onclick="toggleDark()" id="darkBtn">🌙</button>
            <a href="/board/{{ board['id'] }}" class="btn-back">← Board</a>
        </div>
    </div>
    <div class="cal-grid" id="calGrid"></div>
    <script>
    const tasks = {{ tasks_json|tojson }};
    let viewDate = new Date();
    function toggleDark() {
        const isDark = document.documentElement.getAttribute('data-theme')==='dark';
        document.documentElement.setAttribute('data-theme', isDark?'light':'dark');
        localStorage.setItem('theme', isDark?'light':'dark');
        document.getElementById('darkBtn').textContent = isDark?'🌙':'☀️';
    }
    (function(){ if(localStorage.getItem('theme')==='dark'){ document.documentElement.setAttribute('data-theme','dark'); document.getElementById('darkBtn').textContent='☀️'; }})();
    function render() {
        const y = viewDate.getFullYear(), m = viewDate.getMonth();
        document.getElementById('calTitle').textContent = viewDate.toLocaleString('default',{month:'long',year:'numeric'});
        const first = new Date(y,m,1), startDay = first.getDay(), daysInMonth = new Date(y,m+1,0).getDate();
        const today = new Date(), todayStr = today.getFullYear()+'-'+String(today.getMonth()+1).padStart(2,'0')+'-'+String(today.getDate()).padStart(2,'0');
        const prevDays = new Date(y,m,0).getDate();
        let html = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d=>'<div class="cal-day-header">'+d+'</div>').join('');
        for(let i=0;i<startDay;i++){
            const d=prevDays-startDay+i+1;
            html+='<div class="cal-day other-month"><div class="cal-day-num">'+d+'</div></div>';
        }
        for(let d=1;d<=daysInMonth;d++){
            const ds=y+'-'+String(m+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
            const isToday=ds===todayStr;
            html+='<div class="cal-day'+(isToday?' today':'')+'"><div class="cal-day-num">'+d+'</div>';
            tasks.filter(t=>t.due_date===ds).forEach(t=>{
                html+='<div class="cal-task '+t.priority+'" title="'+t.title+'">'+t.title+'</div>';
            });
            html+='</div>';
        }
        const totalCells=startDay+daysInMonth, remaining=totalCells%7===0?0:7-totalCells%7;
        for(let i=1;i<=remaining;i++){
            html+='<div class="cal-day other-month"><div class="cal-day-num">'+i+'</div></div>';
        }
        document.getElementById('calGrid').innerHTML=html;
    }
    function changeMonth(delta){ viewDate.setMonth(viewDate.getMonth()+delta); render(); }
    render();
    </script></body></html>''', board=board, tasks_json=tasks_json)

@app.route('/gantt/<int:board_id>')
def gantt_view(board_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    board_data = supabase.table('boards').select('*').eq('id', board_id).eq('owner_id', session['user_id']).execute().data
    if not board_data: return redirect(url_for('boards_page'))
    board = board_data[0]
    lists = supabase.table('board_lists').select('*').eq('board_id', board_id).order('position').execute().data
    tasks_raw = supabase.table('tasks').select('*').eq('board_id', board_id).order('position').execute().data
    tasks_json = []
    for t in tasks_raw:
        dd = t.get('due_date')
        if dd:
            dd_short = dd[:10] if len(dd) >= 10 else dd
            tasks_json.append({'id': t['id'], 'title': t['title'], 'list_id': t['list_id'], 'due_date': dd_short, 'priority': t.get('priority', 'medium'), 'status': t.get('status', 'pending'), 'created_at': (t.get('created_at',''))[:10]})
    lists_json = [{'id': l['id'], 'name': l['name']} for l in lists]
    return render_template_string('''<!DOCTYPE html><html><head><title>Gantt - {{ board['name'] }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg: #f0f2f5; --card-bg: white; --text: #333; --text-secondary: #5e6c84; --border: #eee; }
        [data-theme="dark"] { --bg: #1a1a2e; --card-bg: #16213e; --text: #e0e0e0; --text-secondary: #a0a0b0; --border: #333; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Poppins',sans-serif; background:var(--bg); color:var(--text); padding:20px; }
        .gantt-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; flex-wrap:wrap; gap:10px; }
        .gantt-header h1 { font-size:24px; }
        .btn-back { padding:8px 16px; background:var(--card-bg); color:var(--text); text-decoration:none; border-radius:10px; border:2px solid var(--border); font-weight:600; font-family:'Poppins',sans-serif; }
        .dark-toggle { background:var(--card-bg); border:2px solid var(--border); color:var(--text); padding:8px 14px; border-radius:10px; cursor:pointer; font-size:16px; }
        .gantt-container { overflow-x:auto; background:var(--card-bg); border-radius:16px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.05); }
        .gantt-table { width:100%; border-collapse:collapse; }
        .gantt-table th, .gantt-table td { padding:8px 12px; text-align:left; border-bottom:1px solid var(--border); font-size:13px; }
        .gantt-table th { font-weight:600; color:var(--text-secondary); position:sticky; top:0; background:var(--card-bg); }
        .gantt-bar { height:24px; border-radius:6px; position:relative; min-width:20px; }
        .gantt-bar.low { background:#34a853; }
        .gantt-bar.medium { background:#667eea; }
        .gantt-bar.high { background:#ea4335; }
        .gantt-bar.completed { opacity:0.5; }
        .gantt-timeline { position:relative; height:100%; }
        .gantt-label { font-weight:500; font-size:13px; white-space:nowrap; max-width:200px; overflow:hidden; text-overflow:ellipsis; }
        .status-badge { padding:2px 8px; border-radius:6px; font-size:11px; font-weight:600; }
        .status-badge.pending { background:#f3e5f5; color:#6b21a8; }
        .status-badge.completed { background:#dcfce7; color:#166534; }
    </style></head><body>
    <div class="gantt-header">
        <h1>📊 {{ board['name'] }} - Gantt Chart</h1>
        <div style="display:flex;gap:10px;align-items:center;">
            <button class="dark-toggle" onclick="toggleDark()" id="darkBtn">🌙</button>
            <a href="/board/{{ board['id'] }}" class="btn-back">← Board</a>
        </div>
    </div>
    <div class="gantt-container">
        <table class="gantt-table">
            <thead><tr><th style="min-width:200px;">Task</th><th style="min-width:120px;">List</th><th style="min-width:80px;">Priority</th><th style="min-width:90px;">Status</th><th style="min-width:100px;">Start</th><th style="min-width:100px;">Due</th><th style="min-width:300px;">Timeline</th></tr></thead>
            <tbody id="ganttBody"></tbody>
        </table>
    </div>
    <script>
    const tasks = {{ tasks_json|tojson }};
    const lists = {{ lists_json|tojson }};
    const listMap = {};
    lists.forEach(l => listMap[l.id] = l.name);
    function toggleDark() {
        const isDark = document.documentElement.getAttribute('data-theme')==='dark';
        document.documentElement.setAttribute('data-theme', isDark?'light':'dark');
        localStorage.setItem('theme', isDark?'light':'dark');
        document.getElementById('darkBtn').textContent = isDark?'🌙':'☀️';
    }
    (function(){ if(localStorage.getItem('theme')==='dark'){ document.documentElement.setAttribute('data-theme','dark'); document.getElementById('darkBtn').textContent='☀️'; }})();
    const tasksWithDates = tasks.filter(t => t.due_date);
    if(tasksWithDates.length === 0) {
        document.getElementById('ganttBody').innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-secondary);">No tasks with due dates. Set due dates to see the Gantt chart.</td></tr>';
    } else {
        let allDates = [];
        tasksWithDates.forEach(t => { if(t.created_at) allDates.push(t.created_at); allDates.push(t.due_date); });
        allDates = allDates.filter(d=>d).sort();
        const minDate = allDates[0] || new Date().toISOString().slice(0,10);
        const maxDate = allDates[allDates.length-1] || new Date().toISOString().slice(0,10);
        const startMs = new Date(minDate).getTime();
        const endMs = new Date(maxDate).getTime();
        const range = Math.max(endMs - startMs, 86400000);
        let html = '';
        tasksWithDates.forEach(t => {
            const start = t.created_at || t.due_date;
            const startPct = Math.max(0, ((new Date(start).getTime() - startMs) / range) * 100);
            const widthPct = Math.max(2, ((new Date(t.due_date).getTime() - new Date(start).getTime()) / range) * 100);
            html += '<tr>';
            html += '<td class="gantt-label">' + t.title + '</td>';
            html += '<td>' + (listMap[t.list_id]||'') + '</td>';
            html += '<td><span style="font-weight:600;font-size:12px;">' + t.priority + '</span></td>';
            html += '<td><span class="status-badge ' + t.status + '">' + t.status + '</span></td>';
            html += '<td>' + start + '</td>';
            html += '<td>' + t.due_date + '</td>';
            html += '<td><div style="position:relative;width:100%;height:24px;"><div class="gantt-bar ' + t.priority + (t.status==='completed'?' completed':'') + '" style="position:absolute;left:' + startPct + '%;width:' + widthPct + '%;"></div></div></td>';
            html += '</tr>';
        });
        document.getElementById('ganttBody').innerHTML = html;
    }
    </script></body></html>''', board=board, tasks_json=tasks_json, lists_json=lists_json)

# ============ AUTH ROUTES ============

@app.route('/google/login')
def google_login():
    if not GOOGLE_CLIENT_ID:
        flash('Google Login is not configured. Please add GOOGLE_CLIENT_ID.', 'error')
        return redirect(url_for('login'))
    
    import urllib.parse
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': request.url_root.rstrip('/') + url_for('google_auth'),
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'offline',
        'prompt': 'consent'
    }
    auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
    return redirect(auth_url)

@app.route('/google/auth')
def google_auth():
    code = request.args.get('code')
    if not code:
        flash('Google Login failed.', 'error')
        return redirect(url_for('login'))
    
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': request.url_root.rstrip('/') + url_for('google_auth'),
        'grant_type': 'authorization_code'
    }
    r = requests.post(token_url, data=data)
    if r.status_code != 200:
        flash('Failed to retrieve token from Google.', 'error')
        return redirect(url_for('login'))
    
    access_token = r.json().get('access_token')
    
    userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {'Authorization': f'Bearer {access_token}'}
    r_user = requests.get(userinfo_url, headers=headers)
    user_info = r_user.json()
    
    email = user_info.get('email')
    if not email:
        flash('Google did not provide an email address.', 'error')
        return redirect(url_for('login'))
        
    username = email.split('@')[0]
    
    user_data = supabase.table('users').select('*').eq('email', email).execute().data
    if user_data:
        user = user_data[0]
    else:
        try:
            uname_check = supabase.table('users').select('id').eq('username', username).execute().data
            if uname_check:
                import random
                username = f"{username}{random.randint(100,999)}"
                
            res = supabase.table('users').insert({
                'username': username,
                'email': email,
                'password': hashlib.sha256(os.urandom(16)).hexdigest(),
                'role': 'user'
            }).execute()
            user = res.data[0]
            track_event(user['id'], 'user_registered', {
                'ip': request.remote_addr or '',
                'has_email': True,
                'method': 'google'
            })
        except Exception as e:
            flash(f'Error creating account: {str(e)}', 'error')
            return redirect(url_for('login'))
            
    session['user_id'] = user['id']
    session['username'] = user['username']
    try:
        supabase.table('login_logs').insert({
            'user_id': user['id'],
            'username': user['username'],
            'email': user.get('email') or '',
            'ip': request.remote_addr or ''
        }).execute()
    except:
        pass
    track_event(user['id'], 'user_logged_in', {
        'username': user['username'],
        'method': 'google'
    })
    
    flash(f'Welcome, {user["username"]}!', 'success')
    return redirect(url_for('boards_page'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('boards_page'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user_data = supabase.table('users').select('*').eq('username', username).execute().data
        if user_data and hashlib.sha256(password.encode()).hexdigest() == user_data[0]['password']:
            user = user_data[0]
            session['user_id'] = user['id']
            session['username'] = user['username']
            try:
                supabase.table('login_logs').insert({
                    'user_id': user['id'],
                    'username': user['username'],
                    'email': user.get('email') or '',
                    'ip': request.remote_addr or ''
                }).execute()
            except Exception as e:
                print(f"login log warning: {e}")
            track_event(user['id'], 'user_logged_in', {
                'username': user['username'],
                'ip': request.remote_addr or '',
                'source': 'login_page'
            })
            threading.Thread(
                target=notify_login,
                args=(user['username'], user.get('email') or '', request.remote_addr or ''),
                daemon=True
            ).start()
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('boards_page'))
        track_event(request.form.get('username', '') or 'unknown', 'login_failed', {
            'ip': request.remote_addr or ''
        })
        flash('Invalid username or password!', 'error')
    return render_template_string(LOGIN_PAGE)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session: return redirect(url_for('boards_page'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        email = request.form.get('email', '').strip()
        if not username or not password: flash('Please fill all fields!', 'error')
        elif password != confirm: flash('Passwords do not match!', 'error')
        elif len(password) < 4: flash('Password must be at least 4 characters!', 'error')
        else:
            existing = supabase.table('users').select('*').eq('username', username).execute().data
            if existing: flash('Username already taken!', 'error')
            else:
                supabase.table('users').insert({
                    'username': username,
                    'password': hashlib.sha256(password.encode()).hexdigest(),
                    'email': email or None
                }).execute()
                track_event(username, 'user_registered', {
                    'ip': request.remote_addr or '',
                    'has_email': bool(email)
                })
                flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
    return render_template_string(REGISTER_PAGE)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/login-log')
def login_log():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        user_data = supabase.table('users').select('role').eq('id', session['user_id']).execute().data
    except Exception as e:
        print(f"login_log user query warning: {e}")
        user_data = []
    if not user_data or user_data[0].get('role') != 'admin':
        return redirect(url_for('boards_page'))
    setup_needed = False
    try:
        logs = supabase.table('login_logs').select('*').order('login_time', desc=True).limit(500).execute().data
    except Exception as e:
        print(f"login_log query error: {e}")
        logs = []
        setup_needed = True
    counts = {}
    for log in logs:
        key = log['username']
        last = log.get('login_time')
        if key not in counts:
            counts[key] = {'username': key, 'email': log.get('email') or '', 'total': 0, 'last': last or ''}
        counts[key]['total'] += 1
        if last and (not counts[key]['last'] or last > counts[key]['last']):
            counts[key]['last'] = last
    count_rows = sorted(counts.values(), key=lambda x: x['total'], reverse=True)
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login Activity</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Poppins', sans-serif; background: #f0f2f5; min-height: 100vh; padding: 30px 20px; }
            .container { max-width: 1000px; margin: auto; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; flex-wrap: wrap; gap: 10px; }
            .header h1 { font-size: 26px; font-weight: 700; color: #333; }
            .btn-back { padding: 10px 20px; background: white; color: #333; text-decoration: none; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); transition: 0.3s; font-weight: 500; }
            .btn-back:hover { box-shadow: 0 5px 15px rgba(0,0,0,0.1); transform: translateY(-2px); }
            .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }
            .card { background: white; padding: 20px; border-radius: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
            .card .num { font-size: 30px; font-weight: 700; color: #667eea; }
            .card .lbl { font-size: 13px; color: #5e6c84; margin-top: 4px; }
            .section { background: white; border-radius: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); padding: 20px; margin-bottom: 25px; }
            .section h2 { font-size: 18px; font-weight: 600; color: #333; margin-bottom: 15px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 10px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid #eee; }
            th { color: #5e6c84; font-weight: 600; background: #f8f9fa; }
            td { color: #333; }
            .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; background: #e8eaed; color: #333; }
            .badge.top { background: #fee2e2; color: #991b2b; }
            .table-scroll { overflow-x: auto; }
            @media (max-width: 600px) { th, td { font-size: 12px; padding: 8px; } }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 Login Activity</h1>
                <a href="/boards" class="btn-back">← Back to Boards</a>
            </div>
            {% if setup_needed %}
            <div class="section" style="border: 2px solid #f59e0b; background: #fffbeb;">
                <h2 style="color:#b45309;">⚠️ Database setup needed</h2>
                <p style="font-size:13px; color:#92400e; line-height:1.7;">The <code style="background:#fef3c7; padding:2px 6px; border-radius:4px;">login_logs</code> table is missing or has no read access.
                Open your <strong>Supabase Dashboard → SQL Editor</strong>, paste the full <code style="background:#fef3c7; padding:2px 6px; border-radius:4px;">init_supabase.sql</code> file, and run it. Then refresh this page.</p>
            </div>
            {% endif %}
            <div class="cards">
                <div class="card"><div class="num">{{ logs|length }}</div><div class="lbl">Total Logins</div></div>
                <div class="card"><div class="num">{{ count_rows|length }}</div><div class="lbl">Unique Users</div></div>
                <div class="card"><div class="num">{{ count_rows|selectattr('total', 'gt', 1)|list|length }}</div><div class="lbl">Repeat Logins</div></div>
            </div>
            <div class="section">
                <h2>👤 Login Count per User</h2>
                <div class="table-scroll">
                <table>
                    <tr><th>#</th><th>Username</th><th>Email</th><th>Total Logins</th><th>Last Login</th></tr>
                    {% for row in count_rows %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td><span class="badge{% if row['total'] > 1 %} top{% endif %}">{{ row['username'] }}</span></td>
                        <td>{{ row['email'] or '—' }}</td>
                        <td>{{ row['total'] }}</td>
                        <td>{{ row['last'][:19].replace('T', ' ') if row['last'] else '—' }}</td>
                    </tr>
                    {% endfor %}
                </table>
                </div>
            </div>
            <div class="section">
                <h2>📝 Recent Login History</h2>
                <div class="table-scroll">
                <table>
                    <tr><th>#</th><th>Time</th><th>Username</th><th>Email</th><th>IP Address</th></tr>
                    {% for log in logs %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td>{{ (log.get('login_time') or '')[:19].replace('T', ' ') or '—' }}</td>
                        <td>{{ log['username'] }}</td>
                        <td>{{ log.get('email') or '—' }}</td>
                        <td>{{ log.get('ip') or '—' }}</td>
                    </tr>
                    {% endfor %}
                </table>
                </div>
            </div>
        </div>
    </body>
    </html>
    ''', logs=logs, count_rows=count_rows, setup_needed=setup_needed)

LOGIN_PAGE = '''
<!DOCTYPE html>
<html><head><title>Login</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:'Poppins',sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.login-box{background:white;padding:40px;border-radius:20px;box-shadow:0 10px 30px rgba(0,0,0,0.1);max-width:400px;width:90%}h1{color:#1a73e8;text-align:center}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:8px}button{width:100%;padding:12px;background:#1a73e8;color:white;border:none;border-radius:8px;cursor:pointer}.links{text-align:center;margin-top:20px}.flash{padding:12px;border-radius:8px;margin-bottom:15px}.flash-success{background:#e6f4ea;color:#137333}.flash-error{background:#fce8e6;color:#c5221f}</style></head>
<body><div class="login-box"><h1>📋 Task Manager</h1><p style="text-align:center;color:#5f6368;">Login to manage your boards</p>
{% with messages = get_flashed_messages(with_categories=true) %}{% for category, message in messages %}<div class="flash flash-{{ category }}">{{ message }}</div>{% endfor %}{% endwith %}
<form method="POST"><input type="text" name="username" placeholder="Username" required><input type="password" name="password" placeholder="Password" required><button type="submit">🔑 Login</button></form><a href="/google/login" style="display:block;width:100%;padding:12px;background:#fff;color:#333;border:1px solid #ddd;border-radius:8px;text-align:center;text-decoration:none;margin-top:10px;box-sizing:border-box;">?? Continue with Google</a>
<div class="links">Don't have an account? <a href="/register" style="color:#1a73e8;text-decoration:none;">Register here</a></div></div></body></html>
'''

REGISTER_PAGE = '''
<!DOCTYPE html>
<html><head><title>Register</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:'Poppins',sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.register-box{background:white;padding:40px;border-radius:20px;box-shadow:0 10px 30px rgba(0,0,0,0.1);max-width:400px;width:90%}h1{color:#1a73e8;text-align:center}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:8px}button{width:100%;padding:12px;background:#1a73e8;color:white;border:none;border-radius:8px;cursor:pointer}.links{text-align:center;margin-top:20px}.flash{padding:12px;border-radius:8px;margin-bottom:15px}.flash-success{background:#e6f4ea;color:#137333}.flash-error{background:#fce8e6;color:#c5221f}</style></head>
<body><div class="register-box"><h1>📋 Task Manager</h1><p style="text-align:center;color:#5f6368;">Create a new account</p>
{% with messages = get_flashed_messages(with_categories=true) %}{% for category, message in messages %}<div class="flash flash-{{ category }}">{{ message }}</div>{% endfor %}{% endwith %}
<form method="POST"><input type="text" name="username" placeholder="Choose a username" required><input type="email" name="email" placeholder="Email (optional)"><input type="password" name="password" placeholder="Password (min 4 chars)" required><input type="password" name="confirm_password" placeholder="Confirm password" required><button type="submit">✅ Register</button></form><a href="/google/login" style="display:block;width:100%;padding:12px;background:#fff;color:#333;border:1px solid #ddd;border-radius:8px;text-align:center;text-decoration:none;margin-top:10px;box-sizing:border-box;">?? Continue with Google</a>
<div class="links">Already have an account? <a href="/login" style="color:#1a73e8;text-decoration:none;">Login here</a></div></div></body></html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


