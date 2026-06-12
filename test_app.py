import unittest
from unittest.mock import patch, MagicMock
from app import get_relevant_accounts_pgvector

class TestInvoiceEngineDatabase(unittest.TestCase):

    @patch('app.init_supabase')
    @patch('app.get_embedding')
    def test_get_relevant_accounts_pgvector_success(self, mock_get_embedding, mock_init_supabase):
        """Testet, ob die pgvector-Logik die RPC-Antwort der DB korrekt verarbeitet."""
        
        # 1. Mocking des OpenAI-Embeddings (Gibt einen fiktiven Vektor zurück)
        mock_get_embedding.return_value = [0.1] * 1536
        
        # 2. Mocking der kaskadierenden Supabase-Client-Struktur
        mock_client = MagicMock()
        mock_rpc = MagicMock()
        
        # Simuliere die Antwort, die normalerweise aus der PostgreSQL-Funktion 'match_accounts' kommt
        mock_rpc.execute.return_value.data = [
            {"konto": 4940, "bezeichnung": "Zeitschriften/Bücher", "beschreibung": "Fachliteratur", "similarity_score": 0.85},
            {"konto": 4950, "bezeichnung": "Rechts- und Beratungskosten", "beschreibung": "Anwalt", "similarity_score": 0.42}
        ]
        
        mock_client.rpc.return_value = mock_rpc
        mock_init_supabase.return_value = mock_client

        # 3. Ausführung der gehärteten Funktion
        results = get_relevant_accounts_pgvector(
            item_description="Fachbuch über Steuerrecht", 
            target_system="DATEV (SKR03)", 
            top_n=2
        )

        # 4. Assertions (Prüfung der fachlichen Korrektheit)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["konto"], 4940)
        self.assertGreater(results[0]["similarity_score"], results[1]["similarity_score"])
        
        # Prüfen, ob der RPC-Aufruf mit den exakten Parametern gefeuert wurde
        mock_client.rpc.assert_called_once_with("match_accounts", {
            "query_embedding": [0.1] * 1536,
            "match_threshold": 0.2,
            "match_count": 2,
            "filter_system": "DATEV (SKR03)"
        })

    @patch('app.init_supabase')
    def test_get_relevant_accounts_pgvector_db_failure(self, mock_init_supabase):
        """Testet das robuste Fallback-Verhalten bei einem Datenbank-Verbindungsabriss."""
        # Supabase liefert None oder wirft eine Exception
        mock_init_supabase.return_value = None
        
        results = get_relevant_accounts_pgvector("Testleitung", "DATEV (SKR03)")
        
        # Erwartetes Verhalten laut app.py: Eine leere Liste wird zurückgegeben, kein App-Absturz
        self.assertEqual(results, [])

if __name__ == '__main__':
    unittest.main()
    