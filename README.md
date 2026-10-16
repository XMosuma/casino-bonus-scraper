# Casino bonus scraper

Fetches bonus pages for 3 casinos from one public source, uses a language model to turn
the free-text terms into structured fields, writes `bonuses.json`, and shows them in a
table on `index.html`.

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

winget install Ollama.Ollama
ollama pull llama3.2     # one-time download, about 2 GB
python scraper.py 

```