import unittest
from unittest.mock import patch, MagicMock
# Importiere die neue Repository-Klasse statt der alten globalen Funktion
from app import TenantRepository 

class TestInvoiceEngineDatabase(unittest.TestCase):

    @patch('app.get_embedding')
    def test_get_relevant_accounts_pgvector_success(self, mock_get_embedding):
        """Testet, ob die pgvector-Logik des Repositories die RPC-Antwort der DB korrekt verarbeitet."""
        
        # 1. Mocking des OpenAI-Embeddings (Gibt einen fiktiven Vektor zurück)
        mock_get_embedding.return_value = [0.1] * 1536
        
        # 2. Mocking des Supabase-Clients (wird direkt an das Repo übergeben)
        mock_client = MagicMock()
        mock_rpc = MagicMock()
        
        # Simuliere die Antwort aus der PostgreSQL-Funktion 'match_accounts'
        mock_rpc.execute.return_value.data = [
            {"konto": 4940, "bezeichnung": "Zeitschriften/Bücher", "beschreibung": "Fachliteratur", "similarity_score": 0.85},
            {"konto": 4950, "bezeichnung": "Rechts- und Beratungskosten", "beschreibung": "Anwalt", "similarity_score": 0.42}
        ]
        
        mock_client.rpc.return_value = mock_rpc

        # 3. Instanziierung des Repositories mit dem gemockten Client und einer Test-Mandanten-ID
        repo = TenantRepository(supabase_client=mock_client, company_id="DE-Mittelstand-GmbH")

        # 4. Ausführung der gekapselten Methode
        results = repo.get_relevant_accounts_pgvector(
            item_description="Fachbuch über Steuerrecht", 
            target_system="DATEV (SKR03)", 
            top_n=2
        )

        # 5. Assertions (Prüfung der fachlichen Korrektheit)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["konto"], 4940)
        self.assertGreater(results[0]["similarity_score"], results[1]["similarity_score"])
        
        # Prüfen, ob der RPC-Aufruf über den Client mit den exakten Parametern gefeuert wurde
        mock_client.rpc.assert_called_once_with("match_accounts", {
            "query_embedding": [0.1] * 1536,
            "match_threshold": 0.2,
            "match_count": 2,
            "filter_system": "DATEV (SKR03)"
        })

    @patch('app.get_embedding')
    def test_get_relevant_accounts_pgvector_db_failure(self, mock_get_embedding):
        """Testet das robuste Fallback-Verhalten bei einem RPC-Fehler."""
        mock_get_embedding.return_value = [0.1] * 1536
        mock_client = MagicMock()
        
        # Simuliere, dass rpc() aufgrund eines Verbindungsabrisses eine Exception wirft
        mock_client.rpc.side_effect = Exception("Database connection lost")
        
        repo = TenantRepository(supabase_client=mock_client, company_id="DE-Mittelstand-GmbH")
        results = repo.get_relevant_accounts_pgvector("Testleitung", "DATEV (SKR03)")
        
        # Erwartetes Verhalten laut app.py: Eine leere Liste wird zurückgegeben, kein App-Absturz
        self.assertEqual(results, [])

    def test_tenant_repository_init_security_alert(self):
        """Sicherheits-Test: Prüft, ob das Repo die Arbeit ohne company_id blockiert."""
        mock_client = MagicMock()
        with self.assertRaises(ValueError):
            TenantRepository(supabase_client=mock_client, company_id="")

if __name__ == '__main__':
    unittest.main()

    