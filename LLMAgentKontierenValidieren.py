import json
from openai import OpenAI

# 1. Das semantische Gedächtnis (Simulierter SKR03 Kontenrahmen)
# In der Produktion läge das in einer Vektordatenbank.
SKR03_KONTEN = [
    {
        "konto": 4930, 
        "bezeichnung": "Bürobedarf", 
        "beschreibung": "Schreibwaren, Ordner, Kopierpapier, Locher, Stifte und Kleinstmaterial für die Verwaltung."
    },
    {
        "konto": 4940, 
        "bezeichnung": "Zeitschriften, Bücher", 
        "beschreibung": "Fachliteratur, Gesetzestexte, steuerrechtliche Kommentare, Fachzeitschriften und Weiterbildungsmaterial."
    },
    {
        "konto": 4920, 
        "bezeichnung": "Telefon", 
        "beschreibung": "Mobilfunkverträge, Festnetzanschlüsse, Internetgebühren und Kommunikationskosten."
    },
    {
        "konto": 4650, 
        "bezeichnung": "Bewirtungskosten", 
        "beschreibung": "Aufwendungen für die Bewirtung von Geschäftspartnern, Kaffee fürs Büro, Kekse und Mitarbeiterverpflegung."
    }
]

# Client initialisieren (zieht den Key automatisch aus der Umgebungsvariable OPENAI_API_KEY)
client = OpenAI()

def generate_kontierungs_vorschlag(invoice_line, vendor_name):
    """
    Übergibt eine einzelne Rechnungsposition zusammen mit dem Kontenrahmen
    an das LLM, um eine strukturierte Kontierung im JSON-Format zu erhalten.
    """
    
    # System-Prompt definiert die Rolle und die strikten Regeln
    system_prompt = (
        "Du bist ein hochpräziser, digitaler Finanzbuchhalter für deutsche Unternehmen (KMU).\n"
        "Deine Aufgabe ist es, eine gelieferte Rechnungsposition auf den Kontenrahmen SKR03 zu kontieren.\n"
        "Nutze dafür ausschließlich die zur Verfügung gestellten Konten-Optionen.\n"
        "Antworte IMMER und AUSSCHLIESSLICH im folgenden validen JSON-Format:\n"
        "{\n"
        "  \"konto_soll\": 1234,\n"
        "  \"begruendung\": \"Kurze, fachliche Erklärung, warum dieses Konto gewählt wurde.\"\n"
        "}"
    )
    
    # User-Prompt enthält den dynamischen Kontext der E-Rechnung
    user_prompt = f"""
    Kreditor (Lieferant): {vendor_name}
    Rechnungsposition: "{invoice_line['description']}"
    Netto-Betrag: {invoice_line['amount']} EUR
    
    Verfügbare SKR03 Konten-Optionen:
    {json.dumps(SKR03_KONTEN, ensure_ascii=False, indent=2)}
    """
    
    # API-Aufruf mit erzwungenem JSON-Output (Response Format)
    response = client.choices = client.chat.completions.create(
        model="gpt-4o-mini",  # Reicht für strukturierte Klassifizierung völlig aus und ist extrem günstig
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.0 # Absolut deterministisch halten
    )
    
    return json.loads(response.choices[0].message.content)

def validate_and_process(ki_ergebnis, erlaubte_konten):
    """
    Prüft das KI-Ergebnis deterministisch gegen die echten Systemvorgaben.
    """
    vorgeschlagenes_konto = ki_ergebnis.get("konto_soll")
    begruendung = ki_ergebnis.get("begruendung", "")
    
    # Extrahiere alle gültigen Kontonummern aus unserem "Stamm"
    gueltige_kontonummern = [k["konto"] for k in erlaubte_konten]
    
    # Regel 1: Existiert das Konto im Kontenrahmen?
    if vorgeschlagenes_konto not in gueltige_kontonummern:
        return {
            "status": "REJECTED", 
            "reason": f"Konto {vorgeschlagenes_konto} ist im Kontenrahmen nicht existent."
        }
        
    # Regel 2: Gibt es eine ausreichende Begründung für den Wirtschaftsprüfer?
    if not begruendung or len(begruendung) < 15:
        return {
            "status": "REJECTED", 
            "reason": "Die Buchungsbegründung ist zu kurz oder fehlt komplett."
        }
        
    # Wenn alle harten Regeln bestanden sind:
    return {
        "status": "APPROVED",
        "data": {
            "konto_soll": vorgeschlagenes_konto,
            "begruendung": begruendung
        }
    }

# --- Erweiterter Testlauf mit Validierung & Export-Vorbereitung ---
parsed_items = [
    {"id": "1", "description": "Leitz Ordner A4 Wolkenmarmor", "amount": 45.00},
    {"id": "2", "description": "Fachbuch Handbuch zum Bilanzrecht 2026", "amount": 120.00}
]
vendor = "Bürobedarf Müller GmbH"
export_ready_buffer = []

print("\n--- Starte KI-gestützte Vorkontierung mit deterministischer Validierung ---")

for item in parsed_items:
    print(f"\n[Verarbeitung] Position {item['id']}: '{item['description']}'...")
    
    # 1. KI-Agenten aufrufen
    ki_ergebnis = generate_kontierungs_vorschlag(item, vendor)
    
    # 2. Deterministische Firewall schalten
    validierungs_ergebnis = validate_and_process(ki_ergebnis, SKR03_KONTEN)
    
    if validierungs_ergebnis["status"] == "APPROVED":
        safe_data = validierungs_ergebnis["data"]
        print(f"   -> [VALIDIERT] Konto: {safe_data['konto_soll']}")
        print(f"   -> Begründung: {safe_data['begruendung']}")
        
        # Datensatz für den späteren CSV/API Export vorbereiten
        export_ready_buffer.append({
            "id": item["id"],
            "beschreibung": item["description"],
            "netto": item["amount"],
            "konto_soll": safe_data["konto_soll"],
            "begruendung": safe_data["begruendung"]
        })
    else:
        print(f"   -> [ABGEWIESEN] Grund: {validierungs_ergebnis['reason']}")

# 3. Das finale, saubere Ergebnis-Array für die App/Datenbank
print("\n--- Bereit für den Export / Human-in-the-Loop UI ---")
print(json.dumps(export_ready_buffer, ensure_ascii=False, indent=2))