import asyncio
import os
import sys
import time

# Ensure backend path is in Python environment
sys.path.insert(0, "/app/backend")

from open_webui.internal.db import get_async_db
from open_webui.models.users import Users
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.models.functions import Functions, FunctionForm, FunctionMeta
from open_webui.models.models import Model
from open_webui.utils.plugin import load_tool_module_by_id, load_function_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from sqlalchemy import select

async def inject_tool(tool_id, filepath, user_id, db):
    print(f"--- Injecting tool: {tool_id} ---")
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Pre-process content
    content = replace_imports(content)
    
    # 1. Clean existing tool if any
    existing = await Tools.get_tool_by_id(tool_id, db=db)
    if existing:
        print(f"Tool {tool_id} already exists, deleting first...")
        await Tools.delete_tool_by_id(tool_id, db=db)

    # 2. Get specs and frontmatter
    tool_module, frontmatter = await load_tool_module_by_id(tool_id, content=content)
    specs = get_tool_specs(tool_module)
    
    # 3. Create ToolForm
    form_data = ToolForm(
        id=tool_id,
        name=frontmatter.get('title', tool_id),
        content=content,
        meta=ToolMeta(description=frontmatter.get('description', ''), manifest=frontmatter),
        access_grants=[
            {
                "principal_type": "user",
                "principal_id": "*",
                "permission": "read"
            }
        ]
    )
    
    # 4. Insert tool
    result = await Tools.insert_new_tool(user_id, form_data, specs, db=db)
    if result:
        print(f"Successfully injected tool {tool_id}")
    else:
        print(f"Failed to inject tool {tool_id}")


async def inject_function(function_id, filepath, user_id, db):
    print(f"--- Injecting function: {function_id} ---")
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Pre-process content
    content = replace_imports(content)
    
    # 1. Clean existing function if any
    existing = await Functions.get_function_by_id(function_id, db=db)
    if existing:
        print(f"Function {function_id} already exists, deleting first...")
        await Functions.delete_function_by_id(function_id, db=db)

    # 2. Get type and frontmatter
    function_module, function_type, frontmatter = await load_function_module_by_id(function_id, content=content)
    
    # 3. Create FunctionForm
    form_data = FunctionForm(
        id=function_id,
        name=frontmatter.get('title', function_id),
        content=content,
        meta=FunctionMeta(description=frontmatter.get('description', ''), manifest=frontmatter)
    )
    
    # 4. Insert function
    result = await Functions.insert_new_function(user_id, function_type, form_data, db=db)
    if result:
        print(f"Successfully injected function {function_id} ({function_type})")
        # Global filter/action needs is_global = True, pipe needs is_global = False
        is_global = function_type in ['filter', 'action']
        await Functions.update_function_by_id(
            function_id,
            {'is_active': True, 'is_global': is_global},
            db=db
        )
        if function_type == 'filter' and getattr(function_module, 'toggle', None):
            await Functions.update_function_metadata_by_id(function_id, {'toggle': True}, db=db)
    else:
        print(f"Failed to inject function {function_id}")


async def enable_tools_for_models(db):
    print("--- Enabling tools for Gemini, GPT, and Claude models ---")
    tool_ids = [
        "google_gmail_tool",
        "code_interpreter",
        "server:0",
        "server:1",
        "server:2",
        "server:3",
        "server:4",
        "server:5",
        "server:6",
        "server:7",
        "server:8",
        "server:9",
        "server:10",
        "server:11"
    ]
    
    result = await db.execute(select(Model))
    models = result.scalars().all()
    for model in models:
        model_id_lower = model.id.lower()
        if 'gemini' in model_id_lower or 'gpt' in model_id_lower or 'claude' in model_id_lower:
            print(f"Updating tools for model: {model.id}")
            meta = model.meta if model.meta else {}
            existing_tools = meta.get("toolIds", [])
            for t_id in tool_ids:
                if t_id not in existing_tools:
                    existing_tools.append(t_id)
            meta["toolIds"] = existing_tools
            
            # Make sure builtin_tools is enabled in capabilities
            capabilities = meta.get("capabilities")
            if not isinstance(capabilities, dict):
                capabilities = {}
            capabilities["builtin_tools"] = True
            capabilities["code_interpreter"] = True
            meta["capabilities"] = capabilities
            
            model.meta = dict(meta)
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(model, "meta")
            model.updated_at = int(time.time())
            
            db.add(model)
            await db.commit()
            print(f"Updated tools for {model.id} successfully!")


async def main():
    async with get_async_db() as db:
        # Get first admin user
        user = await Users.get_first_user(db=db)
        if not user:
            print("No admin user found in OpenWebUI database!")
            return
        user_id = user.id
        print(f"Using user: {user.email} (id={user_id})")

        # Inject components from /tmp/tools
        await inject_tool("google_gmail_tool", "/tmp/tools/google_gmail_tool.py", user_id, db)
        await inject_tool("code_interpreter", "/tmp/tools/code_interpreter.py", user_id, db)
        
        await inject_function("action_approval_ui", "/tmp/tools/action_approval_ui.py", user_id, db)
        await inject_function("filter_approval_handler", "/tmp/tools/filter_approval_handler.py", user_id, db)
        await inject_function("deep_research_pipe", "/tmp/tools/deep_research_pipe.py", user_id, db)

        # Enable tools for LLM models
        await enable_tools_for_models(db)

if __name__ == "__main__":
    asyncio.run(main())
