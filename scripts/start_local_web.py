"""Run the web workspace and backend together; Streamlit is not involved."""
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
load_dotenv(ROOT / '.env')
os.environ['BACKEND_ONLY'] = '0'
os.environ.setdefault('SQL_LLM_PROVIDER', 'groq')
os.environ.setdefault('DASHBOARD_STORAGE_DIR', str(ROOT / 'artifacts/local/dashboards'))
# Include the third configured Groq key in the provider's numbered fallback list.
if os.getenv('GROQ_API_KEY_RAGAS'):
    os.environ.setdefault('GROQ_API_KEY_3', os.environ['GROQ_API_KEY_RAGAS'])

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=8000)
