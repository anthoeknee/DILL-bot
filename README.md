# Discord Google Spreadsheet Populator Bot

## Introduction

The Discord Google Spreadsheet Populator Bot is a Python-based Discord bot that automatically populates Google Spreadsheets with content from Discord threads. This bot leverages the Google Sheets API to ensure your spreadsheets are always up-to-date with the latest discussions from your Discord server.

## Prerequisites

Before setting up the bot, ensure you have the following:

- **Python 3.8 or higher** installed on your machine.
- **Google Cloud Account** with access to the Google Sheets API.
- **Discord Account** with permissions to add bots to your server.
- **Git** (optional, for cloning the repository).
- **A Google Spreadsheet** where you want to populate data.

## Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/yourusername/discord-google-sheets-bot.git
   cd discord-google-sheets-bot
   ```

2. **Create a Virtual Environment**

   It's recommended to use a virtual environment to manage dependencies.

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Set Up Google API Credentials**

   - **Enable Google Sheets API:**
     - Go to the [Google Cloud Console](https://console.cloud.google.com/).
     - Create a new project or select an existing one.
     - Navigate to **APIs & Services > Library**.
     - Search for **Google Sheets API** and enable it.

   - **Create a Service Account:**
     - In the Cloud Console, go to **IAM & Admin > Service Accounts**.
     - Click **Create Service Account**.
     - Provide a name and description, then click **Create**.
     - Assign the role **Editor** or a more restrictive role that has access to Google Sheets.
     - Click **Done**.

   - **Generate Service Account Key:**
     - Find your newly created service account in the list.
     - Click the three dots under **Actions** and select **Manage Keys**.
     - Click **Add Key > Create New Key**, choose **JSON**, and click **Create**.
     - A JSON file will be downloaded. Save this file as `google-credentials.json` in the `data` directory of your project.

   - **Share Your Spreadsheet with the Service Account:**
     - Open your Google Spreadsheet.
     - Click **Share** and add the service account's email (found in the `google-credentials.json` file) with **Editor** permissions.

2. **Configure Bot Settings**

   - Create a `settings.yml` file inside the `data` directory with the following content:

     ```yaml
     token: "YOUR_DISCORD_BOT_TOKEN"
     owner_id: YOUR_DISCORD_USER_ID
     command_prefix: "!"
     bot_description: "A Discord Bot with custom commands."
     status_text: "your commands"
     status_type: "watching"  # Options: playing, streaming, listening, watching
     ```

   - Replace `"YOUR_DISCORD_BOT_TOKEN"` with your actual Discord bot token.
   - Replace `YOUR_DISCORD_USER_ID` with your Discord user ID.

## Running the Bot

1. **Start the Bot**

   ```bash
   python main.py
   ```

   You should see logs indicating that the bot has started and connected to Discord.

## Setting Up Forum Tracker

1. **Use the Setup Command**

   In your Discord server, use the `/setup_forum_tracker` command to link a forum channel to your Google Spreadsheet.

   ```plaintext
   /setup_forum_tracker
   ```

   - **Parameters:**
     - `forum_channel`: Select the forum channel you want to track.
     - `spreadsheet_id`: Enter your Google Spreadsheet ID (found in the spreadsheet URL).
     - `include_history`: Choose `True` to load all historical posts or `False` to track only new posts.

2. **Verify the Setup**

   Use the `/view_forum_tracker` command to ensure that the tracker has been set up correctly.

   ```plaintext
   /view_forum_tracker
   ```

## Usage

- **View All Settings**

  ```plaintext
  /settings view
  ```

- **Set a New Setting**

  ```plaintext
  /settings set key "welcome_channel" value "#general"
  ```

- **Get a Specific Setting**

  ```plaintext
  /settings get key "welcome_channel"
  ```

- **Delete a Setting**

  ```plaintext
  /settings delete key "welcome_channel"
  ```

- **Stop Forum Tracker**

  ```plaintext
  /stop_forum_tracker
  ```

## Troubleshooting

- **Bot Not Responding:**
  - Ensure the bot is running without errors in the terminal.
  - Verify that the bot has the necessary permissions in your Discord server.

- **Google Sheets Not Updating:**
  - Confirm that the service account has been granted **Editor** access to the spreadsheet.
  - Ensure that the `google-credentials.json` file is correctly placed in the `data` directory.
  - Check the `logs` directory for any error messages related to Google Sheets API.

- **Commands Not Syncing:**
  - Restart the bot to force a resync of slash commands.
  - Ensure that the bot has the `applications.commands` scope authorized in your Discord server.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request for any enhancements or bug fixes.

## License

This project is licensed under the [MIT License](LICENSE).

## Acknowledgements

- [discord.py](https://discordpy.readthedocs.io/en/stable/) for powering the Discord bot functionality.
- [Google Sheets API](https://developers.google.com/sheets/api) for enabling spreadsheet integrations.
- [Rich](https://rich.readthedocs.io/en/stable/) for enhanced logging and console outputs.

---
