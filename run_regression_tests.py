import os
import sys
# Stellt sicher, dass das aktuelle Verzeichnis im Pfad ist
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Die neuen Lade- und Validierungsfunktionen importieren
from app import (
    parse_e_invoice_xml, 
    get_relevant_accounts, 
    get_ki_kontierung, 
    validate_kontierung,
    load_chart_of_accounts_by_system
)

def run_benchmark():
    print("=" * 60)
    print("STARTING REGRESSION BENCHMARK FOR MULTI-ERP ACCOUNTING ENGINE")
    print("=" * 60 + "\n")
    
    # 1. Wir laden den DATEV-Stamm als Baseline für die Regression-Tests
    skr03_stamm = load_chart_of_accounts_by_system("DATEV (SKR03)")
    
    # Pfad zu deinen Test-XMLs (Anpassen, falls der Ordner anders heißt)
    test_dir = "test_invoices" 
    
    # Deine historische Erwartungs-Matrix (Musst du ggf. an deine XMLs anpassen)
    expected_mappings = {
        "buero_reinigung.xml": 4260,
        "fachbuch_python.xml": 4940,
        "google_ads.xml": 4600,
        "internet_leitung.xml": 4920,
        "kaffee_buero.xml": 4980,
        "kopierpapier.xml": 4930,
        "miete_buero.xml": 4210,
        "steuerberater.xml": 4950,
        "subunternehmer_dev.xml": 3100,
        "wareneingang_komp.xml": 3400
    }
    
    passed_tests = 0
    total_tests = 0
    
    for filename, expected_konto in expected_mappings.items():
        file_path = os.path.join(test_dir, filename)
        if not os.path.exists(file_path):
            print(f"[SKIP] {filename} nicht im Ordner gefunden.")
            continue
            
        total_tests += 1
        try:
            # 1. XML parsen
            vendor, lines, totals = parse_e_invoice_xml(file_path)
            
            # Wir testen die erste Position stellvertretend für den Benchmark
            first_item = lines[0]
            
            # 2. RAG-Retriever aufrufen – JETZT MIT DEM GELADENEN STAMM
            gefilterte_konten = get_relevant_accounts(first_item["description"], skr03_stamm, top_n=3)
            
            # 3. KI-Entscheidung holen
            ki_res = get_ki_kontierung(first_item, vendor, gefilterte_konten)
            
            # 4. Validieren gegen den Stamm
            is_valid, msg = validate_kontierung(ki_res, skr03_stamm)
            
            if not is_valid:
                print(f"[FAIL] {filename} -> Validierungsfehler: {msg}")
                continue
                
            ki_konto = ki_res.get("konto_soll")
            
            if ki_konto == expected_konto:
                print(f"[PASS] {filename:<25} -> Erwartet: {expected_konto} | KI: {ki_konto} ✅")
                passed_tests += 1
            else:
                print(f"[FAIL] {filename:<25} -> Erwartet: {expected_konto} | KI: {ki_konto} ❌")
                
        except Exception as e:
            print(f"[ERROR] Fehler beim Verarbeiten von {filename}: {e}")
            
    print("\n" + "=" * 60)
    if total_tests > 0:
        accuracy = (passed_tests / total_tests) * 100
        print(f"BENCHMARK ERGEBNIS: {passed_tests} von {total_tests} Tests bestanden.")
        print(f"Modell-Präzision (Accuracy): {accuracy:.1f}%")
    print("=" * 60)

if __name__ == "__main__":
    run_benchmark()
    