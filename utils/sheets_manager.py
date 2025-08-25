import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pickle
from pathlib import Path
import config
from utils.data_models import MemberProfile
from utils.table_generator import TableGenerator


class GoogleSheetsManager:
    """Manager for Google Sheets operations"""
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    def __init__(self):
        self.creds = None
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Sheets API"""
        
        # Try to load existing token
        token_path = Path("token.pickle")
        
        if token_path.exists():
            with open(token_path, 'rb') as token:
                self.creds = pickle.load(token)
        
        # If there are no (valid) credentials available, authenticate
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if config.GOOGLE_SHEETS_CREDENTIALS_PATH:
                    # Check if it's a service account or OAuth2 credentials
                    if config.GOOGLE_SHEETS_CREDENTIALS_PATH.endswith('.json'):
                        with open(config.GOOGLE_SHEETS_CREDENTIALS_PATH, 'r') as f:
                            cred_data = json.load(f)
                            
                        if 'type' in cred_data and cred_data['type'] == 'service_account':
                            # Service account credentials
                            self.creds = service_account.Credentials.from_service_account_file(
                                config.GOOGLE_SHEETS_CREDENTIALS_PATH,
                                scopes=self.SCOPES
                            )
                        else:
                            # OAuth2 credentials
                            flow = InstalledAppFlow.from_client_secrets_file(
                                config.GOOGLE_SHEETS_CREDENTIALS_PATH, self.SCOPES
                            )
                            self.creds = flow.run_local_server(port=0)
                    
                    # Save the credentials for the next run
                    if not isinstance(self.creds, service_account.Credentials):
                        with open(token_path, 'wb') as token:
                            pickle.dump(self.creds, token)
        
        if self.creds:
            self.service = build('sheets', 'v4', credentials=self.creds)
    
    def create_spreadsheet(self, title: str) -> str:
        """Create a new spreadsheet"""
        if not self.service:
            print("Google Sheets not authenticated")
            return None
            
        spreadsheet = {
            'properties': {
                'title': title
            }
        }
        
        try:
            spreadsheet = self.service.spreadsheets().create(
                body=spreadsheet,
                fields='spreadsheetId'
            ).execute()
            
            print(f"Created spreadsheet: {title}")
            print(f"Spreadsheet ID: {spreadsheet.get('spreadsheetId')}")
            return spreadsheet.get('spreadsheetId')
            
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None
    
    def update_master_sheet(self, profiles: List[MemberProfile], spreadsheet_id: str = None) -> bool:
        """Update master spreadsheet with all profiles"""
        if not self.service:
            print("Google Sheets not authenticated. Skipping sheets update.")
            return False
            
        if not spreadsheet_id:
            spreadsheet_id = config.MASTER_SPREADSHEET_ID
            
        if not spreadsheet_id:
            # Create new master spreadsheet
            spreadsheet_id = self.create_spreadsheet("YARD Business Club - Участники")
            if not spreadsheet_id:
                return False
            print(f"Created new master spreadsheet. Update MASTER_SPREADSHEET_ID in .env: {spreadsheet_id}")
        
        try:
            # Prepare data
            values = [config.SHEETS_COLUMNS]  # Header row
            
            for profile in profiles:
                values.append(profile.to_sheets_row())  # Empty reasoning for master sheet
            
            body = {
                'values': values
            }
            
            # Clear existing content and update
            # Calculate range based on actual data size and columns count
            num_cols = len(config.SHEETS_COLUMNS)
            num_rows = len(values)
            end_col = chr(ord('A') + num_cols - 1)  # Convert number to column letter
            range_name = f'A1:{end_col}{num_rows + 100}'  # Add buffer rows for safety
            
            # Clear first
            self.service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            # Then update
            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            print(f"Updated {result.get('updatedCells')} cells in master spreadsheet")
            return True
            
        except HttpError as error:
            print(f"An error occurred: {error}")
            return False
    
    def create_analysis_sheet(self, analysis_results: List, criteria: str, mode: str = "professional") -> Optional[str]:
        """Add a new sheet with analysis results to master spreadsheet using unified table generator"""
        if not self.service:
            print("Google Sheets not authenticated. Skipping sheets creation.")
            return None
            
        # Use master spreadsheet
        spreadsheet_id = config.MASTER_SPREADSHEET_ID
        if not spreadsheet_id:
            print("No master spreadsheet ID configured. Please run 'sync' first to create master sheet.")
            return None
            
        # Create sheet name
        timestamp = datetime.now().strftime("%m-%d %H:%M")
        safe_criteria = "".join(c for c in criteria if c.isalnum() or c in (' ', '-', '_'))[:20]
        safe_criteria = safe_criteria.replace(' ', '_')
        sheet_name = f"Анализ_{safe_criteria}_{timestamp}"
        
        try:
            # First, create a new sheet in the existing spreadsheet
            requests = [{
                'addSheet': {
                    'properties': {
                        'title': sheet_name
                    }
                }
            }]
            
            # Create the new sheet
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()
            
            # Use TableGenerator to prepare data
            values = TableGenerator.prepare_sheets_data(
                analysis_results=analysis_results,
                criteria=criteria,
                mode=mode,
                include_all_profiles=True  # Включаем все профили
            )
            
            # Update the new sheet with data
            body = {'values': values}
            self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!A1',  # Write to the new sheet
                valueInputOption='RAW',
                body=body
            ).execute()
            
            print(f"Created analysis sheet: {sheet_name}")
            print(f"Spreadsheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}#gid=0")
            return spreadsheet_id
            
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None
    
    def load_all_profiles_from_disk(self) -> List[MemberProfile]:
        """Load all profiles from JSON files"""
        profiles = []
        json_files = list(config.PROFILES_DIR.glob("*.json"))
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                    profile = MemberProfile(**profile_data)
                    profiles.append(profile)
            except Exception as e:
                print(f"Error loading profile from {json_file}: {str(e)}")
        
        return profiles
    
    def sync_all_to_sheets(self) -> bool:
        """Sync all saved profiles to master Google Sheet"""
        profiles = self.load_all_profiles_from_disk()
        
        if not profiles:
            print("No profiles found to sync")
            return False
        
        print(f"Syncing {len(profiles)} profiles to Google Sheets...")
        return self.update_master_sheet(profiles)