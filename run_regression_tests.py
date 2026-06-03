import os
import glob
# Wir importieren die Kernlogik direkt aus deiner bestehenden app.py
from app import parse_e_invoice_xml, get_relevant_accounts, get_ki_kontierung

# Definition der Ground Truth (Was MUSS mathematisch/fachlich herauskommen?)
GROUND_TRUTH = {
    "miete_buero.xml": 4960,       # Miete
    "steuerberater.xml": 4950,     # Rechts- und Beratungskosten
    "internet_leitung.xml": 4920,   # Telefon / Internet
    "fachbuch_python.xml": 4940,    # Zeitschriften, Bücher
    "subunternehmer_dev.xml": 3100  # Fremdleistungen
}

def run_benchmark():
    test_files = glob.glob("test_invoices/*.xml")
    if not test_files:
        print("Keine Testdateien gefunden. Bitte zuerst generate_test_data.py ausführen.")
        return

    passed_tests = 0
    total_tests = len(test_files)
    
    print("\n==================================================")
    print("STARTING REGRESSION BENCHMARK FOR AI ACCOUNTING ENGINE")
    print("==================================================\n")

    for file_path in test_files:
        filename = os.path.basename(file_path)
        expected_konto = GROUND_TRUTH.get(filename)
        
        if not expected_konto:
            print(f"[SKIP] Keine Ground Truth für {filename} definiert.")
            continue
            
        try:
            # 1. Parsing
            vendor, lines = parse_e_invoice_xml(file_path)
            item = lines[0] # Wir wissen, dass unsere Testdateien eine Zeile haben
            
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
                
        except Exception as e:
            print(f"[ERROR] Fehler beim Verarbeiten von {filename}: {e}")

    accuracy = (passed_tests / total_tests) * 100
    print("\n==================================================")
    print(f"BENCHMARK ERGEBNIS: {passed_tests} von {total_tests} Tests bestanden.")
    print(f"Modell-Präzision (Accuracy): {accuracy:.1f}%")
    print("==================================================\n")

if __name__ == "__main__":
    run_benchmark()