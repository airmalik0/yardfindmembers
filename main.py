#!/usr/bin/env python3
import click
import json
import subprocess
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import track
from workflows.main_workflow import ProfileProcessingWorkflow, BatchProcessingWorkflow
from agents.text_analyzer import TextAnalyzerAgent
from agents.embedding_agent import EmbeddingAgent
from utils.sheets_manager import GoogleSheetsManager
from utils.data_models import AnalysisRequest, MemberProfile, AnalysisResult
from utils.table_generator import TableGenerator
import config

console = Console()


@click.group()
def cli():
    """YARD Business Club Profile Analyzer - AI-powered profile extraction and analysis"""
    pass


@cli.command()
@click.option('--image', '-i', type=click.Path(exists=True), help='Path to a single image file')
@click.option('--directory', '-d', type=click.Path(exists=True), help='Directory containing images')
@click.option('--photos-dir', is_flag=True, help='Use default photos directory from config')
def extract(image, directory, photos_dir):
    """Extract profiles from images"""
    
    workflow = BatchProcessingWorkflow()
    
    if image:
        # Process single image
        console.print(f"[cyan]Processing image: {image}[/cyan]")
        profile_workflow = ProfileProcessingWorkflow()
        result = profile_workflow.process_single_image(image)
        
        if result.get("error"):
            console.print(f"[red]Error: {result['error']}[/red]")
        else:
            profile = result.get("profile")
            if profile:
                if result.get("was_cached"):
                    console.print(f"[green]✓ Using existing profile for: {profile.get('name')}[/green]")
                else:
                    console.print(f"[green]✓ Successfully extracted profile for: {profile.get('name')}[/green]")
                
                # Display profile info
                table = Table(title="Profile Information")
                table.add_column("Field", style="cyan")
                table.add_column("Value", style="white")
                
                for key, value in profile.items():
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    elif isinstance(value, dict):
                        value = json.dumps(value, ensure_ascii=False)
                    table.add_row(key.replace("_", " ").title(), str(value) if value else "")
                
                console.print(table)
    
    elif directory or photos_dir:
        # Process batch
        target_dir = Path(directory) if directory else config.PHOTOS_DIR
        console.print(f"[cyan]Processing images from: {target_dir}[/cyan]")
        
        summary = workflow.process_all_images(target_dir)
        
        # Display summary if there were images
        if summary.get("total", 0) > 0:
            table = Table(title="Processing Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="white")
            
            table.add_row("Total Images", str(summary["total"]))
            table.add_row("Successful", f"[green]{summary['successful']}[/green]")
            table.add_row("Failed", f"[red]{summary['failed']}[/red]")
            
            console.print(table)
    
    else:
        console.print("[yellow]Please specify an image, directory, or use --photos-dir flag[/yellow]")


@cli.command()
@click.option('--criteria', '-c', required=True, help='Search criteria (e.g., "связан с отелями")')
@click.option('--search-type', type=click.Choice(['professional', 'personal']), 
              default='professional', help='Type of search: professional (business/expertise) or personal (hobbies/family)')
@click.option('--top-k', '-k', type=click.IntRange(0, 100), default=10,
              help='Number of profiles to analyze with AI (0-100, default: 10). 0 = no AI analysis, only similarity ranking')
@click.option('--create-sheet', is_flag=True, help='Create Google Sheet with results')
def analyze(criteria, search_type, top_k, create_sheet):
    """Analyze profiles based on criteria"""
    
    console.print(f"[cyan]Analyzing profiles with criteria: {criteria}[/cyan]")
    console.print(f"[cyan]Using embeddings search ({search_type} mode)[/cyan]")
    if top_k > 0:
        console.print(f"[cyan]Analyzing top {top_k} profiles with AI[/cyan]")
    else:
        console.print(f"[cyan]No AI analysis - only similarity ranking[/cyan]")
    
    # Create analyzer
    analyzer = TextAnalyzerAgent()
    
    # Always use smart_analyze with embeddings
    results = analyzer.smart_analyze(criteria, search_type, top_k)
    
    # Save results
    filepath = analyzer.save_analysis_results(results, criteria)
    
    # Display results
    table = Table(title="Analysis Results")
    table.add_column("Name", style="cyan")
    table.add_column("Match", style="white")
    table.add_column("Reasoning", style="white", width=50)
    
    # Display only analyzed profiles (those with reasoning)
    for result in results:
        if result.reasoning:  # Only show profiles that were analyzed by LLM
            match_symbol = "✓" if result.matches else "✗"
            match_color = "green" if result.matches else "red"
            
            table.add_row(
                result.profile_name,
                f"[{match_color}]{match_symbol}[/{match_color}]",
                result.reasoning[:100] + "..." if len(result.reasoning) > 100 else result.reasoning
            )
    
    console.print(table)
    
    # Summary
    total = len(results)
    matched = sum(1 for r in results if r.matches)
    console.print(f"\n[bold]Summary:[/bold] {matched}/{total} profiles matched")
    
    # Create Google Sheet if requested
    if create_sheet and results:
        sheets_manager = GoogleSheetsManager()
        # Use the new format with AnalysisResult objects
        spreadsheet_id = sheets_manager.create_analysis_sheet(
            analysis_results=results,
            criteria=criteria,
            mode="professional"  # Could be made configurable
        )
        if spreadsheet_id:
            console.print(f"[green]✓ Created Google Sheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}[/green]")


@cli.command()
def index_embeddings():
    """Index all profiles for embedding-based search"""
    console.print("[cyan]Indexing all profiles for embedding search...[/cyan]")
    
    embedding_agent = EmbeddingAgent()
    count = embedding_agent.batch_index_all_profiles()
    
    console.print(f"[green]✓ Successfully indexed {count} profiles[/green]")
    console.print("[yellow]Now you can use fast embedding search with analyze command[/yellow]")


@cli.command()
@click.option('--clear', is_flag=True, help='Clear all indexes before re-indexing')
def reindex(clear):
    """Re-index all profiles (useful after adding new profiles)"""
    embedding_agent = EmbeddingAgent()
    
    if clear:
        console.print("[yellow]Clearing existing indexes...[/yellow]")
        embedding_agent.clear_all_indexes()
    
    console.print("[cyan]Re-indexing all profiles...[/cyan]")
    count = embedding_agent.batch_index_all_profiles()
    
    console.print(f"[green]✓ Successfully re-indexed {count} profiles[/green]")


@cli.command()
def sync():
    """Sync all profiles to Google Sheets"""
    
    console.print("[cyan]Syncing all profiles to Google Sheets...[/cyan]")
    
    sheets_manager = GoogleSheetsManager()
    success = sheets_manager.sync_all_to_sheets()
    
    if success:
        console.print("[green]✓ Successfully synced profiles to Google Sheets[/green]")
        if config.MASTER_SPREADSHEET_ID:
            console.print(f"[green]Master sheet: https://docs.google.com/spreadsheets/d/{config.MASTER_SPREADSHEET_ID}[/green]")
    else:
        console.print("[red]✗ Failed to sync profiles[/red]")


@cli.command()
def list_profiles():
    """List all extracted profiles"""
    
    json_files = list(config.PROFILES_DIR.glob("*.json"))
    
    if not json_files:
        console.print("[yellow]No profiles found[/yellow]")
        return
    
    table = Table(title=f"Extracted Profiles ({len(json_files)} total)")
    table.add_column("#", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Expertise", style="white")
    table.add_column("Business", style="white")
    table.add_column("File", style="dim")
    
    for i, json_file in enumerate(json_files, 1):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
                expertise = profile_data.get("expertise", "")
                business = profile_data.get("business", "")
                table.add_row(
                    str(i),
                    profile_data.get("name", "Unknown"),
                    expertise[:40] + "..." if len(expertise) > 40 else expertise,
                    business[:40] + "..." if len(business) > 40 else business,
                    json_file.name
                )
        except Exception as e:
            console.print(f"[red]Error reading {json_file}: {e}[/red]")
    
    console.print(table)


@cli.command()
@click.argument('name')
def show(name):
    """Show detailed profile information"""
    
    # Try to find profile by name
    json_files = list(config.PROFILES_DIR.glob("*.json"))
    
    found = False
    for json_file in json_files:
        with open(json_file, 'r', encoding='utf-8') as f:
            profile_data = json.load(f)
            if name.lower() in profile_data.get("name", "").lower():
                found = True
                profile = MemberProfile(**profile_data)
                
                # Display as markdown
                console.print(profile.to_markdown())
                break
    
    if not found:
        console.print(f"[yellow]Profile not found for: {name}[/yellow]")


@cli.command()
@click.argument('analysis_file', type=click.Path(exists=True), required=False)
def sync_analysis(analysis_file):
    """Create Google Sheet from existing analysis results
    
    If ANALYSIS_FILE is not provided, will show list of available analysis files.
    """
    
    if not analysis_file:
        # Show available analysis files
        analysis_files = sorted(config.ANALYSIS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not analysis_files:
            console.print("[yellow]No analysis results found in data/analysis_results/[/yellow]")
            return
        
        console.print("[cyan]Available analysis results:[/cyan]")
        for i, file in enumerate(analysis_files[:10], 1):  # Show last 10
            console.print(f"{i}. {file.name}")
        
        choice = click.prompt("Enter number to select analysis", type=int)
        if 1 <= choice <= len(analysis_files):
            analysis_file = analysis_files[choice - 1]
        else:
            console.print("[red]Invalid selection[/red]")
            return
    
    # Load analysis results
    console.print(f"[cyan]Loading analysis from: {analysis_file}[/cyan]")
    
    try:
        with open(analysis_file, 'r', encoding='utf-8') as f:
            analysis_data = json.load(f)
        
        criteria = analysis_data.get("criteria", "Unknown")
        results_data = analysis_data.get("results", [])
        
        # Convert to AnalysisResult objects
        results = []
        for result_dict in results_data:
            # Handle both old and new formats
            result = AnalysisResult(
                profile_name=result_dict.get("profile_name", ""),
                matches=result_dict.get("matches", False),
                reasoning=result_dict.get("reasoning", ""),
                similarity_score=result_dict.get("similarity_score", 0.0)  # May not exist in old files
            )
            results.append(result)
        
        if not results:
            console.print("[yellow]No results found in this analysis[/yellow]")
            return
        
        # Count matched profiles
        matched_count = sum(1 for r in results if r.matches)
        
        # Create Google Sheet with ALL profiles (new format)
        console.print(f"[cyan]Creating Google Sheet with {len(results)} profiles ({matched_count} matched)...[/cyan]")
        
        sheets_manager = GoogleSheetsManager()
        # Use the new method signature
        spreadsheet_id = sheets_manager.create_analysis_sheet(
            analysis_results=results,
            criteria=criteria,
            mode="professional"  # Default to professional, could be stored in analysis file
        )
        
        if spreadsheet_id:
            console.print(f"[green]✓ Created Google Sheet: https://docs.google.com/spreadsheets/d/{spreadsheet_id}[/green]")
        else:
            console.print("[red]Failed to create Google Sheet[/red]")
            
    except Exception as e:
        console.print(f"[red]Error loading analysis: {str(e)}[/red]")


@cli.command()
def setup():
    """Setup wizard for configuration"""
    
    console.print("[bold cyan]YARD Business Club Analyzer Setup[/bold cyan]\n")
    
    # Check for .env file
    env_path = Path(".env")
    if not env_path.exists():
        console.print("[yellow]Creating .env file...[/yellow]")
        
        # Ask for OpenAI API key
        api_key = click.prompt("Enter your OpenAI API key", hide_input=True)
        
        # Ask for Google Sheets setup
        use_sheets = click.confirm("Do you want to set up Google Sheets integration?")
        
        env_content = f"OPENAI_API_KEY={api_key}\n"
        
        if use_sheets:
            console.print("\n[cyan]Google Sheets Setup:[/cyan]")
            console.print("1. Go to https://console.cloud.google.com/")
            console.print("2. Create a new project or select existing")
            console.print("3. Enable Google Sheets API")
            console.print("4. Create credentials (OAuth2 or Service Account)")
            console.print("5. Download the credentials JSON file\n")
            
            creds_path = click.prompt("Enter path to Google credentials JSON file", type=click.Path(exists=True))
            env_content += f"GOOGLE_SHEETS_CREDENTIALS_PATH={creds_path}\n"
        
        with open(env_path, 'w') as f:
            f.write(env_content)
        
        console.print("[green]✓ Configuration saved to .env[/green]")
    else:
        console.print("[green]✓ .env file already exists[/green]")
    
    # Install dependencies
    if click.confirm("Install Python dependencies?"):
        console.print("[cyan]Installing dependencies...[/cyan]")
        subprocess.run(["pip", "install", "-r", "requirements.txt"])
        console.print("[green]✓ Dependencies installed[/green]")
    
    console.print("\n[bold green]Setup complete![/bold green]")
    console.print("Run [cyan]python main.py --help[/cyan] to see available commands")


if __name__ == "__main__":
    cli()