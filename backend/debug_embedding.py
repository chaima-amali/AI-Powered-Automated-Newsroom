#!/usr/bin/env python3
#"""Debug embedding pipeline to capture full error traceback."""
#import sys
#!/usr/bin/env python3
"""Debug embedding pipeline to capture full error traceback."""
import sys
import traceback
from dotenv import load_dotenv
load_dotenv()

import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Process timeout after 300 seconds")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(300)  # 5 minute timeout

try:
    print("[*] Importing modules...")
    from pipeline.embedding.pipeline import run_embedding_pipeline
    print("[OK] Imports complete")
    
    print("[*] Fetching unprocessed articles...")
    from db.repository import count_unprocessed_articles
    count = count_unprocessed_articles(target_date=None, allowed_languages=("ar", "fr", "en"))
    print(f"[OK] Found {count} unprocessed articles")
    
    if count == 0:
        print("[!] No articles to process")
        sys.exit(0)
    
    print("[*] Importing embedding modules...")
    from pipeline.embedding.pipeline import run_embedding_pipeline
    print("[OK] Imports complete")
    
    print("[*] Starting embedding pipeline...")
    result = run_embedding_pipeline(process_date="*")
    print("[OK] Pipeline complete!")
    print(f"Result: {result}")
except KeyboardInterrupt:
    print("\n[INTERRUPTED] Pipeline interrupted by user")
    sys.exit(1)
except TimeoutError as e:
    print(f"\n[TIMEOUT] {e}")
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"\n[ERROR] {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)
finally:
    signal.alarm(0)  # Cancel alarm
