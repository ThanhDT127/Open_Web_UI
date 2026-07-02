import os
import re
import base64
import uuid
import psycopg2
import psycopg2.extras
import logging
import sys

# Ensure current directory is in python path to import utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.media import convert_bytes_to_webp, save_bytes_to_media

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")

# Base64 regex pattern (matches base64 format in text/markdown)
base64_pattern = re.compile(r'data:image/([a-zA-Z+0-9]+);base64,([a-zA-Z0-9+/=\s\\n]+)')

def process_base64_string(val: str) -> str:
    """
    Scans a string for base64 image strings, decodes them, converts to WebP,
    saves them to local media storage, and replaces the base64 with the public URL.
    """
    if not isinstance(val, str) or "data:image/" not in val:
        return val
        
    new_val = val
    # Clean up any escaped forward slashes in JSON
    cleaned_val = val.replace(r"\/", "/")
    
    matches = list(base64_pattern.finditer(cleaned_val))
    for match in matches:
        img_type = match.group(1)
        b64_data = match.group(2)
        full_match = match.group(0)
        
        try:
            # Clean up whitespace, backslashes, newlines, and quotes
            b64_data_clean = re.sub(r'[\s\\n]+', '', b64_data)
            
            # Pad the base64 string if necessary
            missing_padding = len(b64_data_clean) % 4
            if missing_padding:
                b64_data_clean += '=' * (4 - missing_padding)
                
            img_bytes = base64.b64decode(b64_data_clean)
            
            # Convert to WebP
            webp_bytes = convert_bytes_to_webp(img_bytes, quality=80)
            
            # Save to local media
            filename = save_bytes_to_media(webp_bytes, mime="image/webp")
            
            # Public access URL
            public_url = f"https://localhost:3000/v1/_mw/media/{filename}"
            
            # We want to replace the original match in the unescaped string
            # Also handle potential escaped/raw format of original match in original val
            raw_match = match.group(0)
            escaped_match = raw_match.replace("/", r"\/")
            
            if raw_match in new_val:
                new_val = new_val.replace(raw_match, public_url)
            elif escaped_match in new_val:
                new_val = new_val.replace(escaped_match, public_url.replace("/", r"\/"))
                
            logger.info(f"Successfully migrated base64 image to local media: {public_url}")
        except Exception as e:
            logger.error(f"Failed to decode base64 image: {e}")
            
    return new_val

def migrate_dict_base64(data) -> bool:
    """
    Recursively scans and migrates base64 strings inside python dict/list.
    Returns True if any modification was made.
    """
    modified = False
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                if migrate_dict_base64(v):
                    modified = True
            elif isinstance(v, str) and "data:image/" in v:
                new_v = process_base64_string(v)
                if new_v != v:
                    data[k] = new_v
                    modified = True
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            if isinstance(item, (dict, list)):
                if migrate_dict_base64(item):
                    modified = True
            elif isinstance(item, str) and "data:image/" in item:
                new_item = process_base64_string(item)
                if new_item != item:
                    data[idx] = new_item
                    modified = True
    return modified

def main():
    # Get DATABASE_URL from env, default to openwebui database
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # Middleware database URL points to /middleware. We need to point to /openwebui
        if "/middleware" in db_url:
            db_url = db_url.replace("/middleware", "/openwebui")
    else:
        db_url = "postgresql://openwebui_user:YOUR_DB_PASSWORD@postgres:5432/openwebui?sslmode=disable"

    logger.info(f"Connecting to database: {db_url.split('@')[-1]}")
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return

    # 1. Migrate document_chunk table
    try:
        cursor.execute("SELECT id, text FROM document_chunk WHERE text LIKE '%data:image/%'")
        rows = cursor.fetchall()
        logger.info(f"Found {len(rows)} chunks with base64 images in document_chunk")

        updated_chunks = 0
        for chunk_id, text in rows:
            new_text = process_base64_string(text)
            if new_text != text:
                cursor.execute("UPDATE document_chunk SET text = %s WHERE id = %s", (new_text, chunk_id))
                updated_chunks += 1
        logger.info(f"Successfully updated {updated_chunks} rows in document_chunk.")
    except Exception as e:
        logger.error(f"Error migrating document_chunk: {e}")

    # 2. Migrate document table (full content)
    try:
        cursor.execute("SELECT id, content FROM document WHERE content LIKE '%data:image/%'")
        doc_rows = cursor.fetchall()
        logger.info(f"Found {len(doc_rows)} documents with base64 images in document")

        updated_docs = 0
        for doc_id, content in doc_rows:
            new_content = process_base64_string(content)
            if new_content != content:
                cursor.execute("UPDATE document SET content = %s WHERE id = %s", (new_content, doc_id))
                updated_docs += 1
        logger.info(f"Successfully updated {updated_docs} rows in document.")
    except Exception as e:
        logger.error(f"Error migrating document: {e}")

    # 3. Migrate chat table (chat messages history)
    try:
        cursor.execute("SELECT id, chat FROM chat WHERE chat::text LIKE '%data:image/%'")
        chat_rows = cursor.fetchall()
        logger.info(f"Found {len(chat_rows)} chats with base64 images in chat history")

        updated_chats = 0
        for chat_id, chat_content in chat_rows:
            # chat_content is a dict due to psycopg2 JSON auto-parsing
            if isinstance(chat_content, (dict, list)):
                if migrate_dict_base64(chat_content):
                    cursor.execute(
                        "UPDATE chat SET chat = %s WHERE id = %s",
                        (psycopg2.extras.Json(chat_content), chat_id)
                    )
                    updated_chats += 1
            else:
                # If it was returned as string
                new_chat_content = process_base64_string(chat_content)
                if new_chat_content != chat_content:
                    cursor.execute("UPDATE chat SET chat = %s WHERE id = %s", (new_chat_content, chat_id))
                    updated_chats += 1
        logger.info(f"Successfully updated {updated_chats} rows in chat.")
    except Exception as e:
        logger.error(f"Error migrating chat table: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Database migration process finished.")

if __name__ == "__main__":
    main()
