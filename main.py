import asyncio
import uuid
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from ddgs import DDGS
from dotenv import load_dotenv
from google import genai
from google.genai import types
from weather_tool import get_weather
from vector_memory import (
    save_vector_memory,
    delete_vector_memory,
    search_vector_memories,
    sync_sqlite_memories,
    sync_sqlite_conversations,
    search_vector_conversations,
)


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "memory.db"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is missing. Check your .env file."
    )

client = genai.Client(api_key=API_KEY)
conversation_history = []


# =========================================================
# DATABASE
# =========================================================

def web_search(query, max_results=5):
    """Search the web and return a list of useful results."""

    if not query or not query.strip():
        return {"error": "Search query cannot be empty."}

    try:
        max_results = max(1, min(int(max_results), 10))

        with DDGS() as ddgs:
            results = list(
                ddgs.text(
                    query.strip(),
                    max_results=max_results,
                )
            )

        if not results:
            return {"query": query, "results": [], "message": "No results found."}

        return {
            "query": query,
            "results": [
                {
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                }
                for item in results
            ],
        }

    except Exception as error:
        return {"error": f"Web search failed: {error}"}


def initialize_database():
    """Create and safely migrate the SQLite database."""

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Existing long-term memories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_key TEXT PRIMARY KEY,
                memory_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # One record for each conversation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Preserve the existing message table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Add conversation_id to an existing database if needed
        columns = {
            row[1]
            for row in cursor.execute(
                "PRAGMA table_info(conversation_history)"
            ).fetchall()
        }

        if "conversation_id" not in columns:
            cursor.execute("""
                ALTER TABLE conversation_history
                ADD COLUMN conversation_id TEXT
            """)

        # Keep old messages together as one legacy conversation
        old_messages = cursor.execute("""
            SELECT id, role, content, created_at
            FROM conversation_history
            WHERE conversation_id IS NULL
            ORDER BY id ASC
        """).fetchall()

        if old_messages:
            legacy_id = str(uuid.uuid4())
            created_at = old_messages[0][3]
            updated_at = old_messages[-1][3]

            # Generate a readable title from the first user message
            first_user_message = next(
                (
                    row[2]
                    for row in old_messages
                    if row[1] == "user"
                ),
                "Previous conversation",
            )

            title = " ".join(first_user_message.split())[:60]
            if not title:
                title = "Previous conversation"

            cursor.execute("""
                INSERT INTO conversations (
                    id, title, created_at, updated_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                legacy_id,
                title,
                created_at,
                updated_at,
            ))

            cursor.execute("""
                UPDATE conversation_history
                SET conversation_id = ?
                WHERE conversation_id IS NULL
            """, (legacy_id,))

        conn.commit()

    print("Database initialized successfully.")
    print("Database file:", DB_PATH)
    print("Tables ready: memories, conversations, conversation_history")
# =========================================================
# MCP CLIENT
# =========================================================

MCP_SERVER_PATH = BASE_DIR / "mcp_server.py"


async def call_mcp_tool_async(name, arguments):
    """Connect to the local MCP server and execute a tool."""

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(MCP_SERVER_PATH)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Discover the tools exposed by the MCP server.
            available_tools = await session.list_tools()
            tool_names = {tool.name for tool in available_tools.tools}

            if name not in tool_names:
                return {
                    "error": f"MCP tool '{name}' was not found.",
                    "available_tools": sorted(tool_names),
                }

            result = await session.call_tool(
                name,
                arguments=arguments,
            )

            content = [
                item.text
                for item in result.content
                if hasattr(item, "text")
            ]

            if result.isError:
                return {
                    "error": "\n".join(content) or "MCP tool failed."
                }

            return "\n".join(content)


def call_mcp_tool(name, arguments):
    """Synchronous bridge for the existing Gemini agent."""

    return asyncio.run(call_mcp_tool_async(name, arguments))

# =========================================================
# CALCULATOR
# =========================================================

def calculate(operation, a, b):
    a = float(a)
    b = float(b)

    if operation == "add":
        return a + b
    if operation == "subtract":
        return a - b
    if operation == "multiply":
        return a * b
    if operation == "divide":
        if b == 0:
            return "Error: Cannot divide by zero."
        return a / b
    if operation == "percentage":
        return (a * b) / 100

    return "Error: Unsupported operation."


# =========================================================
# DATE AND TIME
# =========================================================

def get_current_datetime():
    return datetime.now().astimezone().isoformat(
        timespec="seconds"
    )


# =========================================================
# TEXT ANALYZER
# =========================================================

def analyze_text(text):
    return {
        "characters": len(text),
        "characters_without_spaces": len(text.replace(" ", "")),
        "words": len(text.split()),
        "uppercase": text.upper(),
        "lowercase": text.lower(),
    }


# =========================================================
# SAVE / UPDATE MEMORY
# =========================================================

def save_memory(key, value):
    key = normalize_key(key)
    value = str(value).strip()

    if not key or not value:
        return "Error: Memory key and value cannot be empty."

    updated_at = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    # Save to SQLite first.
    with sqlite3.connect(str(DB_PATH)) as connection:
        connection.execute("""
            INSERT INTO memories (
                memory_key, memory_value, updated_at
            )
            VALUES (?, ?, ?)
            ON CONFLICT(memory_key)
            DO UPDATE SET
                memory_value = excluded.memory_value,
                updated_at = excluded.updated_at
        """, (key, value, updated_at))

    # Then update ChromaDB.
    try:
        save_vector_memory(key, value)
    except Exception as error:
        return (
            f"Memory saved to SQLite: {key} = {value}, "
            f"but ChromaDB update failed: {error}. "
            "Run vector_memory.py to resynchronize."
        )

    return (
        f"Memory saved successfully: {key} = {value}. "
        "SQLite and ChromaDB updated."
    )


# =========================================================
# GET MEMORY
# =========================================================

def get_memory(key):
    key = normalize_key(key)

    with sqlite3.connect(str(DB_PATH)) as connection:
        row = connection.execute("""
            SELECT memory_key, memory_value, updated_at
            FROM memories
            WHERE memory_key = ?
        """, (key,)).fetchone()

    if row is None:
        return f"No exact memory found for key: {key}"

    return {
        "key": row[0],
        "value": row[1],
        "updated_at": row[2],
    }


# =========================================================
# LIST MEMORIES
# =========================================================

def list_memories():
    with sqlite3.connect(str(DB_PATH)) as connection:
        rows = connection.execute("""
            SELECT memory_key, memory_value, updated_at
            FROM memories
            ORDER BY memory_key
        """).fetchall()

    return [
        {
            "key": row[0],
            "value": row[1],
            "updated_at": row[2],
        }
        for row in rows
    ]


# =========================================================
# KEYWORD SEARCH
# =========================================================

def search_memories(query):
    stop_words = {
        "the", "and", "for", "what", "which", "who",
        "when", "where", "how", "does", "did", "are",
        "was", "you", "your", "my", "me", "is", "do",
        "find", "search", "tell", "about", "from",
        "have", "has", "know", "remember", "please",
        "can", "could", "would", "like", "i", "a",
        "an", "to", "of", "in", "on",
    }

    query_words = {
        word.strip(".,!?;:'\"()[]{}").lower()
        for word in query.split()
    }
    query_words = {
        word for word in query_words
        if len(word) > 1 and word not in stop_words
    }

    if not query_words:
        return []

    ranked = []

    for memory in list_memories():
        searchable = (
            memory["key"].replace("_", " ")
            + " " + memory["value"]
        ).lower()

        memory_words = {
            word.strip(".,!?;:'\"()[]{}").lower()
            for word in searchable.split()
        }

        matches = query_words.intersection(memory_words)

        if matches:
            ranked.append({
                **memory,
                "matched_words": sorted(matches),
                "score": len(matches),
            })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:5]


# =========================================================
# SEMANTIC MEMORY SEARCH
# =========================================================

def semantic_memory_search(query):
    try:
        results = search_vector_memories(query, limit=3)

        if not results:
            return "No saved vector memories found."

        return results
    except Exception as error:
        return f"Semantic search failed: {error}"


# =========================================================
# DELETE MEMORY
# =========================================================

def delete_memory(key):
    """
    Delete a specific memory from SQLite and ChromaDB.
    SQLite is the primary source of truth.
    """
    key = normalize_key(key)

    with sqlite3.connect(str(DB_PATH)) as connection:
        cursor = connection.execute(
            "DELETE FROM memories WHERE memory_key = ?",
            (key,),
        )
        deleted_count = cursor.rowcount

    if deleted_count == 0:
        return f"No SQLite memory found for key: {key}"

    try:
        delete_vector_memory(key)
    except Exception as error:
        return (
            f"Memory '{key}' deleted from SQLite, but ChromaDB "
            f"deletion failed: {error}. Run vector_memory.py "
            "to synchronize and remove stale vector records."
        )

    return f"Memory '{key}' deleted from SQLite and ChromaDB."


# =========================================================
# GEMINI TOOL DECLARATIONS
# =========================================================



agent_tools = [
    {
        "function_declarations": [
            {
                "name": "calculate",
                "description": "Perform basic calculations.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "operation": {
                            "type": "STRING",
                            "enum": [
                                "add",
                                "subtract",
                                "multiply",
                                "divide",
                                "percentage",
                            ],
                        },
                        "a": {"type": "NUMBER"},
                        "b": {"type": "NUMBER"},
                    },
                    "required": ["operation", "a", "b"],
                },
            },
            {
                "name": "get_current_datetime",
                "description": "Get current local date and time.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
            {
                "name": "analyze_text",
                "description": "Analyze text and count words and characters.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "text": {"type": "STRING"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "save_memory",
                "description": (
                    "Save or update a memory permanently. Only do this "
                    "when the user explicitly asks to remember, save, "
                    "or update information."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "key": {"type": "STRING"},
                        "value": {"type": "STRING"},
                    },
                    "required": ["key", "value"],
                },
            },
            {
                "name": "get_memory",
                "description": "Retrieve a memory by its exact key.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "key": {"type": "STRING"},
                    },
                    "required": ["key"],
                },
            },
            {
                "name": "list_memories",
                "description": "List all saved long-term memories.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
            {
                "name": "search_memories",
                "description": "Search saved memories using keywords.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "semantic_memory_search",
                "description": (
                    "Search long-term memories by meaning, even if the "
                    "user uses different words from the stored memory."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "delete_memory",
                "description": (
                    "Delete a specific saved memory only when the user "
                    "explicitly asks to forget or delete that information. "
                    "Use its exact memory key. If the target is ambiguous, "
                    "ask the user which memory they mean."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "key": {"type": "STRING"},
                    },
                    "required": ["key"],
                },
            },
            {
                "name": "get_weather",
                "description": (
                    "Get current weather for a city using the weather API. "
                    "Returns temperature, feels-like temperature, humidity, "
                    "wind speed, precipitation, and weather conditions. "
                    "Use this tool when the user asks about current weather."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "city": {
                            "type": "STRING",
                            "description": (
                                "The city to check weather for, "
                                "such as Islamabad, Lahore, or Karachi."
                            ),
                        },
                    },
                    "required": ["city"],
                },
            },
            {
                "name": "search_conversations",
                "description": (
                    "Search the user's persistent conversation history "
                    "in SQLite. Use this tool when the user asks about "
                    "previous discussions, earlier questions, past answers, "
                    "or topics discussed in earlier conversations. "
                    "Search both user messages and assistant responses."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": (
                                "Keywords or topic to search for in past messages."
                            ),
                        },
                        "limit": {
                            "type": "INTEGER",
                            "description": (
                                "Maximum number of results, from 1 to 10."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "semantic_conversation_search",
                "description": (
                    "Search previous conversation history by semantic meaning. "
                    "Use this tool when the user asks about earlier discussions "
                    "but describes the topic using different words from the original "
                    "conversation. Prefer this tool when exact keyword matching may "
                    "miss relevant messages. Examples include asking about a feature "
                    "used to check city conditions when the original conversation "
                    "mentioned a weather tool. Do not use this tool for current weather."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": (
                                "The topic or question to search for in past conversations."
                            ),
                        },
                        "limit": {
                            "type": "INTEGER",
                            "description": (
                                "Maximum number of results to return, from 1 to 10."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "mcp_web_search",
                "description": (
                    "Search the web through the connected MCP server. "
                    "Use this tool when the user requests current web "
                    "information or online research."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": "The search query.",
                        },
                        "max_results": {
                            "type": "INTEGER",
                            "description": "Maximum results, from 1 to 5.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "search_pdf_documents",
                "description": (
                    "Search indexed PDF documents in ChromaDB for information "
                    "relevant to the user's question. Returns matching text "
                    "chunks with filenames and page numbers. Use this tool "
                    "when the user asks about uploaded PDF documents, "
                    "document contents, RFP requirements, compliance clauses, "
                    "or information from an indexed PDF."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": (
                                "The question or information to search for "
                                "in indexed PDF documents."
                            ),
                        },
                        "top_k": {
                            "type": "INTEGER",
                            "description": (
                                "Number of relevant text chunks to retrieve, "
                                "between 1 and 20."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            },
        ]
    }
]


def semantic_conversation_search(query, limit=5):
    """Search past conversations by meaning."""
    results = search_vector_conversations(query, limit=limit)

    if not results:
        return "No relevant previous conversations found."

    return results


# =========================================================
# TOOL EXECUTION
# =========================================================



def execute_tool(name, arguments):
    """Execute the tool selected by Gemini."""

    tools = {
        "calculate": lambda args: calculate(
            args["operation"], args["a"], args["b"]
        ),
        "get_current_datetime": lambda args: get_current_datetime(),
        "analyze_text": lambda args: analyze_text(args["text"]),
        "save_memory": lambda args: save_memory(
            args["key"], args["value"]
        ),
        "mcp_web_search": lambda args: call_mcp_tool(
        "web_search",
            {
                "query": args["query"],
                "max_results": max(
                    1, min(int(args.get("max_results", 5)), 5)
                ),
            },
        ),
        "search_pdf_documents": lambda args: call_mcp_tool(
            "search_pdf_documents",
            {
                "query": args["query"],
                "top_k": max(
                    1, min(int(args.get("top_k", 5)), 20)
                ),
            },
        ),
        
        "search_conversations": lambda args: search_conversations(
            args["query"],
            limit=max(1, min(int(args.get("limit", 5)), 10)),
        ),
        "semantic_conversation_search": lambda args: (
            semantic_conversation_search(
                args["query"],
                limit=max(1, min(int(args.get("limit", 5)), 10)),
            )
        ),
        "get_memory": lambda args: get_memory(args["key"]),
        "list_memories": lambda args: list_memories(),
        "search_memories": lambda args: search_memories(
            args["query"]
        ),
        "semantic_memory_search": lambda args: semantic_memory_search(
            args["query"]
        ),
        "delete_memory": lambda args: delete_memory(args["key"]),
        "get_weather": lambda args: get_weather(args["city"]),
        "web_search": lambda args: web_search(
            args["query"],
            max_results=max(
                1, min(int(args.get("max_results", 5)), 5)
            ),
        ),
    }

    tool = tools.get(name)

    if tool is None:
        return f"Unknown tool: {name}"

    try:
        return tool(arguments)
    except Exception as error:
        return f"Tool execution failed ({name}): {error}"


# =========================================================
# GEMINI AGENT LOOP
# =========================================================


def create_conversation(title="New conversation"):
    """Create a new persistent conversation."""
    conversation_id = str(uuid.uuid4())
    timestamp = datetime.now().astimezone().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (conversation_id, title, timestamp, timestamp),
        )

    return conversation_id


def list_conversations():
    """Return saved conversations, newest activity first."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                COUNT(h.id) AS message_count
            FROM conversations c
            LEFT JOIN conversation_history h
                ON h.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_conversation_messages(conversation_id):
    """Return the messages belonging to one conversation."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM conversation_history
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def save_chat_message(role, content, conversation_id):
    """Save a message and update its conversation metadata."""
    timestamp = datetime.now().astimezone().isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversation_history
                (role, content, created_at, conversation_id)
            VALUES (?, ?, ?, ?)
            """,
            (role, content, timestamp, conversation_id),
        )

        # Give a new conversation a title based on its first user message.
        if role == "user":
            row = conn.execute(
                "SELECT title FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()

            if row is not None:
                current_title = row[0]

                if current_title == "New conversation":
                    title = " ".join(content.split())[:60]
                    if not title:
                        title = "New conversation"

                    conn.execute(
                        """
                        UPDATE conversations
                        SET title = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (title, timestamp, conversation_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE conversations
                        SET updated_at = ?
                        WHERE id = ?
                        """,
                        (timestamp, conversation_id),
                    )
        else:
            conn.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE id = ?
                """,
                (timestamp, conversation_id),
            )


def load_recent_chat_history(conversation_id, limit=20):
    """Load recent messages for one conversation in chronological order."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM conversation_history
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()

    history = []

    for role, content in reversed(rows):
        history.append(
            types.Content(
                role="model" if role == "assistant" else role,
                parts=[types.Part.from_text(text=content)],
            )
        )

    return history



def search_conversations(query, limit=5):
    """Search saved conversations using keywords and relevance ranking."""

    import re

    query = query.strip().lower()

    if not query:
        return "Please provide a search query."

    # Split the query into useful words.
    query_words = set(re.findall(r"\w+", query))

    stop_words = {
        "the", "and", "for", "what", "which", "who",
        "when", "where", "how", "did", "does", "was",
        "were", "are", "is", "do", "my", "me", "you",
        "your", "we", "our", "i", "a", "an", "to",
        "of", "in", "on", "about", "tell", "find",
        "search", "please", "remember", "last", "time",
        "it", "this", "that", "with", "from", "earlier",
        "previous", "conversation", "conversations",
    }

    query_words -= stop_words

    if not query_words:
        return "Please provide a more specific search query."

    # Technical concepts and common alternative terms.
    synonyms = {
        "memory": {
            "memory", "memories", "conversation_history",
            "long-term", "persistent",
        },
        "conversation": {
            "conversation", "history", "messages", "chat",
            "conversation_history",
        },
        "semantic": {
            "semantic", "embeddings", "embedding", "vector",
            "chromadb",
        },
        "vector": {
            "vector", "chromadb", "embedding", "embeddings",
        },
        "database": {
            "database", "sqlite", "chromadb", "database",
        },
        "search": {
            "search", "retrieve", "retrieval", "query",
        },
        "implement": {
            "implement", "implemented", "building", "built",
            "created", "added", "developed",
        },
    }

    expanded_words = set(query_words)

    for word in query_words:
        if word in synonyms:
            expanded_words.update(synonyms[word])

    # Search messages containing any expanded keyword.
    conditions = " OR ".join(
        ["LOWER(content) LIKE ?" for _ in expanded_words]
    )

    parameters = [
        f"%{word}%"
        for word in expanded_words
    ]

    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            f"""
            SELECT id, role, content, created_at
            FROM conversation_history
            WHERE {conditions}
            ORDER BY id DESC
            """,
            parameters,
        ).fetchall()

    results = []

    for message_id, role, content, created_at in rows:
        content_lower = content.lower()

        matched_words = [
            word for word in expanded_words
            if word in content_lower
        ]

        # Base score: number of matched keywords.
        score = len(matched_words)

        # Reward messages matching the original query phrase.
        if query in content_lower:
            score += 5

        # Reward messages containing technical implementation terms.
        technical_terms = [
            "sqlite",
            "chromadb",
            "embedding",
            "conversation_history",
            "search_vector_conversations",
            "sync_sqlite_conversations",
            "semantic_conversation_search",
        ]

        technical_matches = [
            term for term in technical_terms
            if term in content_lower
        ]

        score += len(technical_matches) * 2

        results.append({
            "id": message_id,
            "role": role,
            "content": content,
            "created_at": created_at,
            "matched_words": matched_words,
            "technical_matches": technical_matches,
            "score": score,
        })

    # Sort by relevance first, then newest message.
    results.sort(
        key=lambda item: (item["score"], item["id"]),
        reverse=True,
    )

    limit = max(1, min(int(limit), 10))

    return results[:limit] if results else (
        "No relevant previous conversations found."
    )

    return results[:max(1, min(int(limit), 10))]
def semantic_conversation_search(query, limit=5):
    """Search past conversations by meaning."""
    results = search_vector_conversations(query, limit=limit)

    if not results:
        return "No relevant previous conversations found."

    return results


def emit_activity(activity_callback, event, message, details=None):
    """Send a real agent activity to the frontend when a callback exists."""

    if activity_callback is not None:
        try:
            activity_callback(event, message, details or {})
        except Exception as error:
            print(f"Activity callback error: {error}")




def run_agent(user_input, conversation_id, activity_callback=None):
    # Load history for this conversation
    history = load_recent_chat_history(conversation_id)

    # Save the user's message to this conversation
    save_chat_message("user", user_input, conversation_id)

    # Add the new message to the loaded history
    history.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)],
        )
    )

    emit_activity(
        activity_callback,
        "user_message",
        "Received user message.",
    )

    for step in range(15):
        emit_activity(
            activity_callback,
            "thinking",
            f"Agent processing step {step + 1}.",
        )

        response = None

        # Retry temporary Gemini errors
        for attempt in range(3):
            try:
                emit_activity(
                    activity_callback,
                    "gemini_request",
                    "Sending request to Gemini.",
                    {"attempt": attempt + 1},
                )

                response = client.models.generate_content(
                    model=MODEL,
                    contents=history,
                    config=types.GenerateContentConfig(
                        tools=agent_tools,
                        system_instruction=(
                            "You are a helpful AI agent with short-term "
                            "conversation context, persistent SQLite "
                            "conversation history, and persistent long-term "
                            "memory. Use tools when appropriate. "

                            "When the user asks about previous discussions, "
                            "earlier questions, past project work, decisions, "
                            "or information that may not be present in the "
                            "current conversation context, search saved "
                            "conversation history instead of guessing. "

                            "Choose semantic_conversation_search when the "
                            "user describes a past topic using different "
                            "wording or asks about its meaning. Choose "
                            "search_conversations when exact keywords or "
                            "phrases are available. Use retrieved results "
                            "to answer the question; do not simply list "
                            "search results unless asked. "

                            "For questions about saved personal information, "
                            "use semantic_memory_search if the wording differs "
                            "from stored memory. Use exact or keyword memory "
                            "search when appropriate. "

                            "Only claim knowledge of previous conversations "
                            "when supported by context or retrieved results. "
                            "If the results do not provide enough information, "
                            "say so. "

                            "Only save or delete information when explicitly "
                            "asked. Never claim a tool succeeded if its result "
                            "reports failure. If a memory deletion target is "
                            "ambiguous, ask for clarification."
                        ),
                    ),
                )

                emit_activity(
                    activity_callback,
                    "gemini_response",
                    "Gemini returned a response.",
                )

                break

            except Exception as error:
                error_text = str(error)

                temporary_error = (
                    "503" in error_text
                    or "UNAVAILABLE" in error_text.upper()
                )

                if temporary_error and attempt < 2:
                    wait_seconds = 2 ** (attempt + 1)

                    message = (
                        f"Gemini is busy. Retrying in "
                        f"{wait_seconds} seconds."
                    )

                    print(message)

                    emit_activity(
                        activity_callback,
                        "retry",
                        message,
                        {"attempt": attempt + 1},
                    )

                    time.sleep(wait_seconds)

                else:
                    emit_activity(
                        activity_callback,
                        "error",
                        "Gemini request failed.",
                        {"error": error_text},
                    )
                    raise

        if response is None:
            message = "Gemini request failed after retries."

            emit_activity(
                activity_callback,
                "error",
                message,
            )

            return message

        if not response.candidates:
            message = "Gemini returned no response."

            emit_activity(
                activity_callback,
                "error",
                message,
            )

            print("Agent: " + message)
            return message

        # IMPORTANT: Add the model response to the SAME history
        # that is passed to Gemini in the next iteration.
        model_content = response.candidates[0].content
        history.append(model_content)

        function_calls = [
            part.function_call
            for part in model_content.parts
            if part.function_call is not None
        ]

        # If there are no tool calls, return the final answer
        if not function_calls:
            assistant_reply = (
                response.text or "I couldn't generate a response."
            )

            # Store using "assistant"; ensure other code expects this role.
            save_chat_message(
                "assistant",
                assistant_reply,
                conversation_id,
            )

            emit_activity(
                activity_callback,
                "final_answer",
                "Agent generated the final answer.",
            )

            print("Agent: " + assistant_reply)
            return assistant_reply

        function_response_parts = []

        for call in function_calls:
            arguments = dict(call.args or {})

            print(f"\nTool selected: {call.name}")

            emit_activity(
                activity_callback,
                "tool_selected",
                f"Agent selected tool: {call.name}",
                {"tool": call.name},
            )

            print(f"Arguments: {arguments}")

            emit_activity(
                activity_callback,
                "tool_arguments",
                f"Arguments prepared for {call.name}.",
                {
                    "tool": call.name,
                    "arguments": arguments,
                },
            )

            try:
                result = execute_tool(call.name, arguments)

                print(f"Tool result: {result}")

                emit_activity(
                    activity_callback,
                    "tool_completed",
                    f"Tool completed: {call.name}",
                    {"tool": call.name},
                )

            except Exception as error:
                emit_activity(
                    activity_callback,
                    "tool_error",
                    f"Tool failed: {call.name}",
                    {
                        "tool": call.name,
                        "error": str(error),
                    },
                )

                # Return the error to Gemini so it can respond
                # instead of abruptly terminating the whole agent.
                result = {
                    "error": str(error),
                    "tool": call.name,
                }

            if isinstance(result, str):
                result_text = result
            else:
                result_text = json.dumps(
                    result,
                    ensure_ascii=False,
                    default=str,
                )

            function_response_parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    response={"result": result_text},
                )
            )

        # IMPORTANT: Add tool results to the SAME history.
        # Gemini needs these results to decide what to do next.
        history.append(
            types.Content(
                role="user",
                parts=function_response_parts,
            )
        )

    message = (
        "Maximum tool steps reached. The agent could not finish "
        "within 15 processing steps."
    )

    emit_activity(
        activity_callback,
        "error",
        message,
    )

    print("Agent: " + message)
    return message


# =========================================================
# MAIN
# =========================================================



def main():
    initialize_database()

    print("Synchronizing SQLite memories with ChromaDB...")
    try:
        sync_sqlite_memories()
        sync_sqlite_conversations()
    except Exception as error:
        print(f"Memory synchronization warning: {error}")

    try:
        conversation_history.clear()
        conversation_history.extend(
            load_recent_chat_history(limit=20)
        )
        print(
            f"Loaded {len(conversation_history)} "
            "messages from previous conversations."
        )
    except Exception as error:
        print(f"Conversation history loading warning: {error}")

    print("\nAI Agent with SQLite + ChromaDB")
    print("Commands:")
    print("  memories - list saved long-term memories")
    print("  clear    - clear in-memory conversation context")
    print("  exit     - quit the program\n")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            command = user_input.lower()

            if command == "exit":
                print("Goodbye!")
                break

            if command == "clear":
                conversation_history.clear()
                print("In-memory conversation cleared.")
                continue

            if command == "memories":
                saved = list_memories()

                if not saved:
                    print("No saved memories.")
                else:
                    print("\nSaved memories:")
                    for memory in saved:
                        print(
                            f"- {memory['key']}: {memory['value']} "
                            f"(updated: {memory['updated_at']})"
                        )

                print()
                continue

            try:
                run_agent(user_input)
            except Exception as error:
                print(f"Error: {error}")
                print(
                    "Check your API key, model name, connection, "
                    "database tables, and installed packages."
                )

            print()

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()