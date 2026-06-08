import os
import glob
import json
# Wir importieren die Kernlogik direkt aus deiner bestehenden app.py
from app import parse_e_invoice_xml, get_relevant_accounts, get_ki_kontierung

# Definition der erweiterten Ground Truth nach Aktualisierung der skr03_komplett.txt
GROUND_TRUTH = {
    "miete_buero.xml": 4210,        # Miete für unbewegliche Wirtschaftsgüter (angepasst!)
    "steuerberater.xml": 4950,     # Rechts- und Beratungskosten
    "internet_leitung.xml": 4920,   # Telefon / Internet
    "fachbuch_python.xml": 4940,    # Zeitschriften, Bücher
    "subunternehmer_dev.xml": 3100, # Fremdleistungen
    
    # Neu hinzugefügte Test-Szenarien für die erweiterten Konten:
    "google_ads.xml": 4600,         # Werbekosten
    "kopierpapier.xml": 4930,       # Bürobedarf
    "wareneingang_komp.xml": 3400,  # Wareneingang 19%
    "buero_reinigung.xml": 4260,    # Instandhaltung betrieblicher Räume
    "kaffee_buero.xml": 4980        # Betriebsbedarf
}

def run_benchmark():
    test_files = glob.glob("test_invoices/*.xml")
    if not test_files:
        print("Keine Testdateien gefunden. Bitte stelle sicher, dass die XML-Dateien im Ordner 'test_invoices/' liegen.")
        return

    passed_tests = 0
    evaluated_tests = 0
    
    print("\n==================================================")
    print("STARTING REGRESSION BENCHMARK FOR AI ACCOUNTING ENGINE")
    print("==================================================\n")

    for file_path in test_files:
        filename = os.path.basename(file_path)
        expected_konto = GROUND_TRUTH.get(filename)
        
        if not expected_konto:
            print(f"[SKIP] Keine Ground Truth für {filename} definiert.")
            continue
            
        evaluated_tests += 1
        try:
            # 1. Parsing - JETZT MIT FIX FÜR DEN RECHNERISCHEN DRITTEN RÜCKGABEWERT (totals)
            vendor, lines, totals = parse_e_invoice_xml(file_path)
            if not lines:
                print(f"[ERROR] Keine Positionen in {filename} gefunden.")
                continue
                
            item = lines[0] # Testdateien enthalten typischerweise eine Fokus-Zeile
            
            # 2. RAG Retrieval
            gefilterte_konten = get_relevant_accounts(item["description"], top_n=3)
            
            # 3. KI Kontierung
            ki_res = get_ki_kontierung(item, vendor, gefilterte_konten)
            predicted_konto = int(ki_res.get("konto_soll"))
            
            # 4. Evaluation
            if predicted_konto == expected_konto:
                print(f"[PASS] {filename:<25} -> Erwartet: {expected_konto} | KI: {predicted_konto} ✅")
                passed_tests += 1
            else:
                print(f"[FAIL] {filename:<25} -> Erwartet: {expected_konto} | KI: {predicted_konto} ❌")
                print(f"       Begruendung KI: {ki_res.get('begruendung')}")
                print(f"       RAG-Auswahl war: {[k['konto'] for k in gefilterte_konten]}")
                
        except Exception as e:
            print(f"[ERROR] Fehler beim Verarbeiten von {filename}: {e}")

    if evaluated_tests > 0:
        accuracy = (passed_tests / evaluated_tests) * 100
        print("\n==================================================")
        print(f"BENCHMARK ERGEBNIS: {passed_tests} von {evaluated_tests} relevanten Tests bestanden.")
        print(f"Modell-Präzision (Accuracy): {accuracy:.1f}%")
        print("==================================================\n")
    else:
        print("\n[WARN] Keine passenden Ground-Truth-Testdateien verarbeitet.")

if __name__ == "__main__":
    run_benchmark()
