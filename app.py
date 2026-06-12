import streamlit as st
import xml.etree.ElementTree as ET
import json
import pandas as pd
import io
import os
import numpy as np
from openai import OpenAI
from pypdf import PdfReader
import contextlib
from supabase import create_client, Client

# Kaskadierender Import für absolute Kompatibilität mit dem Analytics-Fork
HAS_ANALYTICS = False
streamlit_analytics = None

try:
    import streamlit_analytics2 as streamlit_analytics
    HAS_ANALYTICS = True
    print("[INFO] Modernes streamlit_analytics2 erfolgreich geladen.")
except ModuleNotFoundError:
    try:
        import streamlit_analytics
        HAS_ANALYTICS = True
        print("[INFO] Klassisches streamlit_analytics erfolgreich geladen.")
    except ModuleNotFoundError:
        HAS_ANALYTICS = False
        print("[WARN] Kein Analytics-Modul gefunden. Nutze passiven Fallback-Modus.")

st.set_page_config(page_title="AI Kontierungs-Engine MVP", page_icon="📊", layout="wide")

try:
    client = OpenAI()
except Exception:
    client = None

# ==============================================================================
# SUPABASE ENTERPRISE DATABASE LAYER (Mandantenfähig & pgvector-gestützt)
# ==============================================================================
@st.cache_resource
def init_supabase() -> Client:
    """Initialisiert den gehärteten Admin-Client via Service-Role Key."""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase-Verbindungsfehler: Secrets unvollständig konfiguriert ({e})")
        return None

def log_audit_event(company_id: str, item_key: str, event_type: str, konto_soll: int, actor: str, justification: str):
    """
    Schreibt einen unveränderbaren Eintrag inklusive Mandanten-ID in das PostgreSQL-Audit-Log.
    Die Inkrementierung der Spalte 'version' erfolgt atomar via DB-Trigger.
    """
    supabase = init_supabase()
    if not supabase:
        return

    event_data = {
        "company_id": company_id,
        "item_key": item_key,
        "event_type": event_type,
        "konto_soll": int(konto_soll),
        "actor": actor,
        "justification": justification
    }
    
    try:
        supabase.table("invoice_audit_log").insert(event_data).execute()
    except Exception as e:
        st.error(f"🚨 KRITISCHER COMPLIANCE-FEHLER: Audit-Log-Schreiben fehlgeschlagen: {e}")

def load_user_override_from_db(company_id: str, buchungstext: str) -> int:
    """Lädt die historische Korrektur für einen spezifischen Mandanten aus PostgreSQL."""
    supabase = init_supabase()
    if not supabase:
        return None
    try:
        res = supabase.table("user_knowledge_base")\
            .select("konto_soll")\
            .eq("company_id", company_id)\
            .eq("buchungstext", buchungstext)\
            .maybe_single()\
            .execute()
        return res.data["konto_soll"] if res.data else None
    except Exception:
        return None

def save_user_override_to_db(company_id: str, buchungstext: str, korrigiertes_konto: int):
    """Speichert eine manuelle Korrektur permanent und mandantenabhängig via SQL-Upsert."""
    supabase = init_supabase()
    if not supabase:
        return
    payload = {
        "company_id": company_id,
        "buchungstext": buchungstext,
        "konto_soll": int(korrigiertes_konto)
    }
    try:
        supabase.table("user_knowledge_base").upsert(payload, on_conflict="company_id,buchungstext").execute()
    except Exception as e:
        st.error(f"Fehler beim Speichern des Cloud-Overrides: {e}")

# ==============================================================================
# HARDENED RAG-RETRIEVER VIA PGVECTOR
# ==============================================================================
def get_embedding(text, model="text-embedding-3-small"):
    """Erzeugt einen semantischen Vektor für den Belegtext über die OpenAI-API."""
    if not client:
        return None
    text = text.replace("\n", " ")
    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        st.error(f"Fehler bei der Embedding-Generierung: {e}")
        return None

def get_relevant_accounts_pgvector(item_description: str, target_system: str, top_n=3):
    """
    Nutzt die native pgvector-Erweiterung von PostgreSQL für eine 
    hochperformante Ähnlichkeitssuche direkt in der Cloud-Datenbank.
    """
    supabase = init_supabase()
    if not supabase:
        return []
        
    query_embedding = get_embedding(item_description)
    if not query_embedding:
        return []
        
    try:
        response = supabase.rpc("match_accounts", {
            "query_embedding": query_embedding,
            "match_threshold": 0.2,
            "match_count": top_n,
            "filter_system": target_system
        }).execute()
        
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Fehler bei pgvector-Abfrage: {e}")
        return []

# ==============================================================================
# MATHEMATISCHE PRÜF-ENGINE & UTILS
# ==============================================================================
def check_invoice_math(lines, invoice_totals):
    """Validiert die Grundrechenarten auf Positionsebene sowie die globalen Summen."""
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

def parse_e_invoice_xml(xml_file):
    """Extrahiert semantische Buchungsdaten aus CII und UBL XML-Strukturen."""
    tree = ET.parse(xml_file)
    root = tree.getroot()
    tag = root.tag
    
    invoice_totals = {"gesamt_netto": 0.0, "gesamt_steuer": 0.0, "gesamt_brutto": 0.0}
    
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
    """Generiert eine strukturierte, regelbasierte Vorkontierung via LLM."""
    bereinigte_optionen = []
    for opt in gefilterte_optionen:
        bereinigte_optionen.append({
            "konto": opt["konto"],
            "bezeichnung": opt["bezeichnung"],
            "beschreibung": opt["beschreibung"]
        })

    system_prompt = (
        "Du bist ein extrem pingeliger, konservativer deutscher Finanzbuchhalter.\n"
        "Deine Aufgabe ist es, die Position exakt und ohne kreative Auslegung auf den bereitgestellten Kontenrahmen zu kontieren.\n\n"
        "STRIKTE REGELN FÜR DEINE ENTSCHEIDUNG:\n"
        "1. Physische oder digitale Bücher, Fachliteratur und Dokumentationen sind ZWINGEND als Fachliteratur/Bücher (z.B. 4940) zu kontieren.\n"
        "2. IT-Entwicklung, Programmierung oder Projektarbeit von externen Freelancern sind Kern-Fremdleistungen.\n"
        "3. Wähle das Konto, dessen Beschreibung primär und direkt den Belegtext trifft. Keine logischen Brücken bauen.\n\n"
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

def create_datev_csv(export_data):
    """Erzeugt einen validen DATEV-konformen EXTF-Buchungsstapel."""
    output = io.StringIO()
    output.write("EXTF;700;1;Buchungsstapel;;1;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;\n")
    output.write("Umsatz;Soll/Haben;Konto;Gegenkonto;BU-Schlüssel;Buchungstext\n")
    
    for row in export_data:
        netto = row['netto']
        tax_percent = row.get("tax_percent", 19.0)
        brutto = netto * (1.0 + (tax_percent / 100.0))
        
        betrag_str = f"{brutto:.2f}".replace('.', ',')
        bu_schluessel = "9" if tax_percent == 19.0 else ("8" if tax_percent == 7.0 else "")
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

def on_erp_system_change():
    if "processing_cache" in st.session_state:
        del st.session_state["processing_cache"]
    if "current_file" in st.session_state:
        del st.session_state["current_file"]
    st.session_state["demo_active"] = False

# ==============================================================================
# UI RUNTIME LAYOUT
# ==============================================================================
if HAS_ANALYTICS:
    try:
        cloud_password = st.secrets.get("ANALYTICS_PASSWORD", "lokal_dummy_pass")
    except Exception:
        cloud_password = "lokal_dummy_pass"
    
    if "analytics" in st.query_params and st.query_params["analytics"] == "on":
        analytics_context = streamlit_analytics.track(unsafe_password=cloud_password)
    else:
        analytics_context = streamlit_analytics.track()
else:
    analytics_context = contextlib.nullcontext()

with analytics_context:
    st.title("📊 Autonome E-Rechnungs-Engine")
    st.subheader("Multi-ERP Routing Engine mit pgvector Ledger & Multi-Tenancy Isolation")

    # --- GOVERNANCE CONTROL CENTER (SIDEBAR) ---
    st.sidebar.header("🏢 Mandanten-Governance")
    current_tenant = st.sidebar.selectbox(
        "Aktiver Unternehmens-Mandant (Data Isolation):",
        options=["DE-Mittelstand-GmbH", "FR-Holding-SAS", "Rosenheim-Tech-KG"]
    )
    
    st.sidebar.markdown("---")
    target_system = st.sidebar.radio(
        "🎯 Ziel-ERP / Rechnungslegung:",
        ["DATEV (SKR03)", "SAP (YCOA)", "Kameralistik (Kommune)"],
        on_change=on_erp_system_change
    )

    if "demo_active" not in st.session_state:
        st.session_state["demo_active"] = False

    col_up, col_demo = st.columns([2, 1])

    with col_up:
        uploaded_file = st.file_uploader(
            "1. Eigene E-Rechnung hochladen (XRechnung XML oder ZUGFeRD PDF)", 
            type=["xml", "pdf"]
        )
        if uploaded_file is not None:
            st.session_state["demo_active"] = False

    with col_demo:
        st.write("Keine E-Rechnung zur Hand?")
        if st.button("🚀 Live-Demo-Daten laden", use_container_width=True):
            st.session_state["demo_active"] = True

    xml_source = None
    file_name_label = ""

    if uploaded_file is not None:
        xml_source = uploaded_file
        file_name_label = f"{target_system}_{uploaded_file.name}"
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
            file_name_label = f"{target_system}_steuerberater_DEMO.xml"
            st.success("🤖 Demo-Modus aktiv: Test-Rechnung geladen!")
        else:
            st.error("Demo-Datei nicht im Verzeichnis gefunden.")

    if xml_source is not None:
        try:
            vendor, lines, totals = parse_e_invoice_xml(xml_source)
            st.success(f"Rechnung erfolgreich eingelesen! **Kreditor:** {vendor} | **Mandant:** {current_tenant}")
            
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
                st.error("⚠️ KI-Verarbeitung gestoppt aufgrund formaler Rechnungsfehler.")
                st.stop()
                
            # --- SCHRITT 2: KI KONTIERUNG VIA PGVECTOR & INTERAKTIVES OVERRIDE ---
            st.write("### 🤖 Schritt 2: Extrahierte Positionen & KI-Routing")
            st.info("💡 **Fachexperte schlägt KI:** Manuelle Korrekturen werden persistent im Cloud-Wissensspeicher des Mandanten abgelegt.")
            
            # Cache initialisieren und KI-Analyse EINMALIG pro Beleg ausführen
            if "processing_cache" not in st.session_state or st.session_state.get("current_file") != file_name_label:
                st.session_state["processing_cache"] = []
                st.session_state["current_file"] = file_name_label
                
                with st.spinner("Führe pgvector-Ähnlichkeitssuche auf Cloud-Kontenrahmen aus..."):
                    for item in lines:
                        # Aufruf des optimierten pgvector-Suchen-Verfahrens direkt in Supabase
                        gefilterte_konten = get_relevant_accounts_pgvector(item["description"], target_system, top_n=3)
                        
                        if gefilterte_konten:
                            top_score = gefilterte_konten[0]["similarity_score"]
                            ki_res = get_ki_kontierung(item, vendor, gefilterte_konten)
                        else:
                            top_score = 0.0
                            ki_res = {"konto_soll": 9999, "begruendung": "Keine passenden Stammkonten via Vektor-Abfrage gefunden. Fallback aktiv."}
                        
                        item_key = f"{file_name_label} | Pos {item['id']}: {item['description']}"
                        
                        # 🏛️ COMPLIANCE-LOG: Initialen KI-Vorschlag atomar für diesen Mandanten sichern (Version 1)
                        log_audit_event(
                            company_id=current_tenant,
                            item_key=item_key,
                            event_type="AI_PROPOSAL",
                            konto_soll=ki_res["konto_soll"],
                            actor="AI-Agent (gpt-4o-mini)",
                            justification=ki_res.get("begruendung", "Automatische Vorkontierung via pgvector-RPC.")
                        )
                        
                        st.session_state["processing_cache"].append({
                            "item": item,
                            "ki_res": ki_res,
                            "confidence_score": top_score,
                            "gefilterte_konten": gefilterte_konten
                        })

            validierte_buchungen_liste = []
            
            for index, cached_item in enumerate(st.session_state["processing_cache"]):
                item = cached_item["item"]
                ki_res = cached_item["ki_res"]
                opt = cached_item["gefilterte_konten"]
                score = cached_item.get("confidence_score", 0.0)
                
                text_key = item["description"]
                ai_acc = ki_res.get("konto_soll")
                
                # Mandantenabhängige Prüfung historischer Benutzer-Entscheidungen aus Supabase
                db_history_account = load_user_override_from_db(current_tenant, text_key)
                has_history = db_history_account is not None
                default_account = db_history_account if has_history else ai_acc
                
                # Fallback für Selectbox-Sicherheit aufbauen
                available_accounts = [k["konto"] for k in opt] if opt else [9999]
                if default_account not in available_accounts:
                    available_accounts.insert(0, default_account)
                
                account_labels = {k["konto"]: f"{k['konto']} - {k['bezeichnung']}" for k in opt} if opt else {9999: "Fallback-Konto"}
                if default_account not in account_labels:
                    account_labels[default_account] = f"{default_account} - (Vorschlag/Historie)"

                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 3])
                    with col1:
                        st.markdown(f"**Pos {item['id']}:** {item['description']}")
                        st.caption(f"Netto: {item['amount']:.2f} EUR | 📝 MwSt: {item['tax_percent']}%")
                        if opt:
                            st.caption(f"💡 *pgvector-Top-3: {', '.join([str(k['konto']) for k in opt])}*")
                    
                    with col2:
                        selected_acc = st.selectbox(
                            f"Ziel-Konto anpassen (Pos {item['id']}):",
                            options=available_accounts,
                            index=available_accounts.index(default_account),
                            format_func=lambda x: account_labels.get(x, str(x)),
                            key=f"select_pos_{item['id']}_{index}"
                        )
                        
                        if selected_acc != ai_acc:
                            if has_history and selected_acc == db_history_account:
                                protokoll = f"Historisches Mandanten-Wissen genutzt (KI empfahl {ai_acc})"
                            else:
                                protokoll = f"Manuell korrigiert (KI empfahl {ai_acc} mit Conf {score:.2f})"
                                # Permanent und mandantenisoliert in der Cloud sichern
                                if db_history_account != selected_acc:
                                    save_user_override_to_db(current_tenant, text_key, selected_acc)
                        else:
                            if has_history:
                                protokoll = f"Historisches Mandanten-Wissen genutzt (Identisch mit KI-Vorschlag)"
                            else:
                                protokoll = f"Automatisch kontiert via KI (Conf: {score:.2f})"
                        
                        if has_history:
                            st.success("🔄 Gelernt (Cloud DB)")
                        elif score >= 0.35:
                            st.success(f"🟢 KI Sicher")
                        else:
                            st.warning(f"🟡 Prüfung empfohlen")
                            
                        validierte_buchungen_liste.append({
                            "netto": item['amount'],
                            "konto_soll": selected_acc,
                            "beschreibung": f"{vendor}: {item['description']}",
                            "tax_percent": item['tax_percent'],
                            "audit_trail": protokoll,
                            "raw_item_desc": item['description'],
                            "ki_original_acc": ai_acc
                        })
                    
                    with col3:
                        st.text_area("KI-Originalbegründung (Read-Only)", value=ki_res.get('begruendung', ''), key=f"text_{item['id']}_{index}", height=68, disabled=True)
                st.markdown("<br>", unsafe_allow_html=True)
            
            # --- SCHRITT 3: COMPLIANCE EXPORT & AUDIT TRAIL ---
            if validierte_buchungen_liste:
                st.write("### 🚀 Schritt 3: Prozess abschließen")
                
                df_export = pd.DataFrame(validierte_buchungen_liste)[["netto", "konto_soll", "beschreibung", "tax_percent", "audit_trail"]]
                df_export.columns = ["Netto-Betrag", "Ziel-Konto/Titel", "Buchungstext", "MwSt-%", "Audit-Trail / Protokoll"]
                st.write("#### 📋 Vorschau der zu exportierenden Buchungssätze:")
                st.dataframe(df_export, use_container_width=True)
                
                if st.button("Prozess finalisieren & Audit-Logs in Cloud sichern", use_container_width=True, type="primary"):
                    with st.spinner("Synchronisiere immutable Ledger mit PostgreSQL..."):
                        for row in validierte_buchungen_liste:
                            if row["konto_soll"] != row["ki_original_acc"]:
                                log_audit_event(
                                    company_id=current_tenant,
                                    item_key=f"{file_name_label} | Pos {row['beschreibung']}",
                                    event_type="USER_OVERRIDE",
                                    konto_soll=row["konto_soll"],
                                    actor="Fachexperte (UI)",
                                    justification=row["audit_trail"]
                                )
                        st.success(f"✅ Sämtliche Zustandsänderungen wurden für den Mandanten '{current_tenant}' revisionssicher im PostgreSQL-Ledger festgeschrieben.")
                
                if "DATEV" in target_system:
                    datev_csv_content = create_datev_csv(validierte_buchungen_liste)
                    st.download_button(
                        label="📥 Export nach DATEV (EXTF) herunterladen",
                        data=datev_csv_content,
                        file_name=f"DATEV_EXTF_{current_tenant}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    csv_buffer = io.StringIO()
                    df_export.to_csv(csv_buffer, index=False, sep=";", encoding="utf-8-sig")
                    
                    st.download_button(
                        label=f"📥 Export für {target_system} herunterladen",
                        data=csv_buffer.getvalue(),
                        file_name=f"{target_system.replace(' ', '_')}_{current_tenant}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
        except Exception as e:
            st.error(f"Fehler beim Verarbeiten der Struktur: {e}")
            