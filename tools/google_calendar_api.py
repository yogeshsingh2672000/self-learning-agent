import logging
from typing import Optional, Dict, Any
from langchain_core.tools import Tool
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from tools.base import BaseTool, ToolConfig

logger = logging.getLogger(__name__)
__version__ = "1.0.0"

class ImplementIntegrationWithGoogleCalendarApiTool(BaseTool):
    """Implements User asked: "create an event on my google calendar"

Why needed: The agent doesn't have the capability to interact with third-party apps such as Google Calendar."""
    
    def __init__(self):
        """Initialize the ImplementIntegrationWithGoogleCalendarApiTool tool."""
        super().__init__()
        logger.info(f"Initialized ImplementIntegrationWithGoogleCalendarApiTool v{__version__}")
    
    def get_config(self) -> ToolConfig:
        """Return tool configuration."""
        return ToolConfig(
            name="implement_integration_with_google_calendar_api_tool",
            description="User asked: \"create an event on my google calendar\"\n\nWhy needed: The agent doesn't have the capability to interact with third-party apps such as Google Calendar",
            category="integration"
        )
    
    def execute(self, event) -> Tool:
        """Execute the tool and return LangChain Tool object."""
        def tool_func(input_param: str) -> Dict[str, Any]:
            """Execute tool logic."""
            try:
                SCOPES = ['https://www.googleapis.com/auth/calendar']

                creds = None
                if os.path.exists('token.pickle'):
                    with open('token.pickle', 'rb') as token:
                        creds = pickle.load(token)
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    else:
                        flow = InstalledAppFlow.from_client_secrets_file(
                            'credentials.json', SCOPES)
                        creds = flow.run_local_server(port=0)
                    with open('token.pickle', 'wb') as token:
                        pickle.dump(creds, token)

                service = build('calendar', 'v3', credentials=creds)

                service.events().insert(calendarId='primary', body=event).execute()

                result = {"success": True, "result": None}
                return result
            except Exception as e:
                logger.error(f"Error: {e}", exc_info=True)
                return {"success": False, "error": str(e)}
        
        return Tool(
            name="implement_integration_with_google_calendar_api_tool",
            func=tool_func,
            description="User asked: \"create an event on my google calendar\"\n\nWhy needed: The agent doesn't have the capability to interact with third-party apps such as Google Calendar"
        )