import sys
import os
import shutil

source = r"C:\Users\RD03590\Downloads\backup_openwebui_2026-06-03_10-26-01.sql"
target = r"C:\Users\RD03590\Downloads\backup_openwebui_utf8.sql"

print(f"Converting {source} to {target}...")

encoding = 'utf-16' # default assumption

try:
    with open(source, 'rb') as f:
        bom = f.read(4)
        print(f"File start bytes: {bom.hex()}")
        if bom.startswith(b'\xff\xfe'):
            encoding = 'utf-16'
            print("Detected UTF-16 LE (Unicode)")
        elif bom.startswith(b'\xfe\xff'):
            encoding = 'utf-16-be'
            print("Detected UTF-16 BE")
        elif bom.startswith(b'\xef\xbb\xbf'):
            encoding = 'utf-8-sig'
            print("Detected UTF-8 with BOM")
        else:
            encoding = 'utf-8'
            print("Detected UTF-8 or ASCII")
except Exception as e:
    print(f"Error checking file encoding: {e}")
    sys.exit(1)

if encoding == 'utf-8':
    print("File is already UTF-8, copying directly...")
    shutil.copy(source, target)
else:
    # Read chunk by chunk and write to save memory
    try:
        with open(source, 'r', encoding=encoding, errors='ignore') as f_in:
            with open(target, 'w', encoding='utf-8') as f_out:
                while True:
                    chunk = f_in.read(1024 * 1024) # 1MB chunks
                    if not chunk:
                        break
                    f_out.write(chunk)
        print("Conversion completed successfully!")
    except Exception as e:
        print(f"Error converting file: {e}")
        sys.exit(1)
