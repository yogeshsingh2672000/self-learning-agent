"""
Test suite for GoogleCalendarApi tool.

Tests cover:
- Tool initialization and configuration
- Integration with Google Calendar API
- Error handling and edge cases
"""
import pytest
import logging
from tools.google_calendar_api import GoogleCalendarApi

logger = logging.getLogger(__name__)

@pytest.fixture
def tool():
    """Fixture to provide a GoogleCalendarApi instance."""
    return GoogleCalendarApi()

class TestToolConfiguration:
    """Test tool configuration and initialization."""
    
    def test_tool_initialization(self, tool):
        """Test that tool initializes without errors."""
        assert tool is not None, "Tool initialization failed"
    
    def test_tool_config(self, tool):
        """Test tool configuration is correct."""
        config = tool.get_config()
        assert config.name == "google_calendar_api", "Tool name is incorrect"
        assert config.enabled is True, "Tool is not enabled"

class TestGoogleCalendarApiIntegration:
    """Test integration with Google Calendar API."""
    
    def test_create_event(self, tool):
        """Test that an event can be created on Google Calendar."""
        event = tool.create_event("Test Event", "2022-12-31")
        assert event is not None, "Event creation failed"
        assert event['summary'] == "Test Event", "Event summary is incorrect"
        assert event['start']['date'] == "2022-12-31", "Event start date is incorrect"
    
    def test_get_event(self, tool):
        """Test that an event can be retrieved from Google Calendar."""
        event = tool.create_event("Test Event", "2022-12-31")
        retrieved_event = tool.get_event(event['id'])
        assert retrieved_event is not None, "Event retrieval failed"
        assert retrieved_event['id'] == event['id'], "Retrieved event ID is incorrect"

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_invalid_event_date(self, tool):
        """Test tool handles invalid event dates gracefully."""
        with pytest.raises(ValueError, match="Invalid date format"):
            tool.create_event("Test Event", "31-12-2022")
    
    def test_non_existent_event(self, tool):
        """Test tool handles non-existent events gracefully."""
        with pytest.raises(Exception, match="Event not found"):
            tool.get_event("non_existent_event_id")