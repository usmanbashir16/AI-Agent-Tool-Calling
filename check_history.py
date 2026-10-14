
import sqlite3

connection = sqlite3.connect("memory.db")

count = connection.execute(
    "SELECT COUNT(*) FROM conversation_history"
).fetchone()[0]

print("Total conversation messages:", count)

rows = connection.execute(
    """
    SELECT id, role, content
    FROM conversation_history
    WHERE content LIKE ?
       OR content LIKE ?
       OR content LIKE ?
    ORDER BY id
    """,
    (
        "%ChromaDB%",
        "%search_vector_conversations%",
        "%sync_sqlite_conversations%",
    ),
).fetchall()

print("\nMatching messages:")

if not rows:
    print("No matching implementation messages found.")
else:
    for message_id, role, content in rows:
        print(f"\nID: {message_id} | Role: {role}")
        print(content[:250])

connection.close()