<img width="1907" height="987" alt="image" src="https://github.com/user-attachments/assets/8812f997-4843-459d-a474-e8e2b0790b9c" />

# AI Agent Tool Calling

An AI-powered assistant built with **Google Gemini, Python, FastAPI, React, MCP, SQLite, and ChromaDB**. The project demonstrates how an AI agent can use tools, retrieve information, maintain conversation history, and interact through a web-based chat interface.

## Overview

This project implements a tool-calling AI agent that can process user queries, select relevant tools, and return responses based on the available information. It combines an LLM with external tools, persistent storage, and vector-based retrieval to provide a practical foundation for building AI agents.

The application includes a React frontend, a FastAPI backend, a Gemini-powered agent, an MCP server for web search, and storage for conversations and memories.

## Features

* **LLM-powered Agent:** Uses Google Gemini to understand user requests and generate responses.
* **Tool Calling:** Allows the agent to invoke available tools when required.
* **MCP Web Search:** Connects to a local Model Context Protocol (MCP) server for web search.
* **Persistent Conversations:** Stores conversations and messages in SQLite so they remain available after restarting the application.
* **Conversation Sidebar:** Create new conversations, browse previous chats, and continue existing conversations.
* **Vector Memory:** Uses ChromaDB and sentence embeddings for semantic memory and conversation retrieval.
* **Memory Management:** Stores and retrieves useful information through the agent's memory tools.
* **Real-Time Activity Log:** Displays agent activity and tool-related events through Server-Sent Events (SSE).
* **Backend Connection Status:** Shows whether the frontend can connect to the FastAPI backend.
* **Additional Tools:** Includes utilities such as calculation, date and time, weather, and text analysis, depending on the configured tools.

## Technology Stack

| Component           | Technology                   |
| ------------------- | ---------------------------- |
| Language            | Python                       |
| AI Model            | Google Gemini                |
| Backend API         | FastAPI                      |
| Frontend            | React, Vite, CSS             |
| Tool Integration    | Model Context Protocol (MCP) |
| Relational Database | SQLite                       |
| Vector Database     | ChromaDB                     |
| Embeddings          | Sentence Transformers        |
| Web Search          | DuckDuckGo Search (`ddgs`)   |
| Streaming           | Server-Sent Events (SSE)     |
| Version Control     | Git and GitHub               |

## Architecture

```text
User
 │
 ▼
React + Vite Frontend
 ├── Chat Interface
 ├── Conversation Sidebar
 ├── Backend Status
 └── Live Activity Log
 │
 ▼
FastAPI Backend
 │
 ▼
Gemini-Powered AI Agent
 ├── Tool Calling
 ├── MCP Web Search
 ├── Calculation & Utilities
 ├── Memory Retrieval
 └── Conversation Context
 │
 ├──────────────► SQLite
 │                 ├── Conversations
 │                 ├── Chat History
 │                 └── Memories
 │
 └──────────────► ChromaDB
                   ├── Vector Memories
                   └── Conversation Retrieval
```

## Project Structure

```text
ai-agent-tool-calling/
│
├── frontend/
│   ├── frontend/          # Vite application, if using the current nested setup
│   │   ├── src/
│   │   │   ├── App.jsx
│   │   │   └── App.css
│   │   ├── package.json
│   │   └── index.html
│   └── ...
│
├── api.py                 # FastAPI endpoints and SSE streaming
├── main.py                # Gemini agent and tool-calling logic
├── mcp_server.py          # Local MCP server and web-search tool
├── test_mcp_client.py     # MCP client testing
├── vector_memory.py       # ChromaDB and vector retrieval
├── memory.db              # SQLite database (generated locally)
├── chroma_db/             # Persistent vector database (generated locally)
├── .env                   # API keys and environment variables
├── .gitignore
├── requirements.txt
└── README.md
```

*Note: Adjust the structure above if your actual filenames or frontend folder layout differ.*

## Prerequisites

Before running the project, install:

* Python 3.12 or a compatible version
* Node.js and npm
* Git
* A Google Gemini API key
* Internet access for web search and model requests

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/usmanbashir16/AI-Agent-Tool-Calling.git
cd AI-Agent-Tool-Calling
```

### 2. Create and activate a Python virtual environment

**Windows PowerShell:**

```powershell
python -m venv ai-env
.\ai-env\Scripts\Activate.ps1
```

If PowerShell blocks script execution, use an appropriate execution-policy setting for your environment or activate the environment through your preferred terminal.

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root and add your Gemini API key using the variable name expected by your application.

For example:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Replace the placeholder with your own API key. Never commit your actual `.env` file or API key to GitHub.

### 5. Start the MCP server

Open a terminal in the project root and run the MCP server using the command configured for your project.

For example:

```powershell
python mcp_server.py
```

If your application launches the MCP server automatically through a subprocess, follow the startup flow implemented in `main.py` instead of launching a duplicate instance.

### 6. Start the FastAPI backend

Open another terminal in the project root, activate the virtual environment, and run:

```powershell
uvicorn api:app --reload
```

The API should be available at:

* API base URL: `http://127.0.0.1:8000`
* Interactive API documentation: `http://127.0.0.1:8000/docs`
* Health check: `http://127.0.0.1:8000/health`

### 7. Start the React frontend

Open a separate terminal in the directory containing the frontend's actual `package.json`.

```bash
npm install
npm run dev
```

Open the local URL printed by Vite, usually:

`http://localhost:5173`

If your Vite application is inside `frontend/frontend`, run these commands from that nested directory.

## How It Works

1. The user submits a message through the React chat interface.
2. The frontend sends the message and conversation ID to the FastAPI backend.
3. The backend loads the relevant conversation history from SQLite.
4. Gemini interprets the request and decides whether a tool is needed.
5. The agent invokes available tools, including the configured MCP web-search tool.
6. Tool results are passed back to the model to generate a response.
7. The backend streams activity events to the frontend using SSE.
8. The user message and final assistant response are saved in SQLite.
9. ChromaDB supports semantic retrieval of stored memories and conversation content.

## Databases and Persistence

**SQLite** stores structured application data, including conversations, chat messages, and memories.

**ChromaDB** stores vector representations used for semantic similarity search and retrieval.

Both databases are persisted locally. The SQLite database and ChromaDB directory are generated or updated as the application runs; they should not be committed to the repository unless intentionally sharing test data.

## Security Notes

* Keep API keys in environment variables.
* Add `.env` to `.gitignore`.
* Exclude the virtual environment, local databases, and generated cache files from version control.
* Never publish private conversation data or production credentials.
* Add authentication and appropriate access controls before exposing the backend publicly.

## Current Scope

This project is intended as a practical learning and development project for understanding:

* LLM tool calling and agent workflows
* MCP-based tool integration
* REST APIs and streaming responses
* Persistent conversation management
* Relational and vector databases
* Semantic search and memory retrieval
* React frontend and Python backend integration

## Future Improvements

* Add user authentication and conversation ownership.
* Improve structured tool-event streaming and error handling.
* Add configurable model and tool settings.
* Implement conversation deletion and renaming.
* Improve memory relevance and retrieval filtering.
* Add automated tests and deployment configuration.

## Author

**Muhammad Usman Bashir**

GitHub: [@usmanbashir16](https://github.com/usmanbashir16)

---

*Built to explore practical AI agents, tool calling, MCP integration, and persistent conversational memory.*
