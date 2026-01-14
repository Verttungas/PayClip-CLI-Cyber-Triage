import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

from db_manager import DatabaseManager
from gemini_analyzer import GeminiAnalyzer
import evidence_downloader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_INCIDENTS_DIR = os.getenv("INCIDENTS_DIR", "./data/incidents")


class IncidentProcessor:
    
    def __init__(self):
        self.db = DatabaseManager()
        self.analyzer = GeminiAnalyzer(db_manager=self.db)
        self.base_dir = Path(BASE_INCIDENTS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info("IncidentProcessor inicializado")
    
    def run_download_cycle(self, hours_back: int = 24) -> List[Dict]:
        logger.info(f"Iniciando ciclo de descarga (últimas {hours_back}h)")
        new_incidents = evidence_downloader.download_incidents(
            hours_back=hours_back,
            db_manager=self.db
        )
        logger.info(f"Descarga completada: {len(new_incidents)} nuevos incidentes")
        return new_incidents
    
    def run_analysis_cycle(self, max_incidents: int = 10) -> Dict:
        logger.info(f"Iniciando ciclo de análisis (máx: {max_incidents})")
        
        pending = self.db.get_pending_incidents(limit=max_incidents)
        
        if not pending:
            logger.info("No hay incidentes pendientes de análisis")
            return {'analyzed': 0, 'errors': 0, 'total_tokens': 0}
        
        results = {
            'analyzed': 0,
            'errors': 0,
            'total_tokens': 0,
            'details': []
        }
        
        for incident in pending:
            incident_id = incident['incident_id']
            incident_date = incident.get('incident_date', datetime.now().strftime('%Y-%m-%d'))
            incident_dir = self.base_dir / incident_date / incident_id
            
            if not incident_dir.exists():
                logger.warning(f"Directorio no existe: {incident_dir}")
                results['errors'] += 1
                continue
            
            try:
                analysis_result = self.analyzer.analyze_incident(
                    incident_id=incident_id,
                    incident_dir=incident_dir,
                    use_rag=True
                )
                
                if analysis_result['success']:
                    self._save_analysis_to_file(incident_dir, analysis_result)
                    results['analyzed'] += 1
                    results['total_tokens'] += analysis_result.get('tokens_used', 0)
                    results['details'].append({
                        'incident_id': incident_id,
                        'verdict': analysis_result['verdict'],
                        'confidence': analysis_result['confidence']
                    })
                    logger.info(f"Analizado: {incident_id} -> {analysis_result['verdict']}")
                else:
                    results['errors'] += 1
                    logger.error(f"Error analizando {incident_id}: {analysis_result.get('error')}")
                    
            except Exception as e:
                results['errors'] += 1
                logger.error(f"Excepción analizando {incident_id}: {e}")
        
        logger.info(f"Ciclo completado: {results['analyzed']} analizados, {results['errors']} errores")
        return results
    
    def _save_analysis_to_file(self, incident_dir: Path, analysis_result: Dict):
        analysis_file = incident_dir / "analysis_result.json"
        
        output = {
            'verdict': analysis_result.get('verdict'),
            'confidence': analysis_result.get('confidence'),
            'executive_summary': analysis_result.get('executive_summary'),
            'risk_level': analysis_result.get('risk_level'),
            'incident_context': analysis_result.get('incident_context'),
            'reasoning': analysis_result.get('reasoning'),
            'indicators': analysis_result.get('indicators', []),
            'analyzed_at': datetime.now().isoformat(),
            'processing_time': analysis_result.get('processing_time')
        }
        
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Análisis guardado: {analysis_file}")
    
    def run_full_cycle(self, hours_back: int = 24, max_analysis: int = 10) -> Dict:
        started_at = datetime.now()
        run_date = started_at.strftime('%Y-%m-%d')
        
        logger.info("=" * 60)
        logger.info("INICIANDO CICLO COMPLETO DE PROCESAMIENTO")
        logger.info("=" * 60)
        
        new_incidents = self.run_download_cycle(hours_back=hours_back)
        
        analysis_results = self.run_analysis_cycle(max_incidents=max_analysis)
        
        completed_at = datetime.now()
        
        run_log = {
            'run_date': run_date,
            'incidents_downloaded': len(new_incidents),
            'incidents_analyzed': analysis_results['analyzed'],
            'total_tokens': analysis_results['total_tokens'],
            'errors': analysis_results['errors'],
            'started_at': started_at.isoformat(),
            'completed_at': completed_at.isoformat()
        }
        
        self.db.log_processing_run(run_log)
        
        logger.info("=" * 60)
        logger.info(f"CICLO COMPLETADO en {(completed_at - started_at).seconds}s")
        logger.info(f"  Descargados: {len(new_incidents)}")
        logger.info(f"  Analizados:  {analysis_results['analyzed']}")
        logger.info(f"  Errores:     {analysis_results['errors']}")
        logger.info("=" * 60)
        
        return run_log
    
    def get_incident_summary(self, incident_id: str) -> Optional[Dict]:
        incident = self.db.get_incident(incident_id)
        if not incident:
            return None
        
        analysis = self.db.get_latest_analysis(incident_id)
        
        return {
            'incident': incident,
            'analysis': analysis
        }
    
    def get_daily_summary(self, date: str = None) -> Dict:
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        incidents = self.db.get_incidents_by_date(date)
        
        summary = {
            'date': date,
            'total_incidents': len(incidents),
            'by_verdict': {},
            'by_severity': {},
            'pending_analysis': 0
        }
        
        for inc in incidents:
            sev = inc.get('severity', 'unknown')
            summary['by_severity'][sev] = summary['by_severity'].get(sev, 0) + 1
            
            if inc.get('status') == 'downloaded':
                summary['pending_analysis'] += 1
        
        for inc in incidents:
            analysis = self.db.get_latest_analysis(inc['incident_id'])
            if analysis:
                verdict = analysis.get('gemini_verdict', 'unknown')
                summary['by_verdict'][verdict] = summary['by_verdict'].get(verdict, 0) + 1
        
        return summary


def main():
    processor = IncidentProcessor()
    processor.run_full_cycle(hours_back=24, max_analysis=10)


if __name__ == "__main__":
    main()