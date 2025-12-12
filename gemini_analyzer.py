import os
import json
import time
from typing import Dict, Optional
from pathlib import Path
import logging
import google.generativeai as genai
from db_manager import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    def __init__(
        self, 
        api_key: Optional[str] = None,
        db_manager: Optional[DatabaseManager] = None,
        model_name: str = "gemini-2.5-pro"
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no encontrada.")
        
        genai.configure(api_key=self.api_key)
        self.model_name = model_name
        
        self.db = db_manager or DatabaseManager()
        
        self.system_prompt = self._load_system_prompt()
        
        # NUEVO SCHEMA OPTIMIZADO
        self.response_schema = {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["TRUE_POSITIVE", "FALSE_POSITIVE", "REQUIRES_REVIEW"],
                    "description": "Veredicto del análisis"
                },
                "confidence": {
                    "type": "number",
                    "description": "Nivel de confianza entre 0.0 y 1.0"
                },
                "executive_summary": {
                    "type": "string",
                    "description": "Resumen ejecutivo contextual (Quién, Qué, Dónde) en español latino"
                },
                "incident_context": {
                    "type": "object",
                    "properties": {
                        "user": {"type": "string"},
                        "source": {"type": "string"},
                        "destination": {"type": "string"},
                        "data_type": {"type": "string"}
                    },
                    "required": ["user", "source", "destination"]
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explicación técnica detallada"
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "N/A"],
                    "description": "Nivel de riesgo si es TRUE_POSITIVE"
                },
                "indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de indicadores técnicos encontrados"
                }
            },
            "required": ["verdict", "confidence", "executive_summary", "incident_context", "reasoning", "risk_level", "indicators"]
        }
        
        logger.info(f"GeminiAnalyzer inicializado con modelo: {model_name}")
    
    def _load_system_prompt(self) -> str:
        prompt_path = Path("./prompts/system_prompt.md")
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info("System prompt cargado correctamente")
            return content
        except FileNotFoundError:
            logger.error(f"System prompt no encontrado en {prompt_path}")
            raise
    
    def _build_rag_context(self, limit: int = 5) -> str:
        """Construye contexto RAG desde feedback histórico"""
        feedback_items = self.db.get_feedback_for_rag(limit=limit)
        if not feedback_items:
            return ""
        
        rag_context = f"\n\n{'='*60}\n"
        rag_context += "🧠 APRENDIZAJE DE CASOS ANTERIORES\n"
        rag_context += f"{'='*60}\n\n"
        
        for idx, fb in enumerate(feedback_items, 1):
            rag_context += f"### Caso #{idx}: {fb.get('file_name', 'unknown')}\n\n"
            rag_context += f"**Tu Veredicto Original:** {fb['original_verdict']}\n"
            rag_context += f"**Veredicto Correcto:** {fb['corrected_verdict']}\n"
            rag_context += f"**Comentario:** {fb.get('analyst_comment', 'N/A')}\n\n"
            rag_context += f"{'-'*60}\n\n"
        
        return rag_context
    
    def _read_file_content(self, file_path: str) -> str:
        """Lee contenido de archivo para análisis"""
        try:
            file_extension = Path(file_path).suffix.lower()
            
            if file_extension in ['.txt', '.md', '.py', '.js', '.json', '.xml', '.csv', '.log', '.yaml', '.yml', '.sql']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            
            elif file_extension == '.pdf':
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page in reader.pages:
                            text += page.extract_text()
                        return text
                except Exception as e:
                    return f"[ARCHIVO PDF: {Path(file_path).name} - Error: {e}]"
            
            elif file_extension in ['.docx', '.doc']:
                try:
                    import docx
                    doc = docx.Document(file_path)
                    return "\n".join([para.text for para in doc.paragraphs])
                except Exception as e:
                    return f"[ARCHIVO WORD: {Path(file_path).name} - Error: {e}]"
            
            elif file_extension in ['.xlsx', '.xls']:
                try:
                    import pandas as pd
                    df = pd.read_excel(file_path)
                    return df.to_string()
                except Exception as e:
                    return f"[ARCHIVO EXCEL: {Path(file_path).name} - Error: {e}]"
            
            elif file_extension in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                return f"[ARCHIVO IMAGEN: {Path(file_path).name}]"
            
            else:
                return f"[ARCHIVO BINARIO: {Path(file_path).name} - Tipo: {file_extension}]"
        
        except Exception as e:
            logger.error(f"Error leyendo archivo {file_path}: {e}")
            return f"[ERROR leyendo archivo: {str(e)}]"
    
    def _format_incident_metadata(self, metadata: Dict) -> str:
        """Formatea metadata enriquecida incluyendo Copy/Paste"""
        user = metadata.get('user', {}).get('id', 'unknown')
        
        event_details = metadata.get('event_details', {})
        start_event = event_details.get('start_event', {})
        
        # Acción
        action = start_event.get('action', {}).get('kind', 'unknown')
        
        # Origen (Source)
        src_info = start_event.get('source', {})
        source_str = "Desconocido"
        if 'app' in src_info:
            source_str = f"App: {src_info['app'].get('name')}"
        elif 'file' in src_info:
            source_str = f"File: {src_info['file'].get('name')}"

        # Destino (Destination)
        dst_info = start_event.get('destination', {})
        dest_str = "Desconocido"
        if 'internet' in dst_info:
            dest_str = f"Internet URL: {dst_info['internet'].get('url')}"
        elif 'app' in dst_info:
            dest_str = f"App: {dst_info['app'].get('name')}"
        elif 'removable_media' in dst_info:
            dest_str = "USB / Almacenamiento Externo"
        elif 'email' in dst_info:
             dest_str = f"Email to: {dst_info['email'].get('recipient', 'unknown')}"

        # Copy Paste Content
        clipboard_content = ""
        if 'content_inspection' in metadata:
            clipboard_content = metadata['content_inspection'].get('snippet', '')
        elif 'clipboard' in str(action).lower():
             clipboard_content = metadata.get('payload', '')

        formatted = f"""
{'='*60}
METADATA DEL INCIDENTE
{'='*60}
- Usuario: {user}
- Acción: {action}
- Origen Detectado: {source_str}
- Destino Detectado: {dest_str}
"""
        if clipboard_content:
            formatted += f"\n📋 CONTENIDO DEL PORTAPAPELES (SNIPPET):\n{clipboard_content}\n"
            
        return formatted
    
    def analyze_incident(
        self, 
        incident_id: str,
        incident_dir: Path,
        use_rag: bool = True
    ) -> Dict:
        """
        Analiza un incidente completo.
        """
        start_time = time.time()
        
        try:
            logger.info(f"Analizando incidente: {incident_id}")
            
            # 1. Leer metadata.json
            metadata_path = incident_dir / "metadata.json"
            if not metadata_path.exists():
                return {
                    "success": False,
                    "error": f"No se encontró metadata.json",
                    "incident_id": incident_id
                }
            
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # 2. Buscar archivo adjunto
            file_content = None
            file_name = None
            
            for file in incident_dir.iterdir():
                if file.name != "metadata.json" and file.is_file():
                    file_name = file.name
                    logger.info(f"Archivo detectado: {file_name}")
                    file_content = self._read_file_content(str(file))
                    break
            
            # 3. Construir prompt
            full_prompt = self.system_prompt + "\n\n"
            
            if use_rag:
                rag_context = self._build_rag_context(limit=5)
                if rag_context:
                    full_prompt += rag_context + "\n\n"
            
            full_prompt += self._format_incident_metadata(metadata)
            
            if file_content:
                full_prompt += f"\nCONTENIDO DEL ARCHIVO: {file_name}\n"
                full_prompt += "="*80 + "\n"
                full_prompt += file_content[:50000]
                full_prompt += "\n" + "="*80 + "\n"
            else:
                full_prompt += "\n⚠️ INCIDENTE SIN ARCHIVO FÍSICO\n"
                full_prompt += "Analiza basándote en la metadata de Cyberhaven y el contenido del portapapeles si existe.\n\n"
            
            full_prompt += "\n🎯 GENERA TU ANÁLISIS EN JSON:\n"
            
            # 4. Enviar a Gemini
            logger.info(f"Enviando a Gemini 2.5 Pro...")
            
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": 1.0,
                    "response_mime_type": "application/json",
                    "response_schema": self.response_schema
                }
            )
            
            response = model.generate_content(full_prompt)
            processing_time = time.time() - start_time
            
            raw_response = response.text
            analysis = json.loads(raw_response)
            
            # Validar campos
            required = ['verdict', 'confidence', 'executive_summary', 'reasoning']
            for field in required:
                if field not in analysis:
                    raise ValueError(f"Campo '{field}' no encontrado")
            
            # Guardar en DB
            analysis_data = {
                'incident_id': incident_id,
                'gemini_verdict': analysis['verdict'],
                'gemini_confidence': analysis.get('confidence'),
                'gemini_reasoning': analysis.get('reasoning'),
                'gemini_raw_response': raw_response,
                'processing_time': processing_time
            }
            
            analysis_id = self.db.insert_analysis(analysis_data)
            
            return {
                "success": True,
                "incident_id": incident_id,
                "analysis_id": analysis_id,
                "verdict": analysis['verdict'],
                "confidence": analysis['confidence'],
                "executive_summary": analysis['executive_summary'],
                "incident_context": analysis['incident_context'],
                "reasoning": analysis['reasoning'],
                "risk_level": analysis.get('risk_level', 'N/A'),
                "indicators": analysis.get('indicators', []),
                "processing_time": processing_time,
                "has_file": file_content is not None,
                "file_name": file_name
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON: {e}")
            return {
                "success": False,
                "error": f"Error JSON: {str(e)}",
                "incident_id": incident_id
            }
        
        except Exception as e:
            logger.error(f"Error analizando: {e}")
            return {
                "success": False,
                "error": str(e),
                "incident_id": incident_id
            }
    
    def submit_feedback(
        self, 
        incident_id: str,
        analysis_id: int,
        original_verdict: str,
        corrected_verdict: str,
        analyst_comment: str,
        relevance_score: float = 1.0
    ) -> bool:
        """Registra feedback de analista humano"""
        feedback_data = {
            'incident_id': incident_id,
            'analysis_id': analysis_id,
            'original_verdict': original_verdict,
            'corrected_verdict': corrected_verdict,
            'analyst_comment': analyst_comment,
            'relevance_score': relevance_score
        }
        
        return self.db.insert_feedback(feedback_data)
