import os.path
from typing import List, Any, Dict
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleSheetsClient:
    # Update scope to allow read and write operations
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

    def __init__(self, credentials_path: str = "data/g.json"):
        self.credentials_path = credentials_path
        self.service = self._authenticate()

    def _authenticate(self):
        """Handles authentication with Google Sheets API using a service account."""
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_path, scopes=self.SCOPES
            )
            return build("sheets", "v4", credentials=creds)
        except Exception as e:
            print(f"An error occurred during authentication: {e}")
            return None

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

    def batch_get_values(
        self, spreadsheet_id: str, ranges: List[str]
    ) -> Dict[str, List[List[Any]]]:
        """Batch get values from multiple ranges in a spreadsheet."""
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .batchGet(spreadsheetId=spreadsheet_id, ranges=ranges)
                .execute()
            )
            return {
                range_name: value_range.get("values", [])
                for range_name, value_range in zip(
                    ranges, result.get("valueRanges", [])
                )
            }
        except HttpError as error:
            print(f"An error occurred: {error}")
            return {}

    def batch_update(self, spreadsheet_id: str, requests: List[Dict]) -> bool:
        """Batch update operations on a spreadsheet."""
        try:
            body = {"requests": requests}
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body=body
            ).execute()
            return True
        except HttpError as error:
            print(f"An error occurred: {error}")
            return False

    def create_spreadsheet(self, title: str) -> str:
        """Create a new spreadsheet."""
        try:
            spreadsheet = {"properties": {"title": title}}
            spreadsheet = (
                self.service.spreadsheets()
                .create(body=spreadsheet, fields="spreadsheetId")
                .execute()
            )
            return spreadsheet.get("spreadsheetId")
        except HttpError as error:
            print(f"An error occurred: {error}")
            return ""

    async def validate_spreadsheet_id(self, spreadsheet_id: str) -> bool:
        """
        Validate if a spreadsheet ID exists and is accessible.

        Args:
            spreadsheet_id: The ID of the spreadsheet to validate

        Returns:
            Boolean indicating if the spreadsheet is valid and accessible
        """
        try:
            # Try to get spreadsheet metadata
            self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            return True
        except HttpError as error:
            if error.resp.status == 404:
                print(f"Spreadsheet {spreadsheet_id} not found")
            else:
                print(f"Error validating spreadsheet: {error}")
            return False

    def batch_update_values(self, spreadsheet_id: str, data: List[List[Any]]) -> bool:
        """
        Batch update values in a spreadsheet using a single API call.
        """
        try:
            # Clear existing content first
            self.clear_range(spreadsheet_id, "B2:G")

            # Prepare the batch update request for values only
            batch_data = []
            for i, row in enumerate(data, start=2):
                batch_data.append({"range": f"B{i}:G{i}", "values": [row]})

            # Update values
            body = {"valueInputOption": "RAW", "data": batch_data}
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id, body=body
            ).execute()

            # Apply formatting in a separate request
            format_request = [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": 1,
                            "startColumnIndex": 2,  # Column C
                            "endColumnIndex": 3,  # Column C
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "horizontalAlignment": "LEFT",
                                "wrapStrategy": "WRAP",
                            }
                        },
                        "fields": "userEnteredFormat(horizontalAlignment,wrapStrategy)",
                    }
                }
            ]

            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": format_request}
            ).execute()

            return True

        except HttpError as error:
            print(f"An error occurred: {error}")
            return False

    def set_column_widths(self, spreadsheet_id: str) -> bool:
        """Set optimal column widths for better readability"""
        try:
            requests = [
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": 0,
                            "dimension": "COLUMNS",
                            "startIndex": 1,  # Column B
                            "endIndex": 2,  # Column B
                        },
                        "properties": {
                            "pixelSize": 250  # Level Name width
                        },
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": 0,
                            "dimension": "COLUMNS",
                            "startIndex": 2,  # Column C
                            "endIndex": 3,  # Column C
                        },
                        "properties": {
                            "pixelSize": 400  # Post Description width
                        },
                        "fields": "pixelSize",
                    }
                },
            ]

            body = {"requests": requests}
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body=body
            ).execute()
            return True

        except HttpError as error:
            print(f"An error occurred: {error}")
            return False
