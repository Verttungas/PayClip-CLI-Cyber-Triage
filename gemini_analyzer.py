import os
import json
import time
from typing import Dict, Optional, List
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
        model_name: str = "gemini-2.5-pro-latest"
    ):
        """
        Inicializa el analizador con Gemini 2.5 Pro
        
        Args:
            api_key: API key de Google AI (si no se proporciona, lee de GEMINI_API_KEY)
            db_manager: Instancia de DatabaseManager (opcional)
            model_name: Modelo a usar (default: gemini-2.5-pro-latest)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no encontrada. Configura la variable de entorno o pasa api_key.")
        
        # Configurar Gemini con API estable
        genai.configure(api_key=self.api_key)
        self.model_name = model_name
        
        self.db = db_manager or DatabaseManager()
        
        self.system_prompt = self._load_system_prompt()
        self.rag_template = self._load_rag_template()
        
        # Schema para JSON estructurado
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
                "summary": {
                    "type": "string",
                    "description": "Resumen breve del análisis (máx 200 chars)"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explicación detallada del veredicto (mín 100 chars)"
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
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Acciones recomendadas para el SOC"
                },
                "false_positive_reasons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Razones si es FALSE_POSITIVE"
                }
            },
            "required": ["verdict", "confidence", "summary", "reasoning", "risk_level", "indicators"]
        }
        
        logger.info(f"GeminiAnalyzer inicializado con modelo: {model_name}")
    
    def _load_system_prompt(self) -> str:
        """Carga el system prompt desde archivo"""
        prompt_path = Path("./prompts/system_prompt.md")
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info("System prompt cargado correctamente")
            return content
        except FileNotFoundError:
            logger.error(f"System prompt no encontrado en {prompt_path}")
            raise
    
    def _load_rag_template(self) -> str:
        """Carga el template RAG desde archivo"""
        template_path = Path("./prompts/rag_template.md")
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info("RAG template cargado correctamente")
            return content
        except FileNotFoundError:
            logger.warning(f"RAG template no encontrado en {template_path}")
            return ""
    
    def _build_rag_context(self, limit: int = 5) -> str:
        """Construye contexto RAG con feedback histórico"""
        feedback_items = self.db.get_feedback_for_rag(limit=limit)
        if not feedback_items:
            return self.rag_template.replace("{{#if has_feedback}}", "{{else}}")
        
        rag_context = f"\n\n{'='*60}\n"
        rag_context += "🧠 APRENDIZAJE DE CASOS ANTERIORES\n"
        rag_context += f"{'='*60}\n\n"
        rag_context += f"Se encontraron {len(feedback_items)} correcciones históricas. "
        rag_context += "Estudia estos casos para evitar los mismos errores:\n\n"
        
        for idx, fb in enumerate(feedback_items, 1):
            rag_context += f"### Caso #{idx}: {fb['file_name']}\n\n"
            rag_context += f"**Archivo:** `{fb['file_name']}` (tipo: {fb.get('file_type', 'unknown')})\n\n"
            rag_context += f"**Tu Veredicto Original (INCORRECTO):** {fb['original_verdict']}\n\n"
            rag_context += f"**Veredicto Correcto:** {fb['corrected_verdict']}\n\n"
            rag_context += f"**Comentario del Analista:**\n> {fb.get('analyst_comment', 'Sin comentario adicional')}\n\n"
            
            if fb.get('original_reasoning'):
                rag_context += f"**Tu Razonamiento Original:**\n{fb['original_reasoning']}\n\n"
            
            rag_context += f"**Relevancia:** {fb.get('relevance_score', 1.0)}/1.0\n\n"
            rag_context += "**Lección:**\n"
            rag_context += "- Ajusta tu análisis considerando este contexto empresarial\n"
            rag_context += "- No repitas el mismo error de clasificación\n\n"
            rag_context += f"{'-'*60}\n\n"
        
        stats = self.db.get_feedback_stats()
        rag_context += "📈 **ESTADÍSTICAS DE APRENDIZAJE:**\n"
        rag_context += f"- Total de Feedback: {stats.get('total_feedback', 0)}\n"
        rag_context += f"- Correcciones Aplicadas: {stats.get('corrections', 0)}\n"
        rag_context += f"- Casos en este Análisis: {len(feedback_items)}\n\n"
        
        rag_context += "🎯 **APLICA ESTE CONOCIMIENTO:** Revisa si el archivo actual es similar a estos casos.\n\n"
        
        return rag_context
    
    def _read_file_content(self, file_path: str) -> str:
        """Lee el contenido de un archivo y lo retorna como texto"""
        try:
            file_extension = Path(file_path).suffix.lower()
            
            # Archivos de texto plano
            if file_extension in ['.txt', '.md', '.py', '.js', '.json', '.xml', '.csv', '.log', '.yaml', '.yml']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            
            # PDFs
            elif file_extension == '.pdf':
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page in reader.pages:
                            text += page.extract_text()
                        return text
                except ImportError:
                    logger.warning("PyPDF2 no instalado. No se puede leer PDF.")
                    return f"[ARCHIVO PDF: {Path(file_path).name} - No se pudo extraer texto]"
            
            # Word
            elif file_extension in ['.docx', '.doc']:
                try:
                    import docx
                    doc = docx.Document(file_path)
                    return "\n".join([para.text for para in doc.paragraphs])
                except ImportError:
                    logger.warning("python-docx no instalado. No se puede leer DOCX.")
                    return f"[ARCHIVO WORD: {Path(file_path).name} - No se pudo extraer texto]"
            
            # Imágenes
            elif file_extension in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                return f"[ARCHIVO IMAGEN: {Path(file_path).name} - Requiere análisis visual]"
            
            # Binarios
            else:
                return f"[ARCHIVO BINARIO: {Path(file_path).name} - Tipo: {file_extension}]"
        
        except Exception as e:
            logger.error(f"Error leyendo archivo {file_path}: {e}")
            return f"[ERROR: No se pudo leer el archivo]"
    
    def analyze_file(
        self, 
        file_path: str, 
        incident_id: str,
        use_rag: bool = True
    ) -> Dict:
        """
        Analiza un archivo con Gemini 2.5 Pro y retorna el veredicto
        
        Args:
            file_path: Ruta al archivo a analizar
            incident_id: ID del incidente
            use_rag: Si True, incluye contexto RAG con feedback histórico
            
        Returns:
            Dict con el resultado del análisis
        """
        start_time = time.time()
        try:
            logger.info(f"Analizando archivo: {file_path}")
            file_content = self._read_file_content(file_path)
            
            if not file_content or len(file_content) < 10:
                logger.warning(f"Contenido del archivo insuficiente: {file_path}")
                return {
                    "success": False,
                    "error": "Archivo vacío o contenido insuficiente",
                    "incident_id": incident_id
                }
            
            # Construir prompt completo
            full_prompt = self.system_prompt + "\n\n"
            
            if use_rag:
                rag_context = self._build_rag_context(limit=5)
                full_prompt += rag_context + "\n\n"
            
            full_prompt += f"{'-'*60}\n"
            full_prompt += "## 📄 ARCHIVO A ANALIZAR\n\n"
            full_prompt += f"**Nombre:** {Path(file_path).name}\n"
            full_prompt += f"**Tipo:** {Path(file_path).suffix}\n"
            full_prompt += f"**Incident ID:** {incident_id}\n\n"
            full_prompt += "**CONTENIDO DEL ARCHIVO:**\n"
            full_prompt += "```\n"
            full_prompt += file_content[:50000]  # Limitar a 50k chars
            full_prompt += "\n```\n\n"
            full_prompt += f"{'-'*60}\n\n"
            full_prompt += "🎯 **GENERA TU ANÁLISIS AHORA:**\n"
            
            logger.info(f"Enviando análisis a Gemini 2.5 Pro...")
            
            # Crear modelo con configuración
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": 1.0,
                    "response_mime_type": "application/json",
                    "response_schema": self.response_schema
                }
            )
            
            # Generar respuesta
            response = model.generate_content(full_prompt)
            
            processing_time = time.time() - start_time
            
            raw_response = response.text
            logger.info(f"Respuesta recibida de Gemini en {processing_time:.2f}s")
            
            # Parsear respuesta JSON
            analysis = json.loads(raw_response)
            
            # Validar campos obligatorios
            required_fields = ['verdict', 'confidence', 'summary', 'reasoning']
            for field in required_fields:
                if field not in analysis:
                    raise ValueError(f"Campo obligatorio '{field}' no encontrado en respuesta")
            
            # Guardar análisis en DB
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
                "summary": analysis['summary'],
                "reasoning": analysis['reasoning'],
                "risk_level": analysis.get('risk_level', 'N/A'),
                "indicators": analysis.get('indicators', []),
                "recommendations": analysis.get('recommendations', []),
                "false_positive_reasons": analysis.get('false_positive_reasons', []),
                "processing_time": processing_time,
                "raw_response": raw_response
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON de Gemini: {e}")
            logger.error(f"Respuesta raw: {raw_response if 'raw_response' in locals() else 'No disponible'}")
            return {
                "success": False,
                "error": f"Error parseando respuesta JSON: {str(e)}",
                "incident_id": incident_id,
                "raw_response": raw_response if 'raw_response' in locals() else None
            }
        
        except Exception as e:
            logger.error(f"Error analizando archivo: {e}")
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
        """
        Guarda feedback del analista para RAG
        
        Args:
            incident_id: ID del incidente
            analysis_id: ID del análisis
            original_verdict: Veredicto original de Gemini
            corrected_verdict: Veredicto correcto según analista
            analyst_comment: Comentario explicativo
            relevance_score: Relevancia del caso (0.0-1.0)
            
        Returns:
            True si se guardó correctamente
        """
        feedback_data = {
            'incident_id': incident_id,
            'analysis_id': analysis_id,
            'original_verdict': original_verdict,
            'corrected_verdict': corrected_verdict,
            'analyst_comment': analyst_comment,
            'relevance_score': relevance_score
        }
        success = self.db.insert_feedback(feedback_data)
        
        if success:
            logger.info(f"Feedback registrado para incidente {incident_id}: {original_verdict} → {corrected_verdict}")
        
        return success
    
    def get_analysis_summary(self, incident_id: str) -> Optional[Dict]:
        """Obtiene el último análisis de un incidente"""
        return self.db.get_latest_analysis(incident_id)


if __name__ == "__main__":
    """Test básico del analizador"""
    print("🧪 Test de GeminiAnalyzer (Gemini 2.5 Pro)\n")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY no configurada.")
        print("   Configura con: export GEMINI_API_KEY='tu-api-key'")
        exit(1)
    
    print("✅ API Key encontrada\n")
    
    # Crear archivo de prueba
    test_file = "./evidencia_temp/test_credentials.txt"
    os.makedirs("./evidencia_temp", exist_ok=True)
    
    with open(test_file, 'w') as f:
        f.write("user=admin\npassword=secret123\nAPI_KEY=sk-1234567890abcdef\n")
    print(f"📝 Archivo de prueba creado: {test_file}\n")
    
    try:
        print("🔧 Inicializando GeminiAnalyzer (Gemini 2.5 Pro)...")
        analyzer = GeminiAnalyzer(model_name="gemini-2.5-pro-latest")
        
        print("🤖 Enviando análisis a Gemini 2.5 Pro...\n")
        result = analyzer.analyze_file(
            file_path=test_file,
            incident_id="TEST-GEMINI-25-001",
            use_rag=True
        )
        
        if result['success']:
            print("✅ ANÁLISIS COMPLETADO\n")
            print(f"📊 Veredicto: {result['verdict']}")
            print(f"🎯 Confianza: {result['confidence']:.1%}")
            print(f"📝 Resumen: {result['summary']}")
            print(f"\n🔍 Razonamiento:\n{result['reasoning']}")
            
            if result.get('indicators'):
                print(f"\n⚠️  Indicadores encontrados:")
                for indicator in result['indicators']:
                    print(f"  - {indicator}")
            
            if result.get('recommendations'):
                print(f"\n💡 Recomendaciones:")
                for rec in result['recommendations']:
                    print(f"  - {rec}")
            
            print(f"\n⏱️  Tiempo de procesamiento: {result['processing_time']:.2f}s")
        else:
            print(f"❌ ERROR: {result['error']}")
            if result.get('raw_response'):
                print(f"\nRespuesta raw:\n{result['raw_response'][:500]}...")
    
    except Exception as e:
        print(f"❌ Error en test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"\n🧹 Archivo de prueba eliminado")
