"""Optional live LLM smoke test with a fictional comment; never sends platform replies."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from automation import llm  # noqa: E402

prompt = ('Classify this fictional comment as praise. Return only a JSON array with one object: '
          'id sample-1, kategorie lob, antwort "Thanks!", ausblenden false, eskalieren false, '
          'grund empty string, themenidee null. Comment: "This is so true."')
backend = sys.argv[1]
item = llm.classify("kommentare", prompt, ["sample-1"], backend)["sample-1"]
print(f"{backend}: {item['kategorie']}, eskalieren={item['eskalieren']}")
if item["eskalieren"]:
    raise SystemExit(1)
