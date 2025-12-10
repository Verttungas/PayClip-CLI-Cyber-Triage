#!/usr/bin/env python3
"""
Cyber-Triage CLI
Sistema de análisis DLP desde terminal para GRC team
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
from rich import box

# Importar módulos existentes
from db_manager import DatabaseManager
from gemini_analyzer import GeminiAnalyzer
from evidence_downloader import main as download_evidence

console = Console()


class CyberTriageCLI:
    def __init__(self):
        self.db = DatabaseManager()
        
        # Inicializar Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            console.print("[red]❌ GEMINI_API_KEY no configurada[/red]")
            console.print("[yellow]Configura: export GEMINI_API_KEY='tu-api-key'[/yellow]")
            sys.exit(1)
        
        try:
            self.analyzer = GeminiAnalyzer(
                api_key=api_key,
                db_manager=self.db
            )
            console.print("[green]✅ Gemini 2.5 Pro inicializado[/green]")
        except Exception as e:
            console.print(f"[red]❌ Error inicializando Gemini: {e}[/red]")
            sys.exit(1)

    def show_header(self):
        """Muestra header del sistema"""
        console.clear()
        header = """
        ╔═══════════════════════════════════════════════╗
        ║  🛡️  CYBER-TRIAGE CLI v1.0                    ║
        ║  DLP Incident Analysis System                 ║
        ║  Powered by Gemini 2.5 Pro                    ║
        ╚═══════════════════════════════════════════════╝
        """
        console.print(header, style="bold cyan")

    def show_stats(self):
        """Muestra estadísticas del sistema"""
        stats = self.db.get_database_stats()
        
        table = Table(title="📊 Estadísticas del Sistema", box=box.ROUNDED)
        table.add_column("Métrica", style="cyan", no_wrap=True)
        table.add_column("Valor", style="green")
        
        total_incidents = sum(stats.get('incidents_by_status', {}).values())
        table.add_row("Total Incidentes", str(total_incidents))
        table.add_row("Análisis Realizados", str(stats.get('total_analyses', 0)))
        table.add_row("Feedback Recibido", str(stats.get('total_feedback', 0)))
        
        if stats.get('ai_accuracy'):
            table.add_row("Precisión IA", f"{stats['ai_accuracy']:.1f}%")
        
        console.print(table)
        console.print()

    def main_menu(self) -> str:
        """Menú principal"""
        console.print("\n[bold]Opciones:[/bold]")
        console.print("  [1] 📥 Descargar nuevos incidentes de Cyberhaven")
        console.print("  [2] 🔍 Analizar archivos pendientes")
        console.print("  [3] 📋 Ver incidentes existentes")
        console.print("  [4] 👨‍💼 Proporcionar feedback")
        console.print("  [5] 📊 Ver dashboard completo")
        console.print("  [6] ⚙️  Configuración")
        console.print("  [0] 🚪 Salir")
        console.print()
        
        choice = Prompt.ask("Selecciona una opción", choices=["0", "1", "2", "3", "4", "5", "6"])
        return choice

    def download_incidents(self):
        """Descarga incidentes de Cyberhaven"""
        console.print("\n[bold cyan]📥 Descargando incidentes de Cyberhaven...[/bold cyan]\n")
        
        if not os.getenv("CYBERHAVEN_API_KEY"):
            console.print("[red]❌ CYBERHAVEN_API_KEY no configurada[/red]")
            return
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Descargando...", total=None)
            
            try:
                download_evidence()
                progress.update(task, completed=True)
                console.print("[green]✅ Descarga completada[/green]")
            except Exception as e:
                console.print(f"[red]❌ Error: {e}[/red]")
        
        Prompt.ask("\nPresiona Enter para continuar")

    def get_evidence_files(self) -> List[str]:
        """Lista archivos de evidencia disponibles"""
        evidence_dir = Path("./evidencia_temp")
        if not evidence_dir.exists():
            return []
        
        return sorted(
            [str(f) for f in evidence_dir.iterdir() if f.is_file()],
            key=lambda x: os.path.getmtime(x),
            reverse=True
        )

    def analyze_files(self):
        """Analiza archivos pendientes"""
        console.print("\n[bold cyan]🔍 Análisis de Evidencias[/bold cyan]\n")
        
        files = self.get_evidence_files()
        
        if not files:
            console.print("[yellow]⚠️  No hay archivos en ./evidencia_temp/[/yellow]")
            console.print("[dim]Ejecuta la opción [1] para descargar incidentes[/dim]")
            Prompt.ask("\nPresiona Enter para continuar")
            return
        
        # Mostrar archivos disponibles
        table = Table(title="📂 Archivos Disponibles", box=box.SIMPLE)
        table.add_column("#", style="cyan", width=6)
        table.add_column("Archivo", style="white")
        table.add_column("Tamaño", style="green", justify="right")
        table.add_column("Tipo", style="yellow")
        
        for idx, file in enumerate(files, 1):
            file_path = Path(file)
            size_kb = os.path.getsize(file) / 1024
            table.add_row(
                str(idx),
                file_path.name,
                f"{size_kb:.1f} KB",
                file_path.suffix
            )
        
        console.print(table)
        console.print()
        
        # Seleccionar archivo
        file_num = Prompt.ask(
            "Selecciona archivo (#) o [0] para cancelar",
            choices=[str(i) for i in range(len(files) + 1)]
        )
        
        if file_num == "0":
            return
        
        selected_file = files[int(file_num) - 1]
        
        # Mostrar preview del archivo
        console.print(f"\n[bold]📄 Archivo seleccionado:[/bold] {Path(selected_file).name}\n")
        self._show_file_preview(selected_file)
        
        # Confirmar análisis
        if not Confirm.ask("\n¿Analizar este archivo con Gemini?", default=True):
            return
        
        # Ejecutar análisis
        console.print("\n[bold cyan]🧠 Analizando con Gemini 3 Pro...[/bold cyan]")
        console.print("[dim](Puede tomar 10-30 segundos)[/dim]\n")
        
        incident_id = f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # Registrar incidente en DB
        self.db.insert_incident({
            'incident_id': incident_id,
            'file_name': Path(selected_file).name,
            'file_path': selected_file,
            'file_type': Path(selected_file).suffix,
            'file_size': os.path.getsize(selected_file)
        })
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analizando...", total=None)
            
            try:
                result = self.analyzer.analyze_file(
                    file_path=selected_file,
                    incident_id=incident_id,
                    use_rag=True
                )
                progress.update(task, completed=True)
                
                if result['success']:
                    self._display_analysis_result(result, incident_id)
                else:
                    console.print(f"[red]❌ Error: {result.get('error')}[/red]")
            
            except Exception as e:
                console.print(f"[red]❌ Error durante análisis: {e}[/red]")
        
        Prompt.ask("\nPresiona Enter para continuar")

    def _show_file_preview(self, file_path: str, max_lines: int = 15):
        """Muestra preview del archivo"""
        file_ext = Path(file_path).suffix.lower()
        
        try:
            if file_ext in ['.txt', '.md', '.py', '.js', '.json', '.xml', '.csv', '.log', '.yaml', '.yml']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()[:max_lines]
                    preview = ''.join(lines)
                
                console.print(Panel(preview, title="Vista Previa", border_style="blue"))
            
            elif file_ext == '.pdf':
                console.print("[dim]📄 Archivo PDF - Se analizará el contenido completo[/dim]")
            
            elif file_ext in ['.docx', '.doc']:
                console.print("[dim]📝 Archivo Word - Se analizará el contenido completo[/dim]")
            
            elif file_ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                console.print("[dim]🖼️  Imagen - Se analizará visualmente[/dim]")
            
            else:
                console.print(f"[dim]📦 Archivo binario ({file_ext})[/dim]")
        
        except Exception as e:
            console.print(f"[yellow]⚠️  No se pudo mostrar preview: {e}[/yellow]")

    def _display_analysis_result(self, result: Dict, incident_id: str):
        """Muestra resultado del análisis"""
        console.print("\n" + "="*60)
        console.print("[bold green]✅ ANÁLISIS COMPLETADO[/bold green]")
        console.print("="*60 + "\n")
        
        # Veredicto
        verdict = result['verdict']
        confidence = result['confidence']
        
        verdict_styles = {
            'TRUE_POSITIVE': ('🚨 TRUE POSITIVE', 'red'),
            'FALSE_POSITIVE': ('✅ FALSE POSITIVE', 'green'),
            'REQUIRES_REVIEW': ('⚠️  REQUIRES REVIEW', 'yellow')
        }
        
        verdict_text, verdict_color = verdict_styles.get(verdict, ('❓ UNKNOWN', 'white'))
        
        console.print(Panel(
            f"[bold]{verdict_text}[/bold]\n\nConfianza: {confidence:.1%}",
            border_style=verdict_color,
            title="Veredicto"
        ))
        
        # Resumen
        console.print(f"\n[bold]📝 Resumen:[/bold]")
        console.print(result['summary'])
        
        # Razonamiento
        console.print(f"\n[bold]🔍 Razonamiento:[/bold]")
        console.print(result['reasoning'])
        
        # Indicadores
        if result.get('indicators'):
            console.print(f"\n[bold]⚠️  Indicadores Técnicos:[/bold]")
            for indicator in result['indicators']:
                console.print(f"  • {indicator}")
        
        # Recomendaciones
        if result.get('recommendations'):
            console.print(f"\n[bold]💡 Recomendaciones:[/bold]")
            for i, rec in enumerate(result['recommendations'], 1):
                console.print(f"  {i}. {rec}")
        
        # Razones de falso positivo
        if result.get('false_positive_reasons'):
            console.print(f"\n[bold]✅ Razones de Falso Positivo:[/bold]")
            for reason in result['false_positive_reasons']:
                console.print(f"  • {reason}")
        
        console.print(f"\n[dim]Tiempo de procesamiento: {result['processing_time']:.2f}s[/dim]")
        console.print(f"[dim]Incident ID: {incident_id}[/dim]")
        
        # Ofrecer feedback inmediato
        if Confirm.ask("\n¿Deseas proporcionar feedback sobre este análisis?", default=False):
            self._collect_feedback(result, incident_id)

    def _collect_feedback(self, result: Dict, incident_id: str):
        """Recolecta feedback del usuario"""
        console.print("\n[bold cyan]👨‍💼 Feedback de Analista[/bold cyan]\n")
        
        original_verdict = result['verdict']
        console.print(f"[dim]Veredicto original: {original_verdict}[/dim]\n")
        
        # Veredicto correcto
        console.print("Selecciona el veredicto [bold]correcto[/bold]:")
        console.print("  [1] TRUE_POSITIVE")
        console.print("  [2] FALSE_POSITIVE")
        console.print("  [3] REQUIRES_REVIEW")
        
        verdict_map = {
            "1": "TRUE_POSITIVE",
            "2": "FALSE_POSITIVE",
            "3": "REQUIRES_REVIEW"
        }
        
        verdict_choice = Prompt.ask("Opción", choices=["1", "2", "3"])
        corrected_verdict = verdict_map[verdict_choice]
        
        # Comentario
        console.print("\nExplica por qué este es el veredicto correcto:")
        analyst_comment = Prompt.ask("Comentario")
        
        while len(analyst_comment.strip()) < 10:
            console.print("[yellow]⚠️  Comentario muy corto. Proporciona más detalle.[/yellow]")
            analyst_comment = Prompt.ask("Comentario")
        
        # Relevancia
        console.print("\n¿Qué tan relevante es este caso para aprendizaje futuro?")
        console.print("  [1] Muy relevante (1.0)")
        console.print("  [2] Relevante (0.7)")
        console.print("  [3] Poco relevante (0.3)")
        
        relevance_map = {"1": 1.0, "2": 0.7, "3": 0.3}
        relevance_choice = Prompt.ask("Relevancia", choices=["1", "2", "3"])
        relevance_score = relevance_map[relevance_choice]
        
        # Guardar feedback
        success = self.analyzer.submit_feedback(
            incident_id=incident_id,
            analysis_id=result['analysis_id'],
            original_verdict=original_verdict,
            corrected_verdict=corrected_verdict,
            analyst_comment=analyst_comment,
            relevance_score=relevance_score
        )
        
        if success:
            console.print("\n[green]✅ Feedback guardado. El sistema aprenderá de esta corrección.[/green]")
            
            # Actualizar status del incidente
            status = 'analyzed' if corrected_verdict != 'REQUIRES_REVIEW' else 'pending'
            self.db.update_incident_status(incident_id, status)
        else:
            console.print("\n[red]❌ Error guardando feedback[/red]")

    def view_incidents(self):
        """Muestra incidentes existentes"""
        console.print("\n[bold cyan]📋 Incidentes Registrados[/bold cyan]\n")
        
        incidents = self.db.get_all_incidents()
        
        if not incidents:
            console.print("[yellow]⚠️  No hay incidentes registrados[/yellow]")
            Prompt.ask("\nPresiona Enter para continuar")
            return
        
        # Tabla de incidentes
        table = Table(title=f"Total: {len(incidents)} incidentes", box=box.ROUNDED)
        table.add_column("Incident ID", style="cyan", no_wrap=True)
        table.add_column("Archivo", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("Fecha", style="green")
        
        for inc in incidents[:20]:  # Mostrar últimos 20
            status_icons = {
                'pending': '⏳',
                'analyzed': '✅',
                'error': '❌'
            }
            status_icon = status_icons.get(inc['status'], '❓')
            
            table.add_row(
                inc['incident_id'],
                inc['file_name'][:40],
                f"{status_icon} {inc['status']}",
                inc['timestamp'][:10]
            )
        
        console.print(table)
        
        if len(incidents) > 20:
            console.print(f"\n[dim]Mostrando 20 de {len(incidents)} incidentes[/dim]")
        
        Prompt.ask("\nPresiona Enter para continuar")

    def provide_feedback(self):
        """Interfaz para proporcionar feedback sobre incidentes analizados"""
        console.print("\n[bold cyan]👨‍💼 Proporcionar Feedback[/bold cyan]\n")
        
        # Obtener incidentes con análisis
        incidents = self.db.get_all_incidents(status='analyzed')
        
        if not incidents:
            console.print("[yellow]⚠️  No hay incidentes analizados sin feedback[/yellow]")
            Prompt.ask("\nPresiona Enter para continuar")
            return
        
        # Mostrar incidentes
        table = Table(title="Incidentes Analizados", box=box.SIMPLE)
        table.add_column("#", style="cyan", width=6)
        table.add_column("Incident ID", style="white")
        table.add_column("Archivo", style="green")
        
        for idx, inc in enumerate(incidents[:10], 1):
            table.add_row(str(idx), inc['incident_id'], inc['file_name'])
        
        console.print(table)
        console.print()
        
        incident_num = Prompt.ask(
            "Selecciona incidente (#) o [0] para cancelar",
            choices=[str(i) for i in range(len(incidents[:10]) + 1)]
        )
        
        if incident_num == "0":
            return
        
        selected_incident = incidents[int(incident_num) - 1]
        incident_id = selected_incident['incident_id']
        
        # Obtener análisis
        analysis = self.db.get_latest_analysis(incident_id)
        
        if not analysis:
            console.print("[red]❌ No se encontró análisis para este incidente[/red]")
            Prompt.ask("\nPresiona Enter para continuar")
            return
        
        # Mostrar análisis actual
        console.print(f"\n[bold]📊 Análisis actual:[/bold]")
        console.print(f"Veredicto: {analysis['gemini_verdict']}")
        console.print(f"Confianza: {analysis['gemini_confidence']:.1%}")
        console.print(f"\nRazonamiento:\n{analysis['gemini_reasoning']}")
        
        # Recolectar feedback
        result_mock = {
            'verdict': analysis['gemini_verdict'],
            'analysis_id': analysis['id']
        }
        self._collect_feedback(result_mock, incident_id)

    def show_dashboard(self):
        """Dashboard completo"""
        console.print("\n[bold cyan]📊 Dashboard Completo[/bold cyan]\n")
        
        stats = self.db.get_database_stats()
        
        # Stats principales
        table = Table(title="Métricas Generales", box=box.ROUNDED)
        table.add_column("Métrica", style="cyan", no_wrap=True, width=30)
        table.add_column("Valor", style="green", justify="right")
        
        total_incidents = sum(stats.get('incidents_by_status', {}).values())
        table.add_row("Total Incidentes", str(total_incidents))
        table.add_row("Análisis Realizados", str(stats.get('total_analyses', 0)))
        table.add_row("Feedback Recibido", str(stats.get('total_feedback', 0)))
        
        if stats.get('ai_accuracy'):
            table.add_row("Precisión IA", f"{stats['ai_accuracy']:.1f}%")
        
        console.print(table)
        console.print()
        
        # Incidentes por estado
        if stats.get('incidents_by_status'):
            status_table = Table(title="Incidentes por Estado", box=box.ROUNDED)
            status_table.add_column("Estado", style="yellow")
            status_table.add_column("Cantidad", style="green", justify="right")
            
            for status, count in stats['incidents_by_status'].items():
                status_table.add_row(status, str(count))
            
            console.print(status_table)
            console.print()
        
        # Feedback stats
        feedback_stats = self.db.get_feedback_stats()
        
        fb_table = Table(title="Aprendizaje del Sistema (RAG)", box=box.ROUNDED)
        fb_table.add_column("Métrica", style="cyan", width=30)
        fb_table.add_column("Valor", style="green", justify="right")
        
        fb_table.add_row("Total Feedback", str(feedback_stats.get('total_feedback', 0)))
        fb_table.add_row("Correcciones Aplicadas", str(feedback_stats.get('corrections', 0)))
        
        console.print(fb_table)
        
        Prompt.ask("\nPresiona Enter para continuar")

    def configuration(self):
        """Configuración del sistema"""
        console.print("\n[bold cyan]⚙️  Configuración[/bold cyan]\n")
        
        # Mostrar configuración actual
        table = Table(title="Variables de Entorno", box=box.ROUNDED)
        table.add_column("Variable", style="cyan")
        table.add_column("Estado", style="green")
        
        env_vars = [
            ("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")),
            ("CYBERHAVEN_API_KEY", os.getenv("CYBERHAVEN_API_KEY")),
            ("AWS_S3_BUCKET", os.getenv("AWS_S3_BUCKET")),
            ("EVIDENCE_DIR", os.getenv("EVIDENCE_DIR", "./evidencia_temp")),
        ]
        
        for var, value in env_vars:
            if value:
                masked_value = value[:8] + "..." if len(value) > 8 else value
                table.add_row(var, f"✅ {masked_value}")
            else:
                table.add_row(var, "❌ No configurada")
        
        console.print(table)
        console.print()
        
        # Opciones de mantenimiento
        console.print("[bold]Opciones de Mantenimiento:[/bold]")
        console.print("  [1] Limpiar datos antiguos (>30 días)")
        console.print("  [2] Ver historial de feedback")
        console.print("  [3] Verificar integridad de DB")
        console.print("  [0] Volver")
        
        choice = Prompt.ask("Opción", choices=["0", "1", "2", "3"])
        
        if choice == "1":
            if Confirm.ask("\n¿Eliminar datos de más de 30 días?", default=False):
                deleted = self.db.clear_old_data(days=30)
                console.print(f"\n[green]✅ Eliminados:[/green]")
                console.print(f"  - Incidentes: {deleted[0]}")
                console.print(f"  - Análisis: {deleted[1]}")
                console.print(f"  - Feedback: {deleted[2]}")
        
        elif choice == "2":
            feedback_items = self.db.get_feedback_for_rag(limit=10)
            
            if feedback_items:
                console.print("\n[bold]📚 Historial de Feedback (últimos 10):[/bold]\n")
                for fb in feedback_items:
                    console.print(f"[cyan]Archivo:[/cyan] {fb['file_name']}")
                    console.print(f"  Original: {fb['original_verdict']} → Correcto: {fb['corrected_verdict']}")
                    console.print(f"  Comentario: {fb.get('analyst_comment', 'N/A')}")
                    console.print()
            else:
                console.print("\n[yellow]⚠️  No hay feedback histórico[/yellow]")
        
        elif choice == "3":
            console.print("\n[green]✅ Base de datos operativa[/green]")
        
        Prompt.ask("\nPresiona Enter para continuar")

    def run(self):
        """Loop principal"""
        while True:
            self.show_header()
            self.show_stats()
            
            choice = self.main_menu()
            
            if choice == "0":
                console.print("\n[bold cyan]👋 ¡Hasta luego![/bold cyan]\n")
                sys.exit(0)
            
            elif choice == "1":
                self.download_incidents()
            
            elif choice == "2":
                self.analyze_files()
            
            elif choice == "3":
                self.view_incidents()
            
            elif choice == "4":
                self.provide_feedback()
            
            elif choice == "5":
                self.show_dashboard()
            
            elif choice == "6":
                self.configuration()


def main():
    """Entry point"""
    try:
        cli = CyberTriageCLI()
        cli.run()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]⚠️  Interrumpido por usuario[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]❌ Error crítico: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
