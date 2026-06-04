import os

# Definition der Testfälle: Welcher Inhalt triggert welches Konto?
TEST_SCENARIOS = [
    {"konto": "4600", "filename": "werbung_grafik.xml", "description": "Erstellung von Werbebanner und Social Media Layouts", "sender": "Agentur Blickfang"},
    {"konto": "4920", "filename": "telekom_internet.xml", "description": "Monatliche Grundgebühr für Breitband-Internetanschluss", "sender": "Telekom AG"},
    {"konto": "6825", "filename": "steuerberater_abschluss.xml", "description": "Erstellung der Umsatzsteuervoranmeldung und Buchführung", "sender": "Dr. Steuer & Partner"},
    {"konto": "3100", "filename": "fremdleistung_dev.xml", "description": "Entwicklung der API-Schnittstelle durch externen Freelancer", "sender": "Dev-Consulting GmbH"}
]

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:uncefact:data:standard:CrossIndustryInvoice:100">
    <rsm:SupplyChainTradeTransaction>
        <ram:ApplicableHeaderTradeAgreement>
            <ram:SellerTradeParty>
                <ram:Name>{sender}</ram:Name>
            </ram:SellerTradeParty>
        </ram:ApplicableHeaderTradeAgreement>
        <ram:IncludedSupplyChainTradeLineItem>
            <ram:SpecifiedLineTradeProduct>
                <ram:Name>{description}</ram:Name>
            </ram:SpecifiedLineTradeProduct>
        </ram:IncludedSupplyChainTradeLineItem>
    </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""

def build_suite():
    os.makedirs("tests/fixtures", exist_ok=True)
    for scenario in TEST_SCENARIOS:
        content = TEMPLATE.format(sender=scenario["sender"], description=scenario["description"])
        with open(f"tests/fixtures/{scenario['filename']}", "w", encoding="utf-8") as f:
            f.write(content)
    print(f"{len(TEST_SCENARIOS)} Test-Fixtures erfolgreich generiert!")

if __name__ == "__main__":
    build_suite()