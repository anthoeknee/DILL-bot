import os.path
from typing import List, Any
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleSheetsClient:
    # Update scope to allow read and write operations
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(
        self, credentials_path: str = "credentials.json", token_path: str = "token.json"
    ):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = self._authenticate()

    def _authenticate(self):
        """Handles authentication with Google Sheets API."""
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, self.SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        return build("sheets", "v4", credentials=creds)

    def read_range(self, spreadsheet_id: str, range_name: str) -> List[List[Any]]:
        """
        Read values from a specified range in a spreadsheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            range_name: The A1 notation of the range to read

        Returns:
            List of rows containing the values
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_name)
                .execute()
            )
            return result.get("values", [])
        except HttpError as error:
            print(f"An error occurred: {error}")
            return []

    def write_range(
        self, spreadsheet_id: str, range_name: str, values: List[List[Any]]
    ) -> bool:
        """
        Write values to a specified range in a spreadsheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            range_name: The A1 notation of the range to write
            values: 2D list of values to write

        Returns:
            Boolean indicating success
        """
        try:
            body = {"values": values}
            self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                body=body,
            ).execute()
            return True
        except HttpError as error:
            print(f"An error occurred: {error}")
            return False

    def append_rows(
        self, spreadsheet_id: str, range_name: str, values: List[List[Any]]
    ) -> bool:
        """
        Append rows to a spreadsheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            range_name: The A1 notation of where to append
            values: 2D list of values to append

        Returns:
            Boolean indicating success
        """
        try:
            body = {"values": values}
            self.service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
            return True
        except HttpError as error:
            print(f"An error occurred: {error}")
            return False

    def clear_range(self, spreadsheet_id: str, range_name: str) -> bool:
        """
        Clear values in a specified range.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            range_name: The A1 notation of the range to clear

        Returns:
            Boolean indicating success
        """
        try:
            self.service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id, range=range_name
            ).execute()
            return True
        except HttpError as error:
            print(f"An error occurred: {error}")
            return False
