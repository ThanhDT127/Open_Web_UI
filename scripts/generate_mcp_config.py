import os
import re
import sys

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_path = os.path.join(base_dir, "mcp_config.template.json")
    output_path = os.path.join(base_dir, "mcp_config.json")
    env_path = os.path.join(base_dir, ".env")

    if not os.path.exists(template_path):
        print(f"Error: Template file not found at {template_path}")
        sys.exit(1)

    # Load env from .env file manually to avoid external dependency requirements
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    env_vars[key] = val

    # Merge with os.environ (env vars override .env file)
    env_vars.update(os.environ)

    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find all ${VAR} patterns
    placeholders = re.findall(r"\$\{([^}]+)\}", content)
    missing_vars = []

    for var in placeholders:
        # Fallback: if MCP_POSTGRES_PASSWORD is not defined but POSTGRES_PASSWORD is, use it
        val = env_vars.get(var)
        if not val and var == "MCP_POSTGRES_PASSWORD":
            val = env_vars.get("POSTGRES_PASSWORD")
        
        if val is not None:
            content = content.replace(f"${{{var}}}", val)
        else:
            missing_vars.append(var)

    if missing_vars:
        print(f"Warning: Missing environment variables for placeholders: {', '.join(missing_vars)}")
        # We can still write the file, but warn the user.
        # Alternatively, we can fail-fast if they are required.

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Successfully generated {output_path} from template.")

if __name__ == "__main__":
    main()
