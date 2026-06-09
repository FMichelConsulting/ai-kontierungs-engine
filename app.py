import streamlit as st
import xml.etree.ElementTree as ET
import json
import pandas as pd
import io
import os
import numpy as np
from openai import OpenAI
from pypdf import PdfReader

st.set_page_config(page_title="AI Kontierungs-Engine MVP", page_icon="📊", layout="wide")

try:
    client = OpenAI()
except Exception:
    client = None

# --- MATHEMATISCHE UTILS FÜR SEMANTISCHE VEKTORSUCHE (RAG) ---
def get_embedding(text, model="text-embedding-3-small"):
    """Erzeugt einen semantischen Vektor für einen gegebenen Text über die OpenAI-API."""
    if not client:
        return None
    text = text.replace("\n", " ")
    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        st.error(f"Fehler bei der Embedding-Generierung: {e}")
        return None

def cosine_similarity(a, b):
    """Berechnet die mathematische Kosinus-Ähnlichkeit zwischen zwei Vektoren."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def load_complete_chart_of_accounts_with_embeddings():
    """
    Lädt den vorkalkulierten Kontenrahmen inklusive der semantischen Vektoren
    blitzschnell aus der lokalen JSON-Datei. Verhindert API-Kaltstart-Latenzen.
    """
    json_filename = "skr03_with_embeddings.json"
    if os.path.exists(json_filename):
        with open(json_filename, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        st.warning(f"Cache-Datei {json_filename} nicht gefunden! Nutze minimalen Fallback.")
        return [
            {"konto": 4930, "bezeichnung": "Bürobedarf", "beschreibung": "Schreibwaren, Ordner, Papier.", "embedding": None},
            {"konto": 4940, "bezeichnung": "Zeitschriften, Bücher", "beschreibung": "Fachliteratur, Abos.", "embedding": None}
        ]

# Globaler Import der Stammdaten aus dem lokalen JSON-Cache
ALL_SKR03_KONTEN = load_complete_chart_of_accounts_with_embeddings()

def get_relevant_accounts(item_description, top_n=3):
    """Der RAG-Retriever sucht via Vektor-Ähnlichkeit (Cosine Similarity) passende Konten."""
    item_embedding = get_embedding(item_description)
    if not item_embedding:
        return ALL_SKR03_KONTEN[:top_n]
        
    scored_accounts = []
    for k in ALL_SKR03_KONTEN:
        if k["embedding"] is not None:
            score = cosine_similarity(item_embedding, k["embedding"])
            scored_accounts.append((score, k))
            
    # Sortieren nach dem höchsten mathematischen Score (absteigend)
    scored_accounts.sort(key=lambda x: x[0], reverse=True)
    
    # Die Top-N Konten extrahieren und zurückgeben
    relevant_accounts = [item[1] for item in scored_accounts[:top_n]]
    return relevant_accounts


# --- MATHEMATISCHE PRÜF-ENGINE ---
def check_invoice_math(lines, invoice_totals):
    """
    Validiert die Grundrechenarten auf Positionsebene sowie die globalen Summen.
    Erlaubt eine Rundungstoleranz von maximal 0.02 EUR.
    """
    audit_trail = []
    has_math_error = False
    tolerance = 0.02
    
    calculated_net_total = 0.0
    for item in lines:
        line_net = item["amount"]
        calculated_net_total += line_net
        audit_trail.append(f"✅ Position {item['id']}: Extrahiert Netto {line_net:.2f} € (Steuersatz: {item['tax_percent']}%)")

    passed_net = invoice_totals.get("gesamt_netto", 0.0)
    passed_tax = invoice_totals.get("gesamt_steuer", 0.0)
    passed_gross = invoice_totals.get("gesamt_brutto", 0.0)
    
    if abs(calculated_net_total - passed_net) > tolerance:
        audit_trail.append(f"❌ Netto-Summation fehlerhaft! Summe der Einzelpositionen ({calculated_net_total:.2f} €) weicht von Gesamt-Netto ({passed_net:.2f} €) ab.")
        has_math_error = True
    else:
        audit_trail.append(f"✅ Netto-Summation konsistent ({passed_net:.2f} €)")

    if abs(passed_net + passed_tax - passed_gross) > tolerance:
        audit_trail.append(f"❌ Brutto-Addition fehlerhaft! Netto ({passed_net:.2f} €) + Steuer ({passed_tax:.2f} €) ergibt nicht Brutto ({passed_gross:.2f} €)")
        has_math_error = True
    else:
        audit_trail.append(f"✅ Brutto-Addition korrekt ({passed_gross:.2f} €)")

    status = "RECHNUNG ABGEWIESEN" if has_math_error else "RECHNERISCHE PRÜFUNG ERFOLGREICH"
    return status, audit_trail


# --- PARSER & CORE LOGIK (CII & UBL) ---
def parse_e_invoice_xml(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    tag = root.tag
    
    invoice_totals = {"gesamt_netto": 0.0, "gesamt_steuer": 0.0, "gesamt_brutto": 0.0}
    
    # 1. FALL: CII Standard (ZUGFeRD / Factur-X)
    if "CrossIndustryInvoice" in tag or tag.endswith("CrossIndustryInvoice"):
        vendor_node = root.find('.//{*}SellerTradeParty//{*}Name')
        vendor_name = vendor_node.text if vendor_node is not None else "Unbekannter Kreditor"
        
        net_node, tax_node_tot, gross_node = None, None, None
        for summation in root.findall('.//{*}SpecifiedTradeSettlementMonetarySummation'):
            net_node = summation.find('.//{*}TaxBasisTotalAmount')
            tax_node_tot = summation.find('.//{*}TaxTotalAmount')
            gross_node = summation.find('.//{*}GrandTotalAmount')
            
        if net_node is None: net_node = root.find('.//{*}TaxBasisTotalAmount')
        if tax_node_tot is None: tax_node_tot = root.find('.//{*}TaxTotalAmount')
        if gross_node is None: gross_node = root.find('.//{*}GrandTotalAmount')
        
        if net_node is not None: invoice_totals["gesamt_netto"] = float(net_node.text)
        if tax_node_tot is not None: invoice_totals["gesamt_steuer"] = float(tax_node_tot.text)
        if gross_node is not None: invoice_totals["gesamt_brutto"] = float(gross_node.text)
        
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
                
                tax_node = detail_node.find('.//{*}ApplicableTradeTax/{*}RateApplicablePercent')
                tax_percent = float(tax_node.text) if tax_node is not None else 19.0

                if item_name_node is not None and amount_node is not None:
                    parsed_lines.append({
                        "id": line_id,
                        "description": item_name_node.text,
                        "amount": float(amount_node.text),
                        "tax_percent": tax_percent
                    })
        return vendor_name, parsed_lines, invoice_totals

    # 2. FALL: UBL Standard (XRechnung)
    elif "Invoice" in tag or tag.endswith("Invoice"):
        vendor_node = root.find('.//{*}AccountingSupplierParty//{*}PartyName/{*}Name')
        if vendor_node is None:
            vendor_node = root.find('.//{*}AccountingSupplierParty//{*}Name')
        vendor_name = vendor_node.text if vendor_node is not None else "Unbekannter Kreditor"
        
        net_node = root.find('.//{*}LegalMonetaryTotal/{*}LineExtensionAmount')
        tax_node_tot = root.find('.//{*}TaxTotal/{*}TaxAmount')
        gross_node = root.find('.//{*}LegalMonetaryTotal/{*}TaxInclusiveAmount')
        
        if net_node is not None: invoice_totals["gesamt_netto"] = float(net_node.text)
        if tax_node_tot is not None: invoice_totals["gesamt_steuer"] = float(tax_node_tot.text)
        if gross_node is not None: invoice_totals["gesamt_brutto"] = float(gross_node.text)
        
        parsed_lines = []
        for line in root.findall('.//{*}InvoiceLine'):
            line_id = line.find('{*}ID').text
            item_name = line.find('.//{*}Item/{*}Name').text
            amount = line.find('{*}LineExtensionAmount').text
            
            tax_node = line.find('.//{*}ClassifiedTaxCategory/{*}Percent')
            tax_percent = float(tax_node.text) if tax_node is not None else 19.0
            
            parsed_lines.append({
                "id": line_id, 
                "description": item_name, 
                "amount": float(amount),
                "tax_percent": tax_percent
            })
        return vendor_name, parsed_lines, invoice_totals
    else:
        raise ValueError("Unbekanntes E-Rechnungsformat.")

def get_ki_kontierung(item, vendor_name, gefilterte_optionen):
    bereinigte_optionen = []
    for opt in gefilterte_optionen:
        bereinigte_optionen.append({
            "konto": opt["konto"],
            "bezeichnung": opt["bezeichnung"],
            "beschreibung": opt["beschreibung"]
        })

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
    user_prompt = f"Kreditor: {vendor_name}\nPosition: {item['description']}\nNetto: {item['amount']} EUR\nErlaubte Optionen für diese Zeile:\n{json.dumps(bereinigte_optionen)}"
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.0
    )
    return json.loads(response.choices[0].message.content)

def validate_kontierung(ki_res):
    vorgeschlagenes_konto = ki_res.get("konto_soll")
    gueltige_konten = [k["konto"] for k in ALL_SKR03_KONTEN]
    if vorgeschlagenes_konto not in gueltige_konten:
        return False, f"Konto {vorgeschlagenes_konto} ist im SKR03-Stamm nicht existent."
    return True, "APPROVED"

def create_datev_csv(export_data):
    """
    Erzeugt einen DATEV-konformen EXTF-Buchungsstapel.
    Jede Rechnungsposition wird als eigenständiger Buchungssatz (Split) exportiert.
    WICHTIG: DATEV erwartet bei Nutzung von BU-Schlüsseln den BRUTTO-Umsatz der Position!
    """
    output = io.StringIO()
    # DATEV Header-Zeile
    output.write("EXTF;700;1;Buchungsstapel;;1;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;\n")
    output.write("Umsatz;Soll/Haben;Konto;Gegenkonto;BU-Schlüssel;Buchungstext\n")
    
    for row in export_data:
        # Mathematische Brutto-Ermittlung für den DATEV-Umsatz
        netto = row['netto']
        tax_percent = row.get("tax_percent", 19.0)
        brutto = netto * (1.0 + (tax_percent / 100.0))
        
        # DATEV-Formatierung (Deutsches Komma als Dezimaltrenner)
        betrag_str = f"{brutto:.2f}".replace('.', ',')
        
        bu_schluessel = "9" if tax_percent == 19.0 else ("8" if tax_percent == 7.0 else "")
        
        # Begrenzung des Buchungstextes auf 60 Zeichen (DATEV-Limit)
        buchungstext = row['beschreibung'][:60].replace(';', ' ')
        
        output.write(f"{betrag_str};S;{row['konto_soll']};70000;{bu_schluessel};{buchungstext}\n")
        
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


# --- UI LAYOUT ---
st.title("📊 Autonome E-Rechnungs-Engine")
st.subheader("MVP: Intelligente Zeilenkontierung mit RAG-Gedächtnis")

if not client:
    st.error("Bitte stelle sicher, dass der OPENAI_API_KEY in den Umgebungsvariablen gesetzt ist.")

with st.sidebar:
    st.header("Vollständige SKR03-Stammdaten")
    df_visual = pd.DataFrame(ALL_SKR03_KONTEN)[["konto", "bezeichnung", "beschreibung"]]
    st.dataframe(df_visual, use_container_width=True)

# --- SESSION STATE INITIALISIERUNG ---
if "demo_active" not in st.session_state:
    st.session_state["demo_active"] = False

# Zwei Spalten für flexiblen Einstieg: Manueller Upload ODER Demo-Trigger
col_up, col_demo = st.columns([2, 1])

with col_up:
    uploaded_file = st.file_uploader(
        "1. Eigene E-Rechnung hochladen (XRechnung XML oder ZUGFeRD PDF)", 
        type=["xml", "pdf"]
    )
    if uploaded_file is not None:
        st.session_state["demo_active"] = False  # Demo deaktivieren, wenn manuell geladen wird

with col_demo:
    st.write("Keine E-Rechnung zur Hand?")
    if st.button("🚀 Live-Demo-Daten laden", use_container_width=True):
        st.session_state["demo_active"] = True

# Logik zur Bestimmung der Datenquelle
xml_source = None
file_name_label = ""

if uploaded_file is not None:
    xml_source = uploaded_file
    file_name_label = uploaded_file.name
    if uploaded_file.name.endswith(".pdf"):
        with st.spinner("Extrahiere ZUGFeRD-XML aus PDF..."):
            xml_bytes = extract_xml_from_zugferd(uploaded_file)
        if xml_bytes:
            xml_source = io.BytesIO(xml_bytes)
            st.info("ZUGFeRD-XML erfolgreich extrahiert!")
        else:
            st.error("Keine gültige ZUGFeRD-XML-Struktur in dieser PDF gefunden.")
            st.stop()

elif st.session_state["demo_active"]:
    demo_path = "test_invoices/steuerberater.xml"
    if os.path.exists(demo_path):
        with open(demo_path, "rb") as f:
            xml_source = io.BytesIO(f.read())
        file_name_label = "steuerberater_DEMO.xml"
        st.success("🤖 Demo-Modus aktiv: Test-Rechnung 'Dr. Steuer & Partner' geladen!")
    else:
        st.error("Demo-Datei nicht im Verzeichnis gefunden.")

# Nur ausführen, wenn eine Quelle (Upload oder Demo) existiert
if xml_source is not None:
    try:
        vendor, lines, totals = parse_e_invoice_xml(xml_source)
        st.success(f"Rechnung erfolgreich eingelesen! **Kreditor:** {vendor}")
        
        # --- SCHRITT 1: FORMALE & RECHNERISCHE PRÜFUNG ---
        st.write("### 🧮 Schritt 1: Formale & Rechnerische Feststellung")
        math_status, math_logs = check_invoice_math(lines, totals)
        
        is_error = (math_status != "RECHNERISCHE PRÜFUNG ERFOLGREICH")
        with st.expander(f"Prüfprotokoll anzeigen ({math_status})", expanded=is_error):
            for log in math_logs:
                if "❌" in log:
                    st.error(log)
                else:
                    st.success(log)
        
        if is_error:
            st.error("⚠️ KI-Verarbeitung gestoppt, da die Rechnung formale oder rechnerische Fehler aufweist.")
            st.stop()
            
        # --- SCHRITT 2: KI KONTIERUNG ---
        st.write("### 🤖 Schritt 2: Extrahierte Positionen & KI-Verarbeitung (RAG-optimiert)")
        
        if "processing_cache" not in st.session_state or st.session_state.get("current_file") != file_name_label:
            st.session_state["processing_cache"] = []
            st.session_state["current_file"] = file_name_label
            
            with st.spinner("RAG-Engine sucht passende Konten via Semantik & KI analysiert..."):
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
                    st.caption(f"Netto-Betrag: {item['amount']:.2f} EUR | 📝 Steuersatz: {item['tax_percent']}%")
                    st.caption(f"💡 *RAG-Vektor-Top-3: {', '.join([str(k['konto']) for k in opt])}*")
                
                with col2:
                    if is_valid:
                        st.metric(label="Vorgeschlagenes Konto", value=str(ki_res['konto_soll']))
                        validierte_buchungen_liste.append({
                            "netto": item['amount'],
                            "konto_soll": ki_res['konto_soll'],
                            "beschreibung": f"{vendor}: {item['description']}",
                            "tax_percent": item['tax_percent']
                        })
                    else:
                        st.error(f"Fehler: {msg}")
                
                with col3:
                    st.text_area("Buchungstext / Begründung", value=ki_res['begruendung'], key=f"text_{item['id']}_{index}", height=68)
                st.divider()  
        
        if validierte_buchungen_liste:
            st.write("### 🚀 Schritt 3: Prozess abschließen")
            datev_csv_content = create_datev_csv(validierte_buchungen_liste)
            st.download_button(
                label="Kontierung übernehmen und Export nach DATEV",
                data=datev_csv_content,
                file_name="DATEV_Buchungsstapel_Export.csv",
                mime="text/csv",
                use_container_width=True
            )
                
    except Exception as e:
        st.error(f"Fehler beim Verarbeiten der Struktur: {e}")

