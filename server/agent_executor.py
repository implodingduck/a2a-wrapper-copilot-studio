import logging
import msal
import os

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message, get_message_text
from microsoft_agents.activity import ActivityTypes, load_configuration_from_env
from microsoft_agents.copilotstudio.client import (
    ConnectionSettings,
    CopilotClient,
)

logger = logging.getLogger(__name__)

class CopilotStudioAgent:
    """Copilot Studio Agent."""

    async def create_client(self, access_token):
        settings = ConnectionSettings(
            environment_id=os.environ.get("COPILOTSTUDIOAGENT__ENVIRONMENTID"),
            agent_identifier=os.environ.get("COPILOTSTUDIOAGENT__SCHEMANAME"),
            cloud=None,
            copilot_agent_type=None,
            custom_power_platform_cloud=None,
        )
        logger.info(f"Configuring settings...")
        logger.info(f"Got MCP ...")
        confidentialcredential = msal.ConfidentialClientApplication(
            os.environ.get("COPILOTSTUDIOAGENT__AGENTAPPID"),
            authority=f"https://login.microsoftonline.com/{os.environ.get('COPILOTSTUDIOAGENT__TENANTID')}",
            client_credential=os.environ.get("COPILOTSTUDIOAGENT__CLIENTSECRET")
        )
        logger.info(f"Acquiring Copilot Studio token on behalf of MCP token...")
        copilottoken = confidentialcredential.acquire_token_on_behalf_of(
            user_assertion=access_token,
            scopes=["https://api.powerplatform.com/.default"]
        )
        logger.info(f"Acquired Copilot Studio token: {copilottoken}")

        copilot_client = CopilotClient(settings, copilottoken["access_token"])
        return copilot_client
    
    async def invoke(self, text: str, access_token: str) -> str:
        print(f'CopilotStudioAgent received input: {text}')
        copilot_client =await self.create_client(access_token)
        act = copilot_client.start_conversation(True)
        logger.info("Starting conversation...")
        async for action in act:
            if action.text:
                logger.info(action.text)
                conversation_id = action.conversation.id
        logger.info(f"Conversation ID: {conversation_id}")
        replies = copilot_client.ask_question(text, conversation_id)
        async for reply in replies:
            if reply.type == ActivityTypes.message:
                logger.info(f"Received reply: {reply.text}")
                return reply.text

        #return f'Copilot Studio: {text}'


class CopilotStudioAgentExecutor(AgentExecutor):
    """Test AgentProxy Implementation."""

    def __init__(self):
        self.agent = CopilotStudioAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        
        access_token = None
        

        if hasattr(context, 'call_context'):
            logger.info(f"Context has call_context attribute.")
            if hasattr(context.call_context, 'state'):
                logger.info(f"Context has call_context.state attribute.")
                logger.info(f"Call context state: {context.call_context.state}")
                headers = context.call_context.state.get("headers", {})
                logger.info(f"Extracted headers from call context state: {headers}")
                auth_header = headers.get("authorization", "")
                if auth_header.startswith("Bearer "):
                    access_token = auth_header.split(" ")[1]
                    logger.info(f"Extracted access token from Authorization header.")

        raw_text = get_message_text(context.message) if context.message else ''
        result = await self.agent.invoke(raw_text, access_token)
        logger.info(f"Agent result: {result}")
        await event_queue.enqueue_event(new_agent_text_message(f"{result}"))

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise Exception('cancel not supported')
