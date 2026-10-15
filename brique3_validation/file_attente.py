"""File des réponses à valider (SQLite)."""
import datetime, json, sqlite3
from brique3_validation.config import BASE_FILE

SCHEMA = """CREATE TABLE IF NOT EXISTS file (
    cle TEXT PRIMARY KEY, id_question TEXT, systeme TEXT, formulation TEXT, passe INTEGER,
    objet TEXT, confiance REAL, raison TEXT, priorite INTEGER, statut TEXT DEFAULT 'en_attente',
    reponse_finale TEXT, corrections TEXT, temps_expert_s REAL, traite_par TEXT, date_traitement TEXT)"""


class FileAttente:
    def __init__(self, chemin=BASE_FILE):
        self.cx = sqlite3.connect(chemin, check_same_thread=False)
        self.cx.row_factory = sqlite3.Row
        self.cx.execute(SCHEMA)
        self.cx.commit()

    def ajouter(self, o, cle, passe):
        self.cx.execute(
            "INSERT OR REPLACE INTO file (cle, id_question, systeme, formulation, passe, objet, confiance, "
            "raison, priorite, statut) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'en_attente')",
            (cle, o["id"], o.get("systeme"), o.get("formulation"), passe, json.dumps(o, ensure_ascii=False),
             o["confiance"], o["raison"], o.get("priorite", 2)))
        self.cx.commit()

    def en_attente(self):
        return self.cx.execute(
            "SELECT * FROM file WHERE statut = 'en_attente' ORDER BY priorite, confiance").fetchall()

    def prochaine(self):
        lignes = self.en_attente()
        return lignes[0] if lignes else None

    def enregistrer(self, cle, statut, reponse_finale, corrections, temps, traite_par):
        self.cx.execute(
            "UPDATE file SET statut = ?, reponse_finale = ?, corrections = ?, temps_expert_s = ?, "
            "traite_par = ?, date_traitement = ? WHERE cle = ?",
            (statut, reponse_finale, json.dumps(corrections, ensure_ascii=False), temps, traite_par,
             datetime.datetime.now().isoformat(timespec="seconds"), cle))
        self.cx.commit()

    def statistiques(self):
        lignes = self.cx.execute("SELECT statut, COUNT(*) AS n FROM file GROUP BY statut").fetchall()
        return {l["statut"]: l["n"] for l in lignes}

    def vider(self):
        self.cx.execute("DELETE FROM file")
        self.cx.commit()