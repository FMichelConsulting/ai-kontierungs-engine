import json
import os
from openai import OpenAI

try:
    client = OpenAI()
except Exception:
    print("[ERROR] OpenAI API-Key nicht gefunden.")
    exit(1)

def get_embedding(text, model="text-embedding-3-small"):
    text = text.replace("\n", " ")
    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        print(f"[ERROR] Embedding-Fehler: {e}")
        return None

def create_sap_cache():
    print("🎬 Generiere SAP (YCOA) Vektor-Cache...")
    # Typische SAP Sachkonten (Beispielhaft für unseren Anwendungsbereich)
    sap_accounts = [
        {"konto": 410000, "bezeichnung": "Werbeaufwand", "beschreibung": "Marketing, Google Ads, Design, Grafik, Flyer, Kampagnen"},
        {"konto": 430000, "bezeichnung": "Fremdleistungen / Subunternehmer", "beschreibung": "Externe Entwickler, Freelancer, IT-Dienstleistungen, Software-Programmierung"},
        {"konto": 481000, "bezeichnung": "Büromaterial", "beschreibung": "Schreibwaren, Kopierpapier, Ordner, Stifte"},
        {"konto": 482000, "bezeichnung": "Fachliteratur & Zeitschriften", "beschreibung": "Fachbücher, Abonnements, Gesetzestexte, Dokumentationen"}
    ]
    
    for act in sap_accounts:
        search_text = f"{act['bezeichnung']}: {act['beschreibung']}"
        act["embedding"] = get_embedding(search_text)
        
    with open("sap_ycoa_with_embeddings.json", "w", encoding="utf-8") as f:
        json.dump(sap_accounts, f, ensure_ascii=False, indent=2)
    print("✅ SAP Cache gespeichert.")

def create_kameralistik_cache():
    print("🎬 Generiere Kameralistik (Kommune) Vektor-Cache...")
    # Typische Gruppierungsziffern (Titel) im kommunalen Haushalt
    kommune_accounts = [
        {"konto": 51100, "bezeichnung": "Geschäftsbedarf", "beschreibung": "Büromaterial, Kopierpapier, Drucksachen, Schreibwaren für die Verwaltung"},
        {"konto": 51400, "bezeichnung": "Haltung von Fahrzeugen", "beschreibung": "Kfz-Kosten, Benzin, Diesel, Tankquittungen, Reparatur Dienstwagen"},
        {"konto": 52000, "bezeichnung": "Ausgaben für Dienstleistungen von Dritten", "beschreibung": "Werbeagenturen, Grafiker, Texter, externe Dienstleister, Honorare"},
        {"konto": 53100, "bezeichnung": "Erwerb von Büchern und Zeitschriften", "beschreibung": "Fachliteratur für Ämter, Zeitschriften, digitale Abos, Fachbücher"}
    ]
    
    for act in kommune_accounts:
        search_text = f"{act['bezeichnung']}: {act['beschreibung']}"
        act["embedding"] = get_embedding(search_text)
        
    with open("kameralistik_kommune_with_embeddings.json", "w", encoding="utf-8") as f:
        json.dump(kommune_accounts, f, ensure_ascii=False, indent=2)
    print("✅ Kameralistik Cache gespeichert.")

if __name__ == "__main__":
    create_sap_cache()
    create_kameralistik_cache()