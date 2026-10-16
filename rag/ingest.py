
import hashlib
import re
from io import BytesIO
from pathlib import Path

import chromadb
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DB_PATH = BASE_DIR / "chroma_db"

COLLECTION_NAME = "agent_documents"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

CHUNK_SIZE = 220
CHUNK_OVERLAP = 40
BATCH_SIZE = 100

_model = None
_client = None
_collection = None


# --------------------------------------------------
# Initialize embedding model and vector database
# --------------------------------------------------

def get_embedding_model():
    global _model

    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    return _model


def get_collection():
    global _client, _collection

    if _collection is None:
        CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

        _client = chromadb.PersistentClient(
            path=str(CHROMA_DB_PATH)
        )

        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    return _collection


# --------------------------------------------------
# Clean extracted PDF text while preserving lines
# --------------------------------------------------

def clean_pdf_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = text.replace("\u00a0", " ")

    cleaned_lines = []

    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()

        if line:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


# --------------------------------------------------
# Generic heading detection
# --------------------------------------------------

def is_heading(line: str) -> bool:
    """
    Detect likely section headings using general formatting
    patterns rather than document-specific keywords.
    """

    line = line.strip()

    if not line or len(line) > 100:
        return False

    words = line.split()

    if len(words) > 12:
        return False

    # Avoid treating normal sentences as headings.
    if re.search(r"[.!?]\s*$", line):
        return False

    # Avoid long lines containing detailed information.
    if len(words) >= 8 and not line.isupper():
        return False

    # Examples: "EDUCATION", "PROJECT EXPERIENCE"
    letters = [char for char in line if char.isalpha()]

    if letters:
        uppercase_ratio = (
            sum(char.isupper() for char in letters)
            / len(letters)
        )

        if uppercase_ratio >= 0.80:
            return True

    # Examples: "Education:", "Project Details:"
    if line.endswith(":") and len(words) <= 8:
        return True

    # Numbered headings such as "1. Overview"
    if re.match(
        r"^(?:\d+(?:\.\d+)*[.)]?\s+|[A-Z][.)]\s+).{1,75}$",
        line,
    ):
        return True

    # Short title-style headings, such as "Project Experience".
    if (
        1 < len(words) <= 5
        and all(
            word[0].isupper()
            for word in words
            if word and word[0].isalpha()
        )
        and not re.search(r"[,;.!?]", line)
    ):
        return True

    return False


# --------------------------------------------------
# Split text into heading-aware sections
# --------------------------------------------------

def split_into_sections(text: str) -> list[str]:
    """
    Keep a detected heading with its following content.
    Also separate paragraphs when possible.
    """

    lines = text.splitlines()

    sections = []
    current_heading = None
    current_paragraph = []

    def flush_paragraph():
        nonlocal current_paragraph, current_heading

        paragraph = " ".join(current_paragraph).strip()
        current_paragraph = []

        if not paragraph:
            return

        if current_heading:
            sections.append(
                f"{current_heading}\n{paragraph}"
            )
            current_heading = None
        else:
            sections.append(paragraph)

    for line in lines:
        line = line.strip()

        if not line:
            flush_paragraph()
            continue

        if is_heading(line):
            flush_paragraph()

            # Preserve consecutive headings without losing them.
            if current_heading:
                sections.append(current_heading)

            current_heading = line
        else:
            current_paragraph.append(line)

    flush_paragraph()

    if current_heading:
        sections.append(current_heading)

    return sections


# --------------------------------------------------
# Split long text while preserving word overlap
# --------------------------------------------------

def split_long_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:

    words = text.split()

    if not words:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be at least 0 and smaller than chunk_size."
        )

    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))

        chunk = " ".join(words[start:end]).strip()

        if chunk:
            chunks.append(chunk)

        if end == len(words):
            break

        start = end - overlap

    return chunks


# --------------------------------------------------
# Create section-aware chunks
# --------------------------------------------------

def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:

    text = clean_pdf_text(text)

    if not text:
        return []

    sections = split_into_sections(text)

    chunks = []
    current_parts = []
    current_word_count = 0

    for section in sections:
        section_words = section.split()
        section_word_count = len(section_words)

        if not section_word_count:
            continue

        # A single section may be longer than the chunk limit.
        if section_word_count > chunk_size:
            if current_parts:
                chunks.append("\n".join(current_parts))
                current_parts = []
                current_word_count = 0

            chunks.extend(
                split_long_text(
                    section,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
            )
            continue

        # Pack complete sections together where possible.
        if (
            current_parts
            and current_word_count + section_word_count > chunk_size
        ):
            chunks.append("\n".join(current_parts))

            # Carry some context from the previous chunk.
            previous_text = "\n".join(current_parts)
            previous_words = previous_text.split()

            overlap_text = " ".join(previous_words[-overlap:]) if overlap else ""

            current_parts = [overlap_text] if overlap_text else []
            current_word_count = len(overlap_text.split())

        current_parts.append(section)
        current_word_count += section_word_count

    if current_parts:
        chunks.append("\n".join(current_parts))

    return [chunk.strip() for chunk in chunks if chunk.strip()]


# --------------------------------------------------
# Extract text from each PDF page
# --------------------------------------------------

def extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")

    reader = PdfReader(BytesIO(pdf_bytes))

    if reader.is_encrypted:
        try:
            result = reader.decrypt("")
            if not result:
                raise ValueError(
                    "This PDF is password-protected. "
                    "Please upload an unlocked PDF."
                )
        except Exception as exc:
            raise ValueError(
                "Unable to read the encrypted PDF. "
                "Please upload an unlocked PDF."
            ) from exc

    pages = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        pages.append(clean_pdf_text(page_text))

    if not any(page.strip() for page in pages):
        raise ValueError(
            "No readable text was found in this PDF. "
            "It may be scanned and require OCR."
        )

    return pages


# --------------------------------------------------
# Ingest PDF into ChromaDB
# --------------------------------------------------

def ingest_pdf_bytes(
    pdf_bytes: bytes,
    filename: str,
) -> dict:

    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")

    if not filename or not filename.lower().endswith(".pdf"):
        raise ValueError("Please upload a valid PDF file.")

    document_id = hashlib.sha256(pdf_bytes).hexdigest()

    pages = extract_pdf_pages(pdf_bytes)

    collection = get_collection()
    model = get_embedding_model()

    documents = []
    ids = []
    metadatas = []

    for page_number, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue

        page_chunks = chunk_text(page_text)

        for chunk_index, chunk in enumerate(page_chunks):
            if not chunk.strip():
                continue

            chunk_id = (
                f"{document_id}_p{page_number}_c{chunk_index}"
            )

            documents.append(chunk)
            ids.append(chunk_id)

            metadatas.append({
                "document_id": document_id,
                "filename": filename,
                "page_number": page_number,
                "chunk_index": chunk_index,
            })

    if not documents:
        raise ValueError(
            "No searchable text chunks could be created from this PDF."
        )

    # Replace previously indexed content with the same filename.
    # This also removes old chunks if the file's contents changed.
    try:
        collection.delete(where={"filename": filename})
    except Exception:
        # If no matching records exist, continue with ingestion.
        pass

    # Add chunks in batches to limit memory use.
    for start in range(0, len(documents), BATCH_SIZE):
        end = start + BATCH_SIZE

        batch_documents = documents[start:end]
        batch_ids = ids[start:end]
        batch_metadatas = metadatas[start:end]

        embeddings = model.encode(
            batch_documents,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        collection.add(
            ids=batch_ids,
            documents=batch_documents,
            metadatas=batch_metadatas,
            embeddings=embeddings.tolist(),
        )

    return {
        "filename": filename,
        "document_id": document_id,
        "pages_processed": len(pages),
        "chunks_indexed": len(documents),
        "collection": COLLECTION_NAME,
    }
