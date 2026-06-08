import os

# Synchronisiert mit der GROUND_TRUTH aus run_regression_tests.py

TEST_SCENARIOS = [
    # Hier das & durch &amp; ersetzen:
    {"filename": "miete_buero.xml", "description": "Monatliche Bueromiete Hauptstandort Etage 2", "sender": "Immobilien GmbH &amp; Co. KG"},
    {"filename": "steuerberater.xml", "description": "Erstellung der Umsatzsteuererklaerung und Jahresabschluss", "sender": "Dr. Steuer &amp; Partner"},
    {"filename": "internet_leitung.xml", "description": "Monatliche Grundgebuehr fuer Breitband-Internetanschluss DSL VDSL", "sender": "Telekom AG"},
    {"filename": "fachbuch_python.xml", "description": "Fachbuch Advanced Python Architecture Enterprise Patterns", "sender": "Rheinwerk Verlag"},
    {"filename": "subunternehmer_dev.xml", "description": "Entwicklung der API-Schnittstelle und Backend-Refactoring durch Freelancer", "sender": "Dev-Consulting GmbH"},
    
    {"filename": "google_ads.xml", "description": "Performance Marketing Kampagne Google Ads und LinkedIn Lead Generation", "sender": "Google Ireland Ltd."},
    {"filename": "kopierpapier.xml", "description": "Kopierpapier DIN A4, Ordner, Textmarker und Schreibwaren fuer das Buero", "sender": "Buero-Blitzversand KG"},
    {"filename": "wareneingang_komp.xml", "description": "Rohmaterialien, elektronische Bauteile und Komponenten fuer den Weiterverkauf", "sender": "Tech-Parts Wholesale"},
    {"filename": "buero_reinigung.xml", "description": "Monatliche Unterhaltsreinigung der betrieblichen Raeume und Fensterputzen", "sender": "Blitz-Blank Gebäudereinigung"},
    # Hier das & durch &amp; ersetzen:
    {"filename": "kaffee_buero.xml", "description": "Kaffeebohnen, Espresso, Wasser und Reinigungsmittel fuer die Mitarbeiterkueche", "sender": "Metro Cash &amp; Carry"}
]

# CII / ZUGFeRD-konformes XML-Template, das von deinem Parser (parse_e_invoice_xml) sauber gelesen wird
TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:uncefact:data:standard:CrossIndustryInvoice:100" xmlns:ram="urn:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100">
    <rsm:SupplyChainTradeTransaction>
        <ram:ApplicableHeaderTradeAgreement>
            <ram:SellerTradeParty>
                <ram:Name>{sender}</ram:Name>
            </ram:SellerTradeParty>
        </ram:ApplicableHeaderTradeAgreement>
        <ram:ApplicableHeaderTradeDelivery/>
        <ram:ApplicableHeaderTradeSettlement>
            <ram:SpecifiedTradeSettlementMonetarySummation>
                <ram:TaxBasisTotalAmount>100.00</ram:TaxBasisTotalAmount>
                <ram:TaxTotalAmount>19.00</ram:TaxTotalAmount>
                <ram:GrandTotalAmount>119.00</ram:GrandTotalAmount>
            </ram:SpecifiedTradeSettlementMonetarySummation>
        </ram:ApplicableHeaderTradeSettlement>
        <ram:IncludedSupplyChainTradeLineItem>
            <ram:AssociatedDocumentLineDocument>
                <ram:LineID>1</ram:LineID>
            </ram:AssociatedDocumentLineDocument>
            <ram:SpecifiedTradeProduct>
                <ram:Name>{description}</ram:Name>
            </ram:SpecifiedTradeProduct>
            <ram:SpecifiedLineTradeAgreement/>
            <ram:SpecifiedLineTradeDelivery/>
            <ram:SpecifiedLineTradeSettlement>
                <ram:ApplicableTradeTax>
                    <ram:RateApplicablePercent>19.0</ram:RateApplicablePercent>
                </ram:ApplicableTradeTax>
                <ram:SpecifiedTradeSettlementLineMonetarySummation>
                    <ram:LineTotalAmount>100.00</ram:LineTotalAmount>
                </ram:SpecifiedTradeSettlementLineMonetarySummation>
            </ram:SpecifiedLineTradeSettlement>
        </ram:IncludedSupplyChainTradeLineItem>
    </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""

def build_suite():
    # Wir erstellen den Ordner 'test_invoices', genau wie im Regression-Skript definiert
    target_dir = "test_invoices"
    os.makedirs(target_dir, exist_ok=True)
    
    for scenario in TEST_SCENARIOS:
        content = TEMPLATE.format(sender=scenario["sender"], description=scenario["description"])
        file_path = os.path.join(target_dir, scenario["filename"])
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    print(f"🎯 {len(TEST_SCENARIOS)} Test-Fixtures erfolgreich im Ordner '{target_dir}/' generiert!")

if __name__ == "__main__":
    build_suite()

