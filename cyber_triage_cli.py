#!/usr/bin/env python3
"""
Cyber-Triage CLI - Sistema de análisis automatizado de incidentes DLP
v2.1 - Enhanced TUI Experience
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Rich Imports
from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm, IntPrompt
from rich import box
from rich.layout import Layout

# Project Imports
from db_manager import DatabaseManager
from gemini_analyzer import GeminiAnalyzer
import evidence_downloader

console = Console()
EVIDENCE_DIR = Path(os.getenv("EVIDENCE_DIR", "./evidencia_temp"))

# --- UTILIDADES DE UI ---

def clear_screen():
    """Limpia la pantalla para una experiencia tipo App"""
    console.clear()

def pause():
    """Pausa la ejecución hasta que el usuario esté listo"""
    console.print()
    console.print(Align.center("[dim]Presiona [bold]Enter[/bold] para volver al menú...[/dim]"))
    input()

def print_banner():
    """Imprime el banner ASCII"""
    banner = """
   ██████╗██╗   ██╗██████╗ ███████╗██████╗       ████████╗██████╗ ██╗ █████╗  ██████╗ ███████╗
  ██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗      ╚══██╔══╝██╔══██╗██║██╔══██╗██╔════╝ ██╔════╝
  ██║      ╚████╔╝ ██████╔╝█████╗  ██████╔╝█████╗   ██║   ██████╔╝██║███████║██║  ███╗█████╗  
  ██║       ╚██╔╝  ██╔══██╗██╔══╝  ██╔══██╗╚════╝   ██║   ██╔══██╗██║██╔══██║██║   ██║██╔══╝  
  ╚██████╗   ██║   ██████╔╝███████╗██║  ██║         ██║   ██║  ██║██║██║  ██║╚██████╔╝███████╗
   ╚═════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝         ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
                                                                      v2.1 | Powered by Gemini 2.5
    """
    console.print(Text(banner, style="bold cyan"), justify="center")
    console.print(Align.center(Text("🛡️  SISTEMA DE ANÁLISIS AUTOMATIZADO DE INCIDENTES DLP  🛡️", style="bold white on blue")))
    console.print()

def system_check_step(step_name, status_func):
    """Ejecuta un paso de verificación con animación"""
    with console.status(f"[bold yellow]Verificando {step_name}...", spinner="dots") as status:
        time.sleep(0.3) 
        try:
            result = status_func()
            if result:
                console.print(f"  [green]✔[/green] {step_name}: [green]ONLINE[/green]")
                return result
            else:
                console.print(f"  [red]✖[/red] {step_name}: [red]OFFLINE/ERROR[/red]")
                return None
        except Exception as e:
            console.print(f"  [red]✖[/red] {step_name}: [red]{e}[/red]")
            return None

def initialize_system_pro():
    """Secuencia de inicio profesional"""
    clear_screen()
    print_banner()
    
    console.print(Panel("🔧 INICIALIZANDO SISTEMA", style="blue"))
    
    # 1. Database Check
    db = system_check_step("Base de Datos (SQLite)", lambda: DatabaseManager())
    
    # 2. Gemini API Check
    def check_gemini():
        if not db: return None
        return GeminiAnalyzer(db_manager=db)
    
    analyzer = system_check_step("Motor IA (Gemini 2.5)", check_gemini)
    
    # 3. Directorios
    def check_dirs():
        Path("./data").mkdir(exist_ok=True)
        Path("./logs").mkdir(exist_ok=True)
        return EVIDENCE_DIR.exists() or EVIDENCE_DIR.mkdir(exist_ok=True) or True
        
    system_check_step("Sistema de Archivos", check_dirs)

    # 4. Cyberhaven Token
    def check_token():
        return os.getenv("CYBERHAVEN_API_KEY") is not None
    
    system_check_step("Credenciales Cyberhaven", check_token)
    
    time.sleep(1)
    
    if db and analyzer:
        return db, analyzer
    else:
        console.print("\n[bold red]❌ Error Crítico: El sistema no puede iniciar correctamente.[/bold red]")
        sys.exit(1)

# --- FUNCIONES CORE ---

def download_incidents():
    clear_screen()
    print_banner()
    
    console.print(Panel("📥 DESCARGA DE INCIDENTES", style="blue"))
    console.print("[dim]Conectando con Cyberhaven y AWS S3...[/dim]\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Sincronizando...", total=None)
        
        try:
            evidence_downloader.main()
            progress.update(task, completed=True)
            console.print("\n[bold green]✅ Sincronización finalizada correctamente[/bold green]")
        except Exception as e:
            console.print(f"\n[bold red]❌ Error en descarga: {e}[/bold red]")
    
    pause()

def list_incidents_data():
    """Retorna la lista de incidentes sin imprimir nada (helper)"""
    if not EVIDENCE_DIR.exists():
        return []
    return [d for d in EVIDENCE_DIR.iterdir() if d.is_dir()]

def display_analysis_result(result):
    """Muestra resultado del análisis (Componente UI)"""
    if not result['success']:
        console.print(f"[red]❌ Error: {result['error']}[/red]\n")
        return

    colors = {
        'TRUE_POSITIVE': 'red',
        'FALSE_POSITIVE': 'green',
        'REQUIRES_REVIEW': 'yellow'
    }
    color = colors.get(result['verdict'], 'white')
    emoji = {'TRUE_POSITIVE': '🚨', 'FALSE_POSITIVE': '✅', 'REQUIRES_REVIEW': '⚠️'}.get(result['verdict'], '❓')
    
    ctx = result.get('incident_context', {})
    
    # Tabla Contexto
    context_table = Table(box=None, show_header=False, padding=(0, 2))
    context_table.add_column(style="bold white")
    context_table.add_column(style="white")
    context_table.add_row("Usuario:", str(ctx.get('user', 'N/A')))
    context_table.add_row("Origen:", str(ctx.get('source', 'N/A')))
    context_table.add_row("Destino:", f"[{color}]{ctx.get('destination', 'N/A')}[/{color}]")

    # Contenido Agrupado
    main_content = Group(
        Panel(
            result.get('executive_summary', 'Sin resumen.'),
            title="[bold]Resumen Ejecutivo[/bold]",
            border_style="white"
        ),
        Text(""),
        context_table,
        Text(""),
        Panel(
            result['reasoning'],
            title="[bold]Análisis Técnico[/bold]",
            border_style=color
        )
    )

    console.print(Panel(
        main_content,
        title=f"{emoji} {result['verdict']}",
        subtitle=f"Confianza: {result['confidence']*100:.1f}% | Riesgo: {result.get('risk_level', 'N/A')}",
        border_style=color,
        expand=True
    ))

    if result.get('indicators'):
        console.print("[bold]Indicadores:[/bold]")
        for ind in result['indicators']:
            console.print(f" • {ind}", style="dim")
    console.print()

def collect_feedback(result):
    """UI para feedback"""
    console.print(Panel("👨‍💼 VALIDACIÓN DE ANALISTA", style="cyan"))
    
    if Confirm.ask(f"¿El veredicto [bold]{result['verdict']}[/bold] es correcto?", default=True):
        console.print("[green]✅ Feedback guardado (Positivo)[/green]")
        return None
    
    console.print("\n[bold]Seleccione el veredicto real:[/bold]")
    console.print("1. TRUE_POSITIVE 🚨")
    console.print("2. FALSE_POSITIVE ✅")
    console.print("3. REQUIRES_REVIEW ⚠️")
    
    choice = IntPrompt.ask("Opción", choices=["1", "2", "3"])
    verdicts = {"1": "TRUE_POSITIVE", "2": "FALSE_POSITIVE", "3": "REQUIRES_REVIEW"}
    
    corrected = verdicts[str(choice)]
    comment = Prompt.ask("Comentario de corrección")
    
    return {
        'original_verdict': result['verdict'],
        'corrected_verdict': corrected,
        'analyst_comment': comment,
        'relevance_score': 1.0
    }

def analyze_incidents_menu(analyzer):
    while True:
        clear_screen()
        print_banner()
        
        incidents = list_incidents_data()
        
        if not incidents:
            console.print(Panel("⚠️  No hay incidentes descargados", style="yellow"))
            if Confirm.ask("¿Desea descargar incidentes ahora?"):
                download_incidents()
                continue
            else:
                break

        # Tabla de Selección
        table = Table(title="📋 SELECCIÓN DE INCIDENTE", box=box.SIMPLE_HEAD, expand=True)
        table.add_column("#", justify="right", style="cyan", no_wrap=True)
        table.add_column("ID / Archivo", style="white")
        table.add_column("Fecha", style="blue")

        for idx, inc_dir in enumerate(incidents, 1):
            files = [f.name for f in inc_dir.iterdir() if f.name != "metadata.json"]
            file_name = files[0] if files else "[dim]Sin archivo[/dim]"
            timestamp = inc_dir.stat().st_mtime
            date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
            
            table.add_row(str(idx), f"{file_name}\n[dim]{inc_dir.name[:20]}...[/dim]", date_str)
            table.add_section()

        console.print(table)
        console.print(f"\n[dim]Total: {len(incidents)} incidentes disponibles[/dim]\n")
        
        console.print("[bold]Opciones:[/bold]")
        console.print("1-N. Analizar incidente específico")
        console.print("A.   Analizar [bold]A[/bold]LL (Todos)")
        console.print("0.   Volver al menú principal")
        
        choice = Prompt.ask("\nSelección").upper()
        
        if choice == '0':
            break
            
        to_process = []
        if choice == 'A':
            to_process = incidents
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(incidents):
                to_process = [incidents[idx]]
        
        if not to_process:
            continue
            
        # PROCESAMIENTO
        for inc_dir in to_process:
            clear_screen()
            print_banner()
            console.print(f"🔍 Analizando: [cyan]{inc_dir.name}[/cyan]\n")
            
            with console.status("[bold cyan]Consultando a Gemini 2.5 Pro...[/bold cyan]", spinner="earth"):
                result = analyzer.analyze_incident(inc_dir.name, inc_dir, use_rag=True)
            
            display_analysis_result(result)
            
            if result['success']:
                fb = collect_feedback(result)
                if fb:
                    analyzer.submit_feedback(result['incident_id'], result['analysis_id'], **fb)
            
            console.print("\n" + "─"*50 + "\n")
            if len(to_process) > 1:
                time.sleep(2)
            else:
                pause()

def dashboard_menu(db):
    clear_screen()
    print_banner()
    
    stats = db.get_database_stats()
    
    grid = Table.grid(expand=True, padding=2)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    
    # Paneles de estadísticas
    p1 = Panel(f"[bold green]{stats.get('total_analyses', 0)}[/bold green]", title="Total Análisis", border_style="green")
    p2 = Panel(f"[bold blue]{stats.get('total_feedback', 0)}[/bold blue]", title="Feedback Humano", border_style="blue")
    p3 = Panel(f"[bold yellow]{stats.get('ai_accuracy', 0):.1f}%[/bold yellow]", title="Precisión IA", border_style="yellow")
    
    grid.add_row(p1, p2, p3)
    
    console.print(Panel(grid, title="📊 DASHBOARD DE RENDIMIENTO", border_style="white"))
    
    # Detalle de estatus
    if 'incidents_by_status' in stats:
        console.print("\n[bold]Estado de Incidentes:[/bold]")
        for status, count in stats['incidents_by_status'].items():
            console.print(f" • {status.title()}: {count}")

    pause()

def main_menu():
    """Bucle principal"""
    db, analyzer = initialize_system_pro()
    
    while True:
        clear_screen()
        print_banner()
        
        menu = Table(box=box.DOUBLE_EDGE, show_header=False, expand=True)
        menu.add_column("Opción", style="cyan", justify="center", width=4)
        menu.add_column("Descripción", style="white")
        
        menu.add_row("1", "📥  Sincronizar Incidentes (Descargar)")
        menu.add_row("2", "🔍  Analizar Incidentes Pendientes")
        menu.add_row("3", "📊  Ver Dashboard y Métricas")
        menu.add_row("4", "🚪  Salir del Sistema")
        
        console.print(menu)
        
        choice = Prompt.ask("\n[bold]>> Seleccione una opción[/bold]", choices=["1", "2", "3", "4"])
        
        if choice == "1":
            download_incidents()
        elif choice == "2":
            analyze_incidents_menu(analyzer)
        elif choice == "3":
            dashboard_menu(db)
        elif choice == "4":
            console.print("\n[bold cyan]👋 Cerrando sesión segura...[/bold cyan]")
            time.sleep(0.5)
            clear_screen()
            sys.exit(0)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Operación cancelada por usuario[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]❌ Error fatal no controlado: {e}[/red]")
        sys.exit(1)
