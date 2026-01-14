import os
import json
import time
from typing import Dict, Optional, List, Union
from pathlib import Path
import logging
import google.generativeai as genai
from db_manager import DatabaseManager
import PIL.Image

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
        model_name: str = "gemini-2.0-flash"
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no encontrada.")
        
        genai.configure(api_key=self.api_key)
        self.model_name = model_name
        self.db = db_manager or DatabaseManager()
        self.system_prompt = self._load_system_prompt()
        
        self.response_schema = {
            "type": "object",
            "properties": {
                "v": {
                    "type": "string",
                    "enum": ["TP", "FP", "RR"],
                    "description": "TP=True Positive, FP=False Positive, RR=Requires Review"
                },
                "c": {
                    "type": "number",
                    "description": "Confidence 0.0-1.0"
                },
                "s": {
                    "type": "string",
                    "description": "Executive summary in Spanish"
                },
                "ctx": {
                    "type": "object",
                    "properties": {
                        "u": {"type": "string"},
                        "src": {"type": "string"},
                        "dst": {"type": "string"},
                        "dt": {"type": "string"}
                    }
                },
                "r": {
                    "type": "string",
                    "description": "Technical reasoning"
                },
                "rl": {
                    "type": "string",
                    "enum": ["C", "H", "M", "L", "N"],
                    "description": "C=Critical, H=High, M=Medium, L=Low, N=N/A"
                },
                "ind": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["v", "c", "s", "ctx", "r", "rl"]
        }
        
        logger.info(f"GeminiAnalyzer inicializado: {model_name}")
    
    def _load_system_prompt(self) -> str:
        prompt_path = Path("./prompts/system_prompt.md")
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        return """Eres un analista DLP. Evalúa incidentes y responde JSON."""

    def _build_rag_context(self, limit: int = 3) -> str:
        feedback_items = self.db.get_feedback_for_rag(limit=limit)
        if not feedback_items:
            return ""
        
        rag = "\n[HISTORIAL DE CORRECCIONES HUMANAS]\n"
        for fb in feedback_items:
            rag += f"- Archivo {fb.get('file_type','?')}: La IA dijo {fb['original_verdict']} pero el Humano corrigió a {fb['corrected_verdict']}. Nota: {fb.get('analyst_comment', '')[:100]}\n"
        return rag
    
    def _compress_metadata(self, metadata: Dict) -> str:
        user = metadata.get('user', {}).get('id', 'unknown')
        policy = metadata.get('policy', {})
        
        event = metadata.get('action', {})
        src = metadata.get('source', {})
        dst = metadata.get('destination', {})
        
        src_str = "?"
        if 'app' in src: src_str = src['app'].get('name', '?')
        elif 'file' in src: src_str = src['file'].get('name', '?')
        elif 'email' in src: src_str = "Email Inbound"
        
        dst_str = "?"
        if 'email' in dst:
            email = dst['email']
            to_list = email.get('to', []) or []
            dst_str = f"Email to: {','.join(to_list[:2])}"
            if len(to_list) > 2: dst_str += "..."
        elif 'web' in dst:
            dst_str = dst['web'].get('url', '?')[:60]
        elif 'removable_media' in dst:
            dst_str = "USB Device"
        
        snippet = metadata.get('content_inspection', {}).get('snippet', '')[:300]
        
        compressed = f"""
USUARIO: {user}
POLÍTICA: {policy.get('name','?')} (Severidad: {policy.get('severity','?')})
ACCIÓN: {event.get('kind','?')}
ORIGEN: {src_str}
DESTINO: {dst_str}
TIPO: {src.get('type', '?')} -> {dst.get('type', '?')}
"""
        if snippet:
            compressed += f"\nSNIPPET DLP DETECTADO:\n{snippet}"
        
        return compressed
    
    def _read_file_content(self, file_path: str, max_chars: int = 15000) -> Union[str, PIL.Image.Image]:
        try:
            path_obj = Path(file_path)
            ext = path_obj.suffix.lower()
            
            if ext in ['.png', '.jpg', '.jpeg', '.webp']:
                return PIL.Image.open(file_path)

            if ext in ['.txt', '.md', '.py', '.json', '.xml', '.csv', '.log', '.sql']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()[:max_chars]
            
            elif ext == '.pdf':
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page in reader.pages[:10]:
                            text += page.extract_text() or ""
                        return text[:max_chars]
                except: return "[Error leyendo PDF]"
            
            return f"[Contenido binario no extraído para {ext}]"
        
        except Exception as e:
            return f"[Error leyendo archivo: {e}]"
    
    def _expand_response(self, compact: Dict) -> Dict:
        verdict_map = {"TP": "TRUE_POSITIVE", "FP": "FALSE_POSITIVE", "RR": "REQUIRES_REVIEW"}
        risk_map = {"C": "CRITICAL", "H": "HIGH", "M": "MEDIUM", "L": "LOW", "N": "N/A"}
        
        ctx = compact.get('ctx', {})
        return {
            'verdict': verdict_map.get(compact.get('v'), compact.get('v')),
            'confidence': compact.get('c', 0),
            'executive_summary': compact.get('s', ''),
            'incident_context': {
                'user': ctx.get('u', ''),
                'source': ctx.get('src', ''),
                'destination': ctx.get('dst', ''),
                'data_type': ctx.get('dt', '')
            },
            'reasoning': compact.get('r', ''),
            'risk_level': risk_map.get(compact.get('rl'), compact.get('rl')),
            'indicators': compact.get('ind', [])
        }
    
    def analyze_incident(self, incident_id: str, incident_dir: Path, use_rag: bool = True) -> Dict:
        start_time = time.time()
        
        try:
            metadata_path = incident_dir / "metadata.json"
            if not metadata_path.exists():
                return {"success": False, "error": "metadata.json no encontrado"}
            
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            file_content = None
            file_name = None
            
            for file in incident_dir.iterdir():
                if file.name not in ["metadata.json", "analysis_result.json"] and file.is_file():
                    file_name = file.name
                    file_content = self._read_file_content(str(file))
                    break
            
            prompt_parts = []
            text_prompt = self.system_prompt + "\n\n"
            
            if use_rag:
                rag = self._build_rag_context(limit=3)
                if rag: text_prompt += rag + "\n"
            
            text_prompt += "[INCIDENTE A ANALIZAR]\n"
            text_prompt += self._compress_metadata(metadata)
            
            if file_content:
                text_prompt += f"\n\n[EVIDENCIA DISPONIBLE: {file_name}]\n"
                if isinstance(file_content, PIL.Image.Image):
                    prompt_parts.append(text_prompt)
                    prompt_parts.append(file_content)
                    text_prompt = "\n[Instrucción: Analiza la imagen buscando datos sensibles visuales]\n"
                else:
                    text_prompt += str(file_content)
            else:
                # --- NUEVA LÓGICA PARA CASOS SIN ARCHIVO ---
                text_prompt += "\n\n[⚠️ ALERTA: EVIDENCIA NO DISPONIBLE]\n"
                text_prompt += "CONTEXTO: Este incidente es de tipo 'Metadatos', el archivo no fue capturado por la política.\n"
                text_prompt += "INSTRUCCIONES CRÍTICAS:\n"
                text_prompt += "1. NO intentes adivinar el contenido del archivo.\n"
                text_prompt += "2. Juzga el riesgo basándote ÚNICAMENTE en la combinación Usuario + Destino + Nombre del Archivo/Asunto.\n"
                text_prompt += "3. Si el destino es un email personal pero el nombre del archivo/asunto parece inofensivo (recibos, tareas escolares, citas médicas), clasifícalo como FALSE POSITIVE (FP).\n"
                text_prompt += "4. Solo marca RR o TP si el nombre del archivo sugiere explícitamente datos confidenciales (ej. 'passwords.txt', 'clientes.xlsx')."

            text_prompt += "\n\nResponde estrictamente en formato JSON."
            prompt_parts.append(text_prompt)
            
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                    "response_schema": self.response_schema
                }
            )
            
            response = model.generate_content(prompt_parts)
            
            processing_time = time.time() - start_time
            raw_response = response.text
            compact_result = json.loads(raw_response)
            expanded = self._expand_response(compact_result)
            
            tokens_used = 0
            if hasattr(response, 'usage_metadata'):
                tokens_used = getattr(response.usage_metadata, 'total_token_count', 0)
            
            analysis_data = {
                'incident_id': incident_id,
                'gemini_verdict': expanded['verdict'],
                'gemini_confidence': expanded['confidence'],
                'gemini_reasoning': expanded['reasoning'],
                'gemini_raw_response': raw_response,
                'executive_summary': expanded['executive_summary'],
                'risk_level': expanded['risk_level'],
                'processing_time': processing_time,
                'tokens_used': tokens_used
            }
            
            analysis_id = self.db.insert_analysis(analysis_data)
            
            return {
                "success": True,
                "incident_id": incident_id,
                "analysis_id": analysis_id,
                "verdict": expanded['verdict'],
                "confidence": expanded['confidence'],
                "executive_summary": expanded['executive_summary'],
                "incident_context": expanded['incident_context'],
                "reasoning": expanded['reasoning'],
                "risk_level": expanded['risk_level'],
                "indicators": expanded.get('indicators', []),
                "processing_time": processing_time,
                "tokens_used": tokens_used,
                "has_file": file_content is not None,
                "file_name": file_name
            }
        
        except Exception as e:
            logger.error(f"Error analizando {incident_id}: {e}")
            return {"success": False, "error": str(e), "incident_id": incident_id}