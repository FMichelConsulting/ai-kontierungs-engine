import os
import json
from openai import OpenAI

try:
    client = OpenAI()
except Exception:
    print("[ERROR] OpenAI API-Key nicht gefunden. Bitte exportieren!")
    exit(1)

def get_embedding(text, model="text-embedding-3-small"):
    text = text.replace("\n", " ")
    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        print(f"[ERROR] Fehler bei Embedding für '{text}': {e}")
        return None

def build_cache():
    txt_filename = "skr03_komplett.txt"
    json_filename = "skr03_with_embeddings.json"
    
    if not os.path.exists(txt_filename):
        print(f"[ERROR] Quell-Datei {txt_filename} existiert nicht.")
        return

    cached_accounts = []
    
    print(f"🎬 Starte einmalige Embedding-Generierung aus {txt_filename}...")
    
    with open(txt_filename, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    total_lines = len(lines)
    for index, line in enumerate(lines, 1):
        if ";" in line:
            parts = line.split(";")
            konto = int(parts[0])
            rest = parts[1]
            
            if "(" in rest and ")" in rest:
                bezeichnung = rest.split("(")[0].strip()
                beschreibung = rest.split("(")[1].replace(")", "").strip()
            else:
                bezeichnung = rest.strip()
                beschreibung = rest.strip()
            
            full_search_text = f"{bezeichnung}: {beschreibung}"
            
            print(f"[{index}/{total_lines}] Generiere Vektor für Konto {konto}...")
            embedding = get_embedding(full_search_text)
            
            cached_accounts.append({
                "konto": konto,
                "bezeichnung": bezeichnung,
                "beschreibung": beschreibung,
                "embedding": embedding
            })

    # Als JSON speichern
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(cached_accounts, f, ensure_ascii=False, indent=2)
        
    print(f"🎉 Fertig! {len(cached_accounts)} Konten inklusive Embeddings erfolgreich in '{json_filename}' gespeichert.")

if __name__ == "__main__":
    build_cache()
    