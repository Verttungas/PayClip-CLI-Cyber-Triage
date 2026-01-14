# 🧠 RAG TEMPLATE - Feedback Histórico

---

## 📚 APRENDIZAJE DE CASOS ANTERIORES

A continuación se presenta feedback de analistas humanos sobre análisis previos. **Estudia estos casos cuidadosamente** para evitar cometer los mismos errores y mejorar tu precisión.

---

{{#if has_feedback}}

## 🔄 CORRECCIONES HISTÓRICAS ({{feedback_count}} casos)

{{#each feedback_items}}

### Caso #{{@index_plus_1}}: {{file_name}}

**📄 Archivo Analizado:**

- **Nombre:** `{{file_name}}`
- **Tipo:** {{file_type}}
- **Fecha del Incidente:** {{incident_date}}

**🤖 Tu Veredicto Original (INCORRECTO):**

```
{{original_verdict}}
```

**✅ Veredicto Correcto del Analista:**

```
{{corrected_verdict}}
```

**💬 Comentario del Analista:**

> {{analyst_comment}}

**📊 Relevancia de este Caso:** {{relevance_score}}/1.0

**🎯 Lección Aprendida:**
{{#if lesson_learned}}
{{lesson_learned}}
{{else}}

- Revisa este caso y ajusta tu razonamiento para situaciones similares
- Considera el contexto empresarial y los flujos de trabajo legítimos
- No asumas malicia sin evidencia clara
  {{/if}}

---

{{/each}}

## 🧪 PATRONES IDENTIFICADOS

Basándote en los casos anteriores, ten en cuenta:

{{#if common_patterns}}
{{#each common_patterns}}

- **{{pattern_type}}:** {{pattern_description}}
  {{/each}}
  {{else}}

### Errores Comunes a Evitar:

1. **Sobre-clasificación de TRUE POSITIVE:**

   - No marcar actividades empresariales normales como amenazas
   - Verificar si el usuario tiene autorización para la acción
   - Considerar si el documento ya es público o de baja sensibilidad

2. **Falsos Negativos (Sub-clasificación):**

   - No ignorar credenciales en texto plano aunque estén en repos de dev
   - Datos financieros siempre requieren análisis riguroso
   - Transferencias a dominios externos no corporativos son sospechosas

3. **Ambigüedad sin marcar REQUIRES_REVIEW:**
   - Si no estás 80%+ seguro, escala a humano
   - Archivos cifrados sin contexto siempre requieren revisión
   - Actividad de usuarios nuevos o en horarios inusuales necesita validación
     {{/if}}

---

## 🎯 APLICA ESTE CONOCIMIENTO

Cuando analices el archivo actual:

1. ✅ **Busca similitudes** con los casos anteriores corregidos
2. ✅ **Ajusta tu razonamiento** si el contexto es comparable
3. ✅ **Evita repetir** los mismos errores de clasificación
4. ✅ **Prioriza el contexto empresarial** sobre indicadores técnicos aislados
5. ✅ **Sé más conservador** con TRUE_POSITIVE si hubo sobre-clasificación previa

---

{{else}}

## ℹ️ SIN FEEDBACK HISTÓRICO

Aún no hay feedback de analistas humanos. Estás operando con el conocimiento base del system prompt.

**Instrucciones:**

- Sigue estrictamente los criterios de evaluación del system prompt
- Prefiere REQUIRES_REVIEW sobre veredictos inciertos
- Documenta exhaustivamente tu razonamiento
- Tu análisis creará los primeros casos de aprendizaje para futuras iteraciones

---

{{/if}}

## 📈 ESTADÍSTICAS DE APRENDIZAJE

{{#if has_stats}}

- **Total de Feedback Recibido:** {{total_feedback}}
- **Correcciones Aplicadas:** {{total_corrections}}
- **Precisión Actual del Sistema:** {{ai_accuracy}}%
- **Casos Usados en este Análisis:** {{rag_cases_used}}
  {{else}}
  _Estadísticas aún no disponibles. Este es uno de los primeros análisis._
  {{/if}}

---

_Template Version: 1.0 | Sistema RAG de Cyber-Triage_
