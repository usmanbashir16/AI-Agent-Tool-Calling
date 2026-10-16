<img width="1917" height="983" alt="image" src="https://github.com/user-attachments/assets/1c418dc2-7af5-4d0a-a1f4-116c5f3f8a34" />

# AI Agent Tool Calling — RAG & MCP

An AI-powered question-answering application that combines **Google Gemini, MCP tool integration, PDF Retrieval-Augmented Generation (RAG), FastAPI, React, ChromaDB, and SQLite**.

The project enables an AI agent to answer questions using relevant information retrieved from indexed PDF documents and external web search tools. It also provides a web-based chat interface for interacting with the agent.

## Overview

The project demonstrates how an AI agent can use external tools instead of relying only on its language model's existing knowledge.

The system brings together:

- **LLM-based Agent:** Uses Google Gemini to understand user questions and generate responses.
- **MCP Integration:** Connects the agent with tools through the Model Context Protocol.
- **MCP Web Search:** Enables web search for questions that require information from external sources.
- **MCP-Based RAG Document Search:** Exposes PDF document retrieval as an MCP tool, allowing the agent to search indexed documents and retrieve relevant text.
- **PDF RAG Pipeline:** Extracts, chunks, embeds, and indexes PDF content for retrieval.
- **Hybrid Retrieval:** Combines semantic similarity and BM25 keyword retrieval, with Reciprocal Rank Fusion (RRF) to combine ranked results.
- **Persistent Storage:** Uses ChromaDB for vector-based document retrieval and SQLite for conversation persistence.
- **Web Interface:** Provides a React-based frontend connected to a FastAPI backend.

## Key Features

### 1. AI Agent and Tool Calling

The application uses Google Gemini to interpret user questions and generate responses. The agent can call available tools when additional information is required.

Depending on the question and the implemented tool-calling workflow, the agent can retrieve relevant information from indexed PDF documents or external web search results.

### 2. MCP Integration

The Model Context Protocol (MCP) provides a standardized way for an AI application to interact with tools.

In this project, MCP connects the agent with the following capabilities:

- **Web Search Tool:** Searches the web for relevant external information.
- **PDF Document Search Tool:** Connects the agent to the RAG retrieval pipeline for searching indexed PDF documents.

The document-search tool, `search_pdf_documents`, accepts a query and an optional `top_k` parameter, then delegates retrieval to the underlying `search_documents()` function.

MCP acts as the tool integration protocol, while document retrieval and web search perform the actual search operations.

### 3. PDF RAG Pipeline

The Retrieval-Augmented Generation (RAG) pipeline allows the application to retrieve relevant information from indexed PDF documents and make that context available to the AI agent.

The pipeline includes:

1. **PDF Text Extraction:** Extracts available text from PDF documents.
2. **Text Chunking:** Divides extracted text into smaller sections for retrieval.
3. **Embedding Generation:** Converts text chunks into numerical representations using the `all-MiniLM-L6-v2` embedding model.
4. **Vector Storage:** Stores document chunks, embeddings, and associated metadata in ChromaDB.
5. **Relevant Context Retrieval:** Searches indexed content to identify passages related to a user's question.
6. **Agent Response Generation:** Makes retrieved information available to the agent to support its answer.

The RAG retrieval functionality is exposed through an MCP tool, enabling the agent to access document search through the tool-calling workflow.

### 4. Hybrid Document Retrieval

The document retrieval module combines two complementary retrieval approaches:

- **Semantic Search:** Finds content based on similarity in meaning.
- **BM25 Keyword Search:** Finds content based on keyword relevance.
- **Reciprocal Rank Fusion (RRF):** Combines ranked results from the retrieval methods into a unified ranking.

This approach helps retrieve relevant passages by considering both semantic similarity and keyword matches.

### 5. Persistent Conversation Storage

SQLite is used to maintain conversation-related data across sessions. ChromaDB provides persistent storage for vector-based document retrieval and associated document data.

This separates conversation persistence from document retrieval.

### 6. FastAPI Backend

FastAPI provides the backend interface between the React frontend and the AI agent.

The application includes API endpoints for health checks, conversation management, message retrieval, and streaming chat responses.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/conversations` | Retrieve conversations |
| POST | `/conversations` | Create a conversation |
| GET | `/conversations/{id}/messages` | Retrieve conversation messages |
| POST | `/chat/stream` | Stream chat responses using Server-Sent Events (SSE) |

### 7. React Frontend

The frontend is built with React and Vite. It provides a browser-based interface for interacting with the AI agent through the backend API.

The frontend and backend run as separate development processes.

## Technology Stack

| Category | Technologies |
|---|---|
| Programming Languages | Python, JavaScript |
| Large Language Model | Google Gemini |
| AI Agent and Tool Calling | Gemini tool calling |
| Tool Integration Protocol | Model Context Protocol (MCP) |
| Retrieval-Augmented Generation | RAG |
| Backend API | FastAPI, Uvicorn |
| Frontend | React, Vite, CSS |
| PDF Processing | pypdf |
| Embeddings | Sentence Transformers, `all-MiniLM-L6-v2` |
| Vector Database | ChromaDB |
| Conversation Database | SQLite |
| Retrieval Techniques | Semantic Search, BM25, Reciprocal Rank Fusion (RRF) |
| Web Search | DDGS-based search integration |
| Environment Configuration | python-dotenv |

## Project Structure

```text
ai-agent-tool-calling/
│
├── api.py
├── main.py
├── mcp_server.py
├── requirements.txt
├── .env.example
├── .gitignore
│
├── rag/
│   ├── __init__.py
│   ├── ingest.py
│   └── retriever.py
│
├── frontend/
│   ├── package.json
│   ├── index.html
│   └── src/
│       ├── App.jsx
│       └── App.css
│
└── chroma_db/
```

*Note: `chroma_db/` contains generated local storage and should not be committed to Git. The exact files in the repository may vary as development continues.*

### Main Components

- `main.py` — Contains the agent's execution and tool-calling workflow.
- `mcp_server.py` — Defines the MCP server and available tools, including PDF document search.
- `api.py` — Provides FastAPI endpoints and connects the frontend to the backend.
- `rag/ingest.py` — Handles PDF text extraction, chunking, and document ingestion.
- `rag/retriever.py` — Implements document retrieval and hybrid ranking.
- `frontend/src/App.jsx` — React application interface.
- `frontend/src/App.css` — Frontend styling.
- `chroma_db/` — Local persistent ChromaDB data.

## Prerequisites

Install the following before running the project:

- Python 3.12 or a compatible Python version
- Node.js and npm
- A Google Gemini API key
- Git

## Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/usmanbashir16/AI-Agent-Tool-Calling.git
cd AI-Agent-Tool-Calling
```

### 2. Create and Activate a Python Virtual Environment

On Windows PowerShell:

```powershell
python -m venv ai-env
.\ai-env\Scripts\Activate.ps1
```

If the virtual environment already exists, activate it rather than creating another one.

### 3. Install Python Dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root and add your Gemini API key:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Use your own API key. Never commit `.env` or expose API keys in source code or public repositories.

### 5. Start the Backend

From the project root, with the virtual environment activated:

```bash
python -m uvicorn api:app --reload
```

The backend will normally be available at:

`http://127.0.0.1:8000`

FastAPI's interactive API documentation is normally available at:

`http://127.0.0.1:8000/docs`

### 6. Start the Frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually:

`http://localhost:5173`

Keep both the backend and frontend terminals running while testing the application.

## Document Ingestion and Retrieval

PDF documents must be ingested into the document collection before they can be searched through the RAG pipeline.

The general workflow is:

```text
PDF Document
     |
     v
Text Extraction
     |
     v
Text Chunking
     |
     v
Embedding Generation
     |
     v
ChromaDB Storage
     |
     v
User Question
     |
     v
Gemini AI Agent
     |
     v
MCP Tool: search_pdf_documents
     |
     v
Hybrid Document Retrieval
(Semantic Search + BM25 + RRF)
     |
     v
Relevant Document Passages
     |
     v
Agent Response
```

The ingestion process prepares PDF content for retrieval. During question answering, the agent can use the MCP document-search tool to retrieve relevant passages from the indexed documents.

## Security and Repository Hygiene

The project uses `.gitignore` rules to exclude local and sensitive files, including:

- `.env` files and API secrets
- Python virtual environments
- Generated Python cache files
- Local ChromaDB data
- SQLite databases and related local data
- Frontend dependencies and build output

Review `.gitignore` before committing new files to ensure that credentials, private documents, and generated local data are not accidentally uploaded.

## Current Scope

The project combines LLM-based tool calling, MCP integration, PDF document retrieval through RAG, hybrid search, persistent storage, and a web interface.

It demonstrates how an AI agent can access both indexed document content and external web search through a tool-based architecture.

## Future Improvements

Potential future enhancements include:

- Improved source citations and page-level references in generated answers
- Authentication and user-level access controls
- More comprehensive retrieval evaluation
- OCR support for scanned PDFs
- Deployment and production monitoring
- Expanded automated testing

These are potential enhancements, not claims that all of them are currently implemented.

## Author

**Muhammad Usman Bashir**

GitHub: [usmanbashir16](https://github.com/usmanbashir16)

Repository: [AI-Agent-Tool-Calling](https://github.com/usmanbashir16/AI-Agent-Tool-Calling)
