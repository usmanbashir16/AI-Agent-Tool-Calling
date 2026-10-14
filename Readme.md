
<img width="1896" height="978" alt="image" src="https://github.com/user-attachments/assets/0a29368b-ddb1-4c8b-a80f-ab2e653066fc" />

<img width="1896" height="223" alt="image" src="https://github.com/user-attachments/assets/e7094467-41dc-4a75-b11b-9a23e36d4dcc" />

# AI Agent with Tool Calling & Semantic Memory

A tool-calling AI agent built with Python and Google's Gemini API. The project combines AI-powered conversations, external tools, persistent memory, semantic search, and a React-based web interface with a live agent activity log.

## Overview

This project demonstrates how an AI agent can understand user requests, select appropriate tools, execute actions, retrieve relevant saved memories, and generate responses based on tool results.

The application includes a Python backend, local databases for memory and conversation history, a vector search system, and a React frontend for interacting with the agent.

## Features

* **Gemini-Powered Conversations:** Generate responses using Google's Gemini API.
* **Tool Calling:** Allow the agent to select and execute supported tools based on user requests.
* **Persistent Memory:** Store memories and conversation history locally using SQLite.
* **Semantic Memory Search:** Retrieve relevant saved information using vector embeddings and ChromaDB.
* **Conversation Retrieval:** Search previous conversation information using the project's existing retrieval tools.
* **Web Search:** Retrieve web search results through the configured search tool.
* **Weather Tool:** Access weather information through the configured weather integration.
* **Live Activity Log:** Observe agent processing steps, tool selection, arguments, and execution events.
* **Streaming API:** Send agent activity events to the frontend using Server-Sent Events (SSE).
* **Interactive Web Interface:** Chat with the agent through a React and Vite frontend.

## Tech Stack

| Component            | Technology            |
| -------------------- | --------------------- |
| Programming Language | Python                |
| AI Model             | Google Gemini API     |
| Backend API          | FastAPI               |
| API Server           | Uvicorn               |
| Relational Database  | SQLite                |
| Vector Database      | ChromaDB              |
| Embeddings           | Sentence Transformers |
| Web Search           | DDGS                  |
| Frontend             | React                 |
| Frontend Build Tool  | Vite                  |
| Frontend Language    | JavaScript            |
| Version Control      | Git and GitHub        |

## Project Structure

```text
ai-agent-tool-calling/
│
├── main.py                 # Agent logic and tool execution
├── api.py                  # FastAPI backend and streaming endpoint
├── vector_memory.py        # Vector memory and retrieval utilities
├── weather_tool.py         # Weather search integration
├── web_search_tool.py      # Web search integration
├── check_history.py        # Conversation history utility
├── test_conversation_search.py
│
├── frontend/               # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.jsx
│   ├── package.json
│   └── package-lock.json
│
├── .env.example            # Environment variable template
├── .gitignore              # Excludes secrets and local data
├── requirements.txt        # Python dependencies
└── README.md
```

**Local-only files:** `.env`, `memory.db`, and `chroma_db/` are created or maintained locally and should not be committed to the repository.

## Prerequisites

Install these tools before setting up the project:

* Python 3.12
* Node.js and npm
* Git
* A Google Gemini API key

You can obtain a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).

## Installation and Setup

### 1. Clone the Repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd ai-agent-tool-calling
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with the HTTPS URL of this GitHub repository.

### 2. Create a Python Virtual Environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script activation, use the Python executable at `.venv\Scripts\python.exe` directly or adjust your local execution policy as appropriate.

### 3. Install Python Dependencies

From the project root:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create your local `.env` file from the example template:

```powershell
Copy-Item .env.example .env
```

Open `.env` and add your own Gemini API key:

```dotenv
GEMINI_API_KEY=your_own_gemini_api_key
```

Use your own key and keep the `.env` file private. Never commit API keys or other credentials to GitHub.

### 5. Start the Backend

From the project root, activate your Python environment and run:

```powershell
python -m uvicorn api:app --reload
```

The backend should be available at:

* **API base URL:** http://127.0.0.1:8000
* **Health check:** http://127.0.0.1:8000/health
* **Interactive API documentation:** http://127.0.0.1:8000/docs

Keep this terminal open while using the frontend.

### 6. Install Frontend Dependencies

Open a second terminal and navigate to the frontend directory:

```powershell
cd frontend
npm install
```

### 7. Start the Frontend

Run:

```powershell
npm run dev
```

Open the local URL displayed by Vite, usually:

http://localhost:5173

You can now send messages to the AI agent and view its activity events in the web interface.

## How It Works

1. **User Input:** A user submits a message through the React frontend.
2. **API Request:** The frontend sends the message to the FastAPI backend.
3. **Agent Processing:** The backend passes the message to the Gemini-powered agent.
4. **Tool Selection:** When appropriate, the model selects a supported tool and provides its arguments.
5. **Tool Execution:** The backend executes the selected tool and returns its result to the agent.
6. **Memory Retrieval:** Memory-related requests can retrieve relevant information from the configured local memory and vector search system.
7. **Response Generation:** The agent uses the available information to generate a final response.
8. **Activity Streaming:** Agent activity events are streamed to the frontend and displayed in the activity log.

## Local Data and Database Initialization

The application uses local storage for conversation history and saved memories.

* **SQLite:** Stores persistent application data, including conversation history and memories, according to the existing implementation.
* **ChromaDB:** Stores vector representations used by the configured semantic retrieval system.
* **Embedding Model:** Sentence Transformers provides embeddings for semantic search.

The database files are intentionally excluded from GitHub to keep personal data separate between developers.

When setting up a fresh clone, run the application using the steps above. The project's initialization and synchronization functions should create or prepare the required local data stores.

If the current implementation expects existing database files or requires a separate ingestion step, complete that step before testing the related functionality.

## Security and Privacy

The following files and directories must remain local:

```text
.env
memory.db
chroma_db/
```

The repository's `.gitignore` excludes environment secrets, local databases, Python virtual environments, frontend dependencies, and generated files.

Each developer is responsible for configuring their own API key and maintaining their own local conversation history and memory data.

**Never upload real API keys, credentials, private conversations, or personal database files to a public repository.**

## Troubleshooting

### Backend does not start

* Confirm that the Python virtual environment is activated.
* Install dependencies using `pip install -r requirements.txt`.
* Confirm that `.env` exists and contains a valid Gemini API key.
* Check the backend terminal for initialization or model errors.

### Frontend cannot connect to the backend

* Confirm that the FastAPI server is running on port `8000`.
* Open http://127.0.0.1:8000/health to check backend availability.
* Confirm that the frontend is using the expected API URL.
* Check the browser console for CORS or network errors.

### Semantic search returns no relevant memories

* Confirm that the local SQLite and ChromaDB stores have been initialized.
* Check whether relevant memories have actually been saved or indexed.
* Confirm that the embedding model can load successfully.
* Review the agent's retrieval tool and its execution logs.

### Frontend dependencies are missing

From the `frontend` directory, run:

```powershell
npm install
npm run dev
```

## Future Improvements

* Add automated tests for agent tools and memory retrieval.
* Improve visibility into semantic search results and tool execution.
* Add structured logging and error handling.
* Improve conversation management and user experience.
* Add deployment configuration and production security controls.

## License

No license has been specified yet. Unless a license is added to the repository, do not assume that others have permission to reuse, modify, or redistribute this project's code.
