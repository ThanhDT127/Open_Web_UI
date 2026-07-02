"""
Docling Proxy — Intercepts document extraction and materializes images.
This ensures Open WebUI stores clean Markdown with material URLs in its vector DB.
"""

import os
import re
import httpx
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse

from config import logger
from utils.media import maybe_materialize_data_url, save_bytes_to_media, public_media_url

# The actual docling-serve internal URL
REAL_DOCLING_URL = os.getenv("REAL_DOCLING_URL", "http://docling:5001").rstrip("/")


async def docling_proxy(request: Request):
    """
    Catch-all proxy for Docling requests.
    Supports GET /health and POST /convert (the main endpoint).
    """
    path = request.url.path
    # Strip the '/docling-proxy' prefix to get the sub-path
    target_subpath = path.replace("/docling-proxy", "")
    if not target_subpath:
        target_subpath = "/"
    
    target_url = f"{REAL_DOCLING_URL}{target_subpath}"
    
    method = request.method
    headers = dict(request.headers)
    # Host header must be updated to the internal service name
    headers.pop("host", None)
    
    content = await request.body()
    params = dict(request.query_params)

    req_data = None
    req_files = None

    if method == "POST" and "multipart/form-data" in headers.get("content-type", "").lower():
        try:
            form = await request.form()
            req_data = {}
            req_files = []
            for key, value in form.multi_items():
                if hasattr(value, "file"):
                    file_content = await value.read()
                    await value.seek(0)
                    req_files.append((key, (value.filename, file_content, value.content_type)))
                else:
                    req_data[key] = value

            if req_data.get("image_export_mode") == "referenced":
                logger.info("docling_proxy: forcing target_type=zip for referenced image_export_mode in multipart body")
                req_data["target_type"] = "zip"

            headers.pop("content-type", None)
            headers.pop("content-length", None)
            content = None
        except Exception as fe:
            logger.error("docling_proxy: failed to parse/modify incoming form: %s", fe)

    if params.get("image_export_mode") == "referenced":
        logger.info("docling_proxy: forcing target_type=zip in query params")
        params["target_type"] = "zip"

    logger.info("docling_proxy: %s %s -> %s", method, path, target_url)

    try:
        client: httpx.AsyncClient = request.app.state.http_client
        resp = await client.request(
            method,
            target_url,
            headers=headers,
            content=content,
            data=req_data,
            files=req_files,
            params=params,
            timeout=300.0 # Document conversion can be slow
        )
    except Exception as e:
        logger.error("docling_proxy_error: %s", e)
        raise HTTPException(502, f"Error connecting to Docling service: {e}")

    # --- Response Interception & Materialization ---
    
    # 1. Intercept ZIP response (referenced mode)
    if resp.status_code == 200 and (
        "application/zip" in resp.headers.get("content-type", "") 
        or resp.content.startswith(b"PK\x03\x04")
    ):
        try:
            import io
            import zipfile
            from utils.media import convert_bytes_to_webp
            
            zip_buffer = io.BytesIO(resp.content)
            
            markdown_content = ""
            images = {}
            
            with zipfile.ZipFile(zip_buffer) as z:
                # Find markdown file
                md_filename = None
                for name in z.namelist():
                    if name.lower().endswith(".md"):
                        md_filename = name
                        break
                
                if md_filename:
                    markdown_content = z.read(md_filename).decode("utf-8")
                    
                    # Extract and process image files
                    for name in z.namelist():
                        if any(name.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                            img_bytes = z.read(name)
                            
                            # Convert to WebP (nén quality=80)
                            webp_bytes = convert_bytes_to_webp(img_bytes, quality=80)
                            
                            # Save directly to local storage
                            try:
                                local_name = save_bytes_to_media(webp_bytes, mime="image/webp")
                                public_url = public_media_url(request, local_name)
                                images[name] = public_url
                                logger.info("docling_proxy: successfully stored image locally: %s", public_url)
                            except Exception as le:
                                logger.error("docling_proxy: failed to save local image: %s", le)
                    
                    # Replace paths in markdown
                    for local_path, local_url in images.items():
                        # Replace direct local path
                        markdown_content = markdown_content.replace(local_path, local_url)
                        # Replace relative path basename
                        base_name = os.path.basename(local_path)
                        if base_name != local_path:
                            markdown_content = markdown_content.replace(base_name, local_url)
                        # Handing cases where relative path has ./ prefix
                        dot_slash_name = f"./{base_name}"
                        markdown_content = markdown_content.replace(dot_slash_name, local_url)
                    
                    # Return JSON to Open WebUI
                    logger.info("docling_proxy: processed ZIP response. Extracted %d images -> Local Media.", len(images))
                    return JSONResponse(content={
                        "document": {
                            "md_content": markdown_content
                        }
                    })
                else:
                    logger.warning("docling_proxy: no markdown file found in ZIP response")
        except Exception as e:
            logger.error("docling_proxy_zip_interception_fail: %s", e)
            raise HTTPException(502, f"Failed to process Docling ZIP response: {e}")

    # 2. Intercept legacy JSON response
    if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
        try:
            data = resp.json()
            modified = False
            
            # Debug: Log all keys to find where images might be hiding
            logger.info("docling_proxy: response keys: %s", list(data.keys()))
            doc_obj = data.get("document", {})
            if isinstance(doc_obj, dict):
                logger.info("docling_proxy: document keys: %s", list(doc_obj.keys()))
            
            # 1. Check for images in md_content
            markdown_content = doc_obj.get("md_content") if isinstance(doc_obj, dict) else None
            
            if isinstance(markdown_content, str):
                logger.info("docling_proxy: md_content length: %d", len(markdown_content))
                if "data:image/" in markdown_content:
                    logger.info("docling_proxy: materializing images found in md_content")
                    
                    start_search = 0
                    while True:
                        idx = markdown_content.find("data:image/", start_search)
                        if idx == -1:
                            break
                        
                        end_idx = len(markdown_content)
                        for char in [" ", "'", "\"", ")", "]", "}", "\n", "\t", "\\", ">"]:
                            term_idx = markdown_content.find(char, idx)
                            if term_idx != -1 and term_idx < end_idx:
                                end_idx = term_idx
                        
                        data_url = markdown_content[idx:end_idx].strip()
                        data_url = data_url.rstrip(".,;)]}>\\")
                        
                        if ";base64," in data_url:
                            try:
                                public_url = maybe_materialize_data_url(request, url=data_url)
                                if public_url != data_url:
                                    markdown_content = markdown_content[:idx] + public_url + markdown_content[end_idx:]
                                    logger.info("docling_proxy: materialized base64 -> %s", public_url)
                                    modified = True
                                    start_search = idx + len(public_url)
                                else:
                                    start_search = idx + len(data_url)
                            except Exception as e:
                                logger.error("docling_proxy_materialize_err: %s", e)
                                start_search = idx + len(data_url)
                        else:
                            start_search = idx + len(data_url)
                    
                    if modified:
                        data["document"]["md_content"] = markdown_content
                else:
                    # Check if images are in a separate field (e.g. data['document']['images'])
                    images_list = doc_obj.get("images", []) if isinstance(doc_obj, dict) else []
                    if images_list:
                        logger.info("docling_proxy: found %d images in separate 'images' field", len(images_list))
                        # Note: stitching images back to MD requires knowing their placeholders. 
                        # For now, we just log their presence.
                    else:
                        logger.info("docling_proxy: NO images found in md_content or images field")
            
            if modified:
                return JSONResponse(content=data)
        except Exception as e:
            logger.error("docling_proxy_interception_fail: %s", e)
            pass

    # Default: proxy the response as-is
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers)
    )
