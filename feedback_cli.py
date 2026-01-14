#!/usr/bin/env python3
import os
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich import box

from db_manager import DatabaseManager

console = Console()
BASE_INCIDENTS_DIR = os.getenv("INCIDENTS_DIR", "./data/incidents")


def clear():
    console.clear()


def print_header():
    console.print(Panel(
        "[bold cyan]CYBER-TRIAGE[/bold cyan] | [white]Revisión de Análisis[/white]",
        style="blue"
    ))
    console.print()


def get_analyzed_incidents(db: DatabaseManager, date: str = None, limit: int = 20):
    conn = db._get_connection()
    cursor = conn.cursor()
    try:
        if date:
            cursor.execute('''
                SELECT i.*, a.gemini_verdict, a.gemini_confidence, a.executive_summary, 
                       a.risk_level, a.id as analysis_id
                FROM incidents i
                JOIN analysis a ON i.incident_id = a.incident_id
                WHERE i.incident_date = ?
                ORDER BY a.created_at DESC
                LIMIT ?
            ''', (date, limit))
        else:
            cursor.execute('''
                SELECT i.*, a.gemini_verdict, a.gemini_confidence, a.executive_summary,
                       a.risk_level, a.id as analysis_id
                FROM incidents i
                JOIN analysis a ON i.incident_id = a.incident_id
                ORDER BY a.created_at DESC
                LIMIT ?
            ''', (limit,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def has_feedback(db: DatabaseManager, incident_id: str) -> bool:
    conn = db._get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT 1 FROM feedback WHERE incident_id = ? LIMIT 1', (incident_id,))
        return cursor.fetchone() is not None
    finally:
        conn.close()


def display_incident_list(incidents, db):
    table = Table(title="Incidentes Analizados", box=box.SIMPLE_HEAD, expand=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Fecha", style="blue", width=12)
    table.add_column("Usuario", width=25)
    table.add_column("Veredicto", width=15)
    table.add_column("Confianza", width=10)
    table.add_column("Riesgo", width=10)
    table.add_column("Revisado", width=8)
    
    for idx, inc in enumerate(incidents, 1):
        verdict = inc.get('gemini_verdict', '?')
        confidence = inc.get('gemini_confidence', 0)
        risk = inc.get('risk_level', 'N/A')
        
        verdict_color = {'TRUE_POSITIVE': 'red', 'FALSE_POSITIVE': 'green', 'REQUIRES_REVIEW': 'yellow'}.get(verdict, 'white')
        
        reviewed = "✓" if has_feedback(db, inc['incident_id']) else ""
        
        table.add_row(
            str(idx),
            inc.get('incident_date', '?'),
            inc.get('user_email', '?')[:24],
            f"[{verdict_color}]{verdict}[/{verdict_color}]",
            f"{confidence*100:.0f}%",
            risk,
            f"[green]{reviewed}[/green]"
        )
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(incidents)} incidentes[/dim]\n")


def display_incident_detail(inc, db):
    clear()
    print_header()
    
    verdict = inc.get('gemini_verdict', '?')
    verdict_color = {'TRUE_POSITIVE': 'red', 'FALSE_POSITIVE': 'green', 'REQUIRES_REVIEW': 'yellow'}.get(verdict, 'white')
    verdict_emoji = {'TRUE_POSITIVE': '🚨', 'FALSE_POSITIVE': '✅', 'REQUIRES_REVIEW': '⚠️'}.get(verdict, '❓')
    
    info_table = Table(box=None, show_header=False, padding=(0, 2))
    info_table.add_column(style="bold")
    info_table.add_column()
    info_table.add_row("ID:", inc['incident_id'][:40] + "...")
    info_table.add_row("Fecha:", inc.get('incident_date', '?'))
    info_table.add_row("Usuario:", inc.get('user_email', '?'))
    info_table.add_row("Severidad:", f"{inc.get('severity', '?')} / {inc.get('policy_severity', '?')}")
    info_table.add_row("Archivo:", inc.get('file_name', 'Sin archivo'))
    
    console.print(Panel(info_table, title="[bold]Información del Incidente[/bold]", border_style="blue"))
    console.print()
    
    console.print(Panel(
        f"[bold {verdict_color}]{verdict_emoji} {verdict}[/bold {verdict_color}]\n\n"
        f"[bold]Confianza:[/bold] {inc.get('gemini_confidence', 0)*100:.1f}%\n"
        f"[bold]Riesgo:[/bold] {inc.get('risk_level', 'N/A')}",
        title="[bold]Veredicto de Gemini[/bold]",
        border_style=verdict_color
    ))
    console.print()
    
    summary = inc.get('executive_summary', 'Sin resumen disponible')
    console.print(Panel(summary, title="[bold]Resumen Ejecutivo[/bold]", border_style="white"))
    console.print()
    
    incident_dir = Path(BASE_INCIDENTS_DIR) / inc.get('incident_date', '') / inc['incident_id']
    analysis_file = incident_dir / "analysis_result.json"
    
    if analysis_file.exists():
        import json
        with open(analysis_file, 'r') as f:
            analysis = json.load(f)
        reasoning = analysis.get('reasoning', 'Sin razonamiento')
        console.print(Panel(reasoning, title="[bold]Razonamiento Técnico[/bold]", border_style="dim"))
        console.print()
    
    reviewed = has_feedback(db, inc['incident_id'])
    if reviewed:
        console.print("[green]✓ Este incidente ya fue revisado[/green]\n")


def collect_feedback(inc, db):
    console.print(Panel("[bold]VALIDACIÓN DEL ANALISTA[/bold]", style="cyan"))
    
    current_verdict = inc.get('gemini_verdict', '?')
    
    if Confirm.ask(f"¿El veredicto [bold]{current_verdict}[/bold] es correcto?", default=True):
        feedback_data = {
            'incident_id': inc['incident_id'],
            'analysis_id': inc.get('analysis_id'),
            'original_verdict': current_verdict,
            'corrected_verdict': current_verdict,
            'analyst_comment': 'Confirmado por analista',
            'relevance_score': 1.0
        }
        db.insert_feedback(feedback_data)
        console.print("[green]✅ Feedback guardado (Confirmado)[/green]")
        return True
    
    console.print("\n[bold]Seleccione el veredicto correcto:[/bold]")
    console.print("1. TRUE_POSITIVE  🚨 (Fuga real)")
    console.print("2. FALSE_POSITIVE ✅ (Falso positivo)")
    console.print("3. REQUIRES_REVIEW ⚠️ (Necesita más revisión)")
    console.print("0. Cancelar")
    
    choice = Prompt.ask("Opción", choices=["0", "1", "2", "3"], default="0")
    
    if choice == "0":
        console.print("[yellow]Cancelado[/yellow]")
        return False
    
    verdicts = {"1": "TRUE_POSITIVE", "2": "FALSE_POSITIVE", "3": "REQUIRES_REVIEW"}
    corrected = verdicts[choice]
    
    comment = Prompt.ask("Comentario (explica la corrección)", default="")
    
    feedback_data = {
        'incident_id': inc['incident_id'],
        'analysis_id': inc.get('analysis_id'),
        'original_verdict': current_verdict,
        'corrected_verdict': corrected,
        'analyst_comment': comment,
        'relevance_score': 1.0
    }
    
    db.insert_feedback(feedback_data)
    console.print(f"[green]✅ Feedback guardado: {current_verdict} → {corrected}[/green]")
    return True


def show_stats(db):
    clear()
    print_header()
    
    stats = db.get_database_stats()
    
    table = Table(title="Estadísticas del Sistema", box=box.ROUNDED)
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", style="white")
    
    table.add_row("Total Incidentes", str(sum(stats.get('incidents_by_status', {}).values())))
    table.add_row("Total Análisis", str(stats.get('total_analyses', 0)))
    table.add_row("Total Feedback", str(stats.get('total_feedback', 0)))
    table.add_row("Precisión IA", f"{stats.get('ai_accuracy', 0):.1f}%")
    table.add_row("Tokens Usados", f"{stats.get('total_tokens_used', 0):,}")
    
    console.print(table)
    console.print()
    
    if stats.get('incidents_by_status'):
        console.print("[bold]Por Estado:[/bold]")
        for status, count in stats['incidents_by_status'].items():
            console.print(f"  • {status}: {count}")
    
    if stats.get('incidents_last_7_days'):
        console.print("\n[bold]Últimos 7 días:[/bold]")
        for date, count in stats['incidents_last_7_days'].items():
            console.print(f"  • {date}: {count} incidentes")
    
    console.print()
    Prompt.ask("[dim]Enter para continuar[/dim]")


def main_menu():
    db = DatabaseManager()
    
    while True:
        clear()
        print_header()
        
        menu = Table(box=box.SIMPLE, show_header=False)
        menu.add_column(style="cyan", width=4)
        menu.add_column(style="white")
        
        menu.add_row("1", "📋 Ver incidentes de HOY")
        menu.add_row("2", "📅 Ver incidentes por fecha")
        menu.add_row("3", "🕐 Ver últimos 20 analizados")
        menu.add_row("4", "📊 Ver estadísticas")
        menu.add_row("0", "🚪 Salir")
        
        console.print(menu)
        console.print()
        
        choice = Prompt.ask("Opción", choices=["0", "1", "2", "3", "4"], default="1")
        
        if choice == "0":
            console.print("[cyan]Hasta luego![/cyan]")
            sys.exit(0)
        
        elif choice == "1":
            today = datetime.now().strftime('%Y-%m-%d')
            incidents = get_analyzed_incidents(db, date=today)
            
        elif choice == "2":
            date_input = Prompt.ask("Fecha (YYYY-MM-DD)", default=datetime.now().strftime('%Y-%m-%d'))
            incidents = get_analyzed_incidents(db, date=date_input)
            
        elif choice == "3":
            incidents = get_analyzed_incidents(db, limit=20)
            
        elif choice == "4":
            show_stats(db)
            continue
        
        if choice in ["1", "2", "3"]:
            if not incidents:
                console.print("[yellow]No hay incidentes analizados[/yellow]")
                Prompt.ask("[dim]Enter para continuar[/dim]")
                continue
            
            while True:
                clear()
                print_header()
                display_incident_list(incidents, db)
                
                console.print("[bold]Opciones:[/bold]")
                console.print("1-N  Ver detalle y dar feedback")
                console.print("0    Volver al menú")
                
                sel = Prompt.ask("Selección", default="0")
                
                if sel == "0":
                    break
                
                if sel.isdigit() and 1 <= int(sel) <= len(incidents):
                    selected = incidents[int(sel) - 1]
                    display_incident_detail(selected, db)
                    collect_feedback(selected, db)
                    Prompt.ask("[dim]Enter para continuar[/dim]")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelado[/yellow]")
        sys.exit(0)