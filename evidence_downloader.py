import os
import boto3
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import List, Dict, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CYBERHAVEN_TOKEN = os.getenv("CYBERHAVEN_API_KEY")
CYBERHAVEN_BASE_URL = os.getenv("CYBERHAVEN_API_URL", "https://payclip.cyberhaven.io/public")
BUCKET_NAME = os.getenv("AWS_S3_BUCKET", "clip-cyberhaven-upload")
BASE_INCIDENTS_DIR = os.getenv("INCIDENTS_DIR", "./data/incidents")

SEVERITY_FILTER = ["high", "critical"]


def get_token() -> Optional[str]:
    if not CYBERHAVEN_TOKEN:
        logger.error("CYBERHAVEN_API_KEY no configurada")
        return None
    url = f"{CYBERHAVEN_BASE_URL}/v2/auth/token/access"
    try:
        logger.info("Obteniendo access token...")
        resp = requests.post(url, json={"refresh_token": CYBERHAVEN_TOKEN}, timeout=10)
        resp.raise_for_status()
        return resp.json()['access_token']
    except Exception as e:
        logger.error(f"Error obteniendo token: {e}")
        return None


def get_date_directory(incident_date: str = None) -> Path:
    if incident_date is None:
        incident_date = datetime.utcnow().strftime('%Y-%m-%d')
    date_dir = Path(BASE_INCIDENTS_DIR) / incident_date
    date_dir.mkdir(parents=True, exist_ok=True)
    return date_dir


def download_from_s3(file_hash: str, output_path: str) -> bool:
    s3 = boto3.client('s3')
    try:
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=file_hash)
        
        if 'Contents' not in response:
            logger.warning(f"No encontrado en S3: {file_hash[:20]}...")
            return False

        target_key = None
        for obj in response['Contents']:
            key = obj['Key']
            if not key.endswith('.html') and not key.endswith('.json'):
                target_key = key
                break

        if not target_key:
            return False

        s3.download_file(BUCKET_NAME, target_key, output_path)
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"Descargado: {output_path} ({file_size_mb:.2f} MB)")
        return True

    except Exception as e:
        logger.error(f"Error S3: {e}")
        return False


def extract_file_info(incident: Dict) -> Tuple[str, Optional[str], Optional[str], str]:
    file_info = {}
    
    event_details = incident.get('event_details', {})
    start_event = event_details.get('start_event', {})
    source = start_event.get('source', {})
    
    if 'file' in source:
        file_info = source['file']
    elif 'file_info' in incident:
        file_info = incident['file_info']
    
    file_name = file_info.get('name', 'unknown')
    sha256 = file_info.get('sha256_hash')
    md5 = file_info.get('md5_hash')
    
    if file_name != 'unknown' and '.' in file_name:
        extension = file_name.split('.')[-1]
    else:
        extension = file_info.get('extension', 'bin')
    
    return file_name, sha256, md5, extension


def extract_incident_metadata(incident: Dict) -> Dict:
    user_info = incident.get('user', {})
    policy_info = incident.get('policy', {})
    dataset_info = incident.get('dataset', {})
    
    event_time = incident.get('event_time', '')
    if event_time:
        try:
            incident_date = datetime.fromisoformat(event_time.replace('Z', '+00:00')).strftime('%Y-%m-%d')
        except:
            incident_date = datetime.utcnow().strftime('%Y-%m-%d')
    else:
        incident_date = datetime.utcnow().strftime('%Y-%m-%d')
    
    return {
        'incident_id': incident.get('id'),
        'user_email': user_info.get('id', user_info.get('email', 'unknown')),
        'severity': dataset_info.get('sensitivity', 'unknown'),
        'policy_severity': policy_info.get('severity', 'unknown'),
        'policy_name': policy_info.get('name', 'unknown'),
        'incident_date': incident_date,
        'event_time': event_time
    }


def compress_metadata_for_storage(incident: Dict) -> Dict:
    event_details = incident.get('event_details', {})
    start_event = event_details.get('start_event', {})
    
    return {
        'id': incident.get('id'),
        'event_time': incident.get('event_time'),
        'user': incident.get('user', {}),
        'policy': {
            'name': incident.get('policy', {}).get('name'),
            'severity': incident.get('policy', {}).get('severity')
        },
        'dataset': {
            'name': incident.get('dataset', {}).get('name'),
            'sensitivity': incident.get('dataset', {}).get('sensitivity')
        },
        'action': start_event.get('action', {}),
        'source': start_event.get('source', {}),
        'destination': start_event.get('destination', {}),
        'content_inspection': incident.get('content_inspection', {})
    }


def process_incident(incident: Dict, base_dir: Path) -> Dict:
    incident_id = incident.get('id')
    incident_dir = base_dir / incident_id
    incident_dir.mkdir(exist_ok=True)
    
    metadata_path = incident_dir / "metadata.json"
    compressed_metadata = compress_metadata_for_storage(incident)
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(compressed_metadata, f, indent=2, ensure_ascii=False)
    
    file_name, sha256, md5, extension = extract_file_info(incident)
    extracted = extract_incident_metadata(incident)
    
    file_downloaded = False
    final_file_path = None
    
    if sha256:
        output_filename = file_name if file_name != 'unknown' else f"file.{extension}"
        output_path = incident_dir / output_filename
        
        if download_from_s3(sha256, str(output_path)):
            file_downloaded = True
            final_file_path = str(output_path)
        elif md5 and download_from_s3(md5, str(output_path)):
            file_downloaded = True
            final_file_path = str(output_path)
    
    return {
        'incident_id': incident_id,
        'file_name': file_name,
        'file_path': final_file_path,
        'file_type': extension,
        'file_size': os.path.getsize(final_file_path) if final_file_path and os.path.exists(final_file_path) else 0,
        'user_email': extracted['user_email'],
        'severity': extracted['severity'],
        'policy_severity': extracted['policy_severity'],
        'incident_date': extracted['incident_date'],
        'cyberhaven_data': compressed_metadata,
        'status': 'downloaded',
        'has_file': file_downloaded
    }


def fetch_filtered_incidents(token: str, hours_back: int = 24, page_size: int = 50) -> List[Dict]:
    start_time = (datetime.utcnow() - timedelta(hours=hours_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    payload = {
        "filter": {
            "dataset_sensitivities": SEVERITY_FILTER,
            "policy_severities": SEVERITY_FILTER,
            "start_time": start_time
        },
        "page_request": {
            "size": page_size,
            "sort_by": "event_time",
            "sort_direction": "DESC"
        }
    }
    
    try:
        resp = requests.post(
            f"{CYBERHAVEN_BASE_URL}/v2/incidents/list",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        incidents = resp.json().get('resources', [])
        logger.info(f"Incidentes HIGH/CRITICAL encontrados: {len(incidents)}")
        return incidents
    except Exception as e:
        logger.error(f"Error obteniendo incidentes: {e}")
        return []


def download_incidents(hours_back: int = 24, db_manager=None) -> List[Dict]:
    logger.info("=" * 60)
    logger.info("CYBER-TRIAGE: DESCARGA DE INCIDENTES HIGH/CRITICAL")
    logger.info("=" * 60)
    
    token = get_token()
    if not token:
        return []
    
    incidents = fetch_filtered_incidents(token, hours_back=hours_back)
    if not incidents:
        logger.info("No hay incidentes nuevos que cumplan criterios")
        return []
    
    processed = []
    
    for inc in incidents:
        incident_id = inc.get('id')
        
        if db_manager and db_manager.incident_exists(incident_id):
            logger.debug(f"Incidente ya existe: {incident_id}")
            continue
        
        extracted = extract_incident_metadata(inc)
        date_dir = get_date_directory(extracted['incident_date'])
        
        result = process_incident(inc, date_dir)
        
        if db_manager:
            db_manager.insert_incident(result)
        
        processed.append(result)
        logger.info(f"Procesado: {incident_id} | Severidad: {result['severity']}/{result['policy_severity']}")
    
    logger.info(f"Total nuevos incidentes procesados: {len(processed)}")
    return processed


def main():
    from db_manager import DatabaseManager
    db = DatabaseManager()
    download_incidents(hours_back=24, db_manager=db)


if __name__ == "__main__":
    main()