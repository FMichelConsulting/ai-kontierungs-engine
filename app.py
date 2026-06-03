import streamlit as st
import xml.etree.ElementTree as ET
import json
import pandas as pd
import io
import os
from openai import OpenAI
from pypdf import PdfReader
import difflib

st.set_page_config(page_title="AI Kontierungs-Engine MVP", page_icon="📊", layout="wide")

try:
    client = OpenAI()
except Exception:
    client = None

# --- NEU: DYNAMISCHER KONTENRAHMEN UTILS ---
def load_complete_chart_of_accounts():
    """Lädt den kompletten Kontenrahmen aus der Textdatei."""
    accounts = []
    filename = "skr03_komplett.txt"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() and ";" in line:
                    parts = line.strip().split(";")
                    if len(parts) == 3:
                        accounts.append({
                            "konto": int(parts[0]),
                            "bezeichnung": parts[1],
                            "beschreibung": parts[2]
                        })
    else:
        # Fallback, falls Datei fehlt
        accounts = [
            {"konto": 4930, "bezeichnung": "Bürobedarf", "beschreibung": "Schreibwaren, Ordner."},
            {"konto": 4940, "bezeichnung": "Zeitschriften, Bücher", "beschreibung": "Fachliteratur."}
        ]
    return accounts

# Alle echten Konten einmalig beim Start in den Speicher laden
ALL_SKR03_KONTEN = load_complete_chart_of_accounts()

def get_relevant_accounts(item_description, top_n=3):
    """
    Der RAG-Retriever: Sucht basierend auf der Positionsbeschreibung 
    die mathematisch ähnlichsten Konten aus der Gesamtliste heraus.
    """
    # Wir bauen einen Such-String aus Bezeichnung und Beschreibung der Konten
    choices = [f"{k['konto']} - {k['bezeichnung']}: {k['beschreibung']}" for k in ALL_SKR03_KONTEN]
    
    # Extrahiere die besten Treffer mittels Text-Ähnlichkeit
    matches = difflib.get_close_matches(item_description, choices, n=top_n, cutoff=0.1)
    
    # Falls gar nichts matcht, nehmen wir standardmäßig die ersten 3 Konten als Fallback
    if not matches:
        return ALL_SKR03_KONTEN[:top_n]
        
    # Filter die echten Kontenobjekte heraus, die gematcht haben
    relevant_accounts = []
    for match in matches:
        konto_num = int(match.split(" - ")[0])
        for k in ALL_SKR03_KONTEN:
            if k["konto"] == konto_num:
                relevant_accounts.append(k)
                break
                
    return relevant_accounts

# --- RESTLICHE PARSER & CORE LOGIK ---
def parse_e_invoice_xml(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    tag = root.tag
    
    # 1. FALL: CII Standard (ZUGFeRD)
    if "CrossIndustryInvoice" in tag or tag.endswith("CrossIndustryInvoice"):
        vendor_node = root.find('.//{*}SellerTradeParty//{*}Name')
        vendor_name = vendor_node.text if vendor_node is not None else "Unbekannter Kreditor"
        
        details_map = {}
        for detail_node in root.findall('.//{*}IncludedSupplyChainTradeLineItem'):
            line_id_node = detail_node.find('.//{*}AssociatedDocumentLineDocument/{*}LineID')
            if line_id_node is not None:
                details_map[line_id_node.text] = detail_node
        
        parsed_lines = []
        for item_node in root.findall('.//{*}AssociatedDocumentLineDocument'):
            line_id_node = item_node.find('{*}LineID')
            if line_id_node is None:
                continue
            line_id = line_id_node.text
            detail_node = details_map.get(line_id)
            
            if detail_node is not None:
                item_name_node = detail_node.find('.//{*}SpecifiedTradeProduct/{*}Name')
                amount_node = detail_node.find('.//{*}SpecifiedTradeSettlementLineMonetarySummation/{*}LineTotalAmount')
                if amount_node is None:
                    amount_node = detail_node.find('.//{*}LineTotalAmount')
                
                # NEU: Steuersatz aus CII extrahieren
                tax_node = detail_node.find('.//{*}ApplicableTradeTax/{*}RateApplicablePercent')
                tax_percent = float(tax_node.text) if tax_node is not None else 19.0

                if item_name_node is not None and amount_node is not None:
                    parsed_lines.append({
                        "id": line_id,
                        "description": item_name_node.text,
                        "amount": float(amount_node.text),
                        "tax_percent": tax_percent
                    })
        return vendor_name, parsed_lines

    # 2. FALL: UBL Standard (XRechnung)
    elif "Invoice" in tag or tag.endswith("Invoice"):
        vendor_node = root.find('.//{*}AccountingSupplierParty//{*}PartyName/{*}Name')
        if vendor_node is None:
            vendor_node = root.find('.//{*}AccountingSupplierParty//{*}Name')
        vendor_name = vendor_node.text if vendor_node is not None else "Unbekannter Kreditor"
        
        parsed_lines = []
        for line in root.findall('.//{*}InvoiceLine'):
            line_id = line.find('{*}ID').text
            item_name = line.find('.//{*}Item/{*}Name').text
            amount = line.find('{*}LineExtensionAmount').text
            
            # NEU: Steuersatz aus UBL extrahieren
            tax_node = line.find('.//{*}ClassifiedTaxCategory/{*}Percent')
            tax_percent = float(tax_node.text) if tax_node is not None else 19.0
            
            parsed_lines.append({
                "id": line_id, 
                "description": item_name, 
                "amount": float(amount),
                "tax_percent": tax_percent
            })
        return vendor_name, parsed_lines
    else:
        raise ValueError("Unbekanntes E-Rechnungsformat.")

def get_ki_kontierung(item, vendor_name, gefilterte_optionen):
    system_prompt = (
        "Du bist ein extrem pingeliger, konservativer deutscher Finanzbuchhalter.\n"
        "Deine Aufgabe ist es, die Position exakt und ohne kreative Auslegung auf den SKR03 zu kontieren.\n\n"
        "STRIKTE REGELN FÜR DEINE ENTSCHEIDUNG:\n"
        "1. Physische oder digitale Bücher, Fachliteratur und Dokumentationen sind ZWINGEND als 'Zeitschriften, Bücher' (4940) zu kontieren. Niemals als Fremdleistung, auch wenn sie Wissen vermitteln.\n"
        "2. IT-Entwicklung, Programmierung oder Projektarbeit von externen Freelancern/Subunternehmern sind Kern-Fremdleistungen (3100). Kontiere sie NUR DANN als Werbekosten (4600), wenn im Text explizit Marketing, SEO, Ads oder Design genannt werden.\n"
        "3. Wähle das Konto, dessen Beschreibung primär und direkt den Belegtext trifft. Keine logischen Brücken bauen (z.B. 'Software hilft bei der Vermarktung, also Werbung' ist VERBOTEN!).\n\n"
        "Antworte AUSSCHLIESSLICH als JSON-Objekt:\n"
        "{\n  \"konto_soll\": 1234,\n  \"begruendung\": \"Kurze, rein fachliche Begründung.\"\n}"
    )
    user_prompt = f"Kreditor: {vendor_name}\nPosition: {item['description']}\nNetto: {item['amount']} EUR\nErlaubte Optionen für diese Zeile:\n{json.dumps(gefilterte_optionen)}"
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.0
    )
    return json.loads(response.choices[0].message.content)

# ÄNDERUNG: Validiert gegen die global geladenen echten Stammdaten
def validate_kontierung(ki_res):
    vorgeschlagenes_konto = ki_res.get("konto_soll")
    gueltige_konten = [k["konto"] for k in ALL_SKR03_KONTEN]
    if vorgeschlagenes_konto not in gueltige_konten:
        return False, f"Konto {vorgeschlagenes_konto} ist im SKR03-Stamm nicht existent."
    return True, "APPROVED"

def create_datev_csv(export_data):
    """
    Erzeugt einen DATEV-kompatiblen Buchungsstapel inklusive BU-Schlüssel für die Vorsteuer.
    """
    output = io.StringIO()
    output.write("EXTF;700;1;Buchungsstapel;;1;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;\n")
    # Spaltenüberschriften um 'BU-Schlüssel' ergänzt
    output.write("Umsatz;Soll/Haben;Konto;Gegenkonto;BU-Schlüssel;Buchungstext\n")
    
    for row in export_data:
        betrag_str = f"{row['netto']:.2f}".replace('.', ',')
        
        # Deterministische Ermittlung des DATEV-Vorsteuerschlüssels
        tax = row.get("tax_percent", 19.0)
        if tax == 19.0:
            bu_schluessel = "9"  # DATEV Kennziffer für 19% Vorsteuer
        elif tax == 7.0:
            bu_schluessel = "8"  # DATEV Kennziffer für 7% Vorsteuer
        else:
            bu_schluessel = ""   # Steuerfrei / Sonstige
            
        output.write(f"{betrag_str};S;{row['konto_soll']};70000;{bu_schluessel};{row['beschreibung'][:60]}\n")
        
    return output.getvalue()

def extract_xml_from_zugferd(pdf_file):
    reader = PdfReader(pdf_file)
    zugferd_filenames = ["factur-x.xml", "zugferd-invoice.xml", "xrechnung-invoice.xml"]
    try:
        embedded_files = reader.attachments
        for name in zugferd_filenames:
            if name in embedded_files:
                return embedded_files[name][0]
    except Exception as e:
        st.error(f"Fehler beim Suchen nach PDF-Anhängen: {e}")
    return None

# --- UI Layout ---
st.title("📊 Autonome E-Rechnungs-Engine")
st.subheader("MVP: Intelligente Zeilenkontierung mit RAG-Gedächtnis")

if not client:
    st.error("Bitte stelle sicher, dass der OPENAI_API_KEY in den Umgebungsvariablen gesetzt ist.")

with st.sidebar:
    st.header("Vollständige SKR03-Stammdaten")
    st.dataframe(ALL_SKR03_KONTEN, use_container_width=True)

uploaded_file = st.file_uploader(
    "Lade eine E-Rechnung hoch (XRechnung XML oder ZUGFeRD PDF)", 
    type=["xml", "pdf"]
)

if uploaded_file is not None:
    try:
        xml_source = uploaded_file
        if uploaded_file.name.endswith(".pdf"):
            with st.spinner("Extrahiere ZUGFeRD-XML aus PDF..."):
                xml_bytes = extract_xml_from_zugferd(uploaded_file)
            if xml_bytes:
                xml_source = io.BytesIO(xml_bytes)
                st.info("ZUGFeRD-XML erfolgreich extrahiert!")
            else:
                st.error("Keine gültige ZUGFeRD-XML-Struktur in dieser PDF gefunden.")
                st.stop()
        
        vendor, lines = parse_e_invoice_xml(xml_source)
        st.success(f"Rechnung erfolgreich eingelesen! **Kreditor:** {vendor}")
        
        st.write("### Extrahierte Positionen & KI-Verarbeitung (RAG-optimiert)")
        
        if "processing_cache" not in st.session_state or st.session_state.get("current_file") != uploaded_file.name:
            st.session_state["processing_cache"] = []
            st.session_state["current_file"] = uploaded_file.name
            
            with st.spinner("RAG-Engine sucht passende Konten & KI analysiert..."):
                for item in lines:
                    gefilterte_konten = get_relevant_accounts(item["description"], top_n=3)
                    ki_res = get_ki_kontierung(item, vendor, gefilterte_konten)
                    is_valid, msg = validate_kontierung(ki_res)
                    
                    st.session_state["processing_cache"].append({
                        "item": item,
                        "ki_res": ki_res,
                        "is_valid": is_valid,
                        "msg": msg,
                        "gefilterte_konten": gefilterte_konten
                    })

        validierte_buchungen_liste = []
        
        for index, cached_item in enumerate(st.session_state["processing_cache"]):
            item = cached_item["item"]
            ki_res = cached_item["ki_res"]
            is_valid = cached_item["is_valid"]
            msg = cached_item["msg"]
            opt = cached_item["gefilterte_konten"]
            
            with st.container():
                col1, col2, col3 = st.columns([2, 1, 2])
                
                with col1:
                    st.markdown(f"**Pos {item['id']}:** {item['description']}")
                    # Hier geben wir den extrahierten Steuersatz im UI aus
                    st.caption(f"Netto-Betrag: {item['amount']:.2f} EUR | 📝 Steuersatz: {item['tax_percent']}%")
                    st.caption(f"💡 *RAG-Auswahl: {', '.join([str(k['konto']) for k in opt])}*")
                
                with col2:
                    if is_valid:
                        st.metric(label="Vorgeschlagenes Konto", value=str(ki_res['konto_soll']))
                        validierte_buchungen_liste.append({
                            "netto": item['amount'],
                            "konto_soll": ki_res['konto_soll'],
                            "beschreibung": item['description'],
                            "tax_percent": item['tax_percent'] # Für den CSV-Export sichern
                        })
                    else:
                        st.error(f"Fehler: {msg}")
                
                with col3:
                    st.text_area("Buchungstext / Begründung", value=ki_res['begruendung'], key=f"text_{item['id']}_{index}", height=68)
                
                st.divider()  
        
        if validierte_buchungen_liste:
            st.write("### Prozess abschließen")
            datev_csv_content = create_datev_csv(validierte_buchungen_liste)
            st.download_button(
                label="🚀 Kontierung übernehmen und Export nach DATEV",
                data=datev_csv_content,
                file_name="DATEV_Buchungsstapel_Export.csv",
                mime="text/csv",
                use_container_width=True
            )
                
    except Exception as e:
        st.error(f"Fehler beim Verarbeiten der Struktur: {e}")