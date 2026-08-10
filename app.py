from flask import Flask, render_template_string, request, redirect, url_for, flash, session, jsonify
from supabase import create_client, Client
import hashlib
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', '') or 'task_manager_secret_key_12345'

# ============ SUPABASE SETUP ============
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

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
    supabase.table('boards').insert({
        'name': name,
        'description': data.get('description'),
        'owner_id': session['user_id']
    }).execute()
    return jsonify({'success': True})

@app.route('/board/<int:board_id>')
def board_view(board_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    board_data = supabase.table('boards').select('*').eq('id', board_id).eq('owner_id', session['user_id']).execute().data
    if not board_data: return redirect(url_for('boards_page'))
    board = board_data[0]
    lists = supabase.table('board_lists').select('*').eq('board_id', board_id).order('position').execute().data
    # Get tasks with user info
    tasks_raw = supabase.table('tasks').select('*, users(username)').eq('board_id', board_id).order('position').execute().data
    tasks = []
    for t in tasks_raw:
        user_info = t.pop('users', None)
        t['users_username'] = user_info['username'] if user_info else ''
        tasks.append(t)
    # Batch fetch checklists, labels, attachments
    task_ids = [t['id'] for t in tasks]
    checklists = {tid: [] for tid in task_ids}
    labels_by_task = {tid: [] for tid in task_ids}
    attachments_by_task = {tid: [] for tid in task_ids}
    if task_ids:
        all_cl = supabase.table('checklists').select('*').in_('task_id', task_ids).execute().data
        for cl in all_cl:
            checklists[cl['task_id']].append(cl)
        all_tl = supabase.table('task_labels').select('task_id, labels(*)').in_('task_id', task_ids).execute().data
        for tl in all_tl:
            label_info = tl.get('labels')
            if label_info:
                labels_by_task[tl['task_id']].append(label_info)
        all_att = supabase.table('attachments').select('*').in_('task_id', task_ids).order('uploaded_at', desc=True).execute().data
        for att in all_att:
            attachments_by_task[att['task_id']].append(att)
    all_labels = supabase.table('labels').select('*').execute().data
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
    result = supabase.table('board_lists').select('position').eq('board_id', board_id).order('position', desc=True).limit(1).execute().data
    max_pos = result[0]['position'] if result else 0
    supabase.table('board_lists').insert({
        'board_id': board_id,
        'name': name,
        'position': max_pos + 1
    }).execute()
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

# ============ AUTH ROUTES ============

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
            existing = supabase.table('users').select('*').eq('username', username).execute().data
            if existing: flash('Username already taken!', 'error')
            else:
                supabase.table('users').insert({
                    'username': username,
                    'password': hashlib.sha256(password.encode()).hexdigest()
                }).execute()
                flash('Account created! Please login.', 'success')
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