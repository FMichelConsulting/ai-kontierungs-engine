import xml.etree.ElementTree as ET
import os

def generate_test_cases():
    # Ordner für Testdaten anlegen
    os.makedirs("test_invoices", exist_ok=True)
    
    # Pfad zu deiner originalen E-Rechnung (muss im selben Ordner liegen)
    source_xml = "erechnung.xml"
    if not os.path.exists(source_xml):
        print(f"Fehler: {source_xml} nicht gefunden! Bitte bereitstellen.")
        return

    # Definition der Testfälle: (Dateiname, Positionstext, Netto, Steuersatz)
    test_cases = [
        ("miete_buero.xml", "Monatsmiete Buero Etage 2", 1200.00, 0.0),
        ("steuerberater.xml", "Erstellung Umsatzsteuererklaerung", 350.00, 19.0),
        ("internet_leitung.xml", "Breitband Internetanschluss Juni", 49.90, 19.0),
        ("fachbuch_python.xml", "Handbuch zu Advanced Python Programming", 79.99, 7.0),
        ("subunternehmer_dev.xml", "Software Entwicklung Core Komponente", 4500.00, 19.0),
    ]

    for filename, desc, amount, tax in test_cases:
        tree = ET.parse(source_xml)
        root = tree.getroot()
        
        # Namespace-agnostischer Tausch im XML-Template (UBL-Struktur)
        # Wir suchen die erste InvoiceLine
        line = root.find('.//{*}InvoiceLine')
        if line is not None:
            # ID setzen
            id_node = line.find('{*}ID')
            if id_node is not None: id_node.text = "1"
            
            # Beschreibung tauschen
            name_node = line.find('.//{*}Item/{*}Name')
            if name_node is not None: name_node.text = desc
            
            # Betrag tauschen
            amount_node = line.find('{*}LineExtensionAmount')
            if amount_node is not None: amount_node.text = str(amount)
            
            # Steuersatz tauschen
            tax_node = line.find('.//{*}ClassifiedTaxCategory/{*}Percent')
            if tax_node is not None: tax_node.text = str(tax)
            
        target_path = os.path.join("test_invoices", filename)
        tree.write(target_path, encoding="utf-8", xml_declaration=True)
        print(f"Testdatei generiert: {target_path}")

if __name__ == "__main__":
    generate_test_cases()