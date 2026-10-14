
import os
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from weather_tool import get_weather
from vector_memory import (
    save_vector_memory,
    delete_vector_memory,
    search_vector_memories,
    sync_sqlite_memories,
)


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "memory.db"

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY is missing. Check your .env file."
    )

client = genai.Client(api_key=API_KEY)
conversation_history = []


# =========================================================
# DATABASE
# =========================================================

def initialize_database():
    with sqlite3.connect(str(DB_PATH)) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                memory_key TEXT PRIMARY KEY,
                memory_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def normalize_key(key):
    return key.strip().lower().replace(" ", "_")


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
                                "add", "subtract", "multiply",
                                "divide", "percentage",
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
        ]
    }
]


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
        "web_search": lambda args: web_search(args["query"],
        max_results=max(1, min(int(args.get("max_results", 5)), 5)),
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

def run_agent(user_input):
    conversation_history.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)],
        )
    )

    for _ in range(8):
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=conversation_history,
                    config=types.GenerateContentConfig(
                        tools=agent_tools,
                        system_instruction=(
                            "You are a helpful AI agent with short-term and "
                            "persistent long-term memory. Use tools when "
                            "appropriate. For questions about saved personal "
                            "information, use semantic_memory_search if the "
                            "wording differs from the stored memory. Use "
                            "exact or keyword search when appropriate. "
                            "Only save or delete information when explicitly "
                            "asked. Never claim a tool succeeded if its "
                            "result reports failure. If the user asks to "
                            "delete a memory but the target is ambiguous, "
                            "ask for clarification instead of deleting."
                        ),
                    ),
                )
                break

            except Exception as error:
                error_text = str(error)
                temporary_error = (
                    "503" in error_text
                    or "UNAVAILABLE" in error_text
                )

                if temporary_error and attempt < 2:
                    wait_seconds = 2 ** (attempt + 1)
                    print(
                        f"Gemini is busy. Retrying in "
                        f"{wait_seconds} seconds..."
                    )
                    time.sleep(wait_seconds)
                else:
                    raise

        if not response.candidates:
            print("Agent: Gemini returned no response.")
            return

        model_content = response.candidates[0].content
        conversation_history.append(model_content)

        function_calls = [
            part.function_call
            for part in model_content.parts
            if part.function_call is not None
        ]

        if not function_calls:
            print(
                "Agent: "
                + (response.text or "I couldn't generate a response.")
            )
            return

        function_response_parts = []

        for call in function_calls:
            arguments = dict(call.args or {})

            print(f"\nTool selected: {call.name}")
            print(f"Arguments: {arguments}")

            result = execute_tool(call.name, arguments)
            print(f"Tool result: {result}")

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

        conversation_history.append(
            types.Content(
                role="user",
                parts=function_response_parts,
            )
        )

    print("Agent: Maximum tool steps reached.")


# =========================================================
# MAIN
# =========================================================

def main():
    initialize_database()

    print("Synchronizing SQLite memories with ChromaDB...")
    try:
        sync_sqlite_memories()
    except Exception as error:
        print(f"Memory synchronization warning: {error}")

    print("\nAI Agent with SQLite + ChromaDB")
    print("Commands:")
    print("  memories - list saved memories")
    print("  clear    - clear short-term conversation")
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
                print("Short-term conversation history cleared.")
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
                    "and installed packages."
                )

            print()

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()