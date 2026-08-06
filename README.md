# 📋 Task Manager (Dockerized)

A full-stack **Task Manager** application built with **Flask** and **SQLite**, containerized with **Docker Compose**. Features user authentication, boards, lists, cards (tasks), checklists, labels, and attachments — plus a live **API request logger** for monitoring all incoming requests.

## ✨ Features

- 🔐 **User authentication** — register, login, logout (bcrypt + SHA-256 password support)
- 🗂️ **Boards** — create, edit, delete boards (owners can assign boards to other users)
- 📝 **Lists & Cards** — add lists, add/move/delete cards (tasks) with descriptions
- ✅ **Checklists** — task-level checklist items with checked state
- 🏷️ **Labels** — attach/remove labels to tasks
- 📎 **Attachments** — file uploads per task
- 📡 **Request Logger** — every incoming request (method, path, IP, username, timestamp) is recorded and viewable via `GET /api/requests`
- 🐳 **Dockerized** — 3-container architecture (backend, frontend reverse-proxy, shared DB volume)

## 🛠️ Tech Stack

| Layer      | Technology                          |
|------------|-------------------------------------|
| Backend    | Python 3.9, Flask, SQLite, bcrypt   |
| Frontend   | HTML, CSS, JavaScript (nginx served)|
| Database   | SQLite (shared `./data` volume)     |
| Infra      | Docker, Docker Compose              |
| API Client | Postman collection included         |

## 🏗️ Architecture

```
User ──▶ frontend (nginx :8080) ──▶ backend (Flask :5000) ──▶ SQLite (./data)
```

- **backend** — Flask app, port `5000`
- **frontend** — nginx reverse-proxy, port `8080` (main entry point)
- **database** — Alpine container sharing the `./data` volume

## 🚀 Run with Docker

```bash
docker compose up -d --build
```

Then open:

- App: **http://localhost:8080**
- Backend API: **http://localhost:5000**

### Default Admin Account

| Username | Password   |
|----------|------------|
| `admin`  | `admin123` |

> New users can register from the login page.

## 🔌 API Endpoints

| Method | Endpoint              | Description                          |
|--------|-----------------------|--------------------------------------|
| POST   | `/api/login`          | Login (form data)                    |
| POST   | `/api/register`       | Register user (form data)            |
| GET    | `/api/boards`         | List all boards                      |
| POST   | `/api/create_board`   | Create board (JSON)                  |
| GET    | `/api/boards/<id>`    | Board detail (board + lists + tasks) |
| POST   | `/api/edit_board`     | Edit board (JSON)                    |
| DELETE | `/api/delete_board/<id>` | Delete board                      |
| POST   | `/api/add_list`       | Add list to board (JSON)             |
| DELETE | `/api/delete_list/<id>` | Delete list                        |
| POST   | `/api/add_card`       | Add task/card to list (JSON)         |
| POST   | `/api/edit_task`      | Edit task (JSON)                     |
| DELETE | `/api/delete_task/<id>` | Delete task                        |
| POST   | `/api/move_task`      | Move task between lists (JSON)       |
| POST   | `/api/add_checklist_item` | Add checklist item (JSON)         |
| POST   | `/api/upload_attachment` | Upload file attachment           |
| GET    | `/api/requests`       | View last 50 logged requests         |

A full **Postman collection** (`TaskManager_API.postman_collection.json`) is included — 8 folders covering auth, boards, lists & cards, checklists, labels, attachments, edit/delete, and the request logger.

## 📸 Screenshots

*(Add screenshots here — login page, boards grid, board view with lists/cards, request logs in Postman.)*

## 📂 Project Structure

```
├── backend/
│   ├── app.py              # Flask application
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── nginx.conf          # Reverse-proxy config
│   └── Dockerfile
├── data/                   # SQLite DB (gitignored)
├── docker-compose.yml
└── TaskManager_API.postman_collection.json
```

## 👤 Author

**[M Usama](https://github.com/musama745-dev)** — Python / Flask / Docker developer.
