import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseManager:
    
    def __init__(self, db_path: str = "./data/incidents.db"):
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_database()
        logger.info(f"DatabaseManager inicializado con DB: {db_path}")

    def _ensure_db_directory(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"Directorio creado: {db_dir}")
    
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    file_name TEXT,
                    file_path TEXT,
                    file_type TEXT,
                    file_size INTEGER,
                    user_email TEXT,
                    cyberhaven_data TEXT,
                    status TEXT DEFAULT 'downloaded',
                    severity TEXT,
                    policy_severity TEXT,
                    incident_date DATE,
                    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    analyzed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_incidents_date ON incidents(incident_date)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity)
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT UNIQUE,
                    gemini_verdict TEXT,
                    gemini_confidence REAL,
                    gemini_reasoning TEXT,
                    gemini_raw_response TEXT,
                    executive_summary TEXT,
                    risk_level TEXT,
                    processing_time REAL,
                    tokens_used INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (incident_id) REFERENCES incidents (incident_id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT,
                    analysis_id INTEGER,
                    original_verdict TEXT,
                    corrected_verdict TEXT,
                    analyst_comment TEXT,
                    relevance_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (incident_id) REFERENCES incidents (incident_id),
                    FOREIGN KEY (analysis_id) REFERENCES analysis (id)
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processing_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date DATE,
                    incidents_downloaded INTEGER DEFAULT 0,
                    incidents_analyzed INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            ''')

            self._migrate_existing_data(cursor)
            
            conn.commit()
            logger.info("Base de datos inicializada correctamente")
            
        except sqlite3.Error as e:
            logger.error(f"Error inicializando base de datos: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def _migrate_existing_data(self, cursor):
        cursor.execute("PRAGMA table_info(incidents)")
        columns = [info[1] for info in cursor.fetchall()]
        
        migrations = {
            'severity': "ALTER TABLE incidents ADD COLUMN severity TEXT",
            'policy_severity': "ALTER TABLE incidents ADD COLUMN policy_severity TEXT",
            'incident_date': "ALTER TABLE incidents ADD COLUMN incident_date DATE",
            'downloaded_at': "ALTER TABLE incidents ADD COLUMN downloaded_at TIMESTAMP",
            'analyzed_at': "ALTER TABLE incidents ADD COLUMN analyzed_at TIMESTAMP"
        }
        
        for col, sql in migrations.items():
            if col not in columns:
                logger.info(f"Migrando DB: Agregando columna '{col}'")
                cursor.execute(sql)
    
    def insert_incident(self, incident_data: Dict) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO incidents (
                    incident_id, file_name, file_path, file_type, 
                    file_size, user_email, cyberhaven_data, status,
                    severity, policy_severity, incident_date, downloaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                incident_data.get('incident_id'),
                incident_data.get('file_name'),
                incident_data.get('file_path'),
                incident_data.get('file_type'),
                incident_data.get('file_size'),
                incident_data.get('user_email'),
                json.dumps(incident_data.get('cyberhaven_data', {})) if isinstance(incident_data.get('cyberhaven_data'), dict) else incident_data.get('cyberhaven_data'),
                incident_data.get('status', 'downloaded'),
                incident_data.get('severity'),
                incident_data.get('policy_severity'),
                incident_data.get('incident_date'),
                datetime.now().isoformat()
            ))
            conn.commit()
            logger.info(f"Incidente insertado: {incident_data.get('incident_id')}")
            return True
            
        except sqlite3.IntegrityError:
            logger.debug(f"Incidente ya existe: {incident_data.get('incident_id')}")
            return False
        except sqlite3.Error as e:
            logger.error(f"Error insertando incidente: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def incident_exists(self, incident_id: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT 1 FROM incidents WHERE incident_id = ? LIMIT 1', (incident_id,))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def is_incident_analyzed(self, incident_id: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT 1 FROM analysis WHERE incident_id = ? LIMIT 1', (incident_id,))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def get_pending_incidents(self, limit: int = 10) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT i.* FROM incidents i
                LEFT JOIN analysis a ON i.incident_id = a.incident_id
                WHERE a.id IS NULL AND i.status = 'downloaded'
                ORDER BY i.downloaded_at ASC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_incident(self, incident_id: str) -> Optional[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM incidents WHERE incident_id = ?', (incident_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    
    def get_incidents_by_date(self, date: str) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT * FROM incidents 
                WHERE incident_date = ?
                ORDER BY downloaded_at DESC
            ''', (date,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_incident_status(self, incident_id: str, status: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE incidents SET status = ? WHERE incident_id = ?", (status, incident_id))
            if status == 'analyzed':
                cursor.execute("UPDATE incidents SET analyzed_at = ? WHERE incident_id = ?", 
                             (datetime.now().isoformat(), incident_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating status: {e}")
            return False
        finally:
            conn.close()

    def insert_analysis(self, analysis_data: Dict) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO analysis (
                    incident_id, gemini_verdict, gemini_confidence, 
                    gemini_reasoning, gemini_raw_response, executive_summary,
                    risk_level, processing_time, tokens_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                analysis_data.get('incident_id'),
                analysis_data.get('gemini_verdict'),
                analysis_data.get('gemini_confidence'),
                analysis_data.get('gemini_reasoning'),
                analysis_data.get('gemini_raw_response'),
                analysis_data.get('executive_summary'),
                analysis_data.get('risk_level'),
                analysis_data.get('processing_time'),
                analysis_data.get('tokens_used', 0)
            ))
            conn.commit()
            analysis_id = cursor.lastrowid
            
            self.update_incident_status(analysis_data.get('incident_id'), 'analyzed')
            
            logger.info(f"Análisis insertado ID: {analysis_id}")
            return analysis_id
        except sqlite3.Error as e:
            logger.error(f"Error insertando análisis: {e}")
            conn.rollback()
            return -1
        finally:
            conn.close()

    def get_latest_analysis(self, incident_id: str) -> Optional[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT * FROM analysis 
                WHERE incident_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (incident_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def insert_feedback(self, feedback_data: Dict) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO feedback (
                    incident_id, analysis_id, original_verdict, 
                    corrected_verdict, analyst_comment, relevance_score
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                feedback_data.get('incident_id'),
                feedback_data.get('analysis_id'),
                feedback_data.get('original_verdict'),
                feedback_data.get('corrected_verdict'),
                feedback_data.get('analyst_comment'),
                feedback_data.get('relevance_score')
            ))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error insertando feedback: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def get_feedback_for_rag(self, limit: int = 5) -> List[Dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT f.*, i.file_name, i.file_type, a.gemini_reasoning as original_reasoning
                FROM feedback f
                JOIN incidents i ON f.incident_id = i.incident_id
                LEFT JOIN analysis a ON f.analysis_id = a.id
                WHERE f.corrected_verdict != f.original_verdict
                ORDER BY f.relevance_score DESC, f.created_at DESC
                LIMIT ?
            ''', (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def log_processing_run(self, run_data: Dict) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO processing_log (
                    run_date, incidents_downloaded, incidents_analyzed,
                    total_tokens, errors, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_data.get('run_date'),
                run_data.get('incidents_downloaded', 0),
                run_data.get('incidents_analyzed', 0),
                run_data.get('total_tokens', 0),
                run_data.get('errors', 0),
                run_data.get('started_at'),
                run_data.get('completed_at')
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_database_stats(self) -> Dict:
        conn = self._get_connection()
        cursor = conn.cursor()
        stats = {}
        try:
            cursor.execute("SELECT status, COUNT(*) as count FROM incidents GROUP BY status")
            stats['incidents_by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
            
            cursor.execute("SELECT COUNT(*) as count FROM analysis")
            stats['total_analyses'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM feedback")
            stats['total_feedback'] = cursor.fetchone()['count']
            
            cursor.execute("SELECT SUM(tokens_used) as total FROM analysis")
            result = cursor.fetchone()['total']
            stats['total_tokens_used'] = result if result else 0
            
            cursor.execute("SELECT COUNT(*) as total FROM feedback")
            total_fb = cursor.fetchone()['total']
            if total_fb > 0:
                cursor.execute("SELECT COUNT(*) as correct FROM feedback WHERE original_verdict = corrected_verdict")
                correct_fb = cursor.fetchone()['correct']
                stats['ai_accuracy'] = (correct_fb / total_fb) * 100
            else:
                stats['ai_accuracy'] = 0.0
            
            cursor.execute('''
                SELECT incident_date, COUNT(*) as count 
                FROM incidents 
                WHERE incident_date >= date('now', '-7 days')
                GROUP BY incident_date
                ORDER BY incident_date DESC
            ''')
            stats['incidents_last_7_days'] = {row['incident_date']: row['count'] for row in cursor.fetchall()}
            
            return stats
        except sqlite3.Error as e:
            logger.error(f"Error getting stats: {e}")
            return {}
        finally:
            conn.close()

    def clear_old_data(self, days: int = 30) -> Tuple[int, int, int]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            cursor.execute("DELETE FROM feedback WHERE incident_id IN (SELECT incident_id FROM incidents WHERE incident_date < ?)", (date_limit,))
            deleted_feedback = cursor.rowcount
            
            cursor.execute("DELETE FROM analysis WHERE incident_id IN (SELECT incident_id FROM incidents WHERE incident_date < ?)", (date_limit,))
            deleted_analysis = cursor.rowcount
            
            cursor.execute("DELETE FROM incidents WHERE incident_date < ?", (date_limit,))
            deleted_incidents = cursor.rowcount
            
            conn.commit()
            return (deleted_incidents, deleted_analysis, deleted_feedback)
        except sqlite3.Error as e:
            logger.error(f"Error clearing old data: {e}")
            conn.rollback()
            return (0, 0, 0)
        finally:
            conn.close()