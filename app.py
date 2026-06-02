import streamlit as st
import xml.etree.ElementTree as ET
import json
import pandas as pd
import io
from openai import OpenAI

st.set_page_config(page_title="AI Kontierungs-Engine MVP", page_icon="📊", layout="wide")

try:
    client = OpenAI()
except Exception:
    client = None

SKR03_KONTEN = [
    {"konto": 4930, "bezeichnung": "Bürobedarf", "beschreibung": "Schreibwaren, Ordner, Kopierpapier, Locher, Stifte."},
    {"konto": 4940, "bezeichnung": "Zeitschriften, Bücher", "beschreibung": "Fachliteratur, Gesetzestexte, steuerrechtliche Kommentare."},
    {"konto": 4920, "bezeichnung": "Telefon", "beschreibung": "Mobilfunkverträge, Festnetzanschlüsse, Internetgebühren."},
    {"konto": 4650, "bezeichnung": "Bewirtungskosten", "beschreibung": "Kaffee fürs Büro, Kekse, Mitarbeiterverpflegung, Kundenbewirtung."}
]

def parse_e_invoice_xml(xml_file):
    namespaces = {
        'ns': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
    }
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    vendor_name = root.find('.//cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name', namespaces).text
    
    parsed_lines = []
    for line in root.findall('.//cac:InvoiceLine', namespaces):
        line_id = line.find('cbc:ID', namespaces).text
        item_name = line.find('.//cac:Item/cbc:Name', namespaces).text
        amount = line.find('cbc:LineExtensionAmount', namespaces).text
        parsed_lines.append({"id": line_id, "description": item_name, "amount": float(amount)})
        
    return vendor_name, parsed_lines

def get_ki_kontierung(item, vendor_name):
    system_prompt = (
        "Du bist ein hochpräziser Finanzbuchhalter. Kontiere die Position auf den SKR03.\n"
        "Antworte AUSSCHLIESSLICH als JSON-Objekt:\n"
        "{\n  \"konto_soll\": 1234,\n  \"begruendung\": \"Fachliche Erklärung.\"\n}"
    )
    user_prompt = f"Kreditor: {vendor_name}\nPosition: {item['description']}\nNetto: {item['amount']} EUR\nOptionen:\n{json.dumps(SKR03_KONTEN)}"
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.0
    )
    return json.loads(response.choices[0].message.content)

def validate_kontierung(ki_res):
    # Fix: Variable konsistent benennen
    vorgeschlagenes_konto = ki_res.get("konto_soll")
    gueltige_konten = [k["konto"] for k in SKR03_KONTEN]
    
    if vorgeschlagenes_konto not in gueltige_konten:
        return False, f"Konto {vorgeschlagenes_konto} ungültig."
    return True, "APPROVED"

# --- NEU: DATEV CSV GENERATOR ---
def create_datev_csv(export_data):
    """
    Erzeugt einen DATEV-kompatiblen Buchungsstapel als CSV im Speicher.
    Gegenkonto (Haben) ist hier beispielhaft das Standard-Kreditor-Sammelkonto 70000.
    """
    output = io.StringIO()
    
    # Header 1: DATEV-Format-Kennzeichnung (erforderlich für den Import)
    # Erster Eintrag 'EXTF' steht für externen Verarbeitungsdatentyp
    output.write("EXTF;700;1;Buchungsstapel;;1;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;\n")
    
    # Header 2: Spaltenüberschriften (DATEV-Standard)
    # Umsatz;Soll/Haben;Konto;Gegenkonto;Buchungstext
    output.write("Umsatz;Soll/Haben;Konto;Gegenkonto;Buchungstext\n")
    
    # Datenzeilen schreiben
    for row in export_data:
        # DATEV nutzt standardmäßig das Semikolon und Komma für Dezimalzahlen
        betrag_str = f"{row['netto']:.2f}".replace('.', ',')
        soll_konto = row['konto_soll']
        haben_konto = 70000 # Dummy Kreditor
        text = row['beschreibung'][:60] # DATEV limitiert Buchungstexte oft
        
        output.write(f"{betrag_str};S;{soll_konto};{haben_konto};{text}\n")
        
    return output.getvalue()


# --- UI Layout ---
st.title("📊 Autonome E-Rechnungs-Engine")
st.subheader("MVP: Intelligente Zeilenkontierung mit DATEV-Export")

if not client:
    st.error("Bitte stelle sicher, dass der OPENAI_API_KEY in den Umgebungsvariablen gesetzt ist.")

with st.sidebar:
    st.header("Geladener Kontenrahmen (Stammdaten)")
    st.dataframe(SKR03_KONTEN, use_container_width=True)

uploaded_file = st.file_uploader("Lade eine E-Rechnungs-XML hoch (UBL/XRechnung)", type=["xml"])

if uploaded_file is not None:
    try:
        vendor, lines = parse_e_invoice_xml(uploaded_file)
        st.success(f"Rechnung erfolgreich eingelesen! **Kreditor:** {vendor}")
        
        st.write("### Extrahierte Positionen & KI-Verarbeitung")
        
        # Puffer, um validierte Daten für den Export zu sammeln
        validierte_buchungen_liste = []
        
        for item in lines:
            with st.container():
                col1, col2, col3 = st.columns([2, 1, 2])
                
                with col1:
                    st.markdown(f"**Pos {item['id']}:** {item['description']}")
                    st.caption(f"Netto-Betrag: {item['amount']:.2f} EUR")
                
                with st.spinner("KI analysiert..."):
                    ki_res = get_ki_kontierung(item, vendor)
                    is_valid, msg = validate_kontierung(ki_res)
                
                with col2:
                    if is_valid:
                        st.metric(label="Vorgeschlagenes Konto", value=str(ki_res['konto_soll']))
                        
                        # In den Export-Puffer schieben
                        validierte_buchungen_liste.append({
                            "netto": item['amount'],
                            "konto_soll": ki_res['konto_soll'],
                            "beschreibung": item['description']
                        })
                    else:
                        st.error(f"Fehler: {msg}")
                
                with col3:
                    st.text_area("Buchungstext / Begründung", value=ki_res['begruendung'], key=f"text_{item['id']}", height=68)
                
                st.divider()
        
        # --- NEU: EXPORT SEKTION ---
        if validierte_buchungen_liste:
            st.write("### Prozess abschließen")
            
            # Generiere das DATEV CSV im Hintergrund
            datev_csv_content = create_datev_csv(validierte_buchungen_liste)
            
            # Streamlit Download Button
            st.download_button(
                label="🚀 Kontierung übernehmen und Export nach DATEV",
                data=datev_csv_content,
                file_name="DATEV_Buchungsstapel_Export.csv",
                mime="text/csv",
                use_container_width=True
            )
                
    except Exception as e:
        st.error(f"Fehler beim Verarbeiten der XML-Struktur: {e}")