import xml.etree.ElementTree as ET

# Minimalistisches Beispiel einer XRechnung / UBL Invoice Struktur als String
xml_data = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:SupplierAssignedAccountID>K-91823</cbc:SupplierAssignedAccountID>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyName><cbc:Name>Bürobedarf Müller GmbH</cbc:Name></cac:PartyName>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="NAR">10</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="EUR">45.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Leitz Ordner A4 Wolkenmarmor</cbc:Name>
        </cac:Item>
    </cac:InvoiceLine>
    <cac:InvoiceLine>
        <cbc:ID>2</cbc:ID>
        <cbc:InvoicedQuantity unitCode="NAR">1</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="EUR">120.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Fachbuch Handbuch zum Bilanzrecht 2026</cbc:Name>
        </cac:Item>
    </cac:InvoiceLine>
</Invoice>"""

def parse_e_invoice(xml_string):
    # Namespaces für UBL-Standard auflösen
    namespaces = {
        'ns': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }
    
    root = ET.fromstring(xml_string)
    
    # Kreditor extrahieren
    vendor_name = root.find('.//cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name', namespaces).text
    print(f"--- Rechnungsverarbeitung für Kreditor: {vendor_name} ---")
    
    # Positionen extrahieren
    parsed_lines = []
    for line in root.findall('.//cac:InvoiceLine', namespaces):
        line_id = line.find('cbc:ID', namespaces).text
        item_name = line.find('.//cac:Item/cbc:Name', namespaces).text
        amount = line.find('cbc:LineExtensionAmount', namespaces).text
        
        parsed_lines.append({
            "id": line_id,
            "description": item_name,
            "amount": float(amount)
        })
        print(f"Pos {line_id}: '{item_name}' | Netto: {amount} EUR")
        
    return parsed_lines

# Ausführung des Parsers
invoice_items = parse_e_invoice(xml_data)