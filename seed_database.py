# seed_database.py
import json
import os
from supabase import create_client

def seed_system(system_name, json_filename):
    url = "https://zxsbdxmxfambmsqhydok.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp4c2JkeG14ZmFtYm1zcWh5ZG9rIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTI0NDQyMCwiZXhwIjoyMDk2ODIwNDIwfQ.q5Uri6fNm3fSPlyvc35omihoGR4OIjTatu85O9bVkzo"
    
    supabase = create_client(url, key)
    
    if not os.path.exists(json_filename):
        print(f"Datei {json_filename} nicht gefunden.")
        return
        
    with open(json_filename, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    print(f"Pushe {len(data)} Konten für {system_name} in die Cloud...")
    for item in data:
        # Falls kein Embedding existiert, überspringen oder Dummy setzen
        if not item.get("embedding"):
            continue
            
        payload = {
            "system_name": system_name,
            "konto": int(item["konto"]),
            "bezeichnung": item["bezeichnung"],
            "beschreibung": item["beschreibung"],
            "embedding": item["embedding"] # pgvector akzeptiert das Python-Array direkt
        }
        supabase.table("chart_of_accounts").insert(payload).execute()
    print(f"Erfolgreich abgeschlossen für {system_name}.")

# Beispielhafter Aufruf (lokal ausführen):
#seed_system("DATEV (SKR03)", "skr03_with_embeddings.json")
#seed_system("SAP (YCOA)", "sap_ycoa_with_embeddings.json")
#seed_system("Kameralistik (Kommune)", "kameralistik_kommune_with_embeddings.json")