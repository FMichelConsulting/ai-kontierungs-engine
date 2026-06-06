# Autonomous AI-Invoicing & Accounting Engine (MVP)

A production-ready Financial AI pipeline built to automate general ledger (GL) account assignment for European structured electronic invoices (EN16931 / ZUGFeRD / Factur-X) without relying blindly on probabilistic AI models. 

This repository demonstrates how to bridge the gap between strict enterprise compliance rules (deterministic logic) and advanced Large Language Models (probabilistic logic).

👉 **Live Demo:** https://ai-kontierungs-engine-4mhh4jz2j9rgisaf6km9ko.streamlit.app/

---

## 🏗️ Architectural Overview

Most AI document processors rely heavily on optical character recognition (OCR) and unstructured text extraction, leading to high error rates and logical hallucinations. This engine bypasses OCR entirely by parsing the native, structured XML metadata embedded in modern European E-invoices.

The pipeline implements a **two-stage verification and routing architecture**:

1. **The Deterministic Guardrail (Stage 1):** Before any external LLM API is touched, the engine enforces strict statutory rules under § 14 UStG (German Value Added Tax Act). It parses the header totals and individual line-item blocks to execute algorithmic calculations:
   * Line-Item Validation: Quantity * Unit Price == Line Total
   * Document Cross-Check: Sum(Line Totals) == Net Total and Net Total + Tax Total == Gross Total

   If a supplier's ERP system generates faulty or corrupted XML structures, the pipeline catches it deterministically, logs the exact error in an audit trail, and halts execution before wasting API tokens.

2. **Context-Aware RAG Retrieval & Probabilistic Alignment (Stage 2):** Once cleared by Stage 1, the item description enters a lightweight vector retrieval simulation (utilizing dynamic token similarity ranking). It extracts the top-N closest matching accounting descriptions from the enterprise's native chart of accounts (e.g., German SKR03 standard). 

This restricted context window is fed into a zero-temperature LLM instructed by strict systemic prompt guardrails. The model determines the exact booking code and generates a precise financial justification text without logical drift.

---

## 🛠️ Tech Stack & Patterns

* **Backend / Pipeline:** Python 3.10+, `xml.etree.ElementTree` (Deterministic XML Parsing)
* **AI Architecture:** OpenAI API (`gpt-4o-mini`), Retrieval-Augmented Generation (RAG)
* **Frontend Workflow:** Streamlit (Enterprise Dashboard Pattern)
* **Data Interchange:** DATEV-compliant EXTF CSV format generation (including specific input tax identification keys like `BU-Schlüssel`)
* **Quality Assurance:** Integrated programmatic regression benchmarking suite (`run_regression_tests.py`) ensuring 100% precision on edge-case core accounting scenarios.

---

## 📈 Enterprise Production Roadmap

To scale this MVP into a distributed high-throughput architecture, the following engineering steps are currently being implemented:

1. **State Machine Migration (LangGraph):** Moving from a sequential script to a cyclic graph to introduce a *Reviewer Node*. If the AI proposes an accounting code that statistical history flags as anomalous, the graph routes the prompt back to the generator node with an auto-generated critique before final submission.
2. **Advanced RAG Patterns:** Transitioning the RAG module to a dedicated Vector DB (`Qdrant` / `pgvector`) utilizing pre-retrieval Metadata Filtering (by vendor industry codes) and Cross-Encoder Re-Ranking to optimize contextual density.
3. **Microservice Decoupling:** Separating the computationally efficient XML parsing and Stage 1 math validation into a highly performant microservice (FastAPI or Spring Boot) to decouple core processing from the presentation layer.

---

## 🚀 Local Setup & Installation

Clone the repository and install the minimal required footprint:

```bash
git clone [https://github.com/FMichelConsulting/ai-kontierungs-engine.git](https://github.com/FMichelConsulting/ai-kontierungs-engine.git)
cd ai-kontierungs-engine

# Initialize environment
python -m venv venv
source venv/Scripts/activate  # On Windows use `venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt

#Set your OpenAI credentials:
export OPENAI_API_KEY="your-api-key-here"  # On Windows use `set`

#Run the interactive local interface:
streamlit run app.py

#Run the automated regression benchmark suite:
python run_regression_tests.py

