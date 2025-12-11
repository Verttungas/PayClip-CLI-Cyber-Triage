import os
import boto3
import requests
import json
from datetime import datetime, timedelta
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CYBERHAVEN_TOKEN = os.getenv("CYBERHAVEN_API_KEY")
CYBERHAVEN_BASE_URL = os.getenv("CYBERHAVEN_API_URL", "https://payclip.cyberhaven.io/public")
BUCKET_NAME = os.getenv("AWS_S3_BUCKET", "clip-cyberhaven-upload")
DOWNLOAD_DIR = os.getenv("EVIDENCE_DIR", "./evidencia_temp")

if not CYBERHAVEN_TOKEN:
    logger.warning("CYBERHAVEN_API_KEY no está configurada. El script fallará si intenta conectar.")

# Crear directorio base
base_dir = Path(DOWNLOAD_DIR)
base_dir.mkdir(exist_ok=True)


def get_token():
    """Obtiene access token de Cyberhaven"""
    if not CYBERHAVEN_TOKEN:
        return None
    url = f"{CYBERHAVEN_BASE_URL}/v2/auth/token/access"
    try:
        logger.info("Obteniendo access token de Cyberhaven...")
        resp = requests.post(url, json={"refresh_token": CYBERHAVEN_TOKEN}, timeout=10)
        resp.raise_for_status()
        logger.info("Token obtenido correctamente")
        return resp.json()['access_token']
    except Exception as e:
        logger.error(f"Error obteniendo token: {e}")
        return None


def download_from_s3(file_hash, output_path):
    """
    Descarga archivo de S3 usando el hash.
    Retorna True si se descargó, False si no.
    """
    s3 = boto3.client('s3')
    try:
        logger.debug(f"Buscando en S3: {file_hash[:20]}...")
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=file_hash)
        
        if 'Contents' not in response:
            logger.warning(f"No se encontró en S3: {file_hash[:20]}")
            return False

        # Buscar archivo que NO sea .html o .json (metadatos)
        target_key = None
        for obj in response['Contents']:
            key = obj['Key']
            if not key.endswith('.html') and not key.endswith('.json'):
                target_key = key
                break

        if not target_key:
            logger.warning(f"No se encontró archivo válido en S3: {file_hash[:20]}")
            return False

        logger.info(f"Descargando: {target_key}")
        s3.download_file(BUCKET_NAME, target_key, output_path)
        
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"✅ Descargado: {output_path} ({file_size_mb:.2f} MB)")
        return True

    except Exception as e:
        logger.error(f"Error descargando de S3: {e}")
        return False


def extract_file_info(incident):
    """
    Extrae información del archivo del incidente.
    Retorna: (file_name, sha256_hash, md5_hash, extension)
    """
    file_info = {}
    
    # Buscar en event_details.start_event.source.file
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
    
    # Determinar extensión
    if file_name != 'unknown' and '.' in file_name:
        extension = file_name.split('.')[-1]
    else:
        extension = file_info.get('extension', 'bin')
    
    return file_name, sha256, md5, extension


def process_incident(incident):
    """
    Procesa un incidente:
    1. Crea directorio
    2. Guarda metadata.json
    3. Descarga archivo de S3 si existe
    """
    incident_id = incident.get('id')
    incident_dir = base_dir / incident_id
    
    # Crear directorio para el incidente
    incident_dir.mkdir(exist_ok=True)
    
    # 1. Guardar metadata completa
    metadata_path = incident_dir / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(incident, f, indent=2, ensure_ascii=False)
    logger.info(f"Metadata guardada: {metadata_path}")
    
    # 2. Extraer info del archivo
    file_name, sha256, md5, extension = extract_file_info(incident)
    
    # 3. Descargar archivo de S3 si existe hash
    if sha256:
        output_filename = f"{file_name}" if file_name != 'unknown' else f"file.{extension}"
        output_path = incident_dir / output_filename
        
        logger.info(f"Archivo detectado: {file_name}")
        
        # Intentar con SHA256
        if download_from_s3(sha256, str(output_path)):
            logger.info(f"✅ Incidente {incident_id}: archivo descargado")
            return True
        
        # Intentar con MD5 si SHA256 falló
        if md5:
            logger.info(f"Intentando con MD5 hash...")
            if download_from_s3(md5, str(output_path)):
                logger.info(f"✅ Incidente {incident_id}: archivo descargado")
                return True
        
        logger.warning(f"No se pudo descargar archivo para: {incident_id}")
        return False
    else:
        logger.info(f"ℹ️  Incidente {incident_id}: sin archivo (solo metadata)")
        return True


def main():
    logger.info("="*60)
    logger.info("CYBER-TRIAGE: EVIDENCE DOWNLOADER")
    logger.info("="*60)
    
    token = get_token()
    if not token:
        logger.error("No se pudo obtener token. Abortando.")
        return

    days_back = int(os.getenv("INCIDENT_DAYS_BACK", "3"))
    start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
    logger.info(f"Buscando incidentes desde: {start_date} ({days_back} días atrás)")

    try:
        resp = requests.post(
            f"{CYBERHAVEN_BASE_URL}/v2/incidents/list",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "page_request": {"size": 20, "sort_by": "event_time"},
                "filter": {"start_time": start_date}
            },
            timeout=30
        )
        resp.raise_for_status()
        incidents = resp.json().get('resources', [])
        logger.info(f"Incidentes encontrados: {len(incidents)}")
        
        for inc in incidents:
            incident_id = inc.get('id')
            logger.info(f"\nProcesando: {incident_id}")
            process_incident(inc)
            
    except Exception as e:
        logger.error(f"Error obteniendo incidentes: {e}")
        return
    
    logger.info("\n" + "="*60)
    logger.info("✅ DESCARGA COMPLETADA")
    logger.info("="*60)


if __name__ == "__main__":
    main()
